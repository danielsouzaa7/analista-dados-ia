import shutil
import sys
import time
from pathlib import Path

import pytest

from app import python_tool

pytestmark = pytest.mark.skipif(shutil.which("deno") is None, reason="deno não está no PATH")

CSV = "a,b\n1,2\n3,4\n"
SEGREDO = Path(__file__)  # arquivo real fora da pasta liberada


def rodar(codigo: str, **kw) -> dict:
    return python_tool.rodar(codigo, CSV, **kw)


def test_soma() -> None:
    r = rodar("print(df['a'].sum())")
    assert r["saida"].strip() == "4" and not r["erro"]


@pytest.mark.parametrize("codigo", [
    "import js\njs.fetch('https://example.com')",
    "import js\nprint(js.Deno.env.get('LLM_API_KEY'))",
    f"import js\nprint(js.Deno.readTextFileSync({SEGREDO.as_posix()!r}))",
])
def test_fugas_bloqueadas_pelo_deno(codigo: str) -> None:
    r = rodar(codigo)
    assert "NotCapable" in (r["erro"] or ""), r
    assert rodar("print(1+1)")["saida"].strip() == "2"


def test_fs_virtual_do_pyodide_nao_ve_o_host() -> None:
    # O /etc/passwd do Pyodide é virtual: não é fuga, só confirma que o host não aparece.
    assert rodar("open('/etc/passwd').read()")["erro"]


def test_timeout() -> None:
    # 20 s cobre o carregamento do Pyodide: o estouro tem de acontecer dentro do while True.
    r = rodar("print('antes', flush=True)\nwhile True: pass", timeout=20)
    assert "Tempo limite" in r["erro"]
    assert rodar("print(1)")["saida"].strip() == "1"


def test_saida_gigante_do_deno_e_cortada() -> None:
    codigo = ("import js\nb = js.Uint8Array.new(1024*1024)\n"
              "for _ in range(5): js.Deno.stdout.writeSync(b)\n")
    r = rodar(codigo)
    assert "grande demais" in (r["erro"] or ""), r


def test_saida_forjada_nao_vale() -> None:
    r = rodar("import js\njs.console.log('{\"saida\":\"FORJADO\",\"erro\":null}')\njs.Deno.exit(0)")
    assert r["saida"] != "FORJADO" and r["erro"]


def test_semaforo_limita_concorrencia() -> None:
    assert python_tool.SEMAFORO._initial_value == 2


def test_ambiente_sem_chave(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "valor-falso-de-teste")
    r = rodar("import os\nprint('LLM_API_KEY' in os.environ)\nimport js\n")
    assert r["saida"].strip() == "False"
    r = rodar("import js\nprint(js.Deno.env.get('LLM_API_KEY'))")
    assert "valor-falso-de-teste" not in (r["saida"] or "") + (r["erro"] or "")


def test_saida_cortada() -> None:
    r = rodar("print('x' * 50000)")
    assert len(r["saida"]) <= 10_000


def test_espera_final_tem_prazo() -> None:
    # Fecha o stdout e dorme: sem prazo no wait(), ficaria pendurado por 15 s.
    ini = time.monotonic()
    _, estado = python_tool._executar(
        [sys.executable, "-c", "import os,time; os.close(1); time.sleep(15)"], b"", timeout=2)
    assert time.monotonic() - ini < 6 and estado["timeout"]




CODIGO_FORJA = r'''
import js
from pyodide.ffi import create_proxy
js.JSON.stringify = create_proxy(lambda *a: '{"nonce":"x","saida":"FORJADO","erro":null}')
js.console.log = create_proxy(lambda *a: None)
print("legitimo")
'''


def test_js_json_stringify_trocado_nao_forja_saida() -> None:
    r = rodar(CODIGO_FORJA)
    assert r["saida"] == "legitimo\n" and not r["erro"], r


def test_preludio_disponivel_no_sandbox() -> None:
    r = rodar("r = teste_t_welch([1, 2, 3, 4, 5], [3, 4, 5, 6, 7])\nprint(r)\n"
              "print(teste_correlacao([1, 2, 3, 4], [1, 3, 2, 5]).p_valor)")
    assert not r["erro"]
    assert "ResultadoTeste(t=-2.0, gl=8.0, p_valor=0.08" in r["saida"]
    assert 0 < float(r["saida"].splitlines()[-1]) < 1
