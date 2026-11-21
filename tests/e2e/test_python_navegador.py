"""Fluxo completo do Python no navegador: página real, SSE, worker do Pyodide e POST do resultado.

Só roda com E2E_PYODIDE=1 (baixa ~20 MB do jsDelivr). O uvicorn sobe numa thread com o LLM roteirizado.
Motores: E2E_MOTORES=chromium,firefox,webkit (padrão: os três). O WebKit do Playwright não é o Safari nem o iOS.
"""
import logging
import os
import re
import socket
import threading
import time

import pytest
import uvicorn

from app import config, main, python_navegador
from app.main import create_app, obter_llm
from tests.test_agent import LlmFalso, chamada, texto

pytestmark = pytest.mark.skipif(not os.environ.get("E2E_PYODIDE"), reason="defina E2E_PYODIDE=1 para rodar")
sync_api = pytest.importorskip("playwright.sync_api")

MOTORES = os.environ.get("E2E_MOTORES", "chromium,firefox,webkit").split(",")
CARGA_MS = 90_000  # com 60 s deu timeout intermitente (fatia 3)
EXECUCAO_MS = 15_000
SQL = "SELECT valor_pedido FROM pedidos"
CODIGO = ("print(len(df)); r = teste_t_welch(df.valor_pedido[:4000], df.valor_pedido[4000:]); "
          "print(f\"p_valor = {r.p_valor:.3g}\")")


def _roteiro():
    return LlmFalso([texto("Comparar as duas metades."), chamada("rodar_python", sql=SQL, codigo=CODIGO),
                     texto("A base tem 8.000 pedidos.")])


@pytest.fixture
def url(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setattr(config, "SESSIONS_DIR", tmp_path / "sessions")
    monkeypatch.setattr(main, "_VAGAS", threading.BoundedSemaphore(1))
    main._zerar_metricas()
    python_navegador._PENDENTES.clear()
    app = create_app()
    app.dependency_overrides[obter_llm] = lambda: _roteiro()
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        porta = s.getsockname()[1]
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=porta, log_level="warning"))
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    while not srv.started:
        time.sleep(0.05)
    yield f"http://127.0.0.1:{porta}"
    srv.should_exit = True
    thread.join(10)
    app.dependency_overrides.clear()


@pytest.fixture(params=MOTORES)
def pagina(request):
    with sync_api.sync_playwright() as p:
        nav = getattr(p, request.param).launch()
        pag = nav.new_page(viewport={"width": 1366, "height": 768})
        pag.motor = request.param
        pag.erros = []
        pag.on("pageerror", lambda e: pag.erros.append(str(e)))
        pag.on("console", lambda m: pag.erros.append(m.text)
               if (m.type == "error" and "Failed to load resource" not in m.text) or "Content Security Policy" in m.text
               or "Content-Security-Policy" in m.text else None)
        yield pag
        nav.close()


def _perguntar(pagina, pergunta: str) -> float:
    """Envia a pergunta e devolve os segundos do passo Python (do aparecimento até a saída)."""
    pagina.locator("#pergunta").fill(pergunta)
    pagina.get_by_role("button", name="Perguntar").click()
    passo = pagina.locator(".turno").last.locator(".passo-python")
    passo.wait_for(state="attached", timeout=60_000)
    t0 = time.monotonic()
    sync_api.expect(passo.locator(".saida")).to_be_visible(timeout=CARGA_MS + EXECUCAO_MS)
    segundos = time.monotonic() - t0
    sync_api.expect(pagina.locator(".turno").last.locator(".final")).to_be_visible(timeout=60_000)
    return segundos


def test_python_roda_no_navegador_do_visitante(pagina, url, caplog) -> None:
    caplog.set_level(logging.INFO, logger="analista")
    pagina.goto(url)
    pagina.get_by_role("button", name="Usar CSV de exemplo").click()
    sync_api.expect(pagina.locator("#esquema")).to_be_visible()

    primeira = _perguntar(pagina, "Compare as duas metades do pedido.")
    turno = pagina.locator(".turno").last
    sync_api.expect(turno.locator(".passo-python .selo")).to_have_text("no seu navegador")
    saida = turno.locator(".passo-python .saida").inner_text()
    assert "8000" in saida and re.search(r"p_valor = \S+", saida), saida
    sync_api.expect(turno.locator(".final")).to_contain_text("números conferidos")

    segunda = _perguntar(pagina, "E de novo?")
    assert "8000" in pagina.locator(".turno").last.locator(".passo-python .saida").inner_text()
    bytes_pedido = [int(m) for m in re.findall(r"python_pedido bytes=(\d+)", caplog.text)]
    print(f"\n[{pagina.motor}] 1a execucao {primeira:.1f} s, 2a {segunda:.1f} s, python_pedido {bytes_pedido} bytes")
    assert bytes_pedido and bytes_pedido[0] > 30_000  # o CSV de 8.000 linhas viaja inteiro
    assert pagina.erros == []
