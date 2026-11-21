"""Aba fechada durante o python_pedido, no uvicorn REAL: a pendente sai, o "cancelado" é registrado e a vaga volta.

Roda sempre (não usa navegador): só httpx contra um uvicorn numa thread."""
import socket
import threading
import time

import httpx
import pytest
import uvicorn

from app import main, python_navegador, sessions
from app.main import create_app, obter_llm
from tests.test_agent import LlmFalso, chamada, texto

PRAZO_VAGA_S = 3


def _llm_roteirizado():
    """Primeira pergunta chama rodar_python (e fica esperando o navegador); as outras respondem direto."""
    pedidos = []

    def fabrica():
        pedidos.append(1)
        if len(pedidos) == 1:
            return LlmFalso([texto("plano"), chamada("rodar_python", sql="SELECT sum(valor) AS t FROM dados",
                                                     codigo="print(df.t[0])"), texto("O total é 350.")])
        return LlmFalso([texto("plano"), texto("Resposta direta.")])
    return fabrica


@pytest.fixture
def servidor(monkeypatch: pytest.MonkeyPatch):
    import threading as th
    monkeypatch.setattr(main, "_VAGAS", th.BoundedSemaphore(1))
    main._zerar_metricas()
    python_navegador._PENDENTES.clear()
    app = create_app()
    app.dependency_overrides[obter_llm] = _llm_roteirizado()
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        porta = s.getsockname()[1]
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=porta, log_level="warning"))
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    while not srv.started:
        time.sleep(0.02)
    yield f"http://127.0.0.1:{porta}"
    srv.should_exit = True
    thread.join(10)
    app.dependency_overrides.clear()


def _esperar(condicao, limite_s: float) -> float | None:
    desde = time.monotonic()
    while time.monotonic() - desde < limite_s:
        if condicao():
            return time.monotonic() - desde
        time.sleep(0.02)
    return None


def test_fechar_a_aba_devolve_a_vaga(servidor: str) -> None:
    sessao = sessions.criar_de_csv("dados.csv", b"regiao,valor\nNorte,100\nSul,250\n")
    corpo = {"sessao": sessao.id, "pergunta": "Qual o total?"}
    with httpx.Client(base_url=servidor, timeout=10) as cliente:
        with cliente.stream("POST", "/api/perguntar", json=corpo) as r:
            assert r.status_code == 200
            for linha in r.iter_lines():
                if linha == "event: python_pedido":
                    break
            else:
                pytest.fail("o stream acabou sem python_pedido")
            assert sessao.id in python_navegador._PENDENTES
            fechou = time.monotonic()
        # a conexão foi fechada aqui (saída do with): é o que a aba fechada faz
        saiu = _esperar(lambda: sessao.id not in python_navegador._PENDENTES, PRAZO_VAGA_S)
        assert saiu is not None, "a pendente não saiu em 3 s"
        assert _esperar(lambda: main._snapshot_metricas()["erros_por_tipo"].get("cancelado") == 1,
                        PRAZO_VAGA_S) is not None, "o cancelado não foi registrado"
        aceitou = []

        def vaga_voltou() -> bool:
            with cliente.stream("POST", "/api/perguntar", json=corpo) as nova:
                aceitou.append(nova.status_code)
                if nova.status_code == 200:
                    nova.read()  # a segunda pergunta responde direto e devolve a vaga
            return aceitou[-1] == 200

        assert _esperar(vaga_voltou, PRAZO_VAGA_S) is not None, f"a vaga não voltou em 3 s: {aceitou}"
        total = time.monotonic() - fechou
    print(f"vaga de volta {total:.2f} s depois de fechar a conexão (pendente saiu em {saiu:.2f} s)")
    assert total < PRAZO_VAGA_S
