import json
import math
from datetime import date
from decimal import Decimal

import pytest

from app import graficos
from app.errors import ErroUsuario


def moldar(tipo: str, colunas: list[str], linhas: list[tuple], **kw: object) -> dict:
    args = {"x": colunas[0], "y": colunas[1], "titulo": "T", **kw}
    return graficos.moldar(tipo, colunas, linhas, **args)


def test_ranking_ordena_e_agrupa_outros() -> None:
    linhas = [(f"c{i}", i) for i in range(1, 16)]
    g = moldar("ranking", ["cat", "v"], linhas)
    assert g["tipo"] == "ranking" and g["x_nome"] == "cat" and g["y_nome"] == "v"
    assert len(g["dados"]) == 13
    assert g["dados"][0] == {"rotulo": "c15", "valor": 15.0}
    assert g["dados"][-1] == {"rotulo": "Outros", "valor": float(1 + 2 + 3)}
    assert "c15" in g["resumo"] and "120" in g["resumo"]


def test_ranking_nan_vira_nulo_e_sai() -> None:
    g = moldar("ranking", ["c", "v"], [("a", 5), ("b", float("nan")), ("c", None), ("d", Decimal("2.5"))])
    assert [d["rotulo"] for d in g["dados"]] == ["a", "d"]
    json.dumps(g, allow_nan=False)


def test_tendencia_ordena_series_e_limites() -> None:
    linhas = [(date(2025, m, 1), m * 10, "A" if m % 2 else "B") for m in (3, 1, 2)]
    g = moldar("tendencia", ["mes", "v", "s"], linhas, serie="s")
    assert [p["x"] for p in g["dados"]] == ["2025-01-01", "2025-02-01", "2025-03-01"]
    assert {p["serie"] for p in g["dados"]} == {"A", "B"}
    assert "tendência" in g["resumo"].lower() or "subiu" in g["resumo"]


def test_tendencia_corta_em_400_pontos_e_4_series() -> None:
    linhas = [(i, i, f"s{i % 6}") for i in range(2000)]
    g = moldar("tendencia", ["t", "v", "s"], linhas, serie="s")
    assert len(g["dados"]) <= 400 and len({p["serie"] for p in g["dados"]}) == 4


def test_tendencia_nan_vira_nulo() -> None:
    g = moldar("tendencia", ["t", "v"], [(1, 1), (2, float("inf")), (3, 3)])
    assert g["dados"][1]["valor"] is None
    json.dumps(g, allow_nan=False)


def test_composicao_seis_mais_outros() -> None:
    g = moldar("composicao", ["c", "v"], [(f"c{i}", 10 + i) for i in range(9)])
    assert len(g["dados"]) == 7 and g["dados"][-1]["rotulo"] == "Outros"
    assert sum(d["valor"] for d in g["dados"]) == sum(10 + i for i in range(9))


def test_mapa_de_calor() -> None:
    linhas = [("seg", 12, 5), ("seg", 13, 7), ("ter", 12, 3)]
    g = graficos.moldar("mapa_calor", ["dia", "hora", "n"], linhas, x="dia", y="hora", valor="n", titulo="T")
    d = g["dados"]
    assert d["xs"] == ["seg", "ter"] and d["ys"] == [12, 13]
    assert [0, 1, 7.0] in d["celulas"] and len(d["celulas"]) == 3
    assert "7" in g["resumo"]


def test_mapa_de_calor_exige_valor_e_respeita_limite() -> None:
    with pytest.raises(ErroUsuario, match="valor"):
        moldar("mapa_calor", ["a", "b", "c"], [(1, 1, 1)])
    muitos = [(i, 0, 1) for i in range(32)]
    with pytest.raises(ErroUsuario, match="31"):
        graficos.moldar("mapa_calor", ["a", "b", "c"], muitos, x="a", y="b", valor="c", titulo="T")


def test_dispersao_regressao_e_r() -> None:
    g = moldar("dispersao", ["x", "y"], [(i, 2 * i + 1) for i in range(10)])
    t = g["dados"]["tendencia"]
    assert math.isclose(t["a"], 2) and math.isclose(t["b"], 1) and math.isclose(t["r"], 1)
    assert len(g["dados"]["pontos"]) == 10


def test_dispersao_amostra_fixa_acima_de_1500() -> None:
    linhas = [(i, i % 7) for i in range(3000)]
    a = moldar("dispersao", ["x", "y"], linhas)
    b = moldar("dispersao", ["x", "y"], linhas)
    assert len(a["dados"]["pontos"]) == 1500 and a["dados"]["pontos"] == b["dados"]["pontos"]


def test_dispersao_sem_variacao_nao_tem_tendencia() -> None:
    g = moldar("dispersao", ["x", "y"], [(1, 5), (1, 6)])
    assert g["dados"]["tendencia"] is None


def test_tipo_e_colunas_invalidos() -> None:
    with pytest.raises(ErroUsuario, match="Tipo de gráfico inválido"):
        moldar("barra", ["a", "b"], [(1, 1)])
    with pytest.raises(ErroUsuario, match="Coluna 'zz'"):
        graficos.moldar("ranking", ["a", "b"], [(1, 1)], x="a", y="zz", titulo="T")


def test_titulos_truncados_e_sem_dados() -> None:
    g = moldar("ranking", ["a", "b"], [("a", 1)], titulo="t" * 300, subtitulo="s" * 300)
    assert len(g["titulo"]) == 200 and len(g["subtitulo"]) == 200
    with pytest.raises(ErroUsuario, match="sem dados"):
        moldar("ranking", ["a", "b"], [])
