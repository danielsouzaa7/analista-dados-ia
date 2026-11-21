"""Conferência dos números da resposta (formato brasileiro) contra os resultados das ferramentas."""
import math
import re

_SUFIXO = r"\s*(?:milh[ãõ]o|milh[ãõ]es|bilh[ãõ]o|bilh[ãõ]es|mil)\b"
# notação científica como um número só: 1,58 × 10^-52, 1,58 x 10^{-52}, 1,58 \times 10^{-52}, 1,58·10⁻⁵², 1.58e-52
_EXP = r"10(?:\s*(?:\^|\*\*)\s*\{?\s*([-−]?\s*\d+)\s*\}?|([⁻⁰¹²³⁴⁵⁶⁷⁸⁹]+))"  # com ^ ou sobrescrito: "3 x 100" não é ciência
_CIENTIFICA = rf"(?:\s*(?:[×x·*]|\\times|\\cdot)\s*{_EXP}|[eE]([+-]?\d+))"
_SUPERESCRITOS = str.maketrans("⁻⁰¹²³⁴⁵⁶⁷⁸⁹−", "-0123456789-")
_BR = re.compile(rf"\d+(?:[.,]\d+)?{_CIENTIFICA}|\d{{1,3}}(?:\.\d{{3}})+(?:,\d+)?(?:\s?%|{_SUFIXO})?"
                 rf"|\d+(?:,\d+)?(?:\s?%|{_SUFIXO})?")
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
        cientifico = _decompor(original)
        if cientifico and cientifico[1] is not None:
            achados.append((original, float(f"{cientifico[0]}e{cientifico[1]}"), False))
            continue
        numero = re.match(r"[\d.,]+", original).group()
        valor = float(numero.replace(".", "").replace(",", "."))
        achados.append((original, valor, original == numero and "," not in numero and "." not in numero))
    return achados


def _decompor(texto: str) -> tuple[str, int | None] | None:
    """(mantissa com ponto, expoente ou None se não for científica) de um número isolado; None se não for número simples."""
    m = re.fullmatch(rf"\s*\$?\s*(\d*[.,]?\d+)(?:{_CIENTIFICA})?\s*\$?\s*", texto)
    if not m:
        return None
    expoente = m.group(2) or m.group(3) or m.group(4)
    return m.group(1).replace(",", "."), (int(re.sub(r"\s", "", expoente.translate(_SUPERESCRITOS))) if expoente else None)


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


# ---------- significância estatística sem p-valor ----------
_SUJEITO = r"diferen[çc]as?|efeitos?|associa[çc](?:ão|ões)|correla[çc](?:ão|ões)|rela[çc](?:ão|ões)|impactos?"
_AFIRMA = re.compile(
    r"\bestatisticamente\b"
    rf"|\b(?:{_SUJEITO})\b(?:\s+\S+){{0,2}}?\s+significativ\w*"
    r"|\b(?:é|são|foi|foram)\s+significativ\w*", re.I)
_INCAPACIDADE = re.compile(
    r"\bn[ãa]o\s+(?:foi|é|era)\s+poss[íi]vel\b|\bn[ãa]o\s+(?:consegui|pude)\b"
    r"|\bn[ãa]o\s+(?:posso|podemos|d[áa]\s+para|h[áa]\s+como|test(?:ei|amos)|calcul(?:ei|amos))\b"
    r"|\bseria\s+(?:preciso|necess[áa]rio)\b|\bsem\s+(?:um\s+)?teste\b", re.I)
# frase: termina em . ! ? seguido de espaço/fim (não quebra "R$ 1.234,56") ou em quebra de linha; ";" não separa
_FRASES = re.compile(r"[.!?](?=\s|$)|\n+")
# conectivos que invertem ou concluem: a oração depois deles vale por si
_CONECTIVOS = re.compile(r"\b(?:mas|porém|contudo|entretanto|no entanto|portanto|por isso)\b", re.I)
_ROTULO_P = r"\b(?:p[-_ ]?(?:valor|value)|valor[-_ ]?p|p)\b"
# entre o rótulo e o comparador: só espaço ou um qualificador entre parênteses
# (sem dígitos: um número dentro do parêntese tem de passar pela conferência)
_ENTRE = r"(?:\s*\(\s*[^\d)\n]{1,20}\)\s*|\s*)"
_NUM = rf"\d*[.,]?\d+(?:{_CIENTIFICA})?"
_P_VALOR = re.compile(rf"{_ROTULO_P}{_ENTRE}[=:<≤≈]\s*-?({_NUM})(?![\d.,]*\d)", re.I)
# na resposta o comparador pode ser em palavras e o número vir entre $...$: "o p-valor foi inferior a 1e-15",
# "o p-valor de $1,58 \times 10^{-52}$". Palavras de limite valem como "<"
_LIMITE = r"\binferior\s+a\b|\bmenor\s+(?:do\s+)?que\b|\babaixo\s+de\b"
_CITA_P = re.compile(rf"({_ROTULO_P}{_ENTRE})(?:\s+(?:foi|é|ficou|era))?\s*([<≤=≈]|{_LIMITE}|\bde\b|\bigual\s+a\b)"
                    rf"\s*\$?\s*({_NUM})(?![\d.,]*\d)", re.I)
TOLERANCIA_P = 0.01


def afirma_significancia(resposta: str) -> bool:
    """Afirma ou nega significância (forma assertiva), oração a oração; incapacidade na frase inteira não conta."""
    for frase in _FRASES.split(resposta):
        if _INCAPACIDADE.search(frase) and not _CONECTIVOS.search(frase):
            continue
        if any(_AFIRMA.search(o) and not _INCAPACIDADE.search(o) for o in _CONECTIVOS.split(frase)):
            return True
    return False


def _valor_p(texto: str) -> tuple[float, int, bool] | None:
    """(valor, casas decimais da mantissa, em notação científica) ou None se não for número ou estiver fora de [0, 1]."""
    d = _decompor(texto)
    if d is None:
        return None
    mantissa, expoente = d
    valor = float(f"{mantissa}e{expoente or 0}")
    return (valor, len(mantissa.partition(".")[2]), expoente is not None) if 0 <= valor <= 1 else None


def valores_p(saidas: list[str]) -> list[float]:
    achados = (_valor_p(m.group(1)) for s in saidas for m in _P_VALOR.finditer(s))
    return [a[0] for a in achados if a]


def tem_p_valor(saidas: list[str]) -> bool:
    return bool(valores_p(saidas))


def _sustentada(op: str, valor: float, casas: int, cientifica: bool, ps: list[float]) -> bool:
    if op in "<≤":
        return any(p < valor or (op == "≤" and p == valor) for p in ps)
    arredondado = (lambda p: float(f"{p:.{casas}e}")) if cientifica else (lambda p: round(p, casas))
    return any(abs(p - valor) <= TOLERANCIA_P * p or math.isclose(arredondado(p), valor, rel_tol=1e-9, abs_tol=0)
               for p in ps)


def sem_citacoes_de_p(resposta: str, saidas: list[str]) -> str:
    """Tira da resposta só as citações de p que alguma saída sustenta: "p = 0,08" bate com um p de 0.0805 e
    "p < 0,001" exige algum p menor. As demais seguem no texto e caem em numeros_nao_conferidos."""
    ps = valores_p(saidas)

    def tirar(m: re.Match) -> str:
        v = _valor_p(m.group(3))
        op = "<" if re.fullmatch(_LIMITE, m.group(2), re.I) else m.group(2)
        # só o comparador e o número saem: rótulo e qualificador ficam no texto
        return m.group(1) if v and _sustentada(op, *v, ps) else m.group()
    return _CITA_P.sub(tirar, resposta)


def conferir_numeros(resposta: str, fontes: list[str], saidas: list[str], pergunta: str) -> list[str]:
    """Números da resposta sem fonte, já descontadas as citações de p sustentadas pelas saídas do Python."""
    return numeros_nao_conferidos(sem_citacoes_de_p(resposta, saidas), fontes, pergunta)


def significancia_sem_p_valor(resposta: str, saidas: list[str]) -> bool:
    return afirma_significancia(resposta) and not tem_p_valor(saidas)
