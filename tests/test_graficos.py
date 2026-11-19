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


def test_eixo_decimal_ordena_como_numero_e_aparece_sem_zeros_sobrando() -> None:
    linhas = [(Decimal("10"), 1), (Decimal("9"), 5), (Decimal("2.5"), 3)]
    g = moldar("tendencia", ["x", "v"], linhas)
    assert [p["x"] for p in g["dados"]] == [2.5, 9, 10]
    assert "(10)" in g["resumo"] and "(10.0)" not in g["resumo"] and "(2,5)" in g["resumo"]


def test_resumo_nao_muda_o_ano_nem_inteiro_em_float() -> None:
    g = moldar("tendencia", ["ano", "v"], [(2024, 1), (2025.0, 3)])
    assert "(2024)" in g["resumo"] and "(2025)" in g["resumo"]


def test_valor_pequeno_nao_vira_zero_no_resumo() -> None:
    g = moldar("ranking", ["c", "v"], [("a", 0.004), ("b", 0.002)])
    assert "0,0040" in g["resumo"] and "(0,00)" not in g["resumo"]


@pytest.mark.parametrize("r_alvo,forca", [(0.35, "moderada"), (0.65, "forte"), (0.2, "fraca")])
def test_forca_da_correlacao_usa_cortes_do_front(r_alvo: float, forca: str) -> None:
    # y = r*x + ruído ortogonal: r exato com 4 pontos (x centrado, ruído de soma e produto nulos com x)
    xs = [-3.0, -1.0, 1.0, 3.0]
    ruido = [1.0, -1.0, -1.0, 1.0]
    k = r_alvo * math.sqrt(sum(v * v for v in xs) / sum(v * v for v in ruido)) * math.sqrt(1 / r_alvo**2 - 1)
    linhas = [(x, r_alvo * x + k * n) for x, n in zip(xs, ruido, strict=True)]
    g = moldar("dispersao", ["x", "y"], linhas)
    assert math.isclose(g["dados"]["tendencia"]["r"], r_alvo, abs_tol=1e-9) and f"Relação {forca}" in g["resumo"]


def test_dispersao_com_variancia_quase_nula_nao_tem_tendencia() -> None:
    g = moldar("dispersao", ["x", "y"], [(0, 0.1), (1, 0.1), (2, 0.1)])  # a média de 0.1 em float deixa um resíduo
    assert g["dados"]["tendencia"] is None


def test_tendencia_serie_de_referencia_ignora_primeiro_ponto_nulo_e_mantem_o_ultimo() -> None:
    linhas = [(0, None, "B"), (1, 5, "A"), (2, 6, "A"), (3, 7, "B")]
    g = moldar("tendencia", ["t", "v", "s"], linhas, serie="s")
    assert "subiu de 5 (1) para 6 (2)" in g["resumo"]
    grande = [(i, i, "") for i in range(1000)]
    g = moldar("tendencia", ["t", "v", "s"], grande, serie="s")
    assert g["dados"][-1]["x"] == 999


@pytest.mark.parametrize("tipo,linhas,extra", [
    ("ranking", [("a", float("nan")), ("b", float("inf")), ("c", 1e308), ("d", 1e308)], {}),
    ("composicao", [("a", 1e308), ("b", 1e308), ("c", -float("inf"))], {}),
    ("tendencia", [(float("nan"), 1), (float("inf"), 2), (1, 1e308), (2, 1e308), (3, -1e308)], {}),
    ("mapa_calor", [("a", float("inf"), 1e308), ("b", 1, 1e308), ("c", 2, float("nan"))], {"valor": "v"}),
    ("dispersao", [(1e200, 1e200), (2e200, 5e200), (-3e200, 1e200), (float("nan"), 1), (1, float("inf"))], {}),
])
def test_nada_nao_finito_sai_do_moldar(tipo: str, linhas: list, extra: dict) -> None:
    colunas = ["x", "y", "v"] if tipo == "mapa_calor" else ["x", "y"]
    try:
        g = moldar(tipo, colunas, linhas, **extra)
    except ErroUsuario:
        return  # recusar com texto também serve: o que não pode é emitir NaN/inf
    json.dumps(g, allow_nan=False)
