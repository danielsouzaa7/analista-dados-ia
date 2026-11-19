import os
import socket

import pytest

from app import config, sessions, sql_tool
from app.errors import ErroUsuario
from app.sessions import Sessao
from app.sql_tool import executar, para_texto, redigir, validar_sql

CSV = b"x,y\n1,2\n3,4\n5,6\n"
PG_TEST_URL = os.environ.get("PG_TEST_URL")


@pytest.fixture
def s() -> Sessao:
    return sessions.criar_de_csv("dados.csv", CSV)


def test_teto_de_celulas_reduz_as_linhas_de_consulta_larga(s: Sessao, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sql_tool, "MAX_CELULAS", 4)
    r = executar(s, "SELECT x, y FROM dados ORDER BY x", limite=100)
    assert r.linhas == [(1, 2), (3, 4)] and r.truncado  # 4 células / 2 colunas = 2 linhas
    assert executar(s, "SELECT x FROM dados ORDER BY x", limite=100).linhas == [(1,), (3,), (5,)]


def test_select_ok(s: Sessao) -> None:
    r = executar(s, "SELECT x, y FROM dados ORDER BY x")
    assert r.colunas == ["x", "y"]
    assert r.linhas == [(1, 2), (3, 4), (5, 6)]
    assert not r.truncado


def test_with_ok(s: Sessao) -> None:
    assert executar(s, "WITH t AS (SELECT x FROM dados) SELECT count(*) FROM t").linhas == [(3,)]


def test_limite_de_linhas(s: Sessao) -> None:
    r = executar(s, "SELECT * FROM range(10)", limite=3)
    assert len(r.linhas) == 3 and r.truncado


@pytest.mark.parametrize("sql", [
    "INSERT INTO dados VALUES (1, 2)",
    "UPDATE dados SET x = 1",
    "DELETE FROM dados",
    "DROP TABLE dados",
    "CREATE TABLE t (a INT)",
    "COPY dados TO 'saida.csv'",
    "ATTACH 'outro.db' AS o",
    "PRAGMA database_list",
    "SET threads = 1",
    "SELECT 1; DROP TABLE dados",
    "SELECT 1; SELECT 2",
    "",
])
def test_comandos_recusados(s: Sessao, sql: str) -> None:
    with pytest.raises(ErroUsuario):
        validar_sql(sql)
    with pytest.raises(ErroUsuario):
        executar(s, sql)


def test_dados_intactos_apos_recusa(s: Sessao) -> None:
    with pytest.raises(ErroUsuario):
        executar(s, "DROP TABLE dados")
    assert executar(s, "SELECT count(*) FROM dados").linhas == [(3,)]


def test_le_arquivo_fora_da_sessao(s: Sessao, tmp_path) -> None:
    alvo = tmp_path / "segredo.csv"
    alvo.write_text("a\nsegredo\n")
    with pytest.raises(ErroUsuario):
        executar(s, f"SELECT * FROM read_csv('{alvo.as_posix()}')")


def test_rede_bloqueada(s: Sessao) -> None:
    with pytest.raises(ErroUsuario):
        executar(s, "SELECT * FROM read_csv('https://example.com/x.csv')")


def test_timeout(s: Sessao) -> None:
    with pytest.raises(ErroUsuario, match="tempo limite"):
        executar(s, "SELECT count(*) FROM range(1000000000000) a, range(1000000) b", timeout=1)


def test_para_texto_corta_linhas(s: Sessao) -> None:
    r = executar(s, "SELECT * FROM range(100) t(n)")
    texto = para_texto(r, max_linhas=50)
    assert texto.startswith("n\n0\n")
    assert texto.endswith("(100 linhas no total)")
    assert "\n50\n" not in texto and "\n49\n" in texto


def test_para_texto_corta_caracteres(s: Sessao) -> None:
    r = executar(s, "SELECT repeat('a', 5000) AS c FROM range(10)")
    assert len(para_texto(r)) <= 10_000 + 50


def test_redigir_remove_url_e_senha() -> None:
    sessao = Sessao(id="1", tipo="postgres", pg_url="postgresql://u:senhaSecreta123@h:5432/d")
    msg = redigir("falhou em postgresql://u:senhaSecreta123@h:5432/d (senhaSecreta123)", sessao)
    assert "senhaSecreta123" not in msg and "postgresql://" not in msg


def test_url_postgres_invalida_nao_vaza_senha(monkeypatch) -> None:
    monkeypatch.setattr(config, "PG_PERMITIR_INTERNO", True)  # chega a tentar conectar na porta 1
    url = "postgresql://usuario:senhaSecreta123@127.0.0.1:1/banco"
    with pytest.raises(ErroUsuario) as e:
        sessions.criar_de_postgres(url)
    assert "senhaSecreta123" not in str(e.value)
    assert url not in str(e.value)
    assert "Não consegui conectar" in str(e.value)


def test_url_nao_postgres_recusada() -> None:
    with pytest.raises(ErroUsuario):
        sessions.criar_de_postgres("mysql://u:p@h/d")


@pytest.mark.skipif(not PG_TEST_URL, reason="PG_TEST_URL não definida")
def test_postgres_real(monkeypatch) -> None:
    monkeypatch.setattr(config, "PG_PERMITIR_INTERNO", True)  # o Postgres do teste é local
    s = sessions.criar_de_postgres(PG_TEST_URL)
    assert any(t["nome"] == "vendas_pg" for t in s.tabelas)
    assert executar(s, "SELECT sum(v) FROM vendas_pg").linhas == [(6,)]
    with pytest.raises(ErroUsuario):
        executar(s, "INSERT INTO vendas_pg VALUES (1)")
    with pytest.raises(ErroUsuario):
        executar(s, "SELECT * FROM read_csv('/etc/passwd')")
    with pytest.raises(ErroUsuario):
        executar(s, "SELECT * FROM postgres_execute('pg', 'DROP TABLE vendas_pg')")
    assert executar(s, "SELECT count(*) FROM vendas_pg").linhas == [(3,)]
    senha = PG_TEST_URL.split(":")[2].split("@")[0]
    for sql in ("SELECT database_name, path FROM duckdb_databases()", "SELECT * FROM duckdb_secrets()",
                "SELECT * FROM duckdb_settings()"):
        assert senha not in str(executar(s, sql).linhas)
    assert PG_TEST_URL not in str(executar(s, "SELECT path FROM duckdb_databases()").linhas)
    with pytest.raises(ErroUsuario):
        executar(s, CADEIA)
    for sql in CONTORNOS:
        with pytest.raises(ErroUsuario):
            executar(s, sql)
    assert executar(s, "SELECT count(*) FROM vendas_pg").linhas == [(3,)]


CADEIA = ("SELECT * FROM postgres_execute('pg','COMMIT') UNION ALL "
          "SELECT * FROM postgres_execute('pg','SET SESSION CHARACTERISTICS AS TRANSACTION READ WRITE') "
          "UNION ALL SELECT * FROM postgres_execute('pg','CREATE TEMP TABLE probe_t(a int)')")


@pytest.mark.parametrize("sql", [
    CADEIA,
    "SELECT * FROM postgres_query('pg', 'select 1')",
    "SELECT * FROM postgres_attach('x')",
    "SELECT * FROM query('SELECT 1')",
    "SELECT * FROM query_table('t')",
])
def test_funcoes_que_escondem_sql_recusadas(sql: str) -> None:
    with pytest.raises(ErroUsuario):
        validar_sql(sql)


def test_limites_de_memoria_do_duckdb(s: Sessao) -> None:
    r = executar(s, "SELECT current_setting('memory_limit'), current_setting('threads')")
    assert r.linhas[0][0].startswith("488") and r.linhas[0][1] == 2


def test_redigir_remove_senha_decodificada() -> None:
    sessao = Sessao(id="1", tipo="postgres", pg_url="postgresql://u:p%40ss%2Fw@h:5432/d")
    assert "p@ss/w" not in redigir("erro com p@ss/w aqui", sessao)


def test_parametros_pg_da_url() -> None:
    p = sql_tool.parametros_pg("postgresql://us%40er:p%40ss@host.exemplo/banco?sslmode=require")
    assert p == {"host": "host.exemplo", "port": 5432, "database": "banco",
                 "user": "us@er", "password": "p@ss"}


def test_erro_sem_caminho_do_servidor(s: Sessao) -> None:
    pasta = str(s.caminho_db.parent)
    with pytest.raises(ErroUsuario) as e:
        executar(s, f"SELECT * FROM read_csv('{pasta}/nao_existe.csv')")
    assert pasta not in str(e.value) and str(config.RAIZ) not in str(e.value)


def test_leitura_externa_bloqueada_por_configuracao(s: Sessao) -> None:
    with pytest.raises(ErroUsuario, match="(?i)disabled by configuration|enable_external_access"):
        executar(s, "SELECT * FROM read_csv('https://example.com/x.csv')")


CONTORNOS = [
    "SELECT * FROM query/**/('SELECT 42')",
    'SELECT * FROM "query"(\'SELECT 42\')',
    'SELECT * FROM system.main."query"(\'SELECT 42\')',
    "SELECT * FROM \"query_table\"('vendas_pg')",
    "SELECT * FROM \"query\"('SELECT * FROM post' || 'gres_query(''pg'', ''SELECT 7'')')",
    "SELECT * FROM json_execute_serialized_sql(replace(json_serialize_sql("
    "'SELECT * FROM xostgres_execute(''pg'', ''COMMIT'')'), 'xostgres', 'p' || 'ostgres'))",
    "SELECT * FROM json_deserialize_sql(json_serialize_sql('SELECT 1'))",
    "SELECT * FROM POSTGRES_EXECUTE('pg', 'COMMIT')",
    "WITH t AS (SELECT * FROM postgres_execute('pg', 'COMMIT')) SELECT * FROM t",
    "SELECT (SELECT a FROM postgres_query('pg', 'select 1') a) AS x",
    "SELECT * FROM (SELECT * FROM Query('SELECT 1')) q",
]


@pytest.mark.parametrize("sql", CONTORNOS)
def test_contornos_recusados_pela_arvore_sintatica(sql: str) -> None:
    with pytest.raises(ErroUsuario):
        validar_sql(sql)


@pytest.mark.parametrize("sql", [
    "SELECT a.x, b.y FROM dados a JOIN dados b ON a.x = b.x",
    "WITH t AS (SELECT x FROM dados) SELECT sum(x) FROM t",
    "SELECT x, sum(y) OVER (ORDER BY x) FROM dados",
    "SELECT strftime(now(), '%Y'), date_trunc('month', now()), avg(x), count(*) FROM dados",
    "SELECT regiao, sum(valor) FROM (SELECT 'a' AS regiao, 1 AS valor) GROUP BY 1",
])
def test_selects_legitimos_aceitos(sql: str) -> None:
    assert validar_sql(sql) == sql


def test_porta_invalida_vira_erro_do_usuario() -> None:
    sessao = Sessao(id="1", tipo="postgres", pg_url="postgresql://u:s@h:abc/d")
    with pytest.raises(ErroUsuario) as e:
        sql_tool.abrir(sessao)
    assert "postgresql://" not in str(e.value) and e.value.__cause__ is None


def test_tabela_com_prefixo_postgres_consulta_normalmente() -> None:
    s = sessions.criar_de_csv("postgres_export.csv", CSV)
    assert s.tabelas[0]["nome"] == "postgres_export"
    assert executar(s, "SELECT count(*) FROM postgres_export").linhas == [(3,)]


@pytest.mark.parametrize("sql", ["SELECT 1 AS postgres_total", "SELECT 'query(1)'"])
def test_falsos_positivos_aceitos(sql: str) -> None:
    assert validar_sql(sql) == sql


@pytest.mark.parametrize("sql", [
    "SELECT * FROM \"query\"/**/('SELECT 1')",
    "SELECT * FROM json_execute_serialized_sql('{}')",
    "SELECT * FROM json_serialize_plan('SELECT 1')",
])
def test_funcoes_proibidas_recusadas(sql: str) -> None:
    with pytest.raises(ErroUsuario):
        validar_sql(sql)


def _dns(monkeypatch: pytest.MonkeyPatch, *ips: str) -> None:
    resposta = [(socket.AF_INET6 if ":" in ip else socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0)) for ip in ips]
    monkeypatch.setattr(sql_tool.socket, "getaddrinfo", lambda *a, **k: resposta)


@pytest.mark.parametrize("ips", [("10.0.0.5",), ("127.0.0.1",), ("169.254.169.254",), ("::1",),
                                 ("93.184.216.34", "10.0.0.5")])
def test_ssrf_recusa_destino_interno_inclusive_se_so_um_ip_for_interno(monkeypatch, ips) -> None:
    _dns(monkeypatch, *ips)
    with pytest.raises(ValueError):
        sql_tool._ip_do_destino("db.exemplo.com")


def test_ssrf_recusa_host_vazio_e_que_nao_resolve(monkeypatch) -> None:
    with pytest.raises(ValueError):
        sql_tool._ip_do_destino("")
    monkeypatch.setattr(sql_tool.socket, "getaddrinfo", lambda *a, **k: (_ for _ in ()).throw(socket.gaierror()))
    with pytest.raises(ValueError):
        sql_tool._ip_do_destino("nao-existe.invalid")


def test_ssrf_mesma_mensagem_para_interno_e_nao_resolve(monkeypatch) -> None:
    mensagens = set()
    for ips in (("10.0.0.5",), ()):
        _dns(monkeypatch, *ips)
        with pytest.raises(ErroUsuario) as e:
            sql_tool.abrir(Sessao(id="1", tipo="postgres", pg_url="postgresql://u:p@db.exemplo.com/d"))
        mensagens.add(str(e.value))
    assert len(mensagens) == 1 and "Não consegui conectar" in mensagens.pop()


def test_ssrf_liberado_so_com_a_variavel(monkeypatch) -> None:
    _dns(monkeypatch, "127.0.0.1")
    monkeypatch.setattr(config, "PG_PERMITIR_INTERNO", True)
    assert sql_tool._ip_do_destino("localhost") == "127.0.0.1"
    with pytest.raises(ValueError):
        sql_tool._ip_do_destino("")  # vazio vira socket local: continua recusado


def test_attach_fixa_o_ip_e_mantem_o_host_no_secret(monkeypatch) -> None:
    _dns(monkeypatch, "93.184.216.34")
    chamadas: list[tuple] = []

    class Falsa:
        def execute(self, sql, params=None):
            chamadas.append((sql, params))

        def close(self):
            pass

    monkeypatch.setattr(sql_tool.duckdb, "connect", lambda **k: Falsa())
    sql_tool.abrir(Sessao(id="1", tipo="postgres", pg_url="postgresql://u:p@db.exemplo.com:5432/d"))
    assert any(p and p[0] == "db.exemplo.com" for _, p in chamadas)  # SNI/TLS seguem o nome
    assert any("hostaddr=93.184.216.34" in sql for sql, _ in chamadas)
