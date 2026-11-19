import json
import logging
import os
import threading
from datetime import date, timedelta
from pathlib import Path

import openai
import pytest
from fastapi.testclient import TestClient

from app import agent, config, main, sessions
from app.main import create_app, obter_llm
from tests.test_agent import LlmFalso, _erro_api, chamada, texto

CSV = b"regiao,valor\nNorte,100\nSul,250\n"


@pytest.fixture(autouse=True)
def _zera_cota(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(main, "_uso", {"dia": date.today(), "n": 0})
    monkeypatch.setattr(main, "_VAGAS", threading.BoundedSemaphore(1))
    monkeypatch.setattr(main, "GRAVACOES", tmp_path / "gravacoes")
    monkeypatch.setattr(main, "_dormir", lambda _: None)
    main._zerar_metricas()


@pytest.fixture
def client() -> TestClient:
    app = create_app()
    app.dependency_overrides[obter_llm] = lambda: LlmFalso([
        texto("plano"), chamada("consultar_banco", sql="SELECT sum(valor) AS t FROM dados"),
        texto("O total é 350.")])
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


def _upload(c: TestClient) -> dict:
    r = c.post("/api/sessao/csv", files={"arquivo": ("dados.csv", CSV, "text/csv")})
    assert r.status_code == 200, r.text
    return r.json()


def test_pagina_inicial(client: TestClient) -> None:
    assert client.get("/").status_code == 200


def _perguntar(c: TestClient, sessao: str, pergunta: str = "Qual o total?", **extra: object):
    return c.post("/api/perguntar", json={"sessao": sessao, "pergunta": pergunta, **extra})


def _eventos(r) -> list[tuple[str, dict]]:
    """Lê o corpo SSE: lista de (evento, dados)."""
    saida = []
    for bloco in r.text.strip().split(chr(10) * 2):
        linha_evento, linha_dados = bloco.split(chr(10))
        assert linha_evento.startswith("event: ") and linha_dados.startswith("data: ")
        saida.append((linha_evento[7:], json.loads(linha_dados[6:])))
    return saida


def test_upload_e_pergunta_em_streaming(client: TestClient) -> None:
    s = _upload(client)
    assert s["tabelas"][0]["nome"] == "dados" and s["tabelas"][0]["linhas"] == 2
    r = _perguntar(client, s["sessao"])
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    assert r.headers["cache-control"] == "no-cache" and r.headers["x-accel-buffering"] == "no"
    evs = _eventos(r)
    nomes = [n for n, _ in evs]
    assert nomes[0] == "recebido" and nomes[-1] == "fim" and "resposta" in nomes and "metricas" in nomes
    resposta = dict(evs)["resposta"]
    assert resposta["texto"] == "O total é 350." and resposta["conferido"] is True
    assert "content-security-policy" in r.headers  # o middleware continua valendo no stream


def test_sessao_traz_perfil_e_perguntas_sugeridas(client: TestClient) -> None:
    s = _upload(client)
    assert [c["nome"] for c in s["tabelas"][0]["perfil"]["colunas"]] == ["regiao", "valor"]
    assert isinstance(s["perguntas_sugeridas"], list) and 1 <= len(s["perguntas_sugeridas"]) <= 4


def test_exemplo_usa_pedidos_e_traz_perguntas(client: TestClient) -> None:
    r = client.post("/api/sessao/exemplo")
    assert r.status_code == 200 and len(r.json()["perguntas"]) >= 6
    assert r.json()["tabelas"][0]["nome"] == "pedidos" and r.json()["tabelas"][0]["linhas"] > 1000
    assert r.json()["tabelas"][0]["perfil"]["colunas"] and len(r.json()["perguntas_sugeridas"]) <= 4


def test_exemplos_nao_expoe_gabarito(client: TestClient) -> None:
    r = client.get("/api/exemplos")
    assert r.status_code == 200
    itens = r.json()
    assert len(itens) >= 6
    assert all(set(i) == {"id", "botao", "pergunta", "tipo_grafico", "depende_de", "seguranca"} for i in itens)
    assert any(i["seguranca"] for i in itens) and any(i["depende_de"] for i in itens)
    assert "numeros_chave" not in r.text and "esperado" not in r.text


def test_sessao_inexistente(client: TestClient) -> None:
    r = client.post("/api/perguntar", json={"sessao": "nada", "pergunta": "Oi?"})
    assert r.status_code == 400 and "Sessão expirada" in r.json()["detail"]


@pytest.mark.parametrize("pergunta", ["", "a" * 501])
def test_pergunta_invalida(client: TestClient, pergunta: str) -> None:
    s = _upload(client)
    assert client.post("/api/perguntar", json={"sessao": s["sessao"], "pergunta": pergunta}).status_code == 422


def test_csv_grande_recusado(client: TestClient) -> None:
    grande = b"a\n" + b"1\n" * (11 * 1024 * 1024)
    r = client.post("/api/sessao/csv", files={"arquivo": ("g.csv", grande, "text/csv")})
    assert r.status_code == 413  # recusado pelo Content-Length, antes de ler o corpo
    pouco_acima = b'a' + chr(10).encode() + (b'1' + chr(10).encode()) * (sessions.MAX_CSV_BYTES // 2)
    r = client.post("/api/sessao/csv", files={"arquivo": ("g.csv", pouco_acima, "text/csv")})
    assert r.status_code == 400 and "20 MB" in r.json()["detail"]


def test_csv_ilegivel_recusado(client: TestClient) -> None:
    r = client.post("/api/sessao/csv", files={"arquivo": ("v.csv", b"", "text/csv")})
    assert r.status_code == 400 and "Não consegui ler" in r.json()["detail"]


def test_url_postgres_invalida_nao_vaza(client: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    url = "postgresql://usuario:senhaSecreta123@127.0.0.1:1/banco"
    with caplog.at_level(logging.DEBUG):
        r = client.post("/api/sessao/postgres", json={"url": url})
    assert r.status_code == 400
    assert "senhaSecreta123" not in r.text and url not in r.text
    assert "senhaSecreta123" not in caplog.text


def test_sem_chave_responde_503(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "LLM_API_KEY", "")
    c = TestClient(create_app())
    s = _upload(c)
    r = c.post("/api/perguntar", json={"sessao": s["sessao"], "pergunta": "Oi?"})
    assert r.status_code == 503 and "LLM_API_KEY" in r.json()["detail"]


def test_erro_inesperado_no_meio_vira_erro_e_fim(client: TestClient, monkeypatch: pytest.MonkeyPatch,
                                                  caplog: pytest.LogCaptureFixture) -> None:
    def quebra(*a, **k):
        raise RuntimeError("segredo interno")
        yield  # noqa: B901 - torna a função um gerador

    monkeypatch.setattr(agent, "executar", quebra)
    s = _upload(client)
    with caplog.at_level(logging.DEBUG):
        r = _perguntar(client, s["sessao"], "Oi?")
    evs = _eventos(r)
    assert [n for n, _ in evs][-2:] == ["erro", "fim"] and "segredo" not in r.text and "segredo" not in caplog.text
    assert main._VAGAS.acquire(blocking=False)  # vaga liberada mesmo com falha


def _pergunta(c: TestClient):
    s = _upload(c)
    return _perguntar(c, s["sessao"])


def test_excecao_nao_vaza_nem_no_log(caplog: pytest.LogCaptureFixture) -> None:
    app = create_app()

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("postgresql://u:SENHA@h/db")

    with caplog.at_level(logging.DEBUG):
        r = TestClient(app).get("/boom")  # raise_server_exceptions=True: o middleware não pode relançar
    assert r.status_code == 500 and r.json() == {"detail": "Algo deu errado do nosso lado. Tente de novo."}
    assert "SENHA" not in caplog.text and "SENHA" not in r.text


def test_422_nao_ecoa_entrada(client: TestClient) -> None:
    r = client.post("/api/sessao/postgres", json={"url": "postgresql://u:SENHAFALSA@h/" + "x" * 3000})
    assert r.status_code == 422 and "SENHAFALSA" not in r.text
    assert r.json() == {"detail": "Entrada inválida. Confira os dados e tente de novo."}


def test_corpo_json_grande_recusado(client: TestClient) -> None:
    r = client.post("/api/perguntar", content=b"x" * (16 * 1024 + 1), headers={"content-type": "application/json"})
    assert r.status_code == 413 and "grande" in r.json()["detail"]


def test_csv_acima_do_limite_recusado_pelo_cabecalho(client: TestClient) -> None:
    r = client.post("/api/sessao/csv", content=b"x", headers={
        "content-length": str(sessions.MAX_CSV_BYTES + 64 * 1024 + 1), "content-type": "text/csv"})
    assert r.status_code == 413


def test_post_chunked_recusado(client: TestClient) -> None:
    r = client.post("/api/perguntar", content=iter([b'{"sessao": "a"}']))
    assert r.status_code == 413


def test_sessao_longa_e_pergunta_so_espacos(client: TestClient) -> None:
    s = _upload(client)
    assert client.post("/api/perguntar", json={"sessao": "a" * 65, "pergunta": "Oi?"}).status_code == 422
    assert client.post("/api/perguntar", json={"sessao": s["sessao"], "pergunta": "   "}).status_code == 422


def test_sem_vaga_responde_429(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    s = _upload(client)
    monkeypatch.setattr(main, "_VAGAS", threading.BoundedSemaphore(0))
    r = _perguntar(client, s["sessao"], "Oi?")
    assert r.status_code == 429 and r.json()["detail"] == "Muita gente usando agora. Tente de novo em um minuto."


def test_vaga_so_e_devolvida_no_fim_do_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    durante: list[bool] = []

    class Espiao(LlmFalso):
        def __call__(self, *a, **k):
            livre = main._VAGAS.acquire(blocking=False)
            durante.append(livre)
            if livre:
                main._VAGAS.release()
            return super().__call__(*a, **k)

    app = create_app()
    app.dependency_overrides[obter_llm] = lambda: Espiao([texto("plano"), texto("Oi.")])
    c = TestClient(app)
    s = _upload(c)
    assert _perguntar(c, s["sessao"], "Oi?").status_code == 200
    assert durante and not any(durante)  # segurada durante todo o stream
    assert main._VAGAS.acquire(blocking=False)  # e livre depois
    main._VAGAS.release()
    assert _perguntar(c, s["sessao"], "Oi de novo?").status_code == 200  # nova pergunta consegue vaga


def test_teto_diario_e_reinicio(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main, "_uso", {"dia": date.today(), "n": main.LIMITE_DIARIO})
    r = _pergunta(client)
    assert r.status_code == 429 and r.json()["detail"] == "O limite diário da demonstração acabou. Volte amanhã."
    assert main._VAGAS.acquire(blocking=False)  # vaga devolvida
    main._VAGAS.release()
    monkeypatch.setattr(main, "_uso", {"dia": date.today() - timedelta(days=1), "n": main.LIMITE_DIARIO})
    assert _pergunta(client).status_code == 200


def test_teto_diario_vem_do_ambiente() -> None:
    assert main.LIMITE_DIARIO == int(os.environ.get("DEMO_TETO_DIARIO", "80"))


@pytest.mark.parametrize("rota,kw", [
    ("/api/sessao/exemplo", {}),
    ("/api/sessao/csv", {"files": {"arquivo": ("d.csv", CSV, "text/csv")}}),
    ("/api/sessao/postgres", {"json": {"url": "postgresql://u:p@h/db"}}),
])
def test_servidor_cheio(client: TestClient, monkeypatch: pytest.MonkeyPatch, rota: str, kw: dict) -> None:
    monkeypatch.setattr(main, "MAX_SESSOES", 0)
    r = client.post(rota, **kw)
    assert r.status_code == 400 and r.json()["detail"] == "Servidor cheio agora. Tente de novo mais tarde."


def test_lotado_libera_vaga_da_sessao_sem_pergunta(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main, "MAX_SESSOES", 1)
    sessions.SESSOES.clear()
    velha = client.post("/api/sessao/exemplo").json()["sessao"]
    sessions.SESSOES[velha].criada -= sessions.IDADE_MINIMA + 1  # só sessão parada há mais de 150 s é expulsa
    nova = client.post("/api/sessao/exemplo")
    assert nova.status_code == 200 and velha not in sessions.SESSOES


def test_upload_simultaneo_nao_passa_do_teto_de_sessoes(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from concurrent.futures import ThreadPoolExecutor
    monkeypatch.setattr(main, "MAX_SESSOES", 5)
    sessions.SESSOES.clear()
    with ThreadPoolExecutor(20) as pool:
        codigos = list(pool.map(lambda _: client.post("/api/sessao/exemplo").status_code, range(20)))
    assert len(sessions.SESSOES) <= 5 and codigos.count(200) == len(sessions.SESSOES)


def test_cabecalhos_de_seguranca(client: TestClient) -> None:
    h = client.get("/").headers
    assert h["x-content-type-options"] == "nosniff" and h["referrer-policy"] == "no-referrer"
    assert "frame-ancestors 'self' https://huggingface.co https://*.hf.space" in h["content-security-policy"]
    csp = h["content-security-policy"]
    assert "script-src 'self' https://cdnjs.cloudflare.com" in csp
    assert "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com" in csp
    assert "font-src https://fonts.gstatic.com" in csp
    assert "x-frame-options" not in h


@pytest.mark.parametrize("rota", ["/docs", "/redoc", "/openapi.json"])
def test_docs_desligados(client: TestClient, rota: str) -> None:
    assert client.get(rota).status_code == 404


def test_lifespan_limpa_sessoes_ao_sair() -> None:
    with TestClient(create_app()) as c:
        _upload(c)
        assert sessions.SESSOES
    assert not sessions.SESSOES


# ---------- status, conversa nova, feedback, métricas ----------

def _gravar(nome: str, eventos: list[dict]) -> None:
    main.GRAVACOES.mkdir(parents=True, exist_ok=True)
    (main.GRAVACOES / f"{nome}.jsonl").write_text(
        "\n".join(json.dumps(e, ensure_ascii=False) for e in eventos) + "\n", encoding="utf-8")


GRAVACAO = [{"evento": "recebido", "modelo": "m", "turno": 1}, {"evento": "llm", "n": 1, "fase": "plano", "ms": 1000},
            {"evento": "plano", "texto": "p"}, {"evento": "rascunho", "delta": "Olá", "tentativa": 1},
            {"evento": "resposta", "texto": "Olá", "aviso": None, "reanalises": 0, "sugestoes": [],
             "conferido": True, "turno": 1}, {"evento": "metricas", "ms_total": 1}, {"evento": "fim"}]


def test_status(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _gravar("exemplo_a", GRAVACAO)
    (main.GRAVACOES / "Maiuscula.jsonl").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(main, "_uso", {"dia": date.today(), "n": 5})
    r = client.get("/api/status")
    assert r.status_code == 200
    assert r.json() == {"restantes_hoje": main.LIMITE_DIARIO - 5, "teto_diario": main.LIMITE_DIARIO,
                        "modelo": config.LLM_MODEL, "gravacoes": ["exemplo_a"]}


def test_status_sem_pasta_de_gravacoes(client: TestClient) -> None:
    assert client.get("/api/status").json()["gravacoes"] == []


def test_conversa_nova_limpa_historico(client: TestClient) -> None:
    s = _upload(client)
    assert _perguntar(client, s["sessao"]).status_code == 200
    sessao = sessions.SESSOES[s["sessao"]]
    assert len(sessao.historico) == 1 and sessao.turnos == 1
    r = client.post("/api/conversa/nova", json={"sessao": s["sessao"]})
    assert r.status_code == 200 and sessao.historico == [] and sessao.turnos == 0
    assert client.post("/api/conversa/nova", json={"sessao": "nada"}).status_code == 400


def test_memoria_entre_perguntas_pela_api(client: TestClient) -> None:
    s = _upload(client)
    _perguntar(client, s["sessao"], "Qual o total?")
    evs = _eventos(_perguntar(client, s["sessao"], "E agora?"))
    assert evs[0][1]["turno"] == 2


def test_feedback_agrega_e_valida(client: TestClient) -> None:
    s = _upload(client)
    sessions.SESSOES[s["sessao"]].turnos = 2
    corpo = {"sessao": s["sessao"], "turno": 1, "nota": "nao_util", "motivo": "numeros_errados"}
    assert client.post("/api/feedback", json=corpo).status_code == 204
    assert client.post("/api/feedback", json={"sessao": s["sessao"], "turno": 2, "nota": "util"}).status_code == 204
    assert client.post("/api/feedback", json={**corpo, "nota": "otimo"}).status_code == 422
    assert client.post("/api/feedback", json={**corpo, "motivo": "xyz"}).status_code == 422
    assert client.post("/api/feedback", json={**corpo, "turno": "a"}).status_code == 422
    assert client.post("/api/feedback", json={**corpo, "sessao": "nada"}).status_code == 400
    assert client.post("/api/feedback", json=corpo).status_code == 400  # um voto por turno
    assert client.post("/api/feedback", json={**corpo, "turno": 3}).status_code == 400  # turno que não existe
    fb = client.get("/api/metricas").json()["feedback"]
    assert fb == {"util": 1, "nao_util": 1, "por_motivo": {"numeros_errados": 1}}


def test_metricas_agregam_perguntas(client: TestClient) -> None:
    vazio = client.get("/api/metricas").json()
    assert vazio["perguntas"] == 0 and vazio["p50_ms"] is None and vazio["conferidas_pct"] is None
    assert vazio["feedback"] == {"util": 0, "nao_util": 0, "por_motivo": {}} and vazio["erros_por_tipo"] == {}
    s = _upload(client)
    _perguntar(client, s["sessao"])
    m = client.get("/api/metricas").json()
    assert m["perguntas"] == 1 and m["respondidas"] == 1 and m["conferidas_pct"] == 100.0
    assert m["reanalises_media"] == 0 and m["p50_ms"] >= 0 and m["p90_ms"] >= m["p50_ms"] and m["desde"]
    assert m["tokens_medios"] is None  # o LLM falso não informa uso


def test_metricas_contam_erros_por_tipo() -> None:
    app = create_app()
    app.dependency_overrides[obter_llm] = lambda: LlmFalso([_erro_api(openai.RateLimitError, 429)])
    c = TestClient(app)
    s = _upload(c)
    evs = _eventos(_perguntar(c, s["sessao"]))
    assert [n for n, _ in evs][-3:] == ["erro", "metricas", "fim"]
    m = c.get("/api/metricas").json()
    assert m["perguntas"] == 1 and m["respondidas"] == 0 and m["erros_por_tipo"] == {"cota": 1}


def test_log_estruturado_sem_texto_do_usuario(client: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    s = _upload(client)
    with caplog.at_level(logging.INFO, logger="analista.metricas"):
        _perguntar(client, s["sessao"], "Pergunta confidencial do usuário")
    linhas = [json.loads(r.getMessage()) for r in caplog.records if r.name == "analista.metricas"]
    assert len(linhas) == 1
    assert set(linhas[0]) == {"trace_id", "ms", "chamadas_llm", "chamadas_ferramenta", "tokens_entrada",
                              "tokens_saida", "conferido", "reanalises", "erro_tipo", "modelo", "versao_prompt",
                              "gravacao"}
    assert linhas[0]["conferido"] is True and linhas[0]["gravacao"] is False and linhas[0]["erro_tipo"] is None
    assert "confidencial" not in caplog.text and "O total" not in caplog.text


# ---------- gravações (B5) ----------

def _client_sem_llm() -> TestClient:
    def proibido():
        def llm(*a, **k):
            raise AssertionError("o LLM não deveria ser chamado")
        return llm

    app = create_app()
    app.dependency_overrides[obter_llm] = proibido
    return TestClient(app)


def test_teto_esgotado_com_exemplo_reproduz_gravacao(monkeypatch: pytest.MonkeyPatch) -> None:
    _gravar("exemplo_a", GRAVACAO)
    pausas: list[float] = []
    monkeypatch.setattr(main, "_dormir", pausas.append)
    monkeypatch.setattr(main, "_uso", {"dia": date.today(), "n": main.LIMITE_DIARIO})
    c = _client_sem_llm()
    s = _upload(c)
    r = _perguntar(c, s["sessao"], "Qual?", exemplo_id="exemplo_a")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    evs = _eventos(r)
    assert [n for n, _ in evs] == [e["evento"] for e in GRAVACAO]
    assert all(d["gravacao"] is True for _, d in evs)
    assert 0.4 in pausas and all(p <= 1.5 for p in pausas)  # 40% de 1000 ms
    assert main._VAGAS.acquire(blocking=False)  # não consumiu a vaga


def test_pausa_da_gravacao_tem_teto(monkeypatch: pytest.MonkeyPatch) -> None:
    _gravar("lento", [{"evento": "llm", "ms": 60000}, {"evento": "fim"}])
    pausas: list[float] = []
    monkeypatch.setattr(main, "_dormir", pausas.append)
    monkeypatch.setattr(main, "_uso", {"dia": date.today(), "n": main.LIMITE_DIARIO})
    c = _client_sem_llm()
    _perguntar(c, _upload(c)["sessao"], "Qual?", exemplo_id="lento")
    assert max(pausas) == 1.5


def test_sem_vaga_com_exemplo_reproduz_gravacao(monkeypatch: pytest.MonkeyPatch) -> None:
    _gravar("exemplo_a", GRAVACAO)
    monkeypatch.setattr(main, "_VAGAS", threading.BoundedSemaphore(0))
    c = _client_sem_llm()
    evs = _eventos(_perguntar(c, _upload(c)["sessao"], "Qual?", exemplo_id="exemplo_a"))
    assert evs[-1][0] == "fim" and evs[0][1]["gravacao"] is True


def test_cota_do_provedor_esgotada_cai_na_gravacao() -> None:
    _gravar("exemplo_a", GRAVACAO)
    app = create_app()
    app.dependency_overrides[obter_llm] = lambda: LlmFalso([_erro_api(openai.RateLimitError, 429)])
    c = TestClient(app)
    evs = _eventos(_perguntar(c, _upload(c)["sessao"], "Qual?", exemplo_id="exemplo_a"))
    nomes = [n for n, _ in evs]
    assert "erro" not in nomes and nomes[-1] == "fim" and nomes.count("recebido") == 1
    assert dict(evs)["resposta"]["gravacao"] is True


def test_teto_esgotado_sem_exemplo_continua_429(monkeypatch: pytest.MonkeyPatch) -> None:
    _gravar("exemplo_a", GRAVACAO)
    monkeypatch.setattr(main, "_uso", {"dia": date.today(), "n": main.LIMITE_DIARIO})
    c = _client_sem_llm()
    assert _perguntar(c, _upload(c)["sessao"], "Qual?").status_code == 429


@pytest.mark.parametrize("exemplo_id", ["../segredo", "..\\segredo", "a/b", "A", "x" * 33, "a.b", ""])
def test_exemplo_id_invalido_recusado(client: TestClient, exemplo_id: str) -> None:
    s = _upload(client)
    assert _perguntar(client, s["sessao"], "Qual?", exemplo_id=exemplo_id).status_code == 422


def test_exemplo_id_sem_gravacao_responde_ao_vivo(client: TestClient) -> None:
    s = _upload(client)
    r = _perguntar(client, s["sessao"], "Qual?", exemplo_id="nao_existe")
    assert r.status_code == 200 and dict(_eventos(r))["resposta"]["texto"] == "O total é 350."


def test_gravacao_ignora_linhas_quebradas(monkeypatch: pytest.MonkeyPatch) -> None:
    main.GRAVACOES.mkdir(parents=True)
    (main.GRAVACOES / "ruim.jsonl").write_text('nao json\n[1]\n{"evento": "fim"}\n', encoding="utf-8")
    monkeypatch.setattr(main, "_uso", {"dia": date.today(), "n": main.LIMITE_DIARIO})
    c = _client_sem_llm()
    evs = _eventos(_perguntar(c, _upload(c)["sessao"], "Qual?", exemplo_id="ruim"))
    assert evs == [("fim", {"gravacao": True})]


def test_nova_conversa_sobe_o_contador_e_libera_votos(client: TestClient) -> None:
    s = _upload(client)
    sessao = sessions.SESSOES[s["sessao"]]
    sessao.turnos, sessao.turnos_avaliados = 1, {1}
    client.post("/api/conversa/nova", json={"sessao": s["sessao"]})
    assert sessao.conversa == 1 and sessao.turnos_avaliados == set()


def test_sem_chave_com_exemplo_reproduz_gravacao(monkeypatch: pytest.MonkeyPatch) -> None:
    _gravar("exemplo_a", GRAVACAO)
    monkeypatch.setattr(config, "LLM_API_KEY", "")
    c = TestClient(create_app())
    evs = _eventos(_perguntar(c, _upload(c)["sessao"], "Qual?", exemplo_id="exemplo_a"))
    assert evs[-1][0] == "fim" and evs[0][1]["gravacao"] is True
    assert _perguntar(c, _upload(c)["sessao"], "Qual?").status_code == 503


def test_reproducoes_simultaneas_tem_teto(monkeypatch: pytest.MonkeyPatch) -> None:
    _gravar("exemplo_a", GRAVACAO)
    monkeypatch.setattr(main, "_VAGAS", threading.BoundedSemaphore(0))
    monkeypatch.setattr(main, "_REPRODUCOES", threading.BoundedSemaphore(0))
    c = _client_sem_llm()
    assert _perguntar(c, _upload(c)["sessao"], "Qual?", exemplo_id="exemplo_a").status_code == 429


def test_sse_recusa_nan_e_a_gravacao_ignora_nan() -> None:
    assert b"null" in main._sse({"evento": "x", "v": None})
    with pytest.raises(ValueError):
        main._sse({"evento": "x", "v": float("nan")})


def test_stream_cancelado_conta_como_erro_cancelado() -> None:
    s = sessions.criar_de_csv("d.csv", CSV)
    gerador = main._ao_vivo(main.PerguntaIn(sessao=s.id, pergunta="Oi?"), s,
                            LlmFalso([texto("plano"), texto("Oi.")]), None, lambda: None)
    next(gerador)
    gerador.close()
    assert main._estat["erros"] == {"cancelado": 1}


def test_p50_usa_a_mediana() -> None:
    main._estat["execucoes"] = [{"ms": ms, "respondida": True, "conferido": True, "reanalises": 0,
                                 "tokens_entrada": None, "tokens_saida": None} for ms in (100, 200, 300, 1000)]
    assert main._snapshot_metricas()["p50_ms"] == 250


def test_csp_fixa_o_script_do_echarts() -> None:
    csp = main.CABECALHOS["Content-Security-Policy"]
    assert "https://cdnjs.cloudflare.com/ajax/libs/echarts/5.5.0/echarts.min.js" in csp
    assert "script-src 'self' https://cdnjs.cloudflare.com;" not in csp


def test_cliente_lento_nao_segura_a_vaga(monkeypatch: pytest.MonkeyPatch) -> None:
    import asyncio
    monkeypatch.setattr(main, "PRAZO_SSE", 0.1)
    liberou: list[bool] = []

    async def gerador():
        yield b"x"

    async def send(_):
        await asyncio.sleep(5)  # cliente que parou de ler

    async def rodar() -> None:
        resposta = main._RespostaSSE(gerador(), lambda: liberou.append(True))
        await resposta({"type": "http", "asgi": {"spec_version": "2.3"}, "method": "GET", "headers": []},
                       lambda: asyncio.sleep(5), send)

    asyncio.run(asyncio.wait_for(rodar(), 3))
    assert liberou == [True]


def test_reproducao_nao_traz_turno_e_nao_marca_a_sessao(monkeypatch: pytest.MonkeyPatch) -> None:
    _gravar("exemplo_a", GRAVACAO)
    monkeypatch.setattr(config, "LLM_API_KEY", "")
    c = TestClient(create_app())
    sid = _upload(c)["sessao"]
    assert sessions.SESSOES[sid].perguntou is False
    evs = _eventos(_perguntar(c, sid, "Qual?", exemplo_id="exemplo_a"))
    assert all("turno" not in d for _, d in evs) and sessions.SESSOES[sid].perguntou is False


def test_pergunta_ao_vivo_marca_a_sessao_e_nova_conversa_mantem(client: TestClient) -> None:
    sid = _upload(client)["sessao"]
    _perguntar(client, sid)
    client.post("/api/conversa/nova", json={"sessao": sid})
    sessao = sessions.SESSOES[sid]
    assert sessao.perguntou is True and sessao.turnos == 0
    sessao.ultimo_uso -= 601
    sessions.limpar_expiradas()
    assert sid in sessions.SESSOES  # TTL de 1 h, não de 10 min


def test_visitante_novo_recebe_servidor_cheio_sem_expulsar_ninguem(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main, "MAX_SESSOES", 1)
    c = TestClient(create_app(), raise_server_exceptions=False)
    primeira = _upload(c)["sessao"]
    r = c.post("/api/sessao/csv", files={"arquivo": ("dados.csv", CSV, "text/csv")})
    assert r.status_code == 400 and "cheio" in r.json()["detail"] and primeira in sessions.SESSOES


def test_pergunta_recusada_com_429_nao_marca_a_sessao(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    sid = _upload(client)["sessao"]
    monkeypatch.setattr(main, "_VAGAS", threading.BoundedSemaphore(0))
    assert _perguntar(client, sid).status_code == 429
    monkeypatch.setattr(main, "_VAGAS", threading.BoundedSemaphore(1))
    monkeypatch.setattr(main, "_uso", {"dia": date.today(), "n": main.LIMITE_DIARIO})
    assert _perguntar(client, sid).status_code == 429
    assert sessions.SESSOES[sid].perguntou is False
