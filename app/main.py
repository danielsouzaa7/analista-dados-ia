"""API FastAPI. Endpoints síncronos (DuckDB e subprocess são bloqueantes; o FastAPI usa o threadpool)."""
import asyncio
import json
import logging
import math
import os
import statistics
import threading
import time
import uuid
from collections import Counter
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, StringConstraints

from app import agent, config, perfil, prompts, sessions
from app.errors import ErroUsuario

log = logging.getLogger("analista")
log_metricas = logging.getLogger("analista.metricas")
STATIC = config.RAIZ / "static"
GRAVACOES = config.DATA_DIR / "gravacoes"


def _teto_do_ambiente() -> int:
    try:
        return max(0, int(os.environ.get("DEMO_TETO_DIARIO", "80")))
    except ValueError:
        return 80


MAX_SESSOES = 200
LIMITE_DIARIO = _teto_do_ambiente()  # perguntas por dia, global (protege a cota gratuita do Gemini)
LIMITE_CORPO = 16 * 1024
FOLGA_MULTIPART = 64 * 1024
PAUSA_GRAVACAO = 0.4  # fração do tempo original
PAUSA_MAXIMA = 1.5  # segundos entre eventos
PAUSA_RASCUNHO = 0.03
MAX_EXECUCOES_GUARDADAS = 2000
_ID_GRAVACAO = r"^[a-z0-9_]+$"
_SUBSTANTIVOS = {"plano", "llm", "ferramenta_inicio", "rascunho"}  # depois disso não dá mais para trocar pela gravação
MSG_INTERNO = "Algo deu errado do nosso lado. Tente de novo."
_VAGAS = threading.BoundedSemaphore(1)  # 1 pergunta por vez, segurada até o fim do stream
_REPRODUCOES = threading.BoundedSemaphore(4)  # cada reprodução dorme numa thread do pool
PRAZO_SSE = agent.LIMITE_SEGUNDOS + 15  # cliente que para de ler não segura a vaga
_uso = {"dia": date.today(), "n": 0}  # em memória: reinicia com o processo e na virada do dia
_LOCK = threading.Lock()
_estat: dict = {}
_dormir = time.sleep
CABECALHOS = {
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self' https://cdnjs.cloudflare.com/ajax/libs/echarts/5.5.0/echarts.min.js; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src https://fonts.gstatic.com; "
        "img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; "
        "frame-ancestors 'self' https://huggingface.co https://*.hf.space"),  # sem X-Frame-Options: o HF usa iframe
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
}
CABECALHOS_SSE = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


class PostgresIn(BaseModel):
    url: str = Field(min_length=1, max_length=2000)


class PerguntaIn(BaseModel):
    sessao: str = Field(max_length=64)
    pergunta: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
    exemplo_id: str | None = Field(default=None, max_length=32, pattern=_ID_GRAVACAO)


class ConversaIn(BaseModel):
    sessao: str = Field(max_length=64)


class FeedbackIn(BaseModel):
    sessao: str = Field(max_length=64)
    turno: int = Field(ge=1, le=100_000)
    nota: Literal["util", "nao_util"]
    motivo: Literal["numeros_errados", "nao_entendeu", "grafico_ruim", "lento", "outro"] | None = None


class SessaoOut(BaseModel):
    sessao: str
    tabelas: list[dict]
    perguntas_sugeridas: list[str]


class ExemploOut(SessaoOut):
    perguntas: list[str]


class ExemploItem(BaseModel):
    id: str
    botao: str
    pergunta: str
    tipo_grafico: str | None
    depende_de: str | None
    seguranca: bool


def obter_llm() -> agent.LlmFn | None:
    """None sem chave: o exemplo ainda pode ser reproduzido da gravação (decide `perguntar`)."""
    return agent.llm_padrao() if config.LLM_API_KEY else None


def _saida(s: sessions.Sessao) -> dict:
    return {"sessao": s.id, "tabelas": s.tabelas, "perguntas_sugeridas": perfil.perguntas_sugeridas(s.tabelas)}


def _abrir_vaga_de_sessao() -> None:
    sessions.limpar_expiradas(MAX_SESSOES)
    if len(sessions.SESSOES) >= MAX_SESSOES:
        raise ErroUsuario("Servidor cheio agora. Tente de novo mais tarde.")


def _contar_pergunta() -> None:
    with _LOCK:
        hoje = date.today()
        if _uso["dia"] != hoje:
            _uso.update(dia=hoje, n=0)
        if _uso["n"] >= LIMITE_DIARIO:
            raise HTTPException(429, "O limite diário da demonstração acabou. Volte amanhã.")
        _uso["n"] += 1


def _restantes_hoje() -> int:
    with _LOCK:
        return LIMITE_DIARIO if _uso["dia"] != date.today() else max(0, LIMITE_DIARIO - _uso["n"])


def _corpo_grande_demais(request: Request) -> bool:
    """Recusa antes de ler: Content-Length acima do limite da rota ou corpo chunked sem tamanho."""
    if request.method != "POST":
        return False
    tamanho = request.headers.get("content-length")
    if tamanho is None:
        return "chunked" in request.headers.get("transfer-encoding", "").lower()
    limite = sessions.MAX_CSV_BYTES + FOLGA_MULTIPART if request.url.path == "/api/sessao/csv" else LIMITE_CORPO
    return not tamanho.isdigit() or int(tamanho) > limite


# ---------- métricas e log estruturado ----------

def _zerar_metricas() -> None:
    _estat.clear()
    _estat.update(desde=datetime.now(UTC).isoformat(timespec="seconds"), perguntas=0, execucoes=[],
                  util=0, nao_util=0, por_motivo=Counter(), erros=Counter())


def _percentil(ordenados: list[int], p: float) -> int | None:
    if p == 0.5:  # mesma mediana do scripts/avaliar.py
        return round(statistics.median(ordenados)) if ordenados else None
    return ordenados[min(len(ordenados) - 1, math.ceil(p * len(ordenados)) - 1)] if ordenados else None


def _registrar(linha: dict) -> None:
    """Uma linha JSON por pergunta (sem texto de pergunta, resposta ou dados) + agregado em memória."""
    log_metricas.info(json.dumps(linha, ensure_ascii=False))
    if linha["gravacao"]:
        return
    with _LOCK:
        _estat["perguntas"] += 1
        if linha["erro_tipo"]:
            _estat["erros"][linha["erro_tipo"]] += 1
        _estat["execucoes"] = (_estat["execucoes"] + [{**linha, "respondida": linha["erro_tipo"] is None}])[
            -MAX_EXECUCOES_GUARDADAS:]


def _linha_de_log(saida: dict, metricas: dict | None, resposta: dict | None, ms: int, gravacao: bool) -> dict:
    m = metricas or {}
    return {"trace_id": saida.get("trace_id") or uuid.uuid4().hex[:12], "ms": m.get("ms_total", ms),
            "chamadas_llm": m.get("chamadas_llm", 0), "chamadas_ferramenta": m.get("chamadas_ferramenta", 0),
            "tokens_entrada": m.get("tokens_entrada"), "tokens_saida": m.get("tokens_saida"),
            "conferido": bool(resposta and resposta["conferido"]), "reanalises": m.get("reanalises", 0),
            "erro_tipo": saida.get("erro_tipo"), "modelo": m.get("modelo", config.LLM_MODEL),
            "versao_prompt": prompts.VERSAO, "gravacao": gravacao}


def _media(valores: list[float], casas: int = 2) -> float | None:
    return round(sum(valores) / len(valores), casas) if valores else None


def _snapshot_metricas() -> dict:
    with _LOCK:
        execs = list(_estat["execucoes"])
        base = {"desde": _estat["desde"], "perguntas": _estat["perguntas"], "util": _estat["util"],
                "nao_util": _estat["nao_util"], "por_motivo": dict(_estat["por_motivo"]),
                "erros": dict(_estat["erros"])}
    certas = [e for e in execs if e["respondida"]]
    tokens = [e["tokens_entrada"] + e["tokens_saida"] for e in execs
              if e["tokens_entrada"] is not None and e["tokens_saida"] is not None]
    tempos = sorted(e["ms"] for e in certas)
    return {"desde": base["desde"], "perguntas": base["perguntas"], "respondidas": len(certas),
            "conferidas_pct": _media([100.0 * e["conferido"] for e in certas], 1),
            "reanalises_media": _media([e["reanalises"] for e in certas]),
            "p50_ms": _percentil(tempos, 0.5), "p90_ms": _percentil(tempos, 0.9),
            "tokens_medios": _media(tokens, 0),
            "feedback": {"util": base["util"], "nao_util": base["nao_util"], "por_motivo": base["por_motivo"]},
            "erros_por_tipo": base["erros"]}


# ---------- SSE e gravações ----------

def _sse(evento: dict) -> bytes:
    dados = {k: v for k, v in evento.items() if k != "evento"}
    return f"event: {evento['evento']}\ndata: {json.dumps(dados, ensure_ascii=False, default=str, allow_nan=False)}\n\n".encode()


def _ids_gravacoes() -> list[str]:
    if not GRAVACOES.is_dir():
        return []
    return sorted(p.stem for p in GRAVACOES.glob("*.jsonl") if p.stem and all(c in "abcdefghijklmnopqrstuvwxyz0123456789_" for c in p.stem))


def _gravacao(exemplo_id: str | None) -> Path | None:
    """Só ids que existem na pasta de gravações (o id já passou pelo regex): nunca um caminho livre."""
    if exemplo_id is None or exemplo_id not in _ids_gravacoes():
        return None  # sem gravação, a pergunta do exemplo roda ao vivo
    return GRAVACOES / f"{exemplo_id}.jsonl"


def _reproduzir(caminho: Path, pular_recebido: bool = False) -> Iterator[dict]:
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        try:
            ev = json.loads(linha)
        except ValueError:
            continue
        if not isinstance(ev, dict) or not isinstance(ev.get("evento"), str):
            continue
        if pular_recebido and ev["evento"] == "recebido":
            continue
        ms = ev.get("ms")
        pausa = ms / 1000 * PAUSA_GRAVACAO if isinstance(ms, (int, float)) and not isinstance(ms, bool) else 0
        _dormir(min(PAUSA_MAXIMA, max(pausa, PAUSA_RASCUNHO if ev["evento"] == "rascunho" else 0)))
        yield {**ev, "gravacao": True}


def _so_gravacao(caminho: Path) -> Iterator[bytes]:
    desde, ultimo = time.perf_counter(), None
    for ev in _reproduzir(caminho):
        ultimo = ev["evento"]
        yield _sse(ev)
    if ultimo != "fim":
        yield _sse({"evento": "fim", "gravacao": True})
    _registrar(_linha_de_log({}, None, None, int((time.perf_counter() - desde) * 1000), True))


def _liberador(vaga: threading.BoundedSemaphore | None = None):
    """Devolve a vaga uma única vez (no fim do stream ou, se ele nem começar, no fim da resposta)."""
    liberada = []

    def liberar() -> None:
        with _LOCK:
            if liberada:
                return
            liberada.append(True)
        (vaga or _VAGAS).release()

    return liberar


def _ao_vivo(corpo: PerguntaIn, sessao: sessions.Sessao, llm: agent.LlmFn, gravacao: Path | None,
             liberar) -> Iterator[bytes]:
    saida: dict = {}
    vistos: set[str] = set()
    resposta = metricas = None
    reproduzido = False
    desde = time.perf_counter()
    try:
        try:
            for ev in agent.executar(corpo.pergunta, sessao, llm, saida=saida):
                nome = ev["evento"]
                if nome == "erro" and ev["mensagem"] == agent.MSG_COTA and gravacao and not vistos & _SUBSTANTIVOS:
                    reproduzido = True  # cota do provedor esgotada: o exemplo cai na gravação
                    yield from map(_sse, _reproduzir(gravacao, pular_recebido=True))
                    return
                vistos.add(nome)
                resposta = ev if nome == "resposta" else resposta
                metricas = ev if nome == "metricas" else metricas
                yield _sse(ev)
        except Exception as exc:  # noqa: BLE001 - só o tipo vai para o log: a mensagem pode ter segredos
            log.error("Erro inesperado no stream: %s", type(exc).__name__)
            saida["erro_tipo"] = "interno"
            yield _sse({"evento": "erro", "mensagem": MSG_INTERNO})
            yield _sse({"evento": "fim"})
    except GeneratorExit:
        saida["erro_tipo"] = "cancelado"  # o cliente foi embora no meio: não conta como respondida
        raise
    finally:
        liberar()
        _registrar(_linha_de_log(saida, metricas, resposta, int((time.perf_counter() - desde) * 1000), reproduzido))


class _RespostaSSE(StreamingResponse):
    """O uvicorn espera o socket esvaziar sem prazo: o timeout aqui devolve a vaga a quem parou de ler."""

    def __init__(self, gerador: Iterator[bytes], liberar=None) -> None:
        super().__init__(gerador, media_type="text/event-stream", headers=CABECALHOS_SSE)
        self._liberar = liberar

    async def __call__(self, scope, receive, send) -> None:
        try:
            async with asyncio.timeout(PRAZO_SSE):
                await super().__call__(scope, receive, send)
        except TimeoutError:
            log.warning("Stream SSE encerrado pelo prazo")
        finally:
            if self._liberar:
                self._liberar()


def _resposta_sse(gerador: Iterator[bytes], liberar=None) -> StreamingResponse:
    return _RespostaSSE(gerador, liberar)


def _reproducao(gravacao: Path) -> StreamingResponse:
    if not _REPRODUCOES.acquire(blocking=False):
        raise HTTPException(429, "Muita gente usando agora. Tente de novo em um minuto.")
    return _resposta_sse(_so_gravacao(gravacao), _liberador(_REPRODUCOES))


def _exemplos() -> list[dict]:
    return json.loads((config.DATA_DIR / "perguntas.json").read_text(encoding="utf-8"))


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        sessions.limpar_tudo()
        _zerar_metricas()
        yield
        sessions.limpar_tudo()

    app = FastAPI(title="Analista de dados com IA", lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def protecoes(request: Request, call_next) -> JSONResponse:
        if _corpo_grande_demais(request):
            resposta = JSONResponse({"detail": "Corpo da requisição grande demais."}, status_code=413)
        else:
            try:
                resposta = await call_next(request)
            except Exception as exc:  # noqa: BLE001 - só o tipo vai para o log: a mensagem pode ter segredos
                log.error("Erro inesperado: %s", type(exc).__name__)
                resposta = JSONResponse({"detail": MSG_INTERNO}, status_code=500)
        resposta.headers.update(CABECALHOS)
        return resposta

    @app.exception_handler(ErroUsuario)
    def erro_usuario(_: Request, exc: ErroUsuario) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=400)

    @app.exception_handler(RequestValidationError)
    def entrada_invalida(_: Request, __: RequestValidationError) -> JSONResponse:  # o padrão ecoa o corpo
        return JSONResponse({"detail": "Entrada inválida. Confira os dados e tente de novo."}, status_code=422)

    @app.get("/")
    def pagina() -> FileResponse:
        return FileResponse(STATIC / "index.html")

    @app.get("/api/status")
    def status() -> dict:
        return {"restantes_hoje": _restantes_hoje(), "teto_diario": LIMITE_DIARIO, "modelo": config.LLM_MODEL,
                "gravacoes": _ids_gravacoes()}

    @app.get("/api/metricas")
    def metricas() -> dict:
        return _snapshot_metricas()

    @app.get("/api/exemplos", response_model=list[ExemploItem])
    def exemplos() -> list[dict]:
        return [{"id": e["id"], "botao": e["botao"], "pergunta": e["pergunta"], "tipo_grafico": e.get("tipo_grafico"),
                 "depende_de": e.get("depende_de"), "seguranca": e.get("tipo") == "seguranca"} for e in _exemplos()]

    @app.post("/api/sessao/csv", response_model=SessaoOut)
    def sessao_csv(arquivo: UploadFile = File(...)) -> dict:
        _abrir_vaga_de_sessao()
        conteudo = arquivo.file.read(sessions.MAX_CSV_BYTES + 1)
        return _saida(sessions.criar_de_csv(arquivo.filename or "dados.csv", conteudo))

    @app.post("/api/sessao/exemplo", response_model=ExemploOut)
    def sessao_exemplo() -> dict:
        _abrir_vaga_de_sessao()
        sessao = sessions.criar_de_csv("pedidos.csv", (config.DATA_DIR / "pedidos.csv").read_bytes())
        return {**_saida(sessao), "perguntas": [e["pergunta"] for e in _exemplos()]}

    @app.post("/api/sessao/postgres", response_model=SessaoOut)
    def sessao_postgres(corpo: PostgresIn) -> dict:
        _abrir_vaga_de_sessao()
        return _saida(sessions.criar_de_postgres(corpo.url))

    @app.post("/api/conversa/nova")
    def conversa_nova(corpo: ConversaIn) -> dict:
        sessao = sessions.obter(corpo.sessao)
        sessao.historico, sessao.turnos, sessao.turnos_avaliados = [], 0, set()
        sessao.conversa += 1
        return {"ok": True}

    @app.post("/api/feedback", status_code=204)
    def feedback(corpo: FeedbackIn) -> Response:
        sessao = sessions.obter(corpo.sessao)
        with _LOCK:
            if corpo.turno > sessao.turnos or corpo.turno in sessao.turnos_avaliados:
                raise ErroUsuario("Esse turno não existe ou já foi avaliado.")
            sessao.turnos_avaliados.add(corpo.turno)
            _estat[corpo.nota] += 1
            if corpo.motivo:
                _estat["por_motivo"][corpo.motivo] += 1
        return Response(status_code=204)

    @app.post("/api/perguntar")
    def perguntar(corpo: PerguntaIn, llm: agent.LlmFn | None = Depends(obter_llm)) -> StreamingResponse:
        sessao = sessions.obter(corpo.sessao)
        gravacao = _gravacao(corpo.exemplo_id)
        if llm is None:
            if gravacao:
                return _reproducao(gravacao)
            raise HTTPException(503, "O serviço de IA não está configurado (falta a LLM_API_KEY).")
        if not _VAGAS.acquire(blocking=False):
            if gravacao:
                return _reproducao(gravacao)
            raise HTTPException(429, "Muita gente usando agora. Tente de novo em um minuto.")
        try:
            _contar_pergunta()
        except HTTPException:
            _VAGAS.release()
            if gravacao:
                return _reproducao(gravacao)
            raise
        liberar = _liberador()
        return _resposta_sse(_ao_vivo(corpo, sessao, llm, gravacao, liberar), liberar)

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app


_zerar_metricas()
app = create_app()
