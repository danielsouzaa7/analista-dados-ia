import subprocess
import sys
from pathlib import Path

import duckdb
import pytest

from app import perfil, sessions
from app.errors import ErroUsuario


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


def _tabela_larga(n: int) -> duckdb.DuckDBPyConnection:
    c = duckdb.connect()
    c.execute("CREATE TABLE w AS SELECT " + ", ".join(f"1 AS c{i}" for i in range(n)))
    return c


def test_perfil_acima_do_teto_de_colunas_devolve_minimo() -> None:
    p, grounding = perfil.perfilar(_tabela_larga(perfil.MAX_COLUNAS_PERFIL + 1), "w")
    assert len(p["colunas"]) == perfil.MAX_COLUNAS_PERFIL + 1 and grounding == ""
    assert p["colunas"][0]["nulos_pct"] is None


def test_csv_com_mil_colunas_e_recusado_sem_derrubar_o_processo(tmp_path) -> None:
    # 1000 colunas estouram a pilha nativa do DuckDB: só um subprocesso prova que o processo sobrevive
    codigo = (
        "import sys; from pathlib import Path\n"
        "from app import config, sessions\nfrom app.errors import ErroUsuario\n"
        "config.SESSIONS_DIR = Path(sys.argv[1])\n"
        "csv = ','.join(f'c{i}' for i in range(1000)) + chr(10) + ','.join('1' for _ in range(1000)) + chr(10)\n"
        "try:\n    sessions.criar_de_csv('l.csv', csv.encode())\nexcept ErroUsuario:\n    print('recusado')\n")
    r = subprocess.run([sys.executable, "-c", codigo, str(tmp_path)], capture_output=True, text=True,
                       cwd=Path(__file__).resolve().parent.parent, timeout=60)
    assert r.returncode == 0 and "recusado" in r.stdout
    assert not any(tmp_path.iterdir())


@pytest.mark.parametrize("cabecalho", [",".join(f"c{i}" for i in range(201)), "a\u200bb,c", "a\x07b,c", "n" * 65 + ",c"])
def test_csv_com_cabecalho_ruim_e_recusado_e_apaga_a_pasta(pasta_sessoes, cabecalho: str) -> None:
    linha = ",".join("1" for _ in cabecalho.split(","))
    with pytest.raises(ErroUsuario):
        sessions.criar_de_csv("d.csv", f"{cabecalho}\n{linha}\n".encode())
    assert not pasta_sessoes.exists() or not list(pasta_sessoes.iterdir())  # a recusa antecipada nem cria a pasta


def test_csv_no_teto_de_colunas_e_aceito() -> None:
    cab = ",".join(f"c{i}" for i in range(perfil.MAX_COLUNAS_PERFIL))
    s = sessions.criar_de_csv("d.csv", f"{cab}\n{','.join('1' for _ in range(perfil.MAX_COLUNAS_PERFIL))}\n".encode())
    assert len(s.tabelas[0]["colunas"]) == perfil.MAX_COLUNAS_PERFIL


def test_pii_numerica_nao_expoe_minimo_nem_maximo() -> None:
    c = duckdb.connect()
    c.execute("CREATE TABLE p AS SELECT * FROM (VALUES (12345678901, 11987654321, 5), (23456789012, 11976543210, 7), "
              "(34567890123, 11965432109, 9)) v(documento, fone, qtd)")
    p, _ = perfil.perfilar(c, "p")
    assert _col(p, "fone")["pii"] == "telefone" and "min" not in _col(p, "fone")
    assert _col(p, "documento")["pii"] == "cpf" and "max" not in _col(p, "documento")
    assert _col(p, "qtd")["pii"] is None and _col(p, "qtd")["min"] == "5" and "exemplos" not in _col(p, "qtd")


@pytest.mark.parametrize("nome", ["E-mail", "CPF Cliente", "cpfCliente", "Telefone (celular)", "clienteCpf", "E_MAIL"])
def test_pii_por_nome_variacoes(nome: str) -> None:
    assert perfil.detectar_pii(nome, []) is not None
    assert perfil._minimo([{"nome": nome, "tipo": "VARCHAR"}])["colunas"][0]["pii"] is not None


@pytest.mark.parametrize("nome", ["cpfs_pendentes_x1", "telefonema", "emailing", "profone"])
def test_pii_por_nome_nao_pega_palavra_parecida(nome: str) -> None:
    assert perfil.detectar_pii(nome, []) is None


def test_id_de_texto_com_onze_digitos_nao_e_pii() -> None:
    assert perfil.detectar_pii("pedido_id", ["00012345678", "00012345679"]) is None
    assert perfil.detectar_pii("codigo", ["00012345678", "00012345679"]) == "cpf"


def test_grounding_corta_nome_de_coluna_em_64_caracteres() -> None:
    c = duckdb.connect()
    nome = "x" * 80
    c.execute(f'CREATE TABLE g AS SELECT * FROM (VALUES (\'a\'), (\'b\')) v("{nome}")')
    _, grounding = perfil.perfilar(c, "g")
    assert "x" * 64 in grounding and "x" * 65 not in grounding


@pytest.mark.parametrize("nome", ["usuario_id", "id_cliente", "cliente_id"])
def test_pii_formatada_em_coluna_de_id_e_marcada(nome: str) -> None:
    assert perfil.detectar_pii(nome, ["ana@exemplo.com", "bia@exemplo.com"]) == "email"
    assert perfil.detectar_pii(nome, ["000.456.789-10", "111.456.789-10"]) == "cpf"
    assert perfil.detectar_pii(nome, ["00012345678", "00012345679"]) is None


def test_coluna_inteira_com_epoch_nao_e_telefone() -> None:
    assert perfil.detectar_pii("criado", ["1700000000", "1700000001"], inteira=True) is None
    assert perfil.detectar_pii("fone_x", ["11987654321", "11976543210"], inteira=True) == "telefone"
    assert perfil.detectar_pii("codigo", ["1198765432", "1197654321"]) == "telefone"


@pytest.mark.parametrize("nome", ["telefone2", "email1", "cpf_2"])
def test_pii_por_nome_aceita_digito_depois_da_palavra(nome: str) -> None:
    assert perfil.detectar_pii(nome, []) is not None


def test_pii_com_espacos_e_marcada() -> None:
    assert perfil.detectar_pii("doc", ["529 982 247 25", "111 444 777 35"]) == "cpf"
    assert perfil.detectar_pii("contato", ["(11) 98765 4321", "(21) 91234 5678"]) == "telefone"
