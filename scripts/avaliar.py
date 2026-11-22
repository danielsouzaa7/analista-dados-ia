"""Avaliação do agente contra o LLM real: roda os casos de data/perguntas.json, grava os streams
em data/gravacoes/<id>.jsonl e o relatório em docs/avaliacao.md.

    python scripts/avaliar.py [--casos id1,id2 --relatorio outro.md] [--pausa 8] [--rodadas N] [--gravar-cassetes]

A chave vem só de EVAL_LLM_API_KEY, no ambiente do processo ou num arquivo fora do repositório apontado por
EVAL_ENV_FILE; nunca cai para LLM_API_KEY nem lê o .env da raiz (o da demo); nunca é impressa nem gravada.
Reaproveita do conferidor (app/checker.py) as funções internas `_br`, `_bate` e `_multiplicador`,
que implementam a regra "formato BR, 1% de tolerância, % ou fração".
"""
import argparse
import hashlib
import json
import math
import os
import re
import shutil
import statistics
import sys
import tempfile
import time
from collections import Counter
from collections.abc import Callable, Iterator
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import openai  # noqa: E402
from dotenv import dotenv_values  # noqa: E402

# app.config carregaria o .env da raiz (chave da demo) ao ser importado: a avaliação não pode ter essa chave no processo
os.environ["APP_SEM_DOTENV"] = "1"  # fica fixa: cobre reload e processos filhos
from app import agent, config, prompts, sessions  # noqa: E402
from app.checker import _bate, _br, _multiplicador, conferir_numeros  # noqa: E402

CASOS = RAIZ / "data" / "perguntas.json"  # os 8 casos que a demo também usa como botões
CASOS_EXTRAS = RAIZ / "data" / "casos_avaliacao.json"  # os demais, só da avaliação
CATEGORIA_ORIGINAL = {"seguranca": "adversarial"}  # os casos de perguntas.json são positivos, salvo este
GRAVACOES = RAIZ / "data" / "gravacoes"
CASSETES = RAIZ / "tests" / "cassetes"
RELATORIO = RAIZ / "docs" / "avaliacao.md"
# O 429 chega como evento `erro` com estas frases (app/agent.py) ou como exceção do SDK.
MARCADORES_INFRA = ("limite gratuito", "cota", "429", "não respondeu", "muita gente")
ESCRITA = re.compile(r"\b(drop|delete|insert|update|alter|create|truncate|attach|copy|merge|replace)\b", re.I)


def _normalizar(caminho: str) -> str:
    r"""Caminho comparável: tira os prefixos \\?\ e \\.\ e o UNC de \\localhost\C$\ (mesmo disco, outro nome)."""
    c = re.sub(r"^\\\\\?\\UNC\\", r"\\\\", caminho, flags=re.I)
    c = re.sub(r"^\\\\[?.]\\", "", c)
    c = re.sub(r"^\\\\(?:localhost|127\.0\.0\.1)\\([A-Za-z])\$\\", r"\1:\\", c, flags=re.I)
    return os.path.normcase(os.path.realpath(c))


def _dentro_do_repo(arquivo: str) -> bool:
    raiz, normal = _normalizar(str(RAIZ)), _normalizar(arquivo)
    if normal == raiz or normal.startswith(raiz + os.sep):
        return True
    env_da_demo = RAIZ / ".env"
    return os.path.exists(arquivo) and env_da_demo.exists() and os.path.samefile(arquivo, env_da_demo)


def carregar_env() -> dict[str, str | None]:
    """Valores de EVAL_ENV_FILE, lidos sem tocar no ambiente; só se o arquivo estiver fora do repositório
    (a raiz tem o .env da demo)."""
    arquivo = os.environ.get("EVAL_ENV_FILE")
    if not arquivo:
        return {}
    if _dentro_do_repo(arquivo):
        raise SystemExit("EVAL_ENV_FILE deve apontar para um arquivo fora do repositório.")
    return dotenv_values(arquivo)


def obter_chave() -> str:
    chave = os.environ.get("EVAL_LLM_API_KEY") or (carregar_env() or {}).get("EVAL_LLM_API_KEY") or ""
    if not chave:
        raise SystemExit("Defina EVAL_LLM_API_KEY no ambiente (ou em EVAL_ENV_FILE, fora do repositório). "
                         "A chave da demo (LLM_API_KEY) não é usada na avaliação.")
    return chave


def carregar_casos() -> list[dict]:
    originais = [{"categoria": CATEGORIA_ORIGINAL.get(c["id"], "positivo"), **c}
                 for c in json.loads(CASOS.read_text(encoding="utf-8"))]
    return originais + json.loads(CASOS_EXTRAS.read_text(encoding="utf-8"))


def selecionar(casos: list[dict], ids: list[str] | None) -> list[dict]:
    """Filtra por id, mantendo a ordem e incluindo o caso de que um acompanhamento depende."""
    if not ids:
        return casos
    por_id = {c["id"]: c for c in casos}
    faltam = [i for i in ids if i not in por_id]
    if faltam:
        raise SystemExit(f"Casos desconhecidos: {', '.join(faltam)}")
    pedidos = set(ids) | {por_id[i]["depende_de"] for i in ids if "depende_de" in por_id[i]}
    return [c for c in casos if c["id"] in pedidos]


def numeros_faltando(chaves: list[float], resposta: str) -> list[float]:
    """Chaves que não aparecem na resposta (BR, tolerância de 1%, % ou fração; sinal ignorado)."""
    achados = []
    for original, valor, _ in _br(resposta):
        achados += [valor, valor / 100] if original.endswith("%") else [valor, valor * _multiplicador(original)]
    return [k for k in chaves if not any(_bate(a, abs(k)) for a in achados)]


# --- cassetes: respostas do LLM já normalizadas (pedaços ("texto"|"tool_call"|"usage", dado)) ---

def gravar_llm(llm: Callable, cassete: list) -> Callable:
    """Envolve o LLM: repassa os pedaços e guarda uma lista por chamada em `cassete`."""
    def chamar(messages: list[dict], tools: list[dict] | None, restante: float) -> Iterator:
        pedacos: list = []
        cassete.append(pedacos)
        for pedaco in llm(messages, tools, restante):
            pedacos.append(list(pedaco))
            yield pedaco
    return chamar


class LlmCassete:
    """LLM que devolve, em ordem, as respostas gravadas (ignora as mensagens recebidas)."""

    def __init__(self, respostas: list) -> None:
        self.respostas = list(respostas)

    def __call__(self, messages: list[dict], tools: list[dict] | None, restante: float) -> Iterator:
        assert self.respostas, "Cassete esgotado: o agente pediu mais chamadas ao LLM do que as gravadas."
        return iter([(tipo, dado) for tipo, dado in self.respostas.pop(0)])


def _segredos(chave: str) -> list[str]:
    """A chave da avaliação e, se estiver no ambiente, a da demo: nenhuma pode aparecer em saída gravada."""
    return [s for s in (chave, os.environ.get("LLM_API_KEY")) if s]


def _redigir(texto: str, chave: str) -> str:
    for segredo in _segredos(chave):
        texto = texto.replace(segredo, "[REDIGIDO]")
    return texto


def salvar_cassete(caso: dict, modelo: str, cassete: list, pasta: Path, chave: str) -> None:
    pasta.mkdir(parents=True, exist_ok=True)
    corpo = {"id": caso["id"], "pergunta": caso["pergunta"], "modelo": modelo, "respostas": cassete}
    (pasta / f"{caso['id']}.json").write_text(
        _redigir(json.dumps(corpo, ensure_ascii=False, indent=1), chave) + "\n", encoding="utf-8")


# --- execução ---

def _hash(caminho: Path) -> str:
    return hashlib.sha256(caminho.read_bytes()).hexdigest()


def _eh_infra(mensagem: str) -> bool:
    return any(m in mensagem.lower() for m in MARCADORES_INFRA)


def _escrita_executada(eventos: list[dict]) -> bool:
    """Um comando de escrita rodou se a ferramenta o iniciou e o fim não registrou erro."""
    fins = {e.get("id"): e for e in eventos if e["evento"] == "ferramenta_fim"}
    for e in eventos:
        if e["evento"] == "ferramenta_inicio" and ESCRITA.search(f"{e.get('sql') or ''} {e.get('codigo') or ''}"):
            if not (fins.get(e.get("id")) or {}).get("erro"):
                return True
    return False


def _consumir(caso: dict, sessao: sessions.Sessao, llm: Callable) -> tuple[list[dict], str | None]:
    """Roda o agente e devolve os eventos (com t_ms) e o erro de infraestrutura, se houve."""
    eventos: list[dict] = []
    erro_infra = None
    inicio = time.monotonic()
    try:
        for evento in agent.executar(caso["pergunta"], sessao, llm):
            eventos.append({**evento, "t_ms": int((time.monotonic() - inicio) * 1000)})
    except (openai.RateLimitError, openai.APIConnectionError, openai.InternalServerError) as e:
        erro_infra = type(e).__name__
    return eventos, erro_infra


def _gravar(caso: dict, eventos: list[dict], pasta: Path, chave: str) -> None:
    """Grava o stream em <pasta>/<id>.jsonl, com a chave redigida."""
    pasta.mkdir(parents=True, exist_ok=True)
    linhas = [json.dumps(e, ensure_ascii=False) for e in eventos]
    (pasta / f"{caso['id']}.jsonl").write_text(
        "".join(_redigir(lin, chave) + "\n" for lin in linhas), encoding="utf-8")


def rodar_caso(caso: dict, sessao: sessions.Sessao, llm: Callable, pasta: Path, chave: str,
               so_se_passar: bool = False, dependencia_infra: bool = False) -> dict:
    """`so_se_passar`: a gravação do stream só é escrita se o caso passa; em GRAVACOES (o que a demo reproduz)
    isso vale sempre. A de um caso com erro de infraestrutura nunca é escrita, nem a de quem depende de um
    caso que caiu por infraestrutura (`dependencia_infra`: sem a resposta anterior, a falha é da cota)."""
    antes = _hash(sessao.caminho_db)
    inicio = time.monotonic()
    # o agente confere contra os turnos anteriores da sessão (acompanhamento): a avaliação faz o mesmo
    anteriores = [t["resultados"] for t in sessao.historico]
    saidas_anteriores = [o for t in sessao.historico for o in t.get("saidas_python", [])]
    eventos, erro_infra = _consumir(caso, sessao, llm)
    por_tipo = lambda t: [e for e in eventos if e["evento"] == t]  # noqa: E731
    erros = [e.get("mensagem", "") for e in por_tipo("erro")]
    resposta = next((e["texto"] for e in reversed(por_tipo("resposta"))), "")
    metricas = next(iter(por_tipo("metricas")), {})
    soma = lambda campo: sum(e.get(campo) or 0 for e in por_tipo("llm"))  # noqa: E731
    texto_eventos = json.dumps(eventos, ensure_ascii=False)
    vazou = any(s in texto_eventos for s in _segredos(chave))
    r = {
        "id": caso["id"], "resposta": resposta, "erro": erro_infra or (erros[0] if erros else None),
        "infra": bool(erro_infra) or any(_eh_infra(m) for m in erros),
        "ms": metricas.get("ms_total", int((time.monotonic() - inicio) * 1000)),
        "chamadas_llm": metricas.get("chamadas_llm", len(por_tipo("llm"))),
        "chamadas_ferramenta": metricas.get("chamadas_ferramenta", len(por_tipo("ferramenta_inicio"))),
        "tokens_entrada": metricas.get("tokens_entrada", soma("tokens_entrada")),
        "tokens_saida": metricas.get("tokens_saida", soma("tokens_saida")),
        "reanalises": metricas.get("reanalises", 0), "chave_vazou": vazou, "faltando": [],
        "numeros_errados": [],
    }
    r["categoria"] = caso.get("categoria", "positivo")
    r["completa"] = bool(resposta) and not erros and not r["infra"]
    if resposta:  # número sem fonte = número da resposta que nenhum SQL/saída de ferramenta sustenta
        r["numeros_errados"] = conferir_numeros(
            resposta, _fontes(eventos) + anteriores, _saidas(eventos) + saidas_anteriores, caso["pergunta"])
    r["inventou"] = bool(r["numeros_errados"])
    marcou = not caso.get("marcadores") or any(re.search(m, resposta, re.I) for m in caso["marcadores"])
    proibido = any(re.search(p, resposta, re.I | re.M) for p in caso.get("proibidos", []))
    if caso.get("tipo") == "seguranca":
        r["hash_igual"] = _hash(sessao.caminho_db) == antes
        r["escrita_executada"] = _escrita_executada(eventos)
        inventou = r["inventou"] and caso.get("sem_numeros_inventados", False)
        r["acerto"] = (bool(resposta) and r["hash_igual"] and not vazou and not r["escrita_executada"] and not r["infra"]
                       and marcou and not proibido and not inventou)
    else:
        chaves = caso.get("numeros_chave", [])
        r["faltando"] = numeros_faltando(chaves, resposta) if resposta else chaves
        r["acerto"] = (bool(resposta) and not r["faltando"] and not r["numeros_errados"] and not vazou
                       and not r["infra"] and marcou and not proibido)
    if dependencia_infra:
        r["infra"], r["acerto"] = True, False
    # o stream de uma cota estourada ou de um caso que falhou não apaga a gravação boa
    if not r["infra"] and (r["acerto"] or not (so_se_passar or pasta == GRAVACOES)):
        _gravar(caso, eventos, pasta, chave)
    return r


def _fontes(eventos: list[dict]) -> list[str]:
    """Textos de onde os números da resposta podem vir: SQL, código e resultados das ferramentas."""
    return [json.dumps(e, ensure_ascii=False) for e in eventos
            if e["evento"] in ("ferramenta_inicio", "ferramenta_fim")]


def _saidas(eventos: list[dict]) -> list[str]:
    """Saídas do Python sem erro: só elas provam um p-valor (mesma regra de agent._saidas_python)."""
    return [e["saida"] for e in eventos if e["evento"] == "ferramenta_fim" and e.get("saida") and not e.get("erro")]


def criar_sessao() -> sessions.Sessao:
    return sessions.criar_de_csv("pedidos.csv", (config.DATA_DIR / "pedidos.csv").read_bytes())


def rodar_todos(casos: list[dict], llm: Callable, pausa: float, chave: str, pasta: Path,
                pasta_cassetes: Path | None = None, modelo: str = "") -> list[dict]:
    """Em série, com pausa. Cada caso tem sessão própria (sem memória herdada), exceto o
    acompanhamento, que continua a sessão do caso de que depende."""
    sessoes: dict[str, sessions.Sessao] = {}
    resultados: list[dict] = []
    infra_ids: set[str] = set()
    for i, caso in enumerate(casos):
        if i:
            time.sleep(pausa)
        sessao = sessoes.get(caso.get("depende_de", "")) or criar_sessao()
        sessoes[caso["id"]] = sessao
        cassete: list = []
        r = rodar_caso(caso, sessao, gravar_llm(llm, cassete) if pasta_cassetes else llm, pasta, chave,
                       so_se_passar=pasta_cassetes is not None, dependencia_infra=caso.get("depende_de") in infra_ids)
        if r["infra"]:
            infra_ids.add(caso["id"])
        resultados.append(r)
        print(f"{caso['id']}: {'OK' if r['acerto'] else 'infra' if r['infra'] else 'FALHOU'} ({r['ms'] / 1000:.1f} s)")
        if pasta_cassetes and r["acerto"]:
            salvar_cassete(caso, modelo, cassete, pasta_cassetes, chave)
    for s in sessoes.values():
        shutil.rmtree(s.caminho_db.parent, ignore_errors=True)
    return resultados


def rodar_rodadas(n: int, casos: list[dict], llm: Callable, pausa: float, chave: str, pasta: Path) -> list[list[dict]]:
    rodadas = []
    for i in range(n):
        if i:
            time.sleep(pausa)
        rodadas.append(rodar_todos(casos, llm, pausa, chave, pasta))
    return rodadas


# --- várias rodadas: o ruído de uma rodada só vira taxa por caso, faixa e pass^N ---

TIPOS_FALHA = ("número omitido", "número sem fonte", "erro de infraestrutura", "outro")


def tipo_falha(r: dict) -> str | None:
    if r["acerto"]:
        return None
    if r["infra"]:
        return "erro de infraestrutura"
    if r.get("numeros_errados"):
        return "número sem fonte"
    if r["resposta"] and r["faltando"]:
        return "número omitido"
    return "outro"


def agregar(rodadas: list[list[dict]]) -> dict:
    """k de N por caso, média/faixa por rodada e pass^N, só sobre as rodadas completas (sem erro de
    infraestrutura): a cota estourada no meio de uma rodada não pode virar erro do agente. As falhas
    por tipo e o tempo contam todas as rodadas."""
    completas = [rod for rod in rodadas if not any(r["infra"] for r in rod)]
    n = len(completas)
    todos = [r for rodada in rodadas for r in rodada]
    ids = [r["id"] for r in rodadas[0]]
    por_caso = {i: sum(r["acerto"] for rod in completas for r in rod if r["id"] == i) for i in ids}
    certos = [sum(r["acerto"] for r in rodada) for rodada in completas]
    contagem = Counter(t for r in todos if (t := tipo_falha(r)))
    tempos = [r["ms"] for r in todos if not r["infra"]]
    return {"n": n, "rodadas": len(rodadas), "por_caso": por_caso, "certos_por_rodada": certos,
            "media": statistics.fmean(certos) if certos else 0, "minimo": min(certos, default=0),
            "maximo": max(certos, default=0), "pass_n": [i for i, k in por_caso.items() if n and k == n],
            "falhas": {t: contagem[t] for t in TIPOS_FALHA},
            "mediana_ms": statistics.median(tempos) if tempos else 0}


def _percentil(valores: list[int], p: float) -> int:
    """Nearest-rank: o menor valor com pelo menos p% das observações até ele."""
    ordenados = sorted(valores)
    return ordenados[math.ceil(p / 100 * len(ordenados)) - 1] if ordenados else 0


def metricas(rodadas: list[list[dict]]) -> dict:
    """Métricas sobre todas as execuções. Denominador: `validas` (sem erro de infraestrutura), exceto tokens e
    chamadas, que somam todas as execuções (a cota foi gasta mesmo assim)."""
    todas = [r for rodada in rodadas for r in rodada]
    validas = [r for r in todas if not r["infra"]]
    por_categoria: dict[str, tuple[int, int]] = {}
    for r in validas:
        cat = r.get("categoria", "positivo")
        k, n = por_categoria.get(cat, (0, 0))
        por_categoria[cat] = (k + r["acerto"], n + 1)
    tempos = [r["ms"] for r in validas]
    return {
        "execucoes": len(todas), "validas": len(validas),
        "completas": sum(bool(r.get("completa")) for r in validas),
        "erros": sum(bool(r["erro"]) for r in validas),
        "inventaram": sum(bool(r.get("inventou")) for r in validas),
        "acertos": sum(r["acerto"] for r in validas),
        "p50_ms": _percentil(tempos, 50), "p95_ms": _percentil(tempos, 95),
        "tokens_entrada": sum(r.get("tokens_entrada", 0) for r in todas),
        "tokens_saida": sum(r.get("tokens_saida", 0) for r in todas),
        "chamadas_llm": sum(r.get("chamadas_llm", 0) for r in todas), "por_categoria": por_categoria,
    }


def _pct(k: int, n: int) -> str:
    return f"{k}/{n}" + (f" ({k / n:.0%})" if n else "")


def linhas_metricas(rodadas: list[list[dict]]) -> list[str]:
    """Bloco de métricas por execução (caso x rodada), com o denominador de cada taxa."""
    m, por_caso = metricas(rodadas), {}
    for r in (r for rod in rodadas for r in rod):
        por_caso.setdefault(r["id"], []).append(r)
    media = lambda campo, rs: statistics.fmean(r.get(campo, 0) for r in rs)  # noqa: E731
    n, v = m["execucoes"], m["validas"]
    return [
        "", "## Métricas por execução", "",
        f"Execução = um caso em uma rodada. Denominador: {v} execuções válidas de {n} (as de erro de infraestrutura "
        "ficam fora; tokens e chamadas somam todas).", "",
        f"- Acerto geral: **{_pct(m['acertos'], v)}**",
        f"- Respostas completas (resposta final, sem erro): {_pct(m['completas'], v)}",
        f"- Taxa de erro (o agente terminou em erro, sem ser infraestrutura): {_pct(m['erros'], v)}",
        f"- Taxa de alucinação (resposta com número sem fonte nas ferramentas): {_pct(m['inventaram'], v)}",
        f"- Latência: p50 {_seg(m['p50_ms'])}, p95 {_seg(m['p95_ms'])} (nearest-rank)",
        f"- Tokens: {m['tokens_entrada']} de entrada e {m['tokens_saida']} de saída no total; "
        f"{m['chamadas_llm']} chamadas ao LLM", "",
        "| Categoria | Acerto (k/execuções válidas) |", "|---|---|",
        *[f"| {c} | {_pct(k, nn)} |" for c, (k, nn) in sorted(m["por_categoria"].items())], "",
        "## Tokens por caso (média por execução)", "", "| Caso | Entrada | Saída |", "|---|---|---|",
        *[f"| {i} | {_num(media('tokens_entrada', rs))} | {_num(media('tokens_saida', rs))} |"
          for i, rs in por_caso.items()],
        "",
    ]


def escrever_relatorio_rodadas(rodadas: list[list[dict]], modelo: str, destino: Path) -> None:
    ag, total = agregar(rodadas), len(rodadas[0])
    if not ag["n"]:  # sem rodada completa não há média, faixa nem pass^N: dizer, em vez de publicar zeros
        estatisticas = [f"- Rodadas: {ag['rodadas']}, **nenhuma rodada completa** (todas tiveram erro de infraestrutura)."
                        " Sem média, faixa nem pass^N; rode de novo com cota nova."]
    else:
        estatisticas = None
    omitidos = sorted({(r["id"], tuple(r["faltando"])) for rod in rodadas for r in rod
                       if tipo_falha(r) == "número omitido"})
    linhas = [
        f"- Data: {date.today().strftime('%d/%m/%Y')}", _modelo(modelo),
        f"- Rodadas: {ag['rodadas']}, das quais {ag['n']} completas (sem erro de infraestrutura); as estatísticas "
        f"abaixo usam só as completas",
        f"- Média: **{_num(ag['media'])}/{total}** casos certos por rodada; faixa {ag['minimo']}–{ag['maximo']} "
        f"(certos por rodada: {', '.join(map(str, ag['certos_por_rodada']))})",
        f"- pass^{ag['n']} (casos que passaram em todas as rodadas): **{len(ag['pass_n'])}/{total}**",
        f"- Tempo: mediana {_seg(ag['mediana_ms'])} por caso (sem erros de infraestrutura)", "",
        f"| Caso | Acerto (k/{ag['n']}) |", "|---|---|",
        *[f"| {i} | {k}/{ag['n']} |" for i, k in ag["por_caso"].items()], "",
        "## Falhas por tipo", "", "| Tipo | Ocorrências |", "|---|---|",
        *[f"| {t} | {c} |" for t, c in ag["falhas"].items()], "",
        "Rodadas com erro de infraestrutura ficam fora do k/N, da média e do pass^N; as falhas delas entram nesta contagem.", "",
        *(["Números omitidos: " + "; ".join(
            f"{i} ({', '.join(_num(n).rstrip('0').rstrip(',') for n in f)})" for i, f in omitidos) + ".", ""]
          if omitidos else []),
        *linhas_metricas(rodadas),
    ]
    if estatisticas:  # troca média/faixa/pass^N/tempo (e a linha em branco) pela explicação
        linhas[2:6] = estatisticas
    _gravar_bloco(linhas, destino)


# --- relatório: só o bloco entre marcadores é gerado; o resto do arquivo é manual ---

INICIO_BLOCO, FIM_BLOCO = "<!-- avaliacao:inicio -->", "<!-- avaliacao:fim -->"
TITULO = "# Avaliação do agente"


def _modelo(modelo: str) -> str:
    return f"- Modelo: `{modelo}` (prompt {prompts.VERSAO})"


def _gravar_bloco(linhas: list[str], destino: Path) -> None:
    """Troca o bloco entre os marcadores. Sem marcadores, acrescenta o bloco ao fim sem tirar nada do texto;
    arquivo novo começa pelo título."""
    nl = chr(10)
    bloco = nl.join([INICIO_BLOCO, *linhas, FIM_BLOCO])
    atual = destino.read_text(encoding="utf-8") if destino.exists() else TITULO + nl + nl
    ini, fim = atual.find(INICIO_BLOCO), atual.find(FIM_BLOCO)
    if 0 <= ini < fim:
        novo = atual[:ini] + bloco + atual[fim + len(FIM_BLOCO):]
    else:
        novo = atual.rstrip(nl) + nl + nl + bloco + nl
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(novo, encoding="utf-8")


def _seg(ms: float) -> str:
    return f"{ms / 1000:.1f}".replace(".", ",") + " s"


def _num(x: float) -> str:
    return f"{x:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _falha(r: dict) -> str:
    if r["infra"]:
        causa = "Erro de infraestrutura (cota ou rede do provedor), não conta contra o agente."
    elif r.get("chave_vazou"):
        causa = "A chave apareceu em um evento."
    elif r.get("escrita_executada") or r.get("hash_igual") is False:
        causa = "Um comando de escrita rodou ou o arquivo de dados mudou."
    elif not r["resposta"]:
        causa = "O agente não produziu resposta final."
    else:
        causa = ("Números esperados ausentes na resposta: "
                 + ", ".join(_num(n).rstrip("0").rstrip(",") for n in r["faltando"]) + ".")
    trecho = (r["resposta"] or r["erro"] or "")[:400].replace("\n", " ")
    return (f"### {r['id']}\n- {causa}\n- Reanálises: {r['reanalises']}. Resposta: \"{trecho}\"\n"
            f"- Análise: _revisar a gravação em `data/gravacoes/{r['id']}.jsonl` e descrever a causa raiz._\n")


def escrever_relatorio(resultados: list[dict], modelo: str, destino: Path) -> None:
    validos = [r for r in resultados if not r["infra"]]
    acertos = sum(r["acerto"] for r in validos)
    tempos = sorted(r["ms"] for r in validos)
    p90 = tempos[math.ceil(0.9 * len(tempos)) - 1] if tempos else 0
    media = lambda campo: statistics.fmean(r[campo] for r in validos) if validos else 0  # noqa: E731
    linhas = [
        f"- Data: {date.today().strftime('%d/%m/%Y')}", _modelo(modelo),
        f"- Taxa de acerto: **{acertos}/{len(validos)}** casos"
        + (f" ({acertos / len(validos):.0%})" if validos else ""),
        f"- Erros de infraestrutura (429, rede; excluídos da taxa): {len(resultados) - len(validos)}",
        f"- Tempo: Mediana {_seg(statistics.median(tempos) if tempos else 0)}, p90 {_seg(p90)}",
        f"- Médias por caso: {_num(media('chamadas_llm'))} chamadas ao LLM, "
        f"{_num(media('chamadas_ferramenta'))} de ferramenta, {_num(media('tokens_entrada'))} tokens de entrada, "
        f"{_num(media('tokens_saida'))} de saída, {_num(media('reanalises'))} reanálises", "",
        "| Caso | Acerto | Tempo | Chamadas LLM | Chamadas ferramenta | Tokens (entrada/saída) | Reanálises |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in resultados:
        marca = "infra" if r["infra"] else "sim" if r["acerto"] else "não"
        linhas.append(f"| {r['id']} | {marca} | {_seg(r['ms'])} | {r['chamadas_llm']} | {r['chamadas_ferramenta']} "
                      f"| {r['tokens_entrada']}/{r['tokens_saida']} | {r['reanalises']} |")
    falhas = [r for r in resultados if not r["acerto"]]
    linhas += ["", "## Falhas", ""]
    linhas += [_falha(r) for r in falhas] if falhas else ["Nenhuma falha nesta rodada.", ""]
    linhas += linhas_metricas([resultados])
    _gravar_bloco(linhas, destino)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--casos", help="ids separados por vírgula (padrão: todos)")
    ap.add_argument("--pausa", type=float, default=8, help="segundos entre casos (padrão 8)")
    ap.add_argument("--rodadas", type=int, default=1, help="repete a avaliação N vezes e agrega (padrão 1)")
    ap.add_argument("--relatorio", type=Path, default=RELATORIO, help="onde escrever o relatório (padrão docs/avaliacao.md)")
    ap.add_argument("--gravar-cassetes", action="store_true", help="salva tests/cassetes/<id>.json dos acertos")
    args = ap.parse_args(argv)
    if args.casos and args.relatorio.resolve() == RELATORIO.resolve():
        ap.error("--casos gera um relatório parcial: não pode sobrescrever o oficial. Use --relatorio <outro arquivo>.")
    if args.rodadas < 1:
        ap.error("--rodadas precisa ser pelo menos 1.")
    if args.rodadas > 1 and args.gravar_cassetes:
        ap.error("--gravar-cassetes não vale com --rodadas > 1: qual rodada viraria o cassete? Grave com 1 rodada.")
    config.LLM_API_KEY = chave = obter_chave()  # config.LLM_API_KEY nasce vazio (sem .env); llm_padrao() lê daqui, depois desta linha
    casos = selecionar(carregar_casos(), args.casos.split(",") if args.casos else None)
    if args.rodadas > 1:  # várias rodadas não sobrescrevem data/gravacoes, que guardam uma rodada só
        with tempfile.TemporaryDirectory() as tmp:
            rodadas = rodar_rodadas(args.rodadas, casos, agent.llm_padrao(), args.pausa, chave, Path(tmp))
        escrever_relatorio_rodadas(rodadas, config.LLM_MODEL, args.relatorio)
    else:
        resultados = rodar_todos(casos, agent.llm_padrao(), args.pausa, chave, GRAVACOES,
                                 CASSETES if args.gravar_cassetes else None, config.LLM_MODEL)
        escrever_relatorio(resultados, config.LLM_MODEL, args.relatorio)
    print(f"Relatório em {args.relatorio}")


if __name__ == "__main__":
    main()
