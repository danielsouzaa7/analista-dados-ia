import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))
import orquestracao as oq  # noqa: E402

T0 = datetime(2026, 11, 19, 12, 0, 0, tzinfo=UTC)
SEGREDO = "TEXTO-SECRETO-DA-MENSAGEM"


def ts(m):
    return (T0 + timedelta(minutes=m)).isoformat().replace("+00:00", "Z")


def chamada(m, i=0, o=0, cl=0, cc=0, mid=None):
    usage = {"input_tokens": i, "output_tokens": o, "cache_read_input_tokens": cl,
             "cache_creation_input_tokens": cc}
    return {"type": "assistant", "timestamp": ts(m),
            "message": {"id": mid or f"m{m}-{i}-{o}", "content": [{"type": "text", "text": SEGREDO}],
                        "usage": usage}}


def compacta(m, pre):
    return {"type": "system", "subtype": "compact_boundary", "timestamp": ts(m),
            "compactMetadata": {"preTokens": pre}}


def grava(caminho, eventos):
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text("\n".join(json.dumps(e) for e in eventos), encoding="utf-8")


def agente(pasta, sessao, nome, tipo, eventos):
    a = pasta / sessao / "subagents" / f"agent-{nome}.jsonl"
    grava(a, eventos)
    a.with_suffix(".meta.json").write_text(json.dumps({"agentType": tipo}), encoding="utf-8")


def test_soma_tokens_e_pico_do_agente(tmp_path):
    grava(tmp_path / "s1.jsonl", [chamada(0, i=1)])
    agente(tmp_path, "s1", "a", "ecc:tdd-guide",
           [chamada(1, i=10, o=5, cl=100, cc=20), chamada(2, i=30, o=7, cl=200, cc=0)])
    r = oq.medir(tmp_path)
    assert r["n_agentes"] == 1
    a = r["agentes"][0]
    assert (a["entrada"], a["saida"], a["cache_lido"], a["cache_criado"]) == (40, 12, 300, 20)
    assert a["pico"] == 230  # max(10+100+20, 30+200+0)
    assert a["categoria"] == oq.IMPLEMENTACAO


def test_linhas_duplicadas_do_mesmo_message_id_contam_uma_vez(tmp_path):
    grava(tmp_path / "s1.jsonl", [chamada(0, i=5, o=9, mid="x"), chamada(0, i=5, o=9, mid="x")])
    r = oq.medir(tmp_path)
    assert r["orquestrador"]["saida"] == 9


def test_orquestrador_pico_totais_e_compactacoes(tmp_path):
    grava(tmp_path / "s1.jsonl", [chamada(0, i=1, cl=50, cc=9), chamada(1, i=2, cl=400_000, cc=8),
                                  compacta(2, 400_010), chamada(3, i=3, cl=10)])
    grava(tmp_path / "s2.jsonl", [chamada(5, i=1, cl=20)])
    o = oq.medir(tmp_path)["orquestrador"]
    assert o["pico"] == 400_010
    assert o["entrada"] == 7
    assert o["cache_lido"] == 400_080
    assert o["compactacoes"] == 1
    assert o["pre_compactacao_max"] == 400_010
    assert o["n_sessoes"] == 2
    assert o["sessoes_acima"] == 1


def test_limite_da_zona_e_300_mil():
    assert oq.LIMITE_ZONA == 300_000


def test_corte_ate_ignora_eventos_e_agentes_depois(tmp_path):
    grava(tmp_path / "s1.jsonl", [chamada(0, i=1), chamada(60, i=1000)])
    agente(tmp_path, "s1", "a", "ecc:planner", [chamada(1, i=2)])
    agente(tmp_path, "s1", "b", "ecc:planner", [chamada(90, i=5000)])
    r = oq.medir(tmp_path, ate=T0 + timedelta(minutes=30))
    assert r["n_agentes"] == 1
    assert r["orquestrador"]["entrada"] == 1
    assert r["agentes"][0]["entrada"] == 2


def test_categorias_e_zona_de_genialidade(tmp_path):
    grava(tmp_path / "s1.jsonl", [chamada(0, i=1)])
    agente(tmp_path, "s1", "a", "ecc:code-reviewer", [chamada(1, i=1, cl=299_999)])
    agente(tmp_path, "s1", "b", "ecc:security-reviewer", [chamada(1, i=1, cl=300_000)])
    agente(tmp_path, "s1", "c", "ecc:architect", [chamada(1, i=1)])
    agente(tmp_path, "s1", "d", None, [chamada(1, i=1)])
    r = oq.medir(tmp_path)
    cats = r["categorias"]
    assert cats[oq.REVISAO]["n"] == 2 and cats[oq.SPEC]["n"] == 1 and cats[oq.OUTROS]["n"] == 1
    assert cats[oq.REVISAO]["pico"] == 300_001
    assert r["dentro_zona"] == 3 and r["fora_zona"] == 1  # 300.000 exato fica dentro, 300.001 fora


def test_markdown_e_svg_so_numeros_agregados(tmp_path):
    grava(tmp_path / "s1.jsonl", [chamada(0, i=1, o=2)])
    agente(tmp_path, "s1", "a", "ecc:tdd-guide", [chamada(1, i=10, o=5, cl=100)])
    r = oq.medir(tmp_path)
    md = oq.markdown(r, hoje=T0)
    svg = oq.svg(r)
    for texto in (md, svg):
        assert SEGREDO not in texto and "s1" not in texto.replace("s1.", "")
        assert str(tmp_path) not in texto
    assert "zona de genialidade" in md.lower() and "Implementação" in md
    assert svg.startswith("<svg") and 'role="img"' in svg and "<title" in svg and "<desc" in svg
    assert "<script" not in svg and "http" not in svg.replace("http://www.w3.org/2000/svg", "")
    assert "#131C2E" in svg and len(svg.encode()) <= 30_000


def test_pasta_vazia(tmp_path):
    r = oq.medir(tmp_path)
    assert r["n_agentes"] == 0 and r["orquestrador"]["pico"] == 0
