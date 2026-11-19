import duckdb
import pytest

from app import perfil, sessions


@pytest.fixture
def con() -> duckdb.DuckDBPyConnection:
    c = duckdb.connect()
    c.execute("""CREATE TABLE t AS SELECT * FROM (VALUES
        ('SP', 10.5, DATE '2025-01-01', 'ana@exemplo.com', '123.456.789-09', '(11) 98888-7777', 1, 100),
        ('RJ', 20.0, DATE '2025-01-02', 'bia@exemplo.com', '98765432100',    '11 97777-6666',   2, 200),
        ('SP', NULL, DATE '2025-01-03', 'cai@exemplo.com', '111.222.333-44', '+55 21 96666-5555', 3, 300),
        ('SP', 5.0,  DATE '2025-01-04', 'dan@exemplo.com', '000.111.222-33', '21966665555',     4, 400)
    ) AS v(cidade, valor, dia, contato, doc, fone, pedido_id, qtd)""")
    yield c
    c.close()


def _col(p: dict, nome: str) -> dict:
    return next(c for c in p["colunas"] if c["nome"] == nome)


def test_estatisticas_basicas(con: duckdb.DuckDBPyConnection) -> None:
    p, _ = perfil.perfilar(con, "t")
    valor = _col(p, "valor")
    assert valor["nulos_pct"] == 25.0 and valor["distintos"] == 3
    assert valor["min"] == "5.0" and valor["max"] == "20.0" and "exemplos" not in valor
    cidade = _col(p, "cidade")
    assert cidade["distintos"] == 2 and sorted(cidade["exemplos"]) == ["RJ", "SP"] and cidade["pii"] is None


def test_pii_por_conteudo_e_por_nome(con: duckdb.DuckDBPyConnection) -> None:
    p, grounding = perfil.perfilar(con, "t")
    assert _col(p, "contato")["pii"] == "email"
    assert _col(p, "doc")["pii"] == "cpf"
    assert _col(p, "fone")["pii"] == "telefone"
    for nome in ("contato", "doc", "fone"):
        assert "exemplos" not in _col(p, nome)
    assert "ana@exemplo.com" not in grounding and "123.456.789-09" not in grounding
    assert _col(p, "cidade")["pii"] is None and _col(p, "pedido_id")["pii"] is None


def test_pii_por_nome_da_coluna() -> None:
    assert perfil.detectar_pii("CPF_cliente", []) == "cpf"
    assert perfil.detectar_pii("celular", []) == "telefone"
    assert perfil.detectar_pii("email", []) == "email"
    assert perfil.detectar_pii("cidade", ["a@b.com", "x", "y"]) is None  # só 33% casam
    assert perfil.detectar_pii("c", ["a@b.com", "x@y.org", None, "z"]) == "email"  # 2 de 3 valores não nulos


def test_grounding_lista_valores_de_categoricas_nao_pii(con: duckdb.DuckDBPyConnection) -> None:
    _, grounding = perfil.perfilar(con, "t")
    assert "t.cidade" in grounding and "RJ" in grounding and "SP" in grounding
    assert "t.valor" not in grounding


def test_grounding_nao_lista_acima_de_30_distintos() -> None:
    c = duckdb.connect()
    c.execute("CREATE TABLE m AS SELECT 'v' || i AS nome FROM range(40) r(i)")
    p, grounding = perfil.perfilar(c, "m")
    assert grounding == "" and len(_col(p, "nome")["exemplos"]) == 5


def test_falha_do_banco_devolve_perfil_minimo() -> None:
    c = duckdb.connect()
    c.execute("CREATE TABLE x AS SELECT 1 AS a")
    p, grounding = perfil.perfilar(c, "nao_existe", colunas=[{"nome": "a", "tipo": "INTEGER"}])
    assert p["colunas"] == [{"nome": "a", "tipo": "INTEGER", "nulos_pct": None, "distintos": None, "pii": None}]
    assert grounding == ""


def test_perguntas_sugeridas_por_tipo() -> None:
    tabelas = [{"nome": "t", "perfil": {"colunas": [
        {"nome": "cidade", "tipo": "VARCHAR", "distintos": 5, "pii": None},
        {"nome": "email", "tipo": "VARCHAR", "distintos": 5, "pii": "email"},
        {"nome": "pedido_id", "tipo": "BIGINT", "distintos": 100, "pii": None},
        {"nome": "valor", "tipo": "DOUBLE", "distintos": 90, "pii": None},
        {"nome": "tempo", "tipo": "INTEGER", "distintos": 50, "pii": None},
        {"nome": "dia", "tipo": "DATE", "distintos": 30, "pii": None}]}}]
    qs = perfil.perguntas_sugeridas(tabelas)
    assert len(qs) == 4
    assert any("cidade" in q and "valor" in q for q in qs)
    assert any("dia" in q for q in qs) and any("valor" in q and "tempo" in q for q in qs)
    assert not any("email" in q or "pedido_id" in q for q in qs)


def test_perguntas_sugeridas_sem_perfil() -> None:
    assert perfil.perguntas_sugeridas([{"nome": "t", "colunas": []}]) == []


def test_sessao_csv_ja_traz_perfil() -> None:
    s = sessions.criar_de_csv("d.csv", b"regiao,valor\nNorte,100\nSul,250\nSul,50\n")
    cols = s.tabelas[0]["perfil"]["colunas"]
    assert [c["nome"] for c in cols] == ["regiao", "valor"] and cols[1]["max"] == "250"
    assert "d.regiao" in s.grounding and "Norte" in s.grounding
