"""Perfil dos dados (nulos, distintos, faixa, exemplos), detecção de dado pessoal e perguntas sugeridas."""
import re
import threading

import duckdb

LIMITE_VALORES = 30  # categórica com até isso de valores distintos entra inteira no prompt
AMOSTRA_PII = 200
MAX_EXEMPLOS = 5
MIN_PII = 0.6
MAX_TABELAS_PERFIL = 10
MAX_COLUNAS_PERFIL = 200  # acima disso o SELECT único de agregados estoura a pilha nativa do DuckDB
MAX_NOME = 64

_PII = {
    "cpf": re.compile(r"\d{3}\.?\d{3}\.?\d{3}-?\d{2}"),
    "email": re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+"),
    "telefone": re.compile(r"(\+?55)?\s?\(?\d{2}\)?\s?9?\d{4}-?\d{4}"),
}
# Palavra inteira, também em camelCase ("cpfCliente"): por isso o (?i:...) só na palavra e não no limite.
_NOME_PII = re.compile(
    r"(?:^|[^A-Za-z0-9]|(?<=[a-z0-9])(?=[A-Z]))((?i:cpf|e[-_ ]?mail|telefone|celular|fone))(?:$|[^A-Za-z0-9]|(?=[A-Z]))")
_INTEIRO = re.compile(r"^U?(TINY|SMALL|BIG|HUGE)?INT(EGER)?$", re.I)
_NUMERICO = re.compile(r"^(U?(TINY|SMALL|BIG|HUGE)?INT(EGER)?|DOUBLE|FLOAT\d?|REAL|DECIMAL.*|NUMERIC.*)$", re.I)
_DATA = re.compile(r"^(DATE|TIMESTAMP.*)$", re.I)
_ID = re.compile(r"(?:^|_)id(?:$|_)", re.I)


def _aspas(nome: str) -> str:
    return '"' + nome.replace('"', '""') + '"'


def detectar_pii(nome: str, valores: list) -> str | None:
    """'cpf' | 'email' | 'telefone' | None: pelo nome da coluna ou por >= 60% dos valores não nulos."""
    achado = _NOME_PII.search(nome)
    if achado:
        palavra = achado.group(1).lower()
        return "email" if "mail" in palavra else "cpf" if palavra == "cpf" else "telefone"
    if _ID.search(nome):  # id de texto com 11 dígitos não é CPF
        return None
    textos = [str(v).strip() for v in valores if v is not None]
    for tipo, regex in _PII.items():
        if textos and sum(bool(regex.fullmatch(t)) for t in textos) / len(textos) >= MIN_PII:
            return tipo
    return None


def _minimo(colunas: list[dict]) -> dict:
    return {"colunas": [{"nome": c["nome"], "tipo": c["tipo"], "nulos_pct": None, "distintos": None,
                         "pii": detectar_pii(c["nome"], [])}
                        for c in colunas]}


def _estatisticas(con: duckdb.DuckDBPyConnection, src: str, colunas: list[dict]) -> list[tuple]:
    partes = ["count(*)"]
    for c in colunas:
        q = _aspas(c["nome"])
        partes += [f"count({q})", f"count(DISTINCT {q})"]
        faixa = _NUMERICO.match(c["tipo"]) or _DATA.match(c["tipo"])
        partes += [f"min({q})::VARCHAR", f"max({q})::VARCHAR"] if faixa else ["NULL", "NULL"]
    linha = con.execute(f"SELECT {', '.join(partes)} FROM {src}").fetchone()
    return [linha[1 + 4 * i: 5 + 4 * i] for i in range(len(colunas))] + [linha[0]]


def _valores(con: duckdb.DuckDBPyConnection, src: str, coluna: str) -> list[str]:
    q = _aspas(coluna)
    rows = con.execute(f"SELECT DISTINCT {q}::VARCHAR FROM {src} WHERE {q} IS NOT NULL LIMIT {AMOSTRA_PII}").fetchall()
    return sorted(r[0] for r in rows)


def _limpo(valor: str) -> str:
    return " ".join(valor.split())[:40]


def _coluna(con: duckdb.DuckDBPyConnection, src: str, tabela: str, c: dict, est: tuple, total: int
            ) -> tuple[dict, str]:
    nn, distintos, minimo, maximo = est
    item = {"nome": c["nome"], "tipo": c["tipo"],
            "nulos_pct": round(100 * (total - nn) / total, 1) if total else 0.0, "distintos": distintos}
    texto = c["tipo"].upper() == "VARCHAR"
    # Coluna inteira também é amostrada: CPF e telefone sem pontuação viram BIGINT.
    valores = _valores(con, src, c["nome"]) if texto or _INTEIRO.match(c["tipo"]) else []
    item["pii"] = detectar_pii(c["nome"], valores)
    if minimo is not None and item["pii"] is None:  # faixa de dado pessoal é dado pessoal
        item.update(min=minimo, max=maximo)
    if texto and item["pii"] is None:
        item["exemplos"] = [_limpo(v) for v in valores[:MAX_EXEMPLOS]]
        if distintos <= LIMITE_VALORES:
            return item, f"- {tabela}.{c['nome'][:MAX_NOME]}: valores possíveis: {', '.join(_limpo(v) for v in valores)}"
    return item, ""


def perfilar(con: duckdb.DuckDBPyConnection, tabela: str, colunas: list[dict] | None = None,
             amostra: int | None = None, timeout: float = 10) -> tuple[dict, str]:
    """(perfil {colunas: [...]}, texto de grounding). Falha ou tempo estourado -> perfil mínimo."""
    src = _aspas(tabela) if amostra is None else f"(SELECT * FROM {_aspas(tabela)} LIMIT {int(amostra)})"
    timer = threading.Timer(timeout, con.interrupt)
    timer.start()
    try:
        if colunas is None:
            colunas = [{"nome": r[0], "tipo": r[1]} for r in con.execute(f"DESCRIBE SELECT * FROM {src}").fetchall()]
        if len(colunas) > MAX_COLUNAS_PERFIL:
            return _minimo(colunas), ""
        *ests, total = _estatisticas(con, src, colunas)
        feitos = [_coluna(con, src, tabela, c, e, total) for c, e in zip(colunas, ests, strict=True)]
    except duckdb.Error:
        return _minimo(colunas or []), ""
    finally:
        timer.cancel()
    return {"colunas": [f[0] for f in feitos]}, "\n".join(f[1] for f in feitos if f[1])


def perguntas_sugeridas(tabelas: list[dict]) -> list[str]:
    """Até 4 perguntas por regras sobre os tipos (sem LLM)."""
    for t in tabelas:
        cols = t.get("perfil", {}).get("colunas", [])
        livres = [c for c in cols if not c.get("pii")]
        cat = [c["nome"] for c in livres if c["tipo"].upper() == "VARCHAR" and 2 <= (c.get("distintos") or 0) <= LIMITE_VALORES]
        num = [c["nome"] for c in livres if _NUMERICO.match(c["tipo"]) and not _ID.search(c["nome"])]
        data = [c["nome"] for c in livres if _DATA.match(c["tipo"])]
        perguntas = []
        if cat and num:
            perguntas.append(f"Qual {cat[0]} tem o maior total de {num[0]}?")
        if data and num:
            perguntas.append(f"Como {num[0]} evoluiu ao longo de {data[0]}?")
        if len(num) > 1:
            perguntas.append(f"Existe relação entre {num[0]} e {num[1]}?")
        if cat:
            perguntas.append(f"Qual a participação de cada {cat[0]} no total?")
        if perguntas:
            return perguntas[:4]
    return []
