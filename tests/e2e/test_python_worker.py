"""Fuga do worker do Pyodide no navegador, sob a CSP real. Só roda com E2E_PYODIDE=1 (baixa ~20 MB do jsDelivr).

Sobe o app numa thread e abre uma página mínima que só cria o worker e posta o código (HTML gerado aqui).
Motores: E2E_MOTORES=chromium,firefox,webkit (padrão: os três).
"""
import os
import socket
import threading
import time

import pytest
import uvicorn

pytestmark = pytest.mark.skipif(not os.environ.get("E2E_PYODIDE"), reason="defina E2E_PYODIDE=1 para rodar")
sync_api = pytest.importorskip("playwright.sync_api")

MOTORES = os.environ.get("E2E_MOTORES", "chromium,firefox,webkit").split(",")
CARGA_MS = 120_000

# a página de teste é servida pelo próprio app de teste, com a CSP real da página
PAGINA = '<!doctype html><meta charset=utf-8><script src="/teste-worker.js"></script>'
# o script vai em arquivo à parte: a CSP da página não permite script inline
SCRIPT = r"""window.rodar = (codigo) => new Promise((ok) => {
  const w = new Worker("/static/python-worker.js", {type: "module"});
  const prazo = (tipo, ms) => setTimeout(() => { ok({tipo}); w.terminate(); }, ms);
  const carga = prazo("timeout_carga", 90000);
  let execucao;
  w.onmessage = ({data}) => {
    clearTimeout(carga); clearTimeout(execucao);
    if (data.tipo === "pronto") { execucao = prazo("timeout_execucao", 15000); w.postMessage({codigo, csv: "a\n1\n", preludio: ""}); }
    else ok(data);
    if (data.tipo !== "pronto") w.terminate();
  };
});
"""


@pytest.fixture(scope="module")
def url():
    from fastapi import Response
    from fastapi.responses import HTMLResponse

    from app.main import create_app
    app = create_app()
    app.add_api_route("/teste-worker", lambda: HTMLResponse(PAGINA), methods=["GET"])
    app.add_api_route("/teste-worker.js", lambda: Response(SCRIPT, media_type="text/javascript"), methods=["GET"])
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        porta = s.getsockname()[1]
    servidor = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=porta, log_level="warning"))
    threading.Thread(target=servidor.run, daemon=True).start()
    while not servidor.started:
        time.sleep(0.05)
    yield f"http://127.0.0.1:{porta}"
    servidor.should_exit = True


@pytest.fixture(scope="module", params=MOTORES)
def navegador(request):
    with sync_api.sync_playwright() as p:
        nav = getattr(p, request.param).launch()
        yield nav
        nav.close()


@pytest.fixture()
def rodar(navegador, url):
    pag = navegador.new_page()
    pag.violacoes = []
    pag.on("console", lambda m: pag.violacoes.append(m.text) if "Content Security Policy" in m.text
           or "Content-Security-Policy" in m.text else None)
    pag.goto(f"{url}/teste-worker")

    def _rodar(codigo: str) -> dict:
        return pag.evaluate("(c) => window.rodar(c)", codigo)

    _rodar.pagina = pag
    yield _rodar
    pag.close()


def _fuga(rodar, codigo: str) -> dict:
    """O código tenta a fuga; imprime SAIU se ela funcionou. Bloqueado = erro e nenhum SAIU."""
    r = rodar(codigo)
    assert r["tipo"] in ("resultado", "timeout_execucao"), r  # o WebKit bloqueia o fetch sem nunca rejeitar a promessa
    assert "SAIU" not in r.get("saida", "")
    return r


def test_worker_carrega_e_roda_print(rodar) -> None:
    r = rodar("print(1)")
    assert r == {"tipo": "resultado", "saida": "1\n", "erro": None}
    assert rodar.pagina.violacoes == []


def test_worker_nao_alcanca_rede_externa_nem_o_proprio_site(rodar) -> None:
    for alvo in ("https://example.com", "/api/status"):
        r = _fuga(rodar, f"import js\nr = await js.fetch({alvo!r})\nprint('SAIU', r.status)")
        assert r["tipo"] == "timeout_execucao" or r["erro"], alvo


def test_worker_nao_carrega_script_de_fora(rodar) -> None:
    # import() só é alcançável via eval, que a CSP (sem 'unsafe-eval') já nega; o script-src fecha o resto
    r = _fuga(rodar, "import js\nm = await js.eval(\"import('https://example.com/x.js')\")\nprint('SAIU')")
    assert r["tipo"] == "timeout_execucao" or r["erro"]


def _canal_bloqueado(rodar, construtor: str) -> None:
    codigo = f"""import asyncio, js
from pyodide.ffi import create_proxy
fim = asyncio.get_event_loop().create_future()
try:
    c = js.{construtor}
except Exception:
    print("bloqueado")  # o motor recusa já no construtor
    raise SystemExit
c.onopen = create_proxy(lambda e: fim.set_result("SAIU"))
c.onerror = create_proxy(lambda e: fim.done() or fim.set_result("bloqueado"))
c.onclose = create_proxy(lambda e: fim.done() or fim.set_result("bloqueado"))
print(await fim)
"""
    r = rodar(codigo)
    assert r["tipo"] == "timeout_execucao" or r["saida"] == "bloqueado\n", r  # WebKit: a promessa bloqueada não resolve


def test_websocket_bloqueado(rodar) -> None:
    _canal_bloqueado(rodar, "WebSocket.new('ws://example.com/')")


def test_eventsource_bloqueado(rodar) -> None:
    _canal_bloqueado(rodar, "EventSource.new('https://example.com/')")
