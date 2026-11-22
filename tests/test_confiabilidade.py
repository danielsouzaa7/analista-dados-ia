"""Confiabilidade: serviços externos fora do ar, falha no meio do stream, reinício e concorrência.

Complementa o que já existe em test_api.py, test_agent.py e test_python_tool.py (ver docs/confiabilidade.md).
Nada aqui chama o modelo real: o LLM e o cliente da API são falsos."""
import importlib
import io
import json
import re
import secrets
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import duckdb
import httpx
import openai
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import agent, main, sessions, sql_tool
from app import python_navegador as pn
from app.errors import ErroUsuario
from app.main import create_app, obter_llm
from app.sessions import Sessao
from tests.test_agent import (
    CSV,
    SQL_TOTAL,
    LlmFalso,
    _429,
    _erro_api,
    _usar_cliente,
    chamada,
    nomes,
    texto,
)
from tests.test_api import _eventos, _perguntar, _upload


@pytest.fixture(autouse=True)
def _estado_limpo(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr(main, "_uso", {"dia": date.today(), "n": 0})
    monkeypatch.setattr(main, "_VAGAS", threading.BoundedSemaphore(1))
    monkeypatch.setattr(main, "GRAVACOES", tmp_path / "gravacoes")
    main._zerar_metricas()
    pn._PENDENTES.clear()


@pytest.fixture
def s() -> Sessao:
    return sessions.criar_de_csv("vendas.csv", CSV)


def _llm_falso_do_app(llm) -> TestClient:
    app = create_app()
    app.dependency_overrides[obter_llm] = lambda: llm
    return TestClient(app, raise_server_exceptions=False)


# ---------- Gemini indisponível ----------

def test_gemini_fora_do_ar_por_erro_de_rede_vira_mensagem_amigavel(monkeypatch: pytest.MonkeyPatch, s: Sessao) -> None:
    falha = openai.APIConnectionError(request=httpx.Request("POST", "https://exemplo.invalido"))
    cliente = _usar_cliente(monkeypatch, [falha])
    saida: dict = {}
    evs = list(agent.executar("Qual?", s, agent.llm_padrao(), saida=saida))
    erro = next(e for e in evs if e["evento"] == "erro")["mensagem"]
    assert erro == agent.MSG_INDISPONIVEL and saida["erro_tipo"] == "provedor"
    assert not re.search(r"\d|Traceback|httpx|openai", erro)  # sem número, sem pilha, sem nome de biblioteca
    assert "resposta" not in nomes(evs) and nomes(evs)[-2:] == ["metricas", "fim"]
    assert len(cliente.pedidos) == 1  # erro de rede não entra em laço de retentativa
    assert s.historico == [] and s.turnos == 0


@pytest.mark.parametrize("status", [502, 504])
def test_5xx_persistente_nos_dois_modelos_vira_indisponivel_sem_numero(
        monkeypatch: pytest.MonkeyPatch, s: Sessao, status: int) -> None:
    _usar_cliente(monkeypatch, [_erro_api(openai.InternalServerError, status)] * 2)
    r = agent.responder("Qual?", s, agent.llm_padrao())
    assert r["resposta"] == agent.MSG_INDISPONIVEL and r["erro_tipo"] == "provedor"
    assert "secreta" not in r["resposta"] and not re.search(r"\d", r["resposta"])


def test_429_persistente_gasta_as_duas_esperas_e_vira_erro_de_cota(monkeypatch: pytest.MonkeyPatch, s: Sessao) -> None:
    esperas: list[float] = []
    cliente = _usar_cliente(monkeypatch, [_429("")] * 5)  # sem retry-after: valem as esperas padrão
    monkeypatch.setattr(agent, "_dormir", esperas.append)
    saida: dict = {}
    evs = list(agent.executar("Qual?", s, agent.llm_padrao(), saida=saida))
    assert esperas == [5.0, 10.0] and len(cliente.pedidos) == 3
    assert [e["segundos"] for e in evs if e["evento"] == "aguardando_cota"] == [5.0, 10.0]
    assert saida["erro_tipo"] == "cota" and saida["resposta"] == agent.MSG_COTA


# ---------- falha parcial no meio do stream ----------

def _stream_que_quebra(parcial: str, erro: Exception):
    def llm(messages, tools, restante):
        yield ("texto", parcial)
        raise erro
    return llm


def test_falha_no_meio_do_stream_do_llm_entrega_erro_e_nao_corrompe_o_estado(s: Sessao) -> None:
    falha = openai.APIConnectionError(request=httpx.Request("POST", "https://exemplo.invalido"))
    llm = _stream_que_quebra("O total é 3", falha)
    evs = list(agent.executar("Qual?", s, llm))
    assert "resposta" not in nomes(evs) and nomes(evs)[-3:] == ["erro", "metricas", "fim"]
    assert s.historico == [] and s.turnos == 0  # o turno pela metade não entra na memória
    ok = agent.responder("Qual?", s, LlmFalso([texto("plano"), chamada("consultar_banco", sql=SQL_TOTAL),
                                                texto("O total é 350.")]))
    assert ok["resposta"] == "O total é 350." and s.turnos == 1


class _QuebraUmaVez:
    """Primeira pergunta: o socket cai no meio do stream (erro do httpx, que o SDK não converte). Depois: normal."""

    def __init__(self) -> None:
        self.quebrou = False
        self.sadio = LlmFalso([texto("plano"), chamada("consultar_banco", sql="SELECT sum(valor) AS t FROM dados"),
                               texto("O total é 350.")])

    def __call__(self, messages, tools, restante):
        if self.quebrou:
            return self.sadio(messages, tools, restante)
        self.quebrou = True
        return _stream_que_quebra("parcial", httpx.ReadError("conexão com 10.0.0.9 caiu"))(messages, tools, restante)


def test_stream_sse_com_falha_no_meio_termina_em_erro_e_fim_e_a_sessao_segue_usavel(
        caplog: pytest.LogCaptureFixture) -> None:
    c = _llm_falso_do_app(_QuebraUmaVez())
    sid = _upload(c)["sessao"]
    r = _perguntar(c, sid)
    evs = _eventos(r)
    assert [n for n, _ in evs][-2:] == ["erro", "fim"] and "resposta" not in [n for n, _ in evs]
    assert "10.0.0.9" not in r.text and "10.0.0.9" not in caplog.text and "ReadError" not in r.text
    assert "Erro inesperado no stream: ReadError" in caplog.text  # o tipo vai para o log; a mensagem (com o IP), não
    assert main._estat["erros"] == {"interno": 1}
    assert main._VAGAS.acquire(blocking=False)  # a vaga voltou
    main._VAGAS.release()
    depois = dict(_eventos(_perguntar(c, sid, "De novo?")))
    assert depois["resposta"]["texto"] == "O total é 350." and depois["resposta"]["turno"] == 1


# ---------- Postgres indisponível ----------

URL_PG = "postgresql://usuario:senhaSecreta123@db.exemplo.invalido:5432/banco"


def _sessao_pg() -> Sessao:
    return Sessao(id="pg", tipo="postgres", pg_url=URL_PG,
                  tabelas=[{"nome": "t", "colunas": [{"nome": "v", "tipo": "INTEGER"}], "linhas": None}])


def test_postgres_que_deixa_de_responder_antes_da_consulta_vira_erro_sem_segredo(monkeypatch: pytest.MonkeyPatch) -> None:
    def cai(url: str):  # o `abrir` real roda; a queda acontece embaixo, com a URL e a senha na mensagem do driver
        raise duckdb.IOException(f"connection to {URL_PG} failed: password authentication failed for senhaSecreta123")

    monkeypatch.setattr(sql_tool, "_abrir_postgres", cai)
    with pytest.raises(ErroUsuario, match="Não consegui conectar aos dados") as e:
        sql_tool.executar(_sessao_pg(), "SELECT 1")
    assert "senhaSecreta123" not in str(e.value) and "exemplo.invalido" not in str(e.value) and e.value.__cause__ is None
    llm = LlmFalso([texto("plano"), chamada("consultar_banco", sql="SELECT 1"), texto("Não consegui consultar o banco.")])
    r = agent.responder("Qual?", _sessao_pg(), llm)
    assert r["passos"][1]["erro"].startswith("Erro: Não consegui conectar")
    assert r["resposta"] == "Não consegui consultar o banco." and r["erro_tipo"] is None
    assert "senhaSecreta123" not in str(r) and "senhaSecreta123" not in str(llm.chamadas)


def test_postgres_que_cai_no_meio_da_consulta_nao_vaza_a_url(monkeypatch: pytest.MonkeyPatch) -> None:
    class ConexaoQueCai:
        def execute(self, sql):
            raise duckdb.IOException(f"connection to server lost ({URL_PG})")

        def interrupt(self) -> None:
            pass

        def close(self) -> None:
            self.fechada = True

    con = ConexaoQueCai()
    monkeypatch.setattr(sql_tool, "abrir", lambda sessao: con)
    with pytest.raises(ErroUsuario) as e:
        sql_tool.executar(_sessao_pg(), "SELECT 1")
    assert "senhaSecreta123" not in str(e.value) and URL_PG not in str(e.value) and "***" in str(e.value)
    assert con.fechada  # a conexão é fechada mesmo com a queda


def test_perfil_do_postgres_que_cai_nao_derruba_a_sessao(monkeypatch: pytest.MonkeyPatch) -> None:
    def cai(_):
        raise ErroUsuario("fora do ar")

    monkeypatch.setattr(sql_tool, "abrir", cai)
    sessao = _sessao_pg()
    sessions._perfilar_postgres(sessao)  # não levanta
    assert sessao.grounding == "" and "perfil" not in sessao.tabelas[0]


# ---------- reinício do app ----------

def test_reinicio_perde_as_sessoes_e_o_cliente_recebe_sessao_expirada() -> None:
    app = create_app()
    app.dependency_overrides[obter_llm] = lambda: LlmFalso([texto("plano"), texto("Oi.")])
    with TestClient(app) as antes:
        sid = _upload(antes)["sessao"]
        pasta = sessions.SESSOES[sid].caminho_db.parent
        assert pasta.exists() and dict(_eventos(_perguntar(antes, sid)))["resposta"]
        assert main._estat["perguntas"] == 1
    with TestClient(app) as depois:  # novo processo: o lifespan limpa o estado em memória e o disco
        assert not pasta.exists() and sessions.SESSOES == {} and main._estat["perguntas"] == 0
        r = _perguntar(depois, sid)
        assert r.status_code == 400 and r.json()["detail"] == "Sessão expirada. Carregue seus dados de novo."
        assert depois.post("/api/conversa/nova", json={"sessao": sid}).status_code == 400
        voto = depois.post("/api/feedback", json={"sessao": sid, "turno": 1, "nota": "util"})
        assert voto.status_code == 400
        assert depois.get("/api/status").status_code == 200
        assert _upload(depois)["sessao"] != sid  # e o app volta a aceitar dados


# ---------- concorrência ----------

def test_duas_perguntas_ao_mesmo_tempo_so_uma_passa_e_a_vaga_volta() -> None:
    dentro, solta = threading.Event(), threading.Event()
    roteiro = LlmFalso([texto("plano"), texto("Sem números.")])

    def llm(messages, tools, restante):
        if not dentro.is_set():
            dentro.set()
            assert solta.wait(10)  # segura a primeira pergunta no meio da execução
        return roteiro(messages, tools, restante)

    c = _llm_falso_do_app(llm)
    sid = _upload(c)["sessao"]
    outro = _upload(c)["sessao"]
    primeira: list = []
    t = threading.Thread(target=lambda: primeira.append(_perguntar(c, sid)))
    t.start()
    try:
        assert dentro.wait(10)
        segunda = _perguntar(c, outro)
        assert segunda.status_code == 429 and "Muita gente" in segunda.json()["detail"]
    finally:
        solta.set()
        t.join(15)
    assert primeira[0].status_code == 200 and dict(_eventos(primeira[0]))["resposta"]
    assert main._VAGAS.acquire(blocking=False)  # exatamente 1 vaga, devolvida no fim
    main._VAGAS.release()


class _DictLento(dict):
    """Leitura com uma pausa: alarga a janela entre "ler" e "gravar" para que a falta do lock sempre apareça."""

    def __getitem__(self, chave):
        time.sleep(0.001)
        return super().__getitem__(chave)

    def get(self, chave, padrao=None):
        time.sleep(0.001)
        return super().get(chave, padrao)


class _SetLento(set):
    """O 1º que pergunta "já votou?" espera até 1 s por um 2º (um Barrier de 2): sem lock os dois passam juntos pela
    checagem e votam; com lock o 2º só chega depois, o Barrier estoura o prazo e a espera não se repete."""

    def __init__(self) -> None:
        super().__init__()
        self._par = threading.Barrier(2, timeout=1)

    def __contains__(self, item) -> bool:
        achou = super().__contains__(item)  # lê antes de esperar: o 2º também lê "não votou" antes do 1º gravar
        try:
            self._par.wait()
        except threading.BrokenBarrierError:
            pass
        return achou


class _SecretsLento:
    """A comparação do nonce fica entre "a pendente ainda está livre" e "gravar o resultado": é onde a corrida mora."""

    @staticmethod
    def compare_digest(a: bytes, b: bytes) -> bool:
        time.sleep(0.02)
        return secrets.compare_digest(a, b)


def test_teto_diario_sob_concorrencia_nao_passa_do_limite(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main, "LIMITE_DIARIO", 10)
    monkeypatch.setattr(main, "_uso", _DictLento(dia=date.today(), n=0))

    def tenta(_: int) -> bool:
        try:
            main._contar_pergunta()
            return True
        except HTTPException:
            return False

    with ThreadPoolExecutor(32) as pool:
        aceitas = sum(pool.map(tenta, range(100)))
    assert aceitas == 10 and dict.__getitem__(main._uso, "n") == 10


def test_voto_duplicado_simultaneo_conta_uma_vez() -> None:
    # pelo HTTP, com threads: o TestClient atende cada requisição na própria thread e não serializa a corrida
    c = _llm_falso_do_app(LlmFalso([]))
    sid = _upload(c)["sessao"]
    sessao = sessions.SESSOES[sid]
    sessao.turnos, sessao.turnos_avaliados = 1, _SetLento()

    def vota(_: int) -> int:
        return c.post("/api/feedback", json={"sessao": sid, "turno": 1, "nota": "util"}).status_code

    with ThreadPoolExecutor(10) as pool:
        codigos = list(pool.map(vota, range(10)))
    assert codigos.count(204) == 1 and codigos.count(400) == 9 and main._estat["util"] == 1


def test_resultado_de_python_entregue_em_paralelo_vale_uma_vez(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pn, "_PENDENTES", _DictLento())
    g = pn.executor("s1")("t1", "print(1)", "a,b", 30)
    nonce = next(g)["nonce"]
    monkeypatch.setattr(pn, "secrets", _SecretsLento)

    def entrega(i: int) -> bool | str:
        try:
            return pn.entregar("s1", "t1", nonce, f"saida{i}", None)
        except KeyError:  # sem lock, o 2º a chegar apaga uma pendente que já não existe
            return "KeyError"

    with ThreadPoolExecutor(16) as pool:
        resultados = list(pool.map(entrega, range(16)))
    g.close()
    assert resultados.count(True) == 1 and resultados.count("KeyError") == 0 and len(pn._PENDENTES) == 0


# ---------- observabilidade ----------

def test_log_de_metricas_sai_no_stream_do_processo_em_producao(monkeypatch: pytest.MonkeyPatch) -> None:
    # sem handler próprio e com o root em WARNING, a linha JSON por pergunta (INFO) sumia no Render
    buffer = io.StringIO()
    assert main.log.handlers
    monkeypatch.setattr(main.log.handlers[0], "stream", buffer)
    c = _llm_falso_do_app(LlmFalso([texto("plano"), texto("Oi.")]))
    _perguntar(c, _upload(c)["sessao"], "Pergunta secreta do visitante?")
    linha = next(x for x in buffer.getvalue().splitlines() if " INFO analista.metricas " in x)
    dados = json.loads(linha.split(" INFO analista.metricas ", 1)[1])
    assert dados["erro_tipo"] is None and dados["chamadas_llm"] == 2 and len(dados["trace_id"]) == 12
    assert "secreta" not in buffer.getvalue()  # a pergunta não vai para o log


def test_recarregar_o_modulo_nao_duplica_o_handler_do_log() -> None:
    # reload simula o reimport (ex.: --reload do uvicorn): sem a guarda `if not log.handlers`, cada um somaria um handler
    foto, handlers = dict(main.__dict__), list(main.log.handlers)
    try:
        importlib.reload(main)
        importlib.reload(main)
        assert len(main.log.handlers) == 1
    finally:
        main.__dict__.update(foto)  # devolve as funções e globais originais aos outros testes
        main.log.handlers[:] = handlers
