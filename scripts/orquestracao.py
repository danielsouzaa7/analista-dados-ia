"""Métricas de orquestração de agentes a partir dos registros locais do Claude Code.

Uso: python scripts/orquestracao.py [--dir PASTA] [--saida docs/orquestracao.md]
    [--svg docs/img/orquestracao.svg] [--svg-celular docs/img/orquestracao-celular.svg]
    [--ate AAAA-MM-DDTHH:MM[:SS] (São Paulo, ou com fuso explícito)] [--ate-commit HASH]
    [--zona 300000]
Lê só timestamps, tipos, contagens de `usage` e a descrição do agente (usada só para detectar retrabalho,
nunca publicada); nunca copia texto de mensagens, IDs ou caminhos.
"""
import argparse
import json
import re
import statistics
import textwrap
from datetime import datetime, timedelta
from pathlib import Path

from tempo_construcao import FUSO, PASTA_PADRAO, RAIZ, _ler, corte_do_commit

SAIDA_PADRAO = RAIZ / "docs" / "orquestracao.md"
SVG_PADRAO = RAIZ / "docs" / "img" / "orquestracao.svg"
SVG_CELULAR_PADRAO = RAIZ / "docs" / "img" / "orquestracao-celular.svg"
LIMITE_ZONA = 300_000  # "zona de genialidade": contexto de pico até aqui mantém a qualidade (configurável)
ENTRADA, SAIDA, CACHE_LIDO, CACHE_CRIADO = (
    "input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")
PAUSA_MAX = timedelta(minutes=15)  # pausa maior entre dois eventos de um agente corta o segmento de atividade
SOMAS = ("entrada", "saida", "cache_lido", "cache_criado")

# ---- papéis (em português) ----
(IMPLEMENTADOR, REVISOR, CRITICO, ARQUITETO, ENG_SEG, QA, AUDITOR, PESQUISADOR, PLANEJADOR, DOCUMENTADOR,
 GERAL, OUTROS) = (
    "Implementador", "Revisor", "Crítico", "Arquiteto", "Engenheiro de segurança", "QA", "Auditor",
    "Pesquisador", "Planejador", "Documentador", "Agente geral", "Outros")
ORDEM_PAPEIS = (IMPLEMENTADOR, REVISOR, ENG_SEG, CRITICO, ARQUITETO, PLANEJADOR, QA, DOCUMENTADOR, AUDITOR,
                PESQUISADOR, GERAL, OUTROS)
PAPEIS_DO_LOOP_ESPERADOS = (CRITICO, AUDITOR, PESQUISADOR)  # citados no relatório quando não aparecem
POR_NOME = {
    "tdd-guide": IMPLEMENTADOR, "build-error-resolver": IMPLEMENTADOR, "gan-generator": IMPLEMENTADOR,
    "architect": ARQUITETO, "code-architect": ARQUITETO, "planner": PLANEJADOR, "doc-updater": DOCUMENTADOR,
    "e2e-runner": QA, "general-purpose": GERAL, "fork": GERAL,  # tipo genérico: o papel real não é declarado
}
# Fragmento do nome do tipo -> papel (primeiro que casar); ordem importa: "security-reviewer" antes de "reviewer".
POR_FRAGMENTO = (("security", ENG_SEG), ("reviewer", REVISOR), ("critic", CRITICO), ("audit", AUDITOR),
                 ("research", PESQUISADOR))
REVISORES_DO_LOOP = (REVISOR, ENG_SEG, CRITICO)  # papéis cuja execução conta como uma revisão
RETRABALHO = re.compile(r"corrig|\bfix(?:es|ed)?\b|volta|rodada\s*[2-9]|ajust|retom|reimpl", re.I)


def papel(agent_type: str | None) -> str:
    """Papel funcional pelo tipo registrado; qualquer prefixo `plugin:` é ignorado."""
    nome = (agent_type or "").split(":")[-1]
    if nome in POR_NOME:
        return POR_NOME[nome]
    for trecho, p in POR_FRAGMENTO:
        if trecho in nome:
            return p
    return QA if "qa" in nome.split("-") else OUTROS


# ---- leitura ----
def _uso(eventos: list[dict], vistos: set | None = None) -> dict:
    """Soma o `usage` das chamadas do assistente, uma vez por message.id (o registro repete a mesma
    resposta em várias linhas), e acha o pico de contexto e as compactações. Ids já presentes em `vistos`
    (de outro arquivo, ex.: fork que herda o início da conversa do pai) não entram nas somas nem na contagem de
    chamadas, mas seguem valendo para o pico, que mede a janela deste arquivo; os ids novos são adicionados."""
    vistos = set() if vistos is None else vistos
    chamadas, compactacoes = {}, []
    for i, e in enumerate(eventos):
        if e.get("type") == "system" and e.get("subtype") == "compact_boundary":
            compactacoes.append((e.get("compactMetadata") or {}).get("preTokens") or 0)
        m = e.get("message")
        if e.get("type") != "assistant" or not isinstance(m, dict) or not isinstance(m.get("usage"), dict):
            continue
        atual = chamadas.setdefault(m.get("id") or f"sem-id-{i}", dict.fromkeys((ENTRADA, SAIDA, CACHE_LIDO, CACHE_CRIADO), 0))
        for campo in atual:
            v = m["usage"].get(campo)
            atual[campo] = max(atual[campo], v if isinstance(v, int) else 0)
    proprias = [c for k, c in chamadas.items() if k.startswith("sem-id-") or k not in vistos]
    vistos.update(k for k in chamadas if not k.startswith("sem-id-"))
    return {
        "entrada": sum(c[ENTRADA] for c in proprias), "saida": sum(c[SAIDA] for c in proprias),
        "cache_lido": sum(c[CACHE_LIDO] for c in proprias), "cache_criado": sum(c[CACHE_CRIADO] for c in proprias),
        "pico": max((c[ENTRADA] + c[CACHE_LIDO] + c[CACHE_CRIADO] for c in chamadas.values()), default=0),
        "chamadas": len(proprias), "compactacoes": len(compactacoes),
        "pre_compactacao_max": max(compactacoes, default=0),
    }


def _novos(u: dict) -> int:
    """Tokens novos: saída + entrada nova + cache criado (exclui o cache lido, que é releitura)."""
    return u["entrada"] + u["cache_criado"] + u["saida"]


def _chamadas_de_agente(eventos: list[dict]) -> set[str]:
    """Ids das chamadas de ferramenta (inclui Agent) feitas por esta conversa."""
    ids = set()
    for e in eventos:
        c = (e.get("message") or {}).get("content") if isinstance(e.get("message"), dict) else None
        for b in c if isinstance(c, list) else []:
            if isinstance(b, dict) and b.get("type") == "tool_use" and isinstance(b.get("id"), str):
                ids.add(b["id"])
    return ids


def _meta(caminho: Path) -> dict:
    try:
        d = json.loads(caminho.with_suffix(".meta.json").read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _segmentos(ts: list[datetime]) -> list[tuple[datetime, datetime]]:
    """Trechos de atividade de um agente: eventos consecutivos separados por até PAUSA_MAX."""
    ts = sorted(ts)
    segs, ini = [], ts[0]
    for ant, t in zip(ts, ts[1:], strict=False):
        if t - ant > PAUSA_MAX:
            segs.append((ini, ant))
            ini = t
    return [*segs, (ini, ts[-1])]


def _ler_agente(caminho: Path, ate: datetime | None, vistos: set) -> dict | None:
    ev = _ler(caminho, ate)
    if not ev:  # começou depois do corte
        return None
    meta, ts = _meta(caminho), [e["_ts"] for e in ev]
    return {**_uso(ev, vistos), "papel": papel(meta.get("agentType")), "descricao": str(meta.get("description") or ""),
            "tool_use": meta.get("toolUseId"), "inicio": min(ts), "fim": max(ts), "segmentos": _segmentos(ts),
            "chamou": _chamadas_de_agente(ev)}


# ---- agent loop e concorrência ----
def _pico_concorrencia(ags: list[dict]) -> int:
    """Maior nº de agentes com segmento de atividade [início, fim) aberto no mesmo instante, medido no início de
    cada segmento. Pausas longas ficam de fora, mas dentro do segmento o agente pode só estar esperando:
    ainda pode superestimar."""
    def ativo(b: dict, t: datetime) -> bool:
        return any(i <= t < f for i, f in b["segmentos"])
    return max((1 + sum(b is not a and ativo(b, i) for b in ags) for a in ags for i, _ in a["segmentos"]), default=0)


def _loop(ags: list[dict]) -> dict:
    """Agent loop de uma sessão do orquestrador, por ordem de início. Execuções consecutivas do mesmo tipo (implementar ou
    revisar) formam um lote; um lote de implementação logo após revisão é reimplementação se alguma descrição
    indica retrabalho, senão abre nova tarefa. Heurística: tudo aqui é estimado."""
    lotes = []
    for a in sorted(ags, key=lambda x: x["inicio"]):
        tipo = "I" if a["papel"] == IMPLEMENTADOR else "R" if a["papel"] in REVISORES_DO_LOOP else None
        if tipo is None:
            continue
        if lotes and lotes[-1][0] == tipo:
            lotes[-1][1].append(a)
        else:
            lotes.append((tipo, [a]))
    tarefas, avulsas, reimpl, atual = [], 0, 0, None
    for tipo, g in lotes:
        if tipo == "R":
            if atual is None:
                avulsas += 1
            else:
                atual["revisoes"] += 1
            continue
        if atual and atual["revisoes"] and any(RETRABALHO.search(a["descricao"]) for a in g):
            atual["reimpl"] += 1
            reimpl += 1
        else:
            atual = {"revisoes": 0, "reimpl": 0}
            tarefas.append(atual)
    com = [t for t in tarefas if t["revisoes"]]
    return {"tarefas": len(tarefas), "com_revisao": len(com), "sem_revisao": len(tarefas) - len(com),
            "ciclos_revisao": sum(t["revisoes"] for t in com), "revisoes_avulsas": avulsas,
            "reimplementacoes": reimpl, "sem_retrabalho": sum(t["reimpl"] == 0 for t in com)}


def _fecha_loop(soma: dict, criticos: int) -> dict:
    return {**soma, "voltas_media": soma["ciclos_revisao"] / soma["com_revisao"] if soma["com_revisao"] else None,
            "criticos": criticos}


def medir(pasta: Path, ate: datetime | None = None, zona: int = LIMITE_ZONA) -> dict:
    lidas = []
    for s in sorted(pasta.glob("*.jsonl")):
        eventos = _ler(s, ate)
        if eventos:
            lidas.append((min(e["_ts"] for e in eventos), s, eventos))
    lidas.sort(key=lambda x: x[0])  # sessão do orquestrador, em ordem cronológica
    vistos: set = set()  # message.id já contado: a sessão principal é a dona; forks herdam e não recontam
    usos = [_uso(eventos, vistos) for _, _, eventos in lidas]
    agentes, por_sessao, sessoes = [], [], []
    for i, ((_, s, _), uso) in enumerate(zip(lidas, usos, strict=True), 1):
        ags = [a for a in (_ler_agente(p, ate, vistos) for p in sorted((s.parent / s.stem / "subagents").glob("agent-*.jsonl"))) if a]
        filhos_de_agentes = set().union(*(a["chamou"] for a in ags)) if ags else set()
        for a in ags:
            a["aninhado"] = a["tool_use"] in filhos_de_agentes
            a["sessao"] = i
        loop = _loop(ags)
        por_sessao.append({"n": i, "agentes": len(ags), "aninhados": sum(a["aninhado"] for a in ags),
                           "saida": sum(a["saida"] for a in ags), "novos": sum(_novos(a) for a in ags),
                           "pico_max": max((a["pico"] for a in ags), default=0), "pico_orq": uso["pico"],
                           "ciclos_revisao": loop["ciclos_revisao"], "reimplementacoes": loop["reimplementacoes"]})
        agentes += ags
        sessoes.append((uso, loop))
    orq = {k: sum(u[k] for u, _ in sessoes) for k in (*SOMAS, "chamadas", "compactacoes")}
    orq |= {"pico": max((u["pico"] for u, _ in sessoes), default=0), "n_sessoes": len(sessoes),
            "pre_compactacao_max": max((u["pre_compactacao_max"] for u, _ in sessoes), default=0),
            "sessoes_acima": sum(u["pico"] > zona for u, _ in sessoes), "sessoes": [u for u, _ in sessoes]}
    papeis = {}
    for p in ORDEM_PAPEIS:
        g = [a for a in agentes if a["papel"] == p]
        papeis[p] = {
            "n": len(g), "pico": max((a["pico"] for a in g), default=0),
            "pico_mediano": int(statistics.median(a["pico"] for a in g)) if g else 0,
            "dentro": sum(a["pico"] <= zona for a in g), "fora": sum(a["pico"] > zona for a in g),
            **{k: sum(a[k] for a in g) for k in SOMAS},
            "agentes": sorted(g, key=lambda a: -a["pico"]),
        }
    soma_loop = {k: sum(lp[k] for _, lp in sessoes) for k in
                 ("tarefas", "com_revisao", "sem_revisao", "ciclos_revisao", "revisoes_avulsas",
                  "reimplementacoes", "sem_retrabalho")}
    return {
        "ate": ate, "zona": zona, "n_agentes": len(agentes), "agentes": agentes,
        "total_agentes": {k: sum(a[k] for a in agentes) for k in (*SOMAS, "chamadas")},
        "orquestrador": orq, "papeis": papeis, "por_sessao": por_sessao,
        "dentro_zona": sum(a["pico"] <= zona for a in agentes),
        "fora_zona": sum(a["pico"] > zona for a in agentes),
        "concorrencia_max": _pico_concorrencia(agentes), "aninhados": sum(a["aninhado"] for a in agentes),
        "loop": _fecha_loop(soma_loop, papeis[CRITICO]["n"]),
    }


# ---- formatação ----
def n(v: int) -> str:
    return f"{v:,}".replace(",", ".")


def mi(v: float) -> str:
    return f"{v / 1e6:.1f}".replace(".", ",") + " mi" if v >= 1e6 else f"{round(v / 1e3)} mil"


def razao(a: int, b: int) -> str:
    return f"{a / b:.1f}".replace(".", ",") + "x" if b else "—"


def pct(a: int, b: int) -> str:
    return f"{100 * a / b:.0f}%" if b else "—"


def qtd(v: int, singular: str, plural: str) -> str:
    return f"{v} {singular if v == 1 else plural}"


def _linha(nome: str, t: int, o: int) -> str:
    return f"| {nome} | {n(t)} | {n(o)} | {razao(t, o)} |"


def _zona(r: dict) -> str:
    return (f"{r['dentro_zona']} de {r['n_agentes']} agentes ficaram na zona de genialidade "
            f"(pico até {n(r['zona'])}) e {qtd(r['fora_zona'], 'passou', 'passaram')} dela")


METODOLOGIA = (
    ("Tokens gerados, entrada nova, cache criado, cache lido", "observada",
     "campo `usage` de cada resposta (agente e orquestrador)",
     "soma por `message.id` (maior valor de cada campo): `output_tokens`, `input_tokens`, "
     "`cache_creation_input_tokens`, `cache_read_input_tokens`; um id que aparece em mais de um arquivo "
     "(fork que herda o início da conversa) conta uma vez, na sessão principal"),
    ("Tokens novos / total bruto / razão agentes ÷ orquestrador", "calculada", "`usage`",
     "novos = saída + entrada nova + cache criado; bruto = novos + cache lido; razão = total dos agentes ÷ total do orquestrador"),
    ("Pico de contexto (tamanho da janela num instante, não é soma)", "calculada", "`usage` de cada chamada",
     "máximo, entre as chamadas, de entrada + cache lido + cache criado"),
    ("Dentro / acima da zona de genialidade", "calculada", "pico de contexto", "dentro se pico ≤ limite (300.000 por padrão, `--zona`)"),
    ("Número de agentes e agentes aninhados", "observada",
     "um arquivo de registro por subagente; `toolUseId` do agente × chamadas (`tool_use`) dos registros",
     "contagem de arquivos; aninhado = chamada feita por outro subagente; cada agente conta uma vez, com o próprio `usage`"),
    ("Papel do agente", "calculada", "tipo registrado do agente (`agentType`)",
     "tabela tipo → papel em português; qualquer prefixo `plugin:` é ignorado; tipo genérico vira \"Agente geral\""),
    ("Sessão do orquestrador (agrupamento dos agentes)", "observada", "arquivo da sessão que contém os agentes",
     "cada agente pertence à sessão cujo registro o originou, numerada por ordem cronológica; os registros não "
     "trazem o nome do fluxo ou da habilidade que disparou o lote"),
    ("Pico de agentes simultâneos", "estimada", "timestamps dos eventos de cada agente",
     "segmentos de atividade = eventos separados por até 15 minutos; pico = maior nº de segmentos abertos no mesmo "
     "instante; dentro de um segmento o agente pode só estar esperando, então pode superestimar (não é limite inferior)"),
    ("Papel Crítico (quantidade)", "observada", "tipo registrado do agente", "contagem de agentes com tipo de crítico"),
    ("Ciclos de revisão, voltas por tarefa, reimplementações", "estimada",
     "ordem de início e descrição dos agentes (a descrição não é publicada)",
     "lotes consecutivos de implementação/revisão por sessão; reimplementação = lote de implementação logo após "
     "revisão com descrição de retrabalho (corrigir, fix, volta, rodada 2, ajustar…); voltas = ciclos ÷ tarefas revisadas"),
    ("Lotes sem retrabalho após a revisão", "estimada", "mesma sequência",
     "tarefas revisadas sem reimplementação ÷ tarefas revisadas; proxy por palavras-chave, não é taxa de aprovação"),
    ("Veredito de cada revisor; tokens por tarefa aprovada; qualidade × consumo", "indisponível",
     "o veredito está em texto livre, que este script não lê; não há avaliação independente por tarefa",
     "sem fórmula: não é calculado nem estimado"),
    ("Compactações de contexto", "observada", "evento de compactação do registro",
     "contagem; o contexto antes de compactar vem de `preTokens` do evento, não do `usage`"),
)


def _tabela_papeis(r: dict) -> list[str]:
    tn = sum(_novos(g) for g in r["papeis"].values())
    linhas = ["| Papel | Agentes | Tokens gerados | Tokens novos | % dos tokens novos | Cache lido | Pico máx. | Pico mediano | Dentro da zona | Acima |",
              "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for p, g in r["papeis"].items():
        if g["n"]:
            linhas.append(f"| {p} | {g['n']} | {n(g['saida'])} | {n(_novos(g))} | {pct(_novos(g), tn)} | {n(g['cache_lido'])} "
                          f"| {n(g['pico'])} | {n(g['pico_mediano'])} | {g['dentro']} | {g['fora']} |")
    ausentes = [p for p in PAPEIS_DO_LOOP_ESPERADOS if not r["papeis"][p]["n"]]
    if ausentes:
        linhas += ["", f"Sem registros (0 agentes): {', '.join(ausentes)}."]
    if not r["papeis"][CRITICO]["n"]:
        linhas += ["", "O papel Crítico não existiu nesta construção: as revisões foram feitas por revisores "
                   "especializados e pelo engenheiro de segurança; nenhum revisor é rotulado como crítico."]
    return linhas


def _tabela_loop(r: dict) -> list[str]:
    lp = r["loop"]
    voltas = f"{lp['voltas_media']:.1f}".replace(".", ",") if lp["voltas_media"] is not None else "—"
    return [
        "| Métrica | Valor | Tipo |", "|---|---:|---|",
        f"| Tarefas (lotes de implementação) | {lp['tarefas']} | estimada |",
        f"| Tarefas revisadas / sem revisão | {lp['com_revisao']} / {lp['sem_revisao']} | estimada |",
        f"| Ciclos de revisão | {lp['ciclos_revisao']} | estimada |",
        f"| Revisões sem implementação antes na sessão | {lp['revisoes_avulsas']} | estimada |",
        f"| Voltas de revisão por tarefa revisada | {voltas} | estimada |",
        f"| Reimplementações | {lp['reimplementacoes']} | estimada |",
        f"| Lotes sem retrabalho após a revisão (proxy por palavras-chave; não é taxa de aprovação) | "
        f"{lp['sem_retrabalho']} de {lp['com_revisao']} ({pct(lp['sem_retrabalho'], lp['com_revisao'])}) | estimada |",
        "| Veredito de cada revisor | — | indisponível |",
        f"| Agentes no papel Crítico | {lp['criticos']} | observada |",
    ]


def _aviso_corte(r: dict) -> list[str]:
    if not r.get("ate"):
        return []
    ate = f"o commit `{r['commit']}`" if r.get("commit") else r["ate"].astimezone(FUSO).strftime("%d/%m/%Y") + " (horário de São Paulo)"
    repro = ""
    if r.get("commit"):
        repro = (" Para reproduzir (exige os registros locais do Claude Code, que não são publicados): "
                 f"`python scripts/orquestracao.py --ate-commit {r['commit']}`.")
    return [f"Mede só a construção do agente, até {ate}.{repro}", ""]


def _secao_resumo(r: dict) -> list[str]:
    o, t = r["orquestrador"], r["total_agentes"]
    bruto_a, bruto_o = _novos(t) + t["cache_lido"], _novos(o) + o["cache_lido"]
    return [
        f"**{r['n_agentes']} agentes geraram {n(t['saida'])} tokens de saída; o orquestrador (conversa "
        f"principal de {o['n_sessoes']} sessões) gerou {n(o['saida'])}** ({razao(t['saida'], o['saida'])}). "
        f"O pico de contexto do orquestrador foi {n(o['pico'])} tokens; {_zona(r)}. "
        f"No máximo {r['concorrencia_max']} agentes rodaram ao mesmo tempo (estimado).", "",
        f"Somando todo o contexto processado, o total é {n(bruto_a)} nos agentes contra {n(bruto_o)} no orquestrador "
        f"({razao(bruto_a, bruto_o)}), bem menos favorável que a razão dos tokens gerados. Cache criado é contexto novo "
        "gravado no cache; cache lido é esse mesmo contexto relido a cada chamada, por isso infla o total bruto.", ""]


def _secao_totais(r: dict) -> list[str]:
    o, t = r["orquestrador"], r["total_agentes"]
    return [
        "## Totais", "",
        "| Medida | Agentes | Orquestrador | Razão agentes ÷ orquestrador |", "|---|---:|---:|---:|",
        _linha("Tokens gerados (saída)", t["saida"], o["saida"]),
        _linha("Entrada nova (`input_tokens`)", t["entrada"], o["entrada"]),
        _linha("Cache criado", t["cache_criado"], o["cache_criado"]),
        _linha("**Tokens novos** (saída + entrada nova + cache criado)", _novos(t), _novos(o)),
        _linha("Cache lido (releitura, não é trabalho novo)", t["cache_lido"], o["cache_lido"]),
        _linha("Total bruto (tokens novos + cache lido)", _novos(t) + t["cache_lido"], _novos(o) + o["cache_lido"]),
        _linha("Chamadas ao modelo", t["chamadas"], o["chamadas"]), ""]


def _secao_sessoes_dos_agentes(r: dict) -> list[str]:
    return [
        "## Agentes por sessão do orquestrador", "",
        "| Sessão do orquestrador | Agentes | Tokens gerados pelos agentes | Tokens novos dos agentes | Pico máx. de agente | Pico do orquestrador | Ciclos de revisão | Reimplementações |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
        *[f"| {w['n']} | {w['agentes']} | {n(w['saida'])} | {n(w['novos'])} | {n(w['pico_max'])} | {n(w['pico_orq'])} "
          f"| {w['ciclos_revisao']} | {w['reimplementacoes']} |" for w in r["por_sessao"]],
        "", f"Agentes criados por outros subagentes (aninhados): {r['aninhados']}. Cada agente aparece uma vez, na sessão "
        "que o originou, e cada resposta (`message.id`) conta uma vez, na sessão principal quando também aparece num fork (cópia de uma conversa que herda o início dela).", ""]


def _secao_concorrencia(r: dict) -> list[str]:
    return [
        f"## Agentes simultâneos: pico de {r['concorrencia_max']} (estimado)", "",
        "Calculado pela sobreposição dos segmentos de atividade de cada agente: pausas de mais de 15 minutos entre "
        "eventos cortam o segmento. Dentro de um segmento o agente pode estar só esperando uma resposta ou ferramenta, "
        "então o valor ainda pode superestimar; não é limite inferior.", ""]


def _secao_loop(r: dict) -> list[str]:
    titulo = ("Agent loop (implementador → revisor → crítico)" if r["loop"]["criticos"]
              else "Agent loop (implementador → revisor; sem papel Crítico nesta construção)")
    return [
        f"## {titulo}", "", *_tabela_loop(r), "",
        "Tudo acima, exceto a contagem de críticos, é estimado: os registros não trazem o fluxo nem o veredito, "
        "só a ordem dos agentes e a descrição de cada um. A \"tarefa\" é um lote de implementação, não uma fatia "
        "individual: fatias lançadas em paralelo compartilham as mesmas revisões.", ""]


def _secao_zona_e_orquestrador(r: dict) -> list[str]:
    o = r["orquestrador"]
    linhas = [
        f"## Zona de genialidade (pico de contexto até {mi(r['zona'])} tokens)", "",
        "| Quem | Dentro da zona | Fora da zona |", "|---|---:|---:|",
        f"| Agentes | {r['dentro_zona']} | {r['fora_zona']} |",
        f"| Orquestrador (sessões) | {o['n_sessoes'] - o['sessoes_acima']} | {o['sessoes_acima']} |", "",
        "## Orquestrador por sessão", "",
        "| Sessão (ordem cronológica) | Pico de contexto | Compactações | Maior contexto antes de compactar |",
        "|---|---:|---:|---:|",
        *[f"| {i} | {n(u['pico'])} | {u['compactacoes']} | "
          f"{n(u['pre_compactacao_max']) if u['compactacoes'] else '—'} |" for i, u in enumerate(o["sessoes"], 1)],
        "", "O contexto antes de compactar vem do campo `preTokens` do evento de compactação, não das chamadas; por isso "
        "pode ser maior que o pico medido pelo `usage`.", ""]
    if o["sessoes_acima"]:
        linhas += [f"**Honestidade:** {qtd(o['sessoes_acima'], 'sessão do orquestrador passou', 'sessões do orquestrador passaram')} de "
                   f"{n(r['zona'])} tokens de pico; o contexto foi compactado {o['compactacoes']} "
                   f"{'vez' if o['compactacoes'] == 1 else 'vezes'} (maior contexto antes de compactar: {n(o['pre_compactacao_max'])}).", ""]
    return linhas


def _secao_metodologia(hoje: datetime) -> list[str]:
    return [
        "## Metodologia", "",
        "Cada métrica é observada (lida direto do registro), calculada (fórmula sobre dados observados), "
        "estimada (heurística) ou indisponível. Os registros são lidos até o corte do projeto (`--ate`); eventos "
        "depois dele são ignorados. Contexto (tamanho da janela num instante) e tokens consumidos (soma de "
        "chamadas) são medidas diferentes e nunca se misturam.", "",
        "| Métrica | Tipo | Fonte | Fórmula |", "|---|---|---|---|",
        *[f"| {m} | {tp} | {fonte} | {formula} |" for m, tp, fonte, formula in METODOLOGIA], "",
        "Limites: o orquestrador tem poucas sessões, cada uma longa; papéis diferentes não são comparáveis em "
        "custo; volume de tokens não mede qualidade nem produtividade. Só contagens agregadas: nenhum texto, "
        "identificador, descrição ou caminho é publicado.", "",
        f"Gerado por `scripts/orquestracao.py` em {hoje.strftime('%d/%m/%Y')}.", ""]


def markdown(r: dict, hoje: datetime | None = None) -> str:
    hoje = hoje or datetime.now(FUSO)
    linhas = [
        "# Orquestração de agentes", "", "Gerado por `scripts/orquestracao.py` a partir dos registros locais do Claude Code.", "",
        *_aviso_corte(r), *_secao_resumo(r), *_secao_totais(r),
        "## Por papel", "", *_tabela_papeis(r), "",
        *_secao_sessoes_dos_agentes(r), *_secao_concorrencia(r), *_secao_loop(r),
        *_secao_zona_e_orquestrador(r), *_secao_metodologia(hoje)]
    return "\n".join(linhas)


# ---- gráfico (paleta: #131C2E fundo; #58A6FF, #39C5CF, #A371F7, #3FB950; cinzas neutros para texto) ----
FUNDO, AZUL, CIANO, ROXO, VERDE = "#131C2E", "#58A6FF", "#39C5CF", "#A371F7", "#3FB950"
TEXTO, SUAVE, MUDO = "#E6EDF3", "#C9D1D9", "#8B949E"
COR = {IMPLEMENTADOR: AZUL, REVISOR: ROXO, ENG_SEG: ROXO, CRITICO: ROXO, AUDITOR: ROXO, ARQUITETO: CIANO,
       PLANEJADOR: CIANO, QA: CIANO, DOCUMENTADOR: CIANO, PESQUISADOR: CIANO, GERAL: MUDO, OUTROS: MUDO}
LARG, X0, X1, LIN = 1200, 230, 1130, 7
ESTILO = ('<style>.s{font-family:system-ui,-apple-system,"Segoe UI",sans-serif}'
          '.m{font-family:ui-monospace,"Cascadia Mono",Consolas,monospace}'
          '.b{transform-box:fill-box;transform-origin:0 50%;animation:g .8s ease-out backwards}'
          '@keyframes g{from{transform:scaleX(0)}}'
          '@media (prefers-reduced-motion:reduce){.b{animation:none}}</style>')


def _textos(r: dict, celular: bool = False) -> tuple[str, str]:
    """(título, descrição) fiéis ao que o gráfico mostra."""
    o, t = r["orquestrador"], r["total_agentes"]
    if celular:
        titulo = "Orquestração: pico de contexto por sessão do orquestrador e pico máximo por papel de agente"
        barras = "Barras com o pico de contexto de cada sessão do orquestrador e o pico máximo por papel de agente"
    else:
        titulo = "Orquestração: pico de contexto de cada agente e de cada sessão do orquestrador"
        barras = "Barras com o pico de contexto de cada sessão do orquestrador e de cada agente, agrupados por papel"
    desc = (f"{barras}, com a "
            f"linha da zona de genialidade em {n(r['zona'])} tokens. {r['n_agentes']} agentes geraram {n(t['saida'])} "
            f"tokens de saída; o orquestrador gerou {n(o['saida'])} (razão {razao(t['saida'], o['saida'])}). "
            f"{r['dentro_zona']} {'agente ficou' if r['dentro_zona'] == 1 else 'agentes ficaram'} na zona de genialidade "
            f"e {qtd(r['fora_zona'], 'passou', 'passaram')} dela. Pico do orquestrador: {n(o['pico'])} tokens. "
            f"No máximo {r['concorrencia_max']} agentes simultâneos.")
    return titulo, desc


def _cabecalho(r: dict) -> list[str]:
    o, t, lp = r["orquestrador"], r["total_agentes"], r["loop"]
    return [
        f"Razão {razao(t['saida'], o['saida'])} em tokens gerados. Cada barra é o pico de contexto: {r['dentro_zona']} agentes "
        f"dentro da zona de genialidade, {r['fora_zona']} acima.",
        f"Orquestrador: pico de {n(o['pico'])} tokens, {o['compactacoes']} compactações. Até {r['concorrencia_max']} agentes ao mesmo tempo (estimado).",
        f"Agent loop (estimado): {lp['ciclos_revisao']} ciclos de revisão, {lp['reimplementacoes']} reimplementações; "
        f"{lp['criticos']} agentes no papel Crítico.",
    ]


def _moldura(r: dict, largura: int, altura: int, corpo: str, celular: bool = False) -> str:
    titulo, desc = _textos(r, celular)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {largura} {altura}" width="{largura}" '
            f'height="{altura}" role="img" aria-labelledby="t d"><title id="t">{titulo}</title>'
            f'<desc id="d">{desc}</desc>{ESTILO}<rect width="{largura}" height="{altura}" rx="14" fill="{FUNDO}"/>'
            f'{corpo}</svg>')


def _svg_desktop(r: dict) -> str:
    o, t = r["orquestrador"], r["total_agentes"]
    maximo = max(r["zona"] * 1.25, o["pico"] * 1.05, *(a["pico"] for a in r["agentes"]))

    def px(v: float) -> float:
        return X0 + (X1 - X0) * v / maximo

    y, corpo = 190, []

    def barra(rotulo: str, v: int, cor: str, atraso: float) -> None:
        nonlocal y
        corpo.append(f'<rect class="b" style="animation-delay:{atraso:.2f}s" x="{X0}" y="{y}" '
                     f'width="{px(v) - X0:.1f}" height="{LIN - 1}" rx="1" fill="{cor}"/>')
        if rotulo:
            corpo.append(f'<text class="s" x="{X0 - 8}" y="{y + 6}" text-anchor="end" font-size="9" '
                         f'fill="{SUAVE}">{rotulo}</text>')
        corpo.append(f'<text class="m" x="{px(v) + 6:.1f}" y="{y + 6}" font-size="10" fill="{MUDO}">{n(v)}</text>')
        y += LIN + 3

    corpo.append(f'<text class="s" x="40" y="{y - 14}" font-size="13" font-weight="700" fill="{TEXTO}">'
                 f'Orquestrador (conversa principal, {o["n_sessoes"]} sessões)</text>')
    for i, u in enumerate(o["sessoes"], 1):
        barra(f"sessão {i}", u["pico"], TEXTO, 0.05 * i)
    y += 10
    for k, (p, g) in enumerate((p, g) for p, g in r["papeis"].items() if g["n"]):
        corpo.append(f'<text class="s" x="40" y="{y + 4}" font-size="13" font-weight="700" fill="{COR[p]}">'
                     f'{p} ({qtd(g["n"], "agente", "agentes")})</text>')
        y += 12
        for j, a in enumerate(g["agentes"]):
            barra("", a["pico"], COR[p], 0.4 + 0.05 * k + 0.005 * j)
        y += 10
    altura, xz, topo = y + 20, px(r["zona"]), 178
    cab = _cabecalho(r)
    cabeca = (
        f'<text class="s" x="40" y="44" font-size="22" font-weight="700" fill="{TEXTO}">'
        f'{r["n_agentes"]} agentes geraram {mi(t["saida"])} tokens; o orquestrador, {mi(o["saida"])}</text>'
        + "".join(f'<text class="s" x="40" y="{70 + 22 * i}" font-size="14" fill="{(MUDO, SUAVE, ROXO)[i]}">{ln}</text>'
                  for i, ln in enumerate(cab)))
    guia = (f'<rect x="{X0}" y="{topo}" width="{xz - X0:.1f}" height="{altura - topo - 20}" fill="{VERDE}" opacity=".08"/>'
            f'<line x1="{xz:.1f}" y1="{topo - 8}" x2="{xz:.1f}" y2="{altura - 20}" stroke="{VERDE}" '
            f'stroke-width="1.5" stroke-dasharray="5 4"/>'
            f'<text class="s" x="{xz + 6:.1f}" y="{topo - 12}" font-size="12" fill="{VERDE}">'
            f'zona de genialidade: até {n(r["zona"])} tokens</text>')
    return _moldura(r, LARG, altura, cabeca + guia + "".join(corpo))


def _svg_celular(r: dict) -> str:
    """Vertical e estreito: cabeçalho em linhas curtas e uma barra por papel (pico máximo) e por sessão."""
    o, t = r["orquestrador"], r["total_agentes"]
    larg, xa, xb = 400, 20, 330
    maximo = max(r["zona"] * 1.25, o["pico"] * 1.05, *(a["pico"] for a in r["agentes"]))
    corpo, y = [], 34
    corpo.append(f'<text class="s" x="{xa}" y="{y}" font-size="17" font-weight="700" fill="{TEXTO}">'
                 f'{r["n_agentes"]} agentes: {mi(t["saida"])} tokens</text>')
    corpo.append(f'<text class="s" x="{xa}" y="{y + 20}" font-size="13" fill="{TEXTO}">'
                 f'orquestrador: {mi(o["saida"])} tokens</text>')
    y += 44
    for ln, cor in zip(_cabecalho(r), (MUDO, SUAVE, ROXO), strict=True):  # roxo: a linha do ciclo de revisão
        for parte in textwrap.wrap(ln, 50):
            corpo.append(f'<text class="s" x="{xa}" y="{y}" font-size="11" fill="{cor}">{parte}</text>')
            y += 15
        y += 4
    topo = y + 14
    y += 34

    def px(v: float) -> float:
        return xa + (xb - xa) * v / maximo

    def item(rotulo: str, v: int, cor: str, atraso: float) -> None:
        nonlocal y
        corpo.append(f'<text class="s" x="{xa}" y="{y}" font-size="11" fill="{cor}">{rotulo}</text>'
                     f'<text class="m" x="{larg - xa}" y="{y}" text-anchor="end" font-size="10" fill="{MUDO}">{n(v)}</text>'
                     f'<rect class="b" style="animation-delay:{atraso:.2f}s" x="{xa}" y="{y + 5}" '
                     f'width="{px(v) - xa:.1f}" height="7" rx="2" fill="{cor}"/>')
        y += 26

    corpo.append(f'<text class="s" x="{xa}" y="{y - 14}" font-size="12" font-weight="700" fill="{TEXTO}">Orquestrador, pico por sessão</text>')
    for i, u in enumerate(o["sessoes"], 1):
        item(f"sessão {i}", u["pico"], TEXTO, 0.05 * i)
    y += 8
    corpo.append(f'<text class="s" x="{xa}" y="{y - 6}" font-size="12" font-weight="700" fill="{TEXTO}">Agentes, pico máximo por papel</text>')
    y += 12
    for k, (p, g) in enumerate((p, g) for p, g in r["papeis"].items() if g["n"]):
        item(f"{p} ({g['n']})", g["pico"], COR[p], 0.4 + 0.05 * k)
    altura, xz = y + 14, px(r["zona"])
    corpo.append(f'<rect x="{xa}" y="{topo}" width="{xz - xa:.1f}" height="{altura - topo - 14}" fill="{VERDE}" opacity=".08"/>'
                 f'<line x1="{xz:.1f}" y1="{topo - 6}" x2="{xz:.1f}" y2="{altura - 14}" stroke="{VERDE}" '
                 f'stroke-width="1.5" stroke-dasharray="5 4"/>'
                 f'<text class="s" x="{xz - 4:.1f}" y="{topo - 10}" text-anchor="end" font-size="10" fill="{VERDE}">'
                 f'zona de genialidade: até {n(r["zona"])}</text>')
    return _moldura(r, larg, altura, "".join(corpo), celular=True)


def svg(r: dict, celular: bool = False) -> str:
    return _svg_celular(r) if celular else _svg_desktop(r)


def parse_ate(texto: str) -> datetime:
    """Instante de corte: sem fuso, vale horário de São Paulo; com fuso explícito, ele é respeitado."""
    d = datetime.fromisoformat(texto)
    return d if d.tzinfo else d.replace(tzinfo=FUSO)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dir", type=Path, default=PASTA_PADRAO)
    p.add_argument("--saida", type=Path, default=SAIDA_PADRAO)
    p.add_argument("--svg", type=Path, default=SVG_PADRAO)
    p.add_argument("--svg-celular", type=Path, default=SVG_CELULAR_PADRAO)
    p.add_argument("--zona", type=int, default=LIMITE_ZONA, help="limite da zona de genialidade, em tokens de contexto")
    p.add_argument("--ate", type=parse_ate,
                   help="corte: eventos depois deste instante são ignorados (sem fuso, vale horário de São Paulo)")
    p.add_argument("--ate-commit", help="commit que marca o corte; sem --ate, o corte é o horário dele no git")
    a = p.parse_args()
    ate = a.ate or (corte_do_commit(a.ate_commit) if a.ate_commit else None)
    r = {**medir(a.dir, ate, a.zona), "commit": a.ate_commit}
    for caminho, texto in ((a.saida, markdown(r)), (a.svg, svg(r)), (a.svg_celular, svg(r, celular=True))):
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_text(texto, encoding="utf-8")
    o, t = r["orquestrador"], r["total_agentes"]
    print(f"{r['n_agentes']} agentes: saída {n(t['saida'])} | orquestrador: saída {n(o['saida'])}, "
          f"pico {n(o['pico'])} | dentro da zona {r['dentro_zona']}, fora {r['fora_zona']} | "
          f"simultâneos {r['concorrencia_max']} | loop {r['loop']}")


if __name__ == "__main__":
    main()
