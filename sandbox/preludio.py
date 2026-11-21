# Funções estatísticas prontas para a IA (sem scipy). Só numpy e a biblioteca padrão.
import math
from collections import namedtuple

import numpy as np

ResultadoTeste = namedtuple("ResultadoTeste", "t gl p_valor")
ResultadoCorrelacao = namedtuple("ResultadoCorrelacao", "r gl p_valor")
MAXIT = 10_000
GL_NORMAL = 1e7  # acima disso a t é a normal (erro < 2e-8); abaixo, a fração contínua é rápida e mais exata


def _fracao_continua(a, b, x):
    """Fração contínua da beta incompleta (Lentz modificado)."""
    tiny = 1e-300
    c, d = 1.0, 1.0 - (a + b) * x / (a + 1.0)
    d = 1.0 / (d if abs(d) > tiny else tiny)
    h = d
    for m in range(1, MAXIT + 1):
        for passo in (m * (b - m) * x / ((a + 2 * m - 1) * (a + 2 * m)),
                      -(a + m) * (a + b + m) * x / ((a + 2 * m) * (a + 2 * m + 1))):
            d = 1.0 + passo * d
            d = 1.0 / (d if abs(d) > tiny else tiny)
            c = 1.0 + passo / c
            c = c if abs(c) > tiny else tiny
            h *= d * c
        if abs(d * c - 1.0) < 1e-15 and passo != 0:
            break
    return h


def _beta_incompleta(a, b, x, y):
    """I_x(a, b), com y = 1 - x calculado à parte para não perder precisão."""
    if x <= 0.0:
        return 0.0
    if y <= 0.0:
        return 1.0
    frente = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log(y))
    if x < (a + 1.0) / (a + b + 2.0):
        return frente * _fracao_continua(a, b, x) / a
    return 1.0 - frente * _fracao_continua(b, a, y) / b


def p_bicaudal_t(t, gl):
    """P(|T| >= |t|) para a t de Student com gl graus de liberdade."""
    t, gl = abs(float(t)), float(gl)
    if math.isnan(t) or math.isnan(gl) or gl <= 0:
        raise ValueError("t e graus de liberdade precisam ser números válidos (gl > 0).")
    if t == 0.0:
        return 1.0
    if math.isinf(t):
        return 0.0
    if gl > GL_NORMAL:
        return float(math.erfc(t / math.sqrt(2.0)))
    base = gl + t * t
    return float(min(1.0, max(0.0, _beta_incompleta(gl / 2.0, 0.5, gl / base, t * t / base))))


def _limpar(valores, nome):
    v = np.asarray(valores, dtype=float).ravel()
    v = v[~np.isnan(v)]
    if not np.isfinite(v).all():
        raise ValueError(f"{nome} tem valores infinitos; remova-os antes do teste.")
    if len(v) < 2:
        raise ValueError(f"{nome} precisa de pelo menos 2 valores válidos (NaN é descartado).")
    return v


def teste_t_welch(a, b):
    """Teste t de Welch bicaudal entre dois grupos. Devolve (t, gl, p_valor)."""
    a, b = _limpar(a, "O primeiro grupo"), _limpar(b, "O segundo grupo")
    ea, eb = a.var(ddof=1) / len(a), b.var(ddof=1) / len(b)
    if ea + eb == 0:
        raise ValueError("Os dois grupos têm variância zero; o teste t não se aplica.")
    t = float((a.mean() - b.mean()) / math.sqrt(ea + eb))
    gl = float((ea + eb) ** 2 / (ea ** 2 / (len(a) - 1) + eb ** 2 / (len(b) - 1)))
    return ResultadoTeste(t, gl, p_bicaudal_t(t, gl))


def teste_correlacao(x, y):
    """Correlação de Pearson e seu p-valor bicaudal. Devolve (r, gl, p_valor)."""
    x, y = np.asarray(x, dtype=float).ravel(), np.asarray(y, dtype=float).ravel()
    if len(x) != len(y):
        raise ValueError("x e y precisam ter o mesmo tamanho.")
    ok = ~(np.isnan(x) | np.isnan(y))
    x, y = _limpar(x[ok], "x"), _limpar(y[ok], "y")
    if x.std() == 0 or y.std() == 0:
        raise ValueError("Uma das variáveis tem variância zero; a correlação não existe.")
    r = float(max(-1.0, min(1.0, np.corrcoef(x, y)[0, 1])))
    gl = float(len(x) - 2)
    if gl <= 0:
        raise ValueError("A correlação precisa de pelo menos 3 pares válidos.")
    if abs(r) == 1.0:
        return ResultadoCorrelacao(r, gl, 0.0)
    return ResultadoCorrelacao(r, gl, p_bicaudal_t(r * math.sqrt(gl / (1.0 - r * r)), gl))
