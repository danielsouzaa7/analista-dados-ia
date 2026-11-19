"""Conferência dos números da resposta (formato brasileiro) contra os resultados das ferramentas."""
import re

_SUFIXO = r"\s*(?:milh[ãõ]o|milh[ãõ]es|bilh[ãõ]o|bilh[ãõ]es|mil)\b"
_BR = re.compile(rf"\d{{1,3}}(?:\.\d{{3}})+(?:,\d+)?(?:\s?%|{_SUFIXO})?|\d+(?:,\d+)?(?:\s?%|{_SUFIXO})?")
_MAQUINA = re.compile(r"-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?")
_INGLES = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?")  # saída Python: 1,234,567.89
_BR_NOS_RESULTADOS = re.compile(r"\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+,\d+")


def _multiplicador(original: str) -> float:
    if re.search(r"bilh", original):
        return 1e9
    return 1e6 if re.search(r"milh", original) else 1e3 if original.endswith("mil") else 1


def _br(texto: str) -> list[tuple[str, float, bool]]:
    """(texto original, valor, é inteiro simples) para cada número em formato brasileiro."""
    achados = []
    for m in _BR.finditer(texto):
        original = m.group()
        numero = re.match(r"[\d.,]+", original).group()
        valor = float(numero.replace(".", "").replace(",", "."))
        achados.append((original, valor, original == numero and "," not in numero and "." not in numero))
    return achados


def _bate(a: float, t: float) -> bool:
    return (a == 0 and t == 0) or abs(a - t) <= 0.01 * abs(t)


def _alvos(resultados: list[str]) -> list[float]:
    alvos = []
    for r in resultados:
        alvos += [abs(float(n.group())) for n in _MAQUINA.finditer(r)]
        alvos += [float(n.group().replace(",", "")) for n in _INGLES.finditer(r)]
        alvos += [v for _, v, _ in _br_resultado(r)]
    return alvos


def _br_resultado(texto: str) -> list[tuple[str, float, bool]]:
    return [(m.group(), float(m.group().replace(".", "").replace(",", ".")), False)
            for m in _BR_NOS_RESULTADOS.finditer(texto)]


def numeros_nao_conferidos(resposta: str, resultados: list[str], pergunta: str) -> list[str]:
    alvos = _alvos(resultados)
    da_pergunta = {v for _, v, _ in _br(pergunta)}
    falhas = []
    for original, valor, inteiro in _br(resposta):
        if (inteiro and 0 <= valor <= 10) or valor in da_pergunta:
            continue
        candidatos = [valor, valor / 100] if original.endswith("%") else [valor, valor * _multiplicador(original)]
        if not any(_bate(a, t) for a in candidatos for t in alvos):
            falhas.append(original)
    return falhas
