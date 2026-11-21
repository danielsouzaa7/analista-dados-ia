import math
import runpy
from pathlib import Path

import numpy as np
import pytest

P = runpy.run_path(str(Path(__file__).parent.parent / "sandbox" / "preludio.py"))
p_bicaudal_t, welch, correlacao = P["p_bicaudal_t"], P["teste_t_welch"], P["teste_correlacao"]  # sem prefixo teste_: o pytest coletaria


def p_por_integracao(t: float, gl: float) -> float:
    """Fonte independente: integra a densidade t por trapézios (numpy), com troca u = atan(x)."""
    u = np.linspace(math.atan(abs(t)), math.pi / 2, 400_001)[:-1]  # o fim tem densidade ~0
    x = np.tan(u)
    logc = math.lgamma((gl + 1) / 2) - math.lgamma(gl / 2) - 0.5 * math.log(gl * math.pi)
    f = np.exp(logc - (gl + 1) / 2 * np.log1p(x * x / gl)) / np.cos(u) ** 2
    return float(2 * np.trapezoid(f, u))


@pytest.mark.parametrize("t,gl", [(2.228139, 10), (2.042272, 30), (1.959964, 1e7), (0, 5)])
def test_p_bicaudal_bate_com_a_tabela_t(t: float, gl: float) -> None:
    esperado = 1.0 if t == 0 else 0.05
    assert p_bicaudal_t(t, gl) == pytest.approx(esperado, abs=1e-5)


@pytest.mark.parametrize("t,gl", [(2.228139, 10), (1.0, 3), (3.5, 25), (-0.7, 120), (5.0, 2.5)])
def test_p_bate_com_a_integracao_numerica_independente(t: float, gl: float) -> None:
    assert p_bicaudal_t(t, gl) == pytest.approx(p_por_integracao(t, gl), abs=1e-6)


def test_gl_grande_nao_troca_pela_normal() -> None:
    assert p_bicaudal_t(2.5, 2e5) == pytest.approx(p_por_integracao(2.5, 2e5), abs=2e-8)


def test_welch_bate_com_a_formula() -> None:
    r = welch([1, 2, 3, 4, 5], [3, 4, 5, 6, 7])
    assert r.t == pytest.approx(-2.0) and r.gl == pytest.approx(8.0)
    assert r.p_valor == pytest.approx(0.0805, abs=1e-4)


def test_resultado_e_namedtuple_com_floats_e_repr_com_p_valor() -> None:
    r = welch([1, 2, 3, 4, 5], [3, 4, 5, 6, 7])
    assert all(type(v) is float for v in r) and "p_valor=" in repr(r)
    c = correlacao([1, 2, 3, 4], [1, 3, 2, 5])
    assert all(type(v) is float for v in c) and "p_valor=" in repr(c)


def test_t_enorme_da_p_minusculo_sem_erro() -> None:
    assert 0 <= p_bicaudal_t(15.557, 2976.68) < 1e-40


def test_gl_gigante_nao_estoura_iteracoes() -> None:
    # a normal só entra acima de 1e7 (antes de 1e5 ela errava ~1e-6); a fração contínua é exata abaixo disso
    assert p_bicaudal_t(1.959964, 1e7) == pytest.approx(math.erfc(1.959964 / math.sqrt(2)), abs=1e-7)
    assert p_bicaudal_t(2.5, 1e12) == pytest.approx(math.erfc(2.5 / math.sqrt(2)), abs=1e-7)
    assert p_bicaudal_t(2.5, math.inf) == pytest.approx(math.erfc(2.5 / math.sqrt(2)), abs=1e-12)


def test_correlacao_perfeita_da_p_zero() -> None:
    r = correlacao([1, 2, 3, 4], [2, 4, 6, 8])
    assert r.r == 1.0 and r.p_valor == 0.0


def test_correlacao_bate_com_a_tabela() -> None:
    # r crítico bicaudal 5% para 10 pares (gl 8) é 0,632
    r = correlacao(range(10), [0, 2, 1, 4, 3, 6, 5, 9, 7, 8])
    assert r.gl == 8.0 and 0 < r.p_valor < 0.01
    assert p_bicaudal_t(0.632 * math.sqrt(8 / (1 - 0.632**2)), 8) == pytest.approx(0.05, abs=1e-3)


def test_ignora_nan() -> None:
    com = welch([1, 2, 3, 4, 5, math.nan], [3, 4, 5, 6, 7])
    assert com.t == pytest.approx(-2.0)
    assert correlacao([1, 2, 3, 4, math.nan], [1, 3, 2, 5, 9]).gl == 2.0


@pytest.mark.parametrize("chamada", [
    lambda: welch([1], [1, 2]),
    lambda: welch([2, 2, 2], [2, 2, 2]),
    lambda: welch([math.nan, math.nan], [1, 2]),
    lambda: correlacao([1, 1, 1], [1, 2, 3]),
    lambda: correlacao([1, 2], [1, 2, 3]),
    lambda: correlacao([1, 2], [1, 2]),
])
def test_grupo_pequeno_ou_variancia_zero_levanta_erro_em_portugues(chamada) -> None:
    with pytest.raises(ValueError, match="[a-zç]"):
        chamada()


def test_infinito_na_amostra_tem_mensagem_propria() -> None:
    with pytest.raises(ValueError, match="infinit"):
        welch([1, 2, math.inf], [3, 4, 5])
    with pytest.raises(ValueError, match="infinit"):
        correlacao([1, 2, 3, -math.inf], [1, 2, 3, 4])
