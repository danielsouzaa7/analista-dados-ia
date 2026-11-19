"""Fluxo ponta a ponta no navegador. Só roda com E2E_URL (ex.: E2E_URL=http://127.0.0.1:8000).

Usa o chip de exemplo: sem chave ou sem cota o servidor toca a gravação; com chave gasta 1 pergunta da cota.
"""
import os

import pytest

pytestmark = pytest.mark.skipif(not os.environ.get("E2E_URL"), reason="defina E2E_URL para rodar o e2e")
sync_api = pytest.importorskip("playwright.sync_api")

RESPOSTA_MS = 150_000


@pytest.fixture()
def pagina():
    with sync_api.sync_playwright() as p:
        navegador = p.chromium.launch()
        pag = navegador.new_page(viewport={"width": 1366, "height": 768})
        pag.erros = []
        pag.on("pageerror", lambda e: pag.erros.append(str(e)))
        # recursos externos (fonte, CDN) falhando não são erro do app
        pag.on("console", lambda m: pag.erros.append(m.text) if m.type == "error" and "Failed to load resource" not in m.text else None)
        yield pag
        navegador.close()


def test_exemplo_pergunta_e_grafico(pagina):
    pagina.goto(os.environ["E2E_URL"])

    pagina.get_by_role("button", name="Usar CSV de exemplo").click()
    sync_api.expect(pagina.locator("#esquema")).to_be_visible()
    sync_api.expect(pagina.locator("#lista-tabelas")).to_contain_text("pedidos")

    pagina.get_by_role("button", name="Receita por culinária").click()
    sync_api.expect(pagina.locator(".final")).to_be_visible(timeout=RESPOSTA_MS)
    sync_api.expect(pagina.locator(".status.parado")).to_be_visible(timeout=RESPOSTA_MS)
    sync_api.expect(pagina.locator(".grafico canvas").first).to_be_visible()
    assert pagina.evaluate("document.querySelector('.grafico canvas').width") > 0

    assert pagina.erros == []
