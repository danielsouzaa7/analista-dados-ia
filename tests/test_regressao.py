"""Regressão sem LLM: reproduz os cassetes (respostas do LLM gravadas por `avaliar.py --gravar-cassetes`)
pelo agente real, com as ferramentas reais e o CSV de exemplo, e confere os numeros_chave."""
import json
import shutil
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))
import avaliar  # noqa: E402

CASSETES = RAIZ / "tests" / "cassetes"
CASOS = avaliar.carregar_casos()


def _llm(id_: str) -> avaliar.LlmCassete:
    arquivo = CASSETES / f"{id_}.json"
    if not arquivo.exists():
        pytest.skip(f"sem cassete em tests/cassetes/{id_}.json (gere com: python scripts/avaliar.py --gravar-cassetes)")
    texto = arquivo.read_text(encoding="utf-8")
    if "rodar_python" in texto and shutil.which("deno") is None:  # mesma regra de test_python_tool
        pytest.skip("o cassete usa a ferramenta Python e o deno não está no PATH")
    return avaliar.LlmCassete(json.loads(texto)["respostas"])


@pytest.mark.parametrize("caso", CASOS, ids=[c["id"] for c in CASOS])
def test_cassete_reproduz_o_acerto(caso: dict, tmp_path: Path) -> None:
    llm = _llm(caso["id"])
    sessao = avaliar.criar_sessao()
    if "depende_de" in caso:  # o acompanhamento precisa da conversa anterior na mesma sessão
        anterior = next(c for c in CASOS if c["id"] == caso["depende_de"])
        avaliar.rodar_caso(anterior, sessao, _llm(anterior["id"]), tmp_path, "chave-de-teste")
    r = avaliar.rodar_caso(caso, sessao, llm, tmp_path, "chave-de-teste")
    assert r["acerto"], f"faltando {r['faltando']}; erro: {r['erro']}; hash_igual: {r.get('hash_igual')}"
    assert not llm.respostas, "o agente usou menos chamadas ao LLM do que o cassete gravado"
