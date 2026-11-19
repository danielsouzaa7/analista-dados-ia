import time
from pathlib import Path

import pytest

from app import sessions
from app.errors import ErroUsuario
from app.sql_tool import executar

CSV_A = b"x,y\n1,2\n3,4\n"
CSV_B = b"z\n99\n"


def test_criar_de_csv_devolve_esquema() -> None:
    s = sessions.criar_de_csv("Vendas 2024.csv", CSV_A)
    assert s.tabelas[0]["nome"] == "vendas_2024"
    assert s.tabelas[0]["linhas"] == 2
    assert [c["nome"] for c in s.tabelas[0]["colunas"]] == ["x", "y"]
    assert not list(s.caminho_db.parent.glob("*.csv"))


@pytest.mark.parametrize("nome,esperado", [("123.csv", "t_123"), ("###.csv", "dados")])
def test_nome_da_tabela(nome: str, esperado: str) -> None:
    assert sessions.criar_de_csv(nome, CSV_A).tabelas[0]["nome"] == esperado


def test_csv_grande_recusado() -> None:
    with pytest.raises(ErroUsuario, match="20 MB"):
        sessions.criar_de_csv("a.csv", b"a\n" + b"1\n" * (11 * 1024 * 1024))


def test_csv_invalido_recusado() -> None:
    with pytest.raises(ErroUsuario, match="Não consegui ler"):
        sessions.criar_de_csv("a.csv", b"")


def test_sessoes_isoladas() -> None:
    a = sessions.criar_de_csv("a.csv", CSV_A)
    b = sessions.criar_de_csv("b.csv", CSV_B)
    assert executar(a, "SELECT sum(x) FROM a").linhas == [(4,)]
    with pytest.raises(ErroUsuario):
        executar(a, "SELECT * FROM b")
    with pytest.raises(ErroUsuario, match="(?i)disabled by configuration|enable_external_access"):
        executar(a, f"SELECT * FROM read_csv('{b.caminho_db.as_posix()}')")
    with pytest.raises(ErroUsuario, match="(?i)disabled by configuration|enable_external_access"):
        executar(a, f"SELECT * FROM '{b.caminho_db.as_posix()}'")
    with pytest.raises(ErroUsuario):
        executar(a, f"ATTACH '{b.caminho_db.as_posix()}' AS o")


def test_obter_desconhecido() -> None:
    with pytest.raises(ErroUsuario, match="Sessão expirada"):
        sessions.obter("nao-existe")


def test_expiracao_apaga_pasta(monkeypatch: pytest.MonkeyPatch) -> None:
    s = sessions.criar_de_csv("a.csv", CSV_A)
    pasta = s.caminho_db.parent
    assert pasta.exists()
    monkeypatch.setattr(time, "time", lambda: s.ultimo_uso + 3601)
    sessions.limpar_expiradas()
    assert not pasta.exists()
    with pytest.raises(ErroUsuario):
        sessions.obter(s.id)


def test_limpar_na_inicializacao(pasta_sessoes: Path) -> None:
    (pasta_sessoes / "velha").mkdir(parents=True)
    sessions.limpar_tudo()
    assert not pasta_sessoes.exists()


def test_repr_nao_mostra_url_postgres() -> None:
    sessao = sessions.Sessao(id="1", tipo="postgres", pg_url="postgresql://u:senhaSecreta123@h/d")
    assert "senhaSecreta123" not in repr(sessao)


def test_limpar_expiradas_tolera_corrida(monkeypatch: pytest.MonkeyPatch) -> None:
    class DictCorrida(dict):
        def items(self):  # outro thread já removeu a sessão depois do snapshot
            return [("fantasma", sessions.Sessao(id="fantasma", tipo="csv", ultimo_uso=0.0))]

    monkeypatch.setattr(sessions, "SESSOES", DictCorrida())
    sessions.limpar_expiradas()  # não pode levantar KeyError


def test_historico_e_isolado_por_sessao() -> None:
    a = sessions.criar_de_csv("a.csv", b"x\n1\n")
    b = sessions.criar_de_csv("b.csv", b"x\n1\n")
    a.historico.append({"pergunta": "oi"})
    assert b.historico == [] and a.turnos == 0 and a.grounding == ""


def test_perfil_do_postgres_usa_amostra_e_nao_derruba_a_sessao(monkeypatch) -> None:
    import duckdb

    from app import perfil, sql_tool

    con = duckdb.connect()
    con.execute("CREATE TABLE t AS SELECT * FROM (VALUES ('SP', 1), ('RJ', 2)) v(cidade, n)")
    amostras: list = []
    original = perfil.perfilar
    monkeypatch.setattr(perfil, "perfilar", lambda *a, **k: (amostras.append(k.get("amostra")), original(*a, **k))[1])
    monkeypatch.setattr(sql_tool, "abrir", lambda sessao: con)
    sessao = sessions.Sessao(id="p", tipo="postgres", tabelas=[
        {"nome": "t", "colunas": [{"nome": "cidade", "tipo": "VARCHAR"}, {"nome": "n", "tipo": "INTEGER"}]}])
    sessions._perfilar_postgres(sessao)
    assert amostras == [5000] and sessao.tabelas[0]["perfil"]["colunas"][0]["distintos"] == 2
    assert "t.cidade" in sessao.grounding
