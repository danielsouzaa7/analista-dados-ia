"""Orquestrador em streaming: plano -> laço de ferramentas -> conferência dos números -> reanálise (até 2x).

`executar` gera os eventos do contrato SSE; `responder` os consome e devolve o dict final."""
import csv
import functools
import io
import json
import math
import os
import re
import time
import uuid
from collections.abc import Callable, Iterator
from decimal import Decimal
from typing import Any

import openai
from openai import OpenAI

from app import config, graficos, prompts, python_tool, sql_tool
from app.checker import numeros_nao_conferidos
from app.errors import ErroUsuario
from app.sessions import Sessao

MAX_CHAMADAS = 8  # ferramentas por pergunta
MAX_CHAMADAS_LLM = 12
MAX_REANALISES = 2
LIMITE_SEGUNDOS = 120
MAX_LINHAS_GRAFICO = 5000
MAX_LINHAS_PYTHON = 100_000  # o df tem que ser o resultado inteiro: estatística numa parte sai errada
MAX_BYTES_PYTHON = 20 * 1024 * 1024  # células largas não podem estourar os 512 MB do V8 do sandbox
MAX_TURNOS = 3
MAX_RESUMO, MAX_RESULTADOS = 2000, 10_000
ESPERAS_429 = (5.0, 10.0)
MODELO_RESERVA = os.environ.get("LLM_MODEL_FALLBACK", "gemini-flash-lite-latest")
MARCADOR = "SUGESTOES:"
_DOBRA = str.maketrans("abcdefghijklmnopqrstuvwxyzõÕ", "ABCDEFGHIJKLMNOPQRSTUVWXYZOO")  # mesmo tamanho: índices valem no original
MAX_NOME, MAX_ESQUEMA = 64, 8000  # nomes e esquema vão a até 13 chamadas por pergunta
MAX_CELULA, MAX_BYTES_LINHAS = 200, 200_000  # ferramenta_fim vai para o navegador
NL = chr(10)
_TAG_DADOS = re.compile(r"<\s*/?\s*dados\s*>", re.IGNORECASE)
_MARCADOR = re.compile(r"(?m)^[ *_#]*" + MARCADOR)  # só no começo da linha: "minhas sugestões:" na prosa é texto
_dormir = time.sleep

TIPOS = {"consultar_banco": "sql", "rodar_python": "python", "gerar_grafico": "grafico"}
# Pedaços normalizados: ("texto", str) | ("tool_call", {id, nome, args, extra_content}) | ("usage", {entrada, saida})
# | ("modelo", str) | ("espera", segundos)
LlmFn = Callable[[list[dict], list[dict] | None, float], Iterator[tuple]]

TOOLS = [
    {"type": "function", "function": {
        "name": "consultar_banco",
        "description": "Executa uma consulta SQL de leitura (um único SELECT) e devolve o resultado em CSV.",
        "parameters": {"type": "object", "properties": {
            "sql": {"type": "string", "description": "Consulta SELECT."}}, "required": ["sql"]}}},
    {"type": "function", "function": {
        "name": "rodar_python",
        "description": ("Roda código Python em ambiente isolado: só pandas, numpy e a biblioteca padrão, "
                        "sem scipy, statsmodels nem sklearn. O resultado do SQL vira o DataFrame `df`. "
                        "Já existem teste_t_welch(a, b) -> (t, gl, p_valor) e teste_correlacao(x, y) -> "
                        "(r, gl, p_valor). Use print() para mostrar resultados, inclusive o p-valor."),
        "parameters": {"type": "object", "properties": {
            "sql": {"type": "string", "description": "SELECT cujo resultado vira o DataFrame df."},
            "codigo": {"type": "string", "description": "Código Python que usa df e imprime com print."}},
            "required": ["sql", "codigo"]}}},
    {"type": "function", "function": {
        "name": "gerar_grafico",
        "description": ("Cria um gráfico a partir de um SELECT. x e y são nomes de colunas do resultado. "
                        "ranking: x=categoria, y=valor. tendencia: x=data/ordem, y=valor, serie opcional. "
                        "composicao: x=categoria, y=valor. mapa_calor: x e y são as duas dimensões e valor é a "
                        "coluna numérica. dispersao: x e y numéricos."),
        "parameters": {"type": "object", "properties": {
            "sql": {"type": "string"},
            "tipo": {"type": "string", "enum": list(graficos.TIPOS)},
            "x": {"type": "string", "description": "Coluna do eixo x (ou da primeira dimensão)."},
            "y": {"type": "string", "description": "Coluna do eixo y (ou da segunda dimensão)."},
            "titulo": {"type": "string"},
            "valor": {"type": "string", "description": "Só no mapa_calor: coluna numérica de cada célula."},
            "serie": {"type": "string", "description": "Só na tendencia: coluna que separa as linhas (até 4)."},
            "subtitulo": {"type": "string"}}, "required": ["sql", "tipo", "x", "y", "titulo"]}}},
]

MSG_LIMITE = "A análise passou do limite de 120 s e foi interrompida. Tente uma pergunta mais simples."
MSG_VAZIA = "O modelo de IA não devolveu uma resposta. Tente reformular a pergunta."
MSG_MAX_CHAMADAS = ("A análise precisou de mais de 8 chamadas de ferramenta e foi "
                    "interrompida. Tente uma pergunta mais específica.")
MSG_MAX_LLM = ("A análise precisou de mais de 12 chamadas ao modelo e foi interrompida. "
               "Tente uma pergunta mais específica.")
MSG_COTA = "O limite gratuito do modelo de IA foi atingido (cota). Espere um minuto e tente de novo."
MSG_RECUSADO = "O serviço de IA recusou o pedido."
MSG_INDISPONIVEL = "O serviço de IA não respondeu agora. Tente de novo em instantes."
_TIPO_ERRO = {MSG_LIMITE: "limite_tempo", MSG_MAX_CHAMADAS: "limite_ferramentas", MSG_MAX_LLM: "limite_llm",
              MSG_VAZIA: "resposta_vazia"}


def _perfil_texto(tabela: dict) -> str:
    linhas = []
    for c in tabela.get("perfil", {}).get("colunas", []):
        if c.get("nulos_pct") is None:
            continue
        faixa = f", de {c['min']} a {c['max']}" if "min" in c and not c.get("pii") else ""
        pessoal = f", DADO PESSOAL ({c['pii']})" if c.get("pii") else ""
        linhas.append(f"    {c['nome'][:MAX_NOME]}: {c['distintos']} distintos, {c['nulos_pct']}% nulos{faixa}{pessoal}")
    return NL.join(linhas)


def _como_dado(texto: str) -> str:
    """O conteúdo do CSV não pode fechar o delimitador nem virar instrução."""
    while (limpo := _TAG_DADOS.sub("", texto)) != texto:  # "</da</dados>dos>" vira tag depois da 1ª passada
        texto = limpo
    return f"<dados>{NL}{texto}{NL}</dados>"


def _esquema(sessao: Sessao) -> str:
    blocos = []
    for t in sessao.tabelas:
        pessoais = {c["nome"] for c in t.get("perfil", {}).get("colunas", []) if c.get("pii")}
        colunas = ", ".join(c["nome"][:MAX_NOME] + " " + c["tipo"] + (" PESSOAL" if c["nome"] in pessoais else "")
                            for c in t["colunas"])
        bloco = f"- {t['nome'][:MAX_NOME]}({colunas})"
        perfil = _perfil_texto(t)
        blocos.append(bloco + (NL + perfil if perfil else ""))
    texto = NL.join(blocos)
    nomes_pessoais = [c["nome"][:MAX_NOME] for t in sessao.tabelas for c in t.get("perfil", {}).get("colunas", [])
                      if c.get("pii")]
    if nomes_pessoais:  # no começo: o corte por MAX_ESQUEMA não pode apagar a marca
        texto = f"Colunas com dado pessoal: {', '.join(nomes_pessoais)}{NL}{texto}"
    texto += f"{NL}{NL}Valores das colunas categóricas:{NL}{sessao.grounding}" if sessao.grounding else ""
    cortado = len(texto) > MAX_ESQUEMA
    return _como_dado(texto[:MAX_ESQUEMA] + (f"{NL}[esquema cortado]" if cortado else ""))


def _historico(sessao: Sessao) -> str:
    if not sessao.historico:
        return ""
    return prompts.HISTORICO + _como_dado(f"{NL}---{NL}".join(t["resumo"] for t in sessao.historico))


def _j(v: object) -> object:
    if isinstance(v, Decimal):
        v = float(v)
    if isinstance(v, float) and not math.isfinite(v):
        return None  # NaN/Infinity não existem em JSON
    if isinstance(v, str):
        return v[:MAX_CELULA]
    return v if v is None or isinstance(v, (int, float, bool)) else str(v)[:MAX_CELULA]


def _linhas_do_evento(linhas: list) -> list[list]:
    saida, bytes_ = [], 0
    for lin in linhas:
        linha = [_j(v) for v in lin]
        bytes_ += len(json.dumps(linha, ensure_ascii=False))
        if bytes_ > MAX_BYTES_LINHAS:
            break
        saida.append(linha)
    return saida


def _csv(r: sql_tool.Resultado) -> tuple[str, int]:
    """CSV para o df do Python, com teto de tamanho (em caracteres). Devolve (csv, linhas que couberam)."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(r.colunas)
    for n, linha in enumerate(r.linhas):
        antes = buf.tell()
        w.writerow(linha)
        if buf.tell() > MAX_BYTES_PYTHON:
            buf.seek(antes)
            buf.truncate()
            return buf.getvalue(), n
    return buf.getvalue(), len(r.linhas)


def _rodar(nome: str, args: dict, sessao: Sessao, timeout: float) -> tuple[str, dict]:
    """Roda uma ferramenta: devolve o texto para o LLM e os campos extras de ferramenta_fim (levanta ErroUsuario)."""
    if nome == "consultar_banco":
        r = sql_tool.executar(sessao, args["sql"], timeout=timeout)
        extra = {"colunas": r.colunas, "linhas": _linhas_do_evento(r.linhas),
                 "total_linhas": len(r.linhas)}
        return sql_tool.para_texto(r), extra
    if nome == "rodar_python":
        r = sql_tool.executar(sessao, args["sql"], limite=MAX_LINHAS_PYTHON, timeout=timeout)
        dados, cabem = _csv(r)
        res = python_tool.rodar(args["codigo"], dados, timeout=timeout)
        if res["erro"]:
            raise ErroUsuario(f"Erro no Python: {res['erro']}")
        aviso = (f"Atenção: o df recebeu só as {cabem} primeiras linhas do SELECT (resultado cortado). "
                 "Agregue no SQL antes de calcular.\n") if r.truncado or cabem < len(r.linhas) else ""
        saida = aviso + (res["saida"] or "(o código não imprimiu nada)")
        return saida, {"saida": saida}
    if nome == "gerar_grafico":
        if args["tipo"] not in graficos.TIPOS:
            raise ErroUsuario(f"Tipo de gráfico inválido. Use um destes: {', '.join(graficos.TIPOS)}.")
        r = sql_tool.executar(sessao, args["sql"], limite=MAX_LINHAS_GRAFICO, timeout=timeout)
        g = graficos.moldar(args["tipo"], r.colunas, r.linhas, x=args["x"], y=args["y"], titulo=args["titulo"],
                            valor=args.get("valor"), serie=args.get("serie"), subtitulo=args.get("subtitulo"))
        return f"Gráfico criado. {g['resumo']}\n" + sql_tool.para_texto(r), {"grafico": g}
    raise ErroUsuario(f"Ferramenta desconhecida: {nome}.")


def _passo(nome: str, args: dict, extra: dict, erro: str | None) -> dict:
    tipo = TIPOS.get(nome)
    if tipo is None or not isinstance(args.get("sql"), str) or not args["sql"]:
        return {"tipo": "erro", "erro": erro}
    if tipo == "python":
        return {"tipo": tipo, "sql": args["sql"], "codigo": args.get("codigo", ""),
                "saida": extra.get("saida", ""), "erro": erro}
    passo = {"tipo": tipo, "sql": args["sql"], "erro": erro}
    if erro:
        return passo
    if tipo == "sql":
        return {**passo, "resultado": {"colunas": extra["colunas"], "linhas": extra["linhas"][:20]}}
    return {**passo, "grafico": extra["grafico"]}


def _restante(inicio: float) -> float:
    return LIMITE_SEGUNDOS - (time.monotonic() - inicio)


def _ms(desde: float) -> int:
    return int((time.perf_counter() - desde) * 1000)


def _ferramenta(tc: dict, sessao: Sessao, passos: list[dict], resultados: list[str],
                restante: float) -> Iterator[dict]:
    """Roda uma tool_call; erros viram texto de volta para o LLM. Devolve o texto da ferramenta."""
    nome, bruto, desde = tc["nome"], tc["args"], time.perf_counter()
    args: dict = {}
    erro = None
    extra: dict = {}
    try:
        args = json.loads(bruto)
        if not isinstance(args, dict):
            raise TypeError("args")
        if nome in TIPOS:
            yield {"evento": "ferramenta_inicio", "id": tc["id"], "tipo": TIPOS[nome], "sql": args.get("sql", ""),
                   **({"codigo": args.get("codigo", "")} if nome == "rodar_python" else {})}
        texto, extra = _rodar(nome, args, sessao, min(30, restante))
        resultados.append(texto + chr(10) + bruto)  # o SQL/código também é fonte dos números
    except (ErroUsuario, KeyError, TypeError, json.JSONDecodeError) as e:
        texto = erro = f"Erro: {e}" if isinstance(e, ErroUsuario) else "Erro: argumentos inválidos."
        args = args if isinstance(args, dict) else {}
    passos.append(_passo(nome, args, extra, erro))
    yield {"evento": "ferramenta_fim", "id": tc["id"], "ms": _ms(desde), **({"erro": erro} if erro else extra)}
    return texto


def _lote(tool_calls: list[dict], sessao: Sessao, passos: list[dict], resultados: list[str],
          messages: list[dict], inicio: float, m: dict) -> Iterator[dict]:
    """Executa as tool_calls; levanta ErroUsuario se estourar chamadas ou tempo."""
    for tc in tool_calls:
        if m["ferramentas"] >= MAX_CHAMADAS:
            raise ErroUsuario(MSG_MAX_CHAMADAS)
        restante = _restante(inicio)
        if restante <= 0:
            raise ErroUsuario(MSG_LIMITE)
        m["ferramentas"] += 1
        texto = yield from _ferramenta(tc, sessao, passos, resultados, restante)
        messages.append({"role": "tool", "tool_call_id": tc["id"], "content": texto})


class _Retentor:
    """Segura o fim do texto para o marcador SUGESTOES: nunca ser transmitido (nem pela metade)."""

    def __init__(self) -> None:
        self.total, self.emitido = "", 0

    def alimentar(self, delta: str, final: bool = False) -> str:
        self.total += delta
        dobrado = self.total.translate(_DOBRA)
        achado = _MARCADOR.search(dobrado)
        if achado:
            corte = achado.start()
        else:
            corte = len(self.total)
            inicio_linha = dobrado.rfind(NL) + 1  # a última linha pode ser o começo do marcador
            if not final and MARCADOR.startswith(dobrado[inicio_linha:].lstrip(" *_#")):
                corte = inicio_linha
        corte = max(corte, self.emitido)
        saida, self.emitido = self.total[self.emitido:corte], corte
        return saida


def _separar(texto: str) -> tuple[str, list[str]]:
    """(corpo, sugestões): sugestões com dígitos são descartadas (os números não passariam pela conferência)."""
    achado = _MARCADOR.search(texto.translate(_DOBRA))
    corpo, resto = (texto, "") if achado is None else (texto[:achado.start()], texto[achado.end():])
    sugestoes = []
    for linha in resto.splitlines():
        item = linha.strip().lstrip("-*• ").strip()
        if item and linha.strip()[0] in "-*•" and not re.search(r"\d", item):
            sugestoes.append(item)
    return corpo.strip(), sugestoes[:3]


def _turno(llm: LlmFn, messages: list[dict], tools: list[dict] | None, restante: float, plano: bool,
           m: dict, tentativa: int) -> Iterator[dict]:
    """Uma chamada ao LLM: repassa rascunho/aguardando_cota e fecha com o evento llm. Devolve (texto, tool_calls)."""
    if m["llm"] >= MAX_CHAMADAS_LLM:
        raise ErroUsuario(MSG_MAX_LLM)
    m["llm"] += 1
    desde, ret, chamadas, usage, modelo = time.perf_counter(), _Retentor(), [], {}, config.LLM_MODEL
    for tipo, valor in llm(messages, tools, restante):
        if time.perf_counter() - desde > restante:  # o timeout do SDK é por leitura, não total
            raise ErroUsuario(MSG_LIMITE)
        if tipo == "texto":
            delta = ret.alimentar(valor)
            if delta and not plano:
                yield {"evento": "rascunho", "delta": delta, "tentativa": tentativa}
        elif tipo == "tool_call":
            chamadas.append(valor)
        elif tipo == "usage":
            usage = valor
        elif tipo == "modelo":
            modelo = valor
        elif tipo == "espera":
            yield {"evento": "aguardando_cota", "segundos": valor}
    delta = ret.alimentar("", final=True)
    if delta and not plano:
        yield {"evento": "rascunho", "delta": delta, "tentativa": tentativa}
    entrada, saida = usage.get("entrada"), usage.get("saida")
    m["modelo"] = modelo
    for chave, v in (("tokens_entrada", entrada), ("tokens_saida", saida)):
        if v is not None:
            m[chave] = (m[chave] or 0) + v
    fase = "plano" if plano else "ferramentas" if chamadas else "resposta"
    yield {"evento": "llm", "n": m["llm"], "fase": fase, "modelo": modelo, "ms": _ms(desde),
           "tokens_entrada": entrada, "tokens_saida": saida}
    return ret.total, chamadas


def _msg_assistente(texto: str, chamadas: list[dict]) -> dict:
    msg: dict = {"role": "assistant"}
    if texto or not chamadas:
        msg["content"] = texto
    if chamadas:
        msg["tool_calls"] = [
            {"id": c["id"], "type": "function", "function": {"name": c["nome"], "arguments": c["args"]},
             **({"extra_content": c["extra_content"]} if c.get("extra_content") else {})} for c in chamadas]
    return msg


def _guardar_turno(sessao: Sessao, pergunta: str, resposta: str, passos: list[dict], resultados: list[str]) -> None:
    sqls = [p["sql"] for p in passos if p.get("sql") and not p.get("erro")]
    resumo = f"Pergunta: {pergunta}\nResposta: {resposta}\nConsultas: {' | '.join(sqls)}"[:MAX_RESUMO]
    turno = {"pergunta": pergunta, "resposta": resposta, "sqls": sqls, "resumo": resumo,
             "resultados": chr(10).join(resultados)[:MAX_RESULTADOS]}
    sessao.historico = (sessao.historico + [turno])[-MAX_TURNOS:]
    sessao.turnos += 1


def _loop(pergunta: str, sessao: Sessao, llm: LlmFn, saida: dict, m: dict, inicio: float) -> Iterator[dict]:
    passos, resultados = saida["passos"], []
    anteriores = [t["resultados"] for t in sessao.historico]
    conversa = sessao.conversa
    historico = _historico(sessao)
    messages: list[dict] = [
        {"role": "system", "content": prompts.SISTEMA + _esquema(sessao)},
        *([{"role": "user", "content": historico}] if historico else []),
        {"role": "user", "content": pergunta}]
    texto_plano, _ = yield from _turno(
        llm, messages + [{"role": "user", "content": prompts.PLANO}], None, _restante(inicio), True, m, 1)
    texto_plano = _separar(texto_plano)[0]  # o modelo às vezes já responde no plano, com o bloco SUGESTOES:
    passos.append({"tipo": "plano", "texto": texto_plano})
    yield {"evento": "plano", "texto": texto_plano}
    messages += [{"role": "assistant", "content": texto_plano}, {"role": "user", "content": prompts.EXECUTE}]
    while True:
        restante = _restante(inicio)
        if restante <= 0:
            raise ErroUsuario(MSG_LIMITE)
        texto, chamadas = yield from _turno(llm, messages, TOOLS, restante, False, m, saida["reanalises"] + 1)
        messages.append(_msg_assistente(texto, chamadas))
        if chamadas:
            yield from _lote(chamadas, sessao, passos, resultados, messages, inicio, m)
            continue
        corpo, sugestoes = _separar(texto)
        if not corpo:
            raise ErroUsuario(MSG_VAZIA)
        faltam = numeros_nao_conferidos(corpo, resultados + anteriores, pergunta)
        tentativa = saida["reanalises"] + 1
        yield {"evento": "conferencia", "ok": not faltam, "falhas": faltam, "tentativa": tentativa}
        if faltam and saida["reanalises"] < MAX_REANALISES:
            saida["reanalises"] += 1
            passos.append({"tipo": "reanalise", "numeros": faltam})
            yield {"evento": "descartado", "tentativa": tentativa, "falhas": faltam}
            messages.append({"role": "user", "content": prompts.REANALISE.format(numeros=", ".join(faltam))})
            continue
        saida.update(resposta=corpo, sugestoes=sugestoes,
                     aviso=f"Alguns números não puderam ser conferidos: {', '.join(faltam)}" if faltam else None)
        guardou = sessao.conversa == conversa  # "nova conversa" no meio da resposta não recebe o turno antigo
        if guardou:
            _guardar_turno(sessao, pergunta, corpo, passos, resultados)
        yield {"evento": "resposta", "texto": corpo, "aviso": saida["aviso"], "reanalises": saida["reanalises"],
               "sugestoes": sugestoes, "conferido": not faltam, "turno": sessao.turnos if guardou else None}
        return


def executar(pergunta: str, sessao: Sessao, llm: LlmFn, saida: dict | None = None) -> Iterator[dict]:
    """Gera os eventos do contrato SSE (dicts {"evento": nome, **dados}). `saida`, se dada, recebe o dict final."""
    saida = saida if saida is not None else {}
    saida.update(passos=[], resposta="", reanalises=0, aviso=None, sugestoes=[], erro_tipo=None,
                 trace_id=uuid.uuid4().hex[:12])
    m = {"llm": 0, "ferramentas": 0, "tokens_entrada": None, "tokens_saida": None, "modelo": config.LLM_MODEL}
    inicio, desde = time.monotonic(), time.perf_counter()
    yield {"evento": "recebido", "modelo": config.LLM_MODEL, "turno": sessao.turnos + 1}
    erro = tipo = None
    try:
        yield from _loop(pergunta, sessao, llm, saida, m, inicio)
    except ErroUsuario as e:
        erro, tipo = str(e), _TIPO_ERRO.get(str(e), "validacao")
    except openai.RateLimitError:
        erro, tipo = MSG_COTA, "cota"
    except openai.BadRequestError:
        erro, tipo = MSG_RECUSADO, "requisicao"
    except openai.APIError:
        erro, tipo = MSG_INDISPONIVEL, "provedor"
    if erro:
        saida.update(resposta=erro, erro_tipo=tipo)
        yield {"evento": "erro", "mensagem": erro}
    yield {"evento": "metricas", "ms_total": _ms(desde), "chamadas_llm": m["llm"],
           "chamadas_ferramenta": m["ferramentas"], "tokens_entrada": m["tokens_entrada"],
           "tokens_saida": m["tokens_saida"], "reanalises": saida["reanalises"], "modelo": m["modelo"],
           "custo": "R$ 0 (plano gratuito)", "trace_id": saida["trace_id"], "versao_prompt": prompts.VERSAO}
    yield {"evento": "fim"}


def responder(pergunta: str, sessao: Sessao, llm: LlmFn) -> dict:
    saida: dict = {}
    for _ in executar(pergunta, sessao, llm, saida=saida):
        pass
    return saida


def _retry_after(erro: openai.RateLimitError) -> float | None:
    try:
        v = float(erro.response.headers.get("retry-after", ""))
    except (ValueError, AttributeError):
        return None
    return v if v > 0 else None


def _normalizar(stream: Any, modelo: str) -> Iterator[tuple]:
    """Pedaços da API -> pedaços normalizados. tool_call chega inteira (index None no Gemini): acumula por id."""
    chamadas: dict[str, dict] = {}
    atual, usage = None, None
    yield ("modelo", modelo)
    for pedaco in stream:
        if pedaco.usage:  # vem repetido: vale o último
            usage = {"entrada": pedaco.usage.prompt_tokens, "saida": pedaco.usage.completion_tokens}
        if not pedaco.choices:
            continue
        delta = pedaco.choices[0].delta
        if delta.content:
            yield ("texto", delta.content)
        for tc in delta.tool_calls or []:
            if tc.id:
                atual = tc.id
                chamadas.setdefault(atual, {"id": atual, "nome": "", "args": "", "extra_content": None})
            if atual is None:
                continue
            alvo = chamadas[atual]
            if tc.function and tc.function.name:
                alvo["nome"] = tc.function.name
            if tc.function and tc.function.arguments:
                alvo["args"] += tc.function.arguments
            extra = getattr(tc, "extra_content", None)
            if extra:
                alvo["extra_content"] = extra
    for c in chamadas.values():
        yield ("tool_call", c)
    if usage:
        yield ("usage", usage)


@functools.cache
def llm_padrao() -> LlmFn:
    cliente = OpenAI(api_key=config.LLM_API_KEY, base_url=config.LLM_BASE_URL)

    def chamar(messages: list[dict], tools: list[dict] | None, restante: float) -> Iterator[tuple]:
        limite, modelo, esperas = time.perf_counter() + restante, config.LLM_MODEL, 0
        extra = {"tools": tools} if tools else {}
        while True:
            try:
                api = cliente.with_options(timeout=max(1, limite - time.perf_counter()), max_retries=0)
                stream = api.chat.completions.create(model=modelo, messages=messages, stream=True,
                                                     stream_options={"include_usage": True}, **extra)
                break
            except openai.RateLimitError as e:
                espera = _retry_after(e) or ESPERAS_429[min(esperas, len(ESPERAS_429) - 1)]
                esperas += 1
                if esperas > len(ESPERAS_429) or espera >= limite - time.perf_counter():
                    raise
                yield ("espera", espera)
                _dormir(espera)
            except (openai.NotFoundError, openai.InternalServerError):
                if modelo == MODELO_RESERVA:
                    raise
                modelo = MODELO_RESERVA
        yield from _normalizar(stream, modelo)

    return chamar
