"""Moldagem dos gráficos: o servidor entrega dados prontos por tipo (o front só desenha)."""
import math
import random
from collections.abc import Sequence
from decimal import Decimal

from app.errors import ErroUsuario

TIPOS = ("ranking", "tendencia", "composicao", "mapa_calor", "dispersao")
MAX_TOP, MAX_PARTES, MAX_PONTOS_TENDENCIA, MAX_SERIES = 12, 6, 400, 4
MAX_MAPA_X, MAX_MAPA_Y, MAX_DISPERSAO = 31, 24, 1500


def _num(v: object) -> float | None:
    if isinstance(v, bool) or not isinstance(v, (int, float, Decimal)):
        return None
    n = float(v)
    return n if math.isfinite(n) else None


def _rot(v: object) -> str:
    return "(vazio)" if v is None else str(v)


def _eixo(v: object) -> object:
    """Valor de eixo serializável: número como número, o resto como texto."""
    n = _num(v)
    return n if n is not None and not isinstance(v, Decimal) and not isinstance(v, str) else _rot(v)


def _fmt(n: float) -> str:
    texto = f"{n:,.0f}" if n == int(n) else f"{n:,.2f}"
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")


def _agrupar(pares: list[tuple[str, float]], maximo: int) -> list[dict]:
    """Ordena desc; o que passa do máximo vira 'Outros'."""
    ordem = sorted(pares, key=lambda p: p[1], reverse=True)
    dados = [{"rotulo": r, "valor": v} for r, v in ordem[:maximo]]
    if len(ordem) > maximo:
        dados.append({"rotulo": "Outros", "valor": sum(v for _, v in ordem[maximo:])})
    return dados


def _partes(colunas: Sequence[str], linhas: Sequence[tuple], x: str, y: str, maximo: int) -> tuple[list[dict], str]:
    pares = [(_rot(lin[0]), _num(lin[1])) for lin in _colunas(colunas, linhas, x, y)]
    pares = [(r, v) for r, v in pares if v is not None]
    if not pares:
        raise ErroUsuario("O resultado não tem valores numéricos para esse gráfico (sem dados).")
    dados = _agrupar(pares, maximo)
    total = sum(v for _, v in pares)
    maior, menor = max(pares, key=lambda p: p[1]), min(pares, key=lambda p: p[1])
    resumo = (f"Maior: {maior[0]} ({_fmt(maior[1])}). Menor: {menor[0]} ({_fmt(menor[1])}). "
              f"Total: {_fmt(total)}.")
    return dados, resumo


def _colunas(colunas: Sequence[str], linhas: Sequence[tuple], *nomes: str) -> list[tuple]:
    for nome in nomes:
        if nome not in colunas:
            raise ErroUsuario(f"Coluna '{nome}' não existe no resultado. Colunas: {', '.join(colunas)}.")
    idx = [colunas.index(n) for n in nomes]
    return [tuple(lin[i] for i in idx) for lin in linhas]


def _ordenar(itens: list, chave) -> list:
    try:
        return sorted(itens, key=chave)
    except TypeError:  # tipos misturados no eixo
        return sorted(itens, key=lambda i: str(chave(i)))


def _tendencia(colunas: Sequence[str], linhas: Sequence[tuple], x: str, y: str, serie: str | None) -> tuple[object, str]:
    nomes = (x, y, serie) if serie else (x, y)
    brutas = _colunas(colunas, linhas, *nomes)
    if serie:
        permitidas = list(dict.fromkeys(_rot(lin[2]) for lin in brutas))[:MAX_SERIES]
        brutas = [lin for lin in brutas if _rot(lin[2]) in permitidas]
    brutas = _ordenar(brutas, lambda lin: lin[0])
    grupos = {}
    for lin in brutas:
        grupos.setdefault(_rot(lin[2]) if serie else "", []).append(lin)
    passo = math.ceil(max(len(g) for g in grupos.values()) / (MAX_PONTOS_TENDENCIA // len(grupos)))
    pontos = []
    for rotulo, g in grupos.items():
        for lin in g[::passo]:
            ponto = {"x": _eixo(lin[0]), "valor": _num(lin[1])}
            if serie:
                ponto["serie"] = rotulo
            pontos.append(ponto)
    pontos = _ordenar(pontos, lambda p: p["x"])
    validos = [p for p in pontos if p["valor"] is not None and p.get("serie", pontos[0].get("serie")) == pontos[0].get("serie")]
    if not validos:
        raise ErroUsuario("O resultado não tem valores numéricos para esse gráfico (sem dados).")
    ini, fim = validos[0], validos[-1]
    alto, baixo = max(validos, key=lambda p: p["valor"]), min(validos, key=lambda p: p["valor"])
    sentido = "subiu" if fim["valor"] > ini["valor"] else "caiu" if fim["valor"] < ini["valor"] else "ficou estável"
    resumo = (f"Tendência: {sentido} de {_fmt(ini['valor'])} ({ini['x']}) para {_fmt(fim['valor'])} ({fim['x']}). "
              f"Máximo: {_fmt(alto['valor'])} ({alto['x']}). Mínimo: {_fmt(baixo['valor'])} ({baixo['x']}).")
    return pontos, resumo


def _mapa(colunas: Sequence[str], linhas: Sequence[tuple], x: str, y: str, valor: str | None) -> tuple[dict, str]:
    if not valor:
        raise ErroUsuario("O mapa de calor precisa do parâmetro valor (coluna numérica de cada célula).")
    brutas = _colunas(colunas, linhas, x, y, valor)
    xs = list(dict.fromkeys(_eixo(lin[0]) for lin in brutas))
    ys = list(dict.fromkeys(_eixo(lin[1]) for lin in brutas))
    if len(xs) > MAX_MAPA_X or len(ys) > MAX_MAPA_Y:
        raise ErroUsuario(f"O mapa de calor aceita até {MAX_MAPA_X} valores em x e {MAX_MAPA_Y} em y "
                          f"(veio {len(xs)}×{len(ys)}). Agrupe mais a consulta.")
    celulas = [[xs.index(_eixo(lin[0])), ys.index(_eixo(lin[1])), v] for lin in brutas if (v := _num(lin[2])) is not None]
    if not celulas:
        raise ErroUsuario("O resultado não tem valores numéricos para esse gráfico (sem dados).")
    alta, baixa = max(celulas, key=lambda c: c[2]), min(celulas, key=lambda c: c[2])
    resumo = (f"Maior valor: {_fmt(alta[2])} em {xs[alta[0]]} × {ys[alta[1]]}. "
              f"Menor: {_fmt(baixa[2])} em {xs[baixa[0]]} × {ys[baixa[1]]}.")
    return {"xs": xs, "ys": ys, "celulas": celulas}, resumo


def _minimos_quadrados(pts: list[tuple[float, float]]) -> dict | None:
    n = len(pts)
    mx, my = sum(p[0] for p in pts) / n, sum(p[1] for p in pts) / n
    sxx = sum((p[0] - mx) ** 2 for p in pts)
    syy = sum((p[1] - my) ** 2 for p in pts)
    if n < 2 or sxx == 0 or syy == 0:
        return None
    sxy = sum((p[0] - mx) * (p[1] - my) for p in pts)
    a = sxy / sxx
    return {"a": a, "b": my - a * mx, "r": sxy / math.sqrt(sxx * syy)}


def _dispersao(colunas: Sequence[str], linhas: Sequence[tuple], x: str, y: str) -> tuple[dict, str]:
    pts = [(a, b) for lin in _colunas(colunas, linhas, x, y) if (a := _num(lin[0])) is not None
           and (b := _num(lin[1])) is not None]
    if not pts:
        raise ErroUsuario("O resultado não tem valores numéricos para esse gráfico (sem dados).")
    tendencia = _minimos_quadrados(pts)
    if len(pts) > MAX_DISPERSAO:
        pts = [pts[i] for i in sorted(random.Random(0).sample(range(len(pts)), MAX_DISPERSAO))]
    if tendencia is None:
        resumo = f"{len(pts)} pontos; não há variação suficiente para calcular uma tendência."
    else:
        forca = "forte" if abs(tendencia["r"]) >= 0.7 else "moderada" if abs(tendencia["r"]) >= 0.4 else "fraca"
        sinal = "positiva" if tendencia["r"] > 0 else "negativa"
        resumo = f"Relação {forca} e {sinal} (r = {_fmt(tendencia['r'])}) em {len(pts)} pontos."
    return {"pontos": [list(p) for p in pts], "tendencia": tendencia}, resumo


def moldar(tipo: str, colunas: Sequence[str], linhas: Sequence[tuple], *, x: str, y: str, titulo: str,
           valor: str | None = None, serie: str | None = None, subtitulo: str | None = None) -> dict:
    """Devolve o gráfico do contrato; levanta ErroUsuario (texto que volta ao LLM) se não der."""
    if tipo not in TIPOS:
        raise ErroUsuario(f"Tipo de gráfico inválido. Use um destes: {', '.join(TIPOS)}.")
    if not linhas:
        raise ErroUsuario("A consulta não devolveu linhas (sem dados para o gráfico).")
    if tipo == "ranking":
        dados, resumo = _partes(colunas, linhas, x, y, MAX_TOP)
    elif tipo == "composicao":
        dados, resumo = _partes(colunas, linhas, x, y, MAX_PARTES)
    elif tipo == "tendencia":
        dados, resumo = _tendencia(colunas, linhas, x, y, serie)
    elif tipo == "mapa_calor":
        dados, resumo = _mapa(colunas, linhas, x, y, valor)
    else:
        dados, resumo = _dispersao(colunas, linhas, x, y)
    return {"tipo": tipo, "titulo": str(titulo)[:200], "subtitulo": str(subtitulo or "")[:200],
            "resumo": resumo, "x_nome": x, "y_nome": y, "dados": dados}
