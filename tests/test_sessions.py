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


def test_sessao_sem_pergunta_expira_em_10_min_e_a_com_pergunta_em_1_h(monkeypatch: pytest.MonkeyPatch) -> None:
    muda = sessions.criar_de_csv("a.csv", CSV_A)
    usada = sessions.criar_de_csv("b.csv", CSV_B)
    usada.perguntou = True
    monkeypatch.setattr(time, "time", lambda: max(muda.ultimo_uso, usada.ultimo_uso) + 601)
    sessions.limpar_expiradas()
    assert muda.id not in sessions.SESSOES and usada.id in sessions.SESSOES
    monkeypatch.setattr(time, "time", lambda: usada.ultimo_uso + 3601)
    sessions.limpar_expiradas()
    assert usada.id not in sessions.SESSOES


def test_lotado_remove_a_mais_antiga_sem_pergunta() -> None:
    velha = sessions.criar_de_csv("a.csv", CSV_A)
    usada = sessions.criar_de_csv("b.csv", CSV_B)
    usada.perguntou = True
    nova = sessions.criar_de_csv("c.csv", CSV_B)
    agora = time.time()
    velha.criada, usada.criada, nova.criada = agora - 500, agora - 900, agora - 1
    velha.ultimo_uso, usada.ultimo_uso, nova.ultimo_uso = agora - 500, agora - 900, agora - 1
    pasta = velha.caminho_db.parent
    sessions.limpar_expiradas(maximo=3)
    assert set(sessions.SESSOES) == {usada.id, nova.id} and not pasta.exists()
    sessions.limpar_expiradas(maximo=3)  # há vaga: não remove mais nada
    assert len(sessions.SESSOES) == 2


def test_lotado_so_com_sessoes_com_pergunta_nao_remove_nenhuma() -> None:
    a = sessions.criar_de_csv("a.csv", CSV_A)
    a.perguntou = True
    a.ultimo_uso -= 1000
    sessions.limpar_expiradas(maximo=1)
    assert a.id in sessions.SESSOES


def test_lotado_nao_remove_sessao_com_a_primeira_pergunta_em_andamento() -> None:
    a = sessions.criar_de_csv("a.csv", CSV_A)
    a.perguntou = True  # perguntou, mas ainda não deu turno
    a.ultimo_uso -= 1000
    sessions.limpar_expiradas(maximo=1)
    assert a.id in sessions.SESSOES and a.caminho_db.parent.exists()


def test_lotado_nao_remove_sessao_nova_com_menos_de_150_s() -> None:
    nova = sessions.criar_de_csv("a.csv", CSV_A)
    nova.criada -= sessions.IDADE_MINIMA - 5
    sessions.limpar_expiradas(maximo=1)
    assert nova.id in sessions.SESSOES
    nova.criada -= 10
    sessions.limpar_expiradas(maximo=1)
    assert nova.id not in sessions.SESSOES


def test_idade_minima_passa_do_prazo_do_sse() -> None:
    from app import main
    assert sessions.IDADE_MINIMA > main.PRAZO_SSE


def test_csv_muito_largo_e_recusado_rapido(pasta_sessoes: Path) -> None:
    cabecalho = ",".join(f"c{i}" for i in range(100_000))
    desde = time.perf_counter()
    with pytest.raises(ErroUsuario, match="mais de 200 colunas"):
        sessions.criar_de_csv("a.csv", f"{cabecalho}\n{','.join('1' for _ in range(100_000))}\n".encode())
    assert time.perf_counter() - desde < 3  # folga de CI (runner mais lento)
    assert not list(pasta_sessoes.glob("*"))


def test_nome_de_arquivo_enorme_vira_tabela_de_ate_64_caracteres() -> None:
    assert len(sessions.criar_de_csv("a" * 5000 + ".csv", CSV_A).tabelas[0]["nome"]) <= 64



def _largo(n: int = 100_000) -> tuple[str, str]:
    return ",".join(f"c{i}" for i in range(n)), ",".join("1" for _ in range(n))


@pytest.mark.parametrize("montar", [
    lambda cab, lin: f"lixo\n{cab}\n{lin}\n",
    lambda cab, lin: f"\n{cab}\n{lin}\n",
    lambda cab, lin: f'"a\nb",{cab}\n{lin}\n',
    lambda cab, lin: ",".join(f'"c{i}\nz"' if i % 150 == 0 else f"c{i}" for i in range(100_000)) + f"\n{lin}\n",
], ids=["lixo_antes", "primeira_linha_vazia", "quebra_entre_aspas", "aspas_a_cada_150"])
def test_csv_largo_com_truque_no_cabecalho_nao_gasta_cpu(montar) -> None:
    cab, lin = _largo()
    desde = time.perf_counter()
    try:  # a linha de lixo vira o cabeçalho: vale recusar ou ler estreito, nunca gastar CPU com 100 mil colunas
        colunas = sessions.criar_de_csv("a.csv", montar(cab, lin).encode()).tabelas[0]["colunas"]
        assert len(colunas) <= 200
    except ErroUsuario:
        pass
    assert time.perf_counter() - desde < 5  # folga de CI


def test_csv_com_fim_de_linha_so_cr_e_aceito() -> None:
    linhas = "".join(f"{i},x,3,4,y\r" for i in range(100))  # sem LF, o split antigo via uma linha só
    s = sessions.criar_de_csv("a.csv", ("a,b,c,d,e\r" + linhas).encode())
    assert len(s.tabelas[0]["colunas"]) == 5 and s.tabelas[0]["linhas"] == 100


def test_csv_com_200_colunas_aceito_e_201_recusado() -> None:
    def csv_de(n: int) -> bytes:
        return (",".join(f"c{i}" for i in range(n)) + "\n" + ",".join("1" for _ in range(n)) + "\n").encode()
    assert len(sessions.criar_de_csv("a.csv", csv_de(200)).tabelas[0]["colunas"]) == 200
    with pytest.raises(ErroUsuario, match="mais de 200 colunas"):
        sessions.criar_de_csv("a.csv", csv_de(201))


def test_csv_com_texto_de_500_virgulas_entre_aspas_e_aceito() -> None:
    conteudo = ('id,descricao\n1,"' + ",".join("xxx" for _ in range(500)) + '"\n').encode()
    assert sessions.criar_de_csv("a.csv", conteudo).tabelas[0]["linhas"] == 1


def test_pedidos_csv_continua_com_13_colunas_e_8000_linhas() -> None:
    from app import config
    t = sessions.criar_de_csv("pedidos.csv", (config.DATA_DIR / "pedidos.csv").read_bytes()).tabelas[0]
    assert len(t["colunas"]) == 13 and t["linhas"] == 8000


def test_keepalive_nao_tranca_a_vaga_da_sessao_sem_pergunta() -> None:
    a = sessions.criar_de_csv("a.csv", CSV_A)
    a.criada -= sessions.IDADE_MINIMA + 1
    sessions.obter(a.id)  # keepalive renova ultimo_uso, mas não a idade
    sessions.limpar_expiradas(maximo=1)
    assert a.id not in sessions.SESSOES


def test_keepalive_nao_impede_o_ttl_de_10_min_da_sessao_sem_pergunta(monkeypatch: pytest.MonkeyPatch) -> None:
    a = sessions.criar_de_csv("a.csv", CSV_A)
    monkeypatch.setattr(time, "time", lambda: a.criada + 601)
    a.ultimo_uso = a.criada + 600  # keepalive um segundo antes
    sessions.limpar_expiradas()
    assert a.id not in sessions.SESSOES


def test_nome_de_tabela_com_prefixo_t_continua_em_64_caracteres() -> None:
    assert len(sessions.criar_de_csv("2024_" + "vendas" * 20 + ".csv", CSV_A).tabelas[0]["nome"]) <= 64


@pytest.mark.parametrize("conteudo", [
    ("'" + ",".join(f"c{i}" for i in range(300)) + "'\n" + ",".join("1" for _ in range(300)) + "\n"),
    ("'" + ",".join(f"c{i}" for i in range(300)) + "'\n'" + ",".join("1" for _ in range(300)) + "'\n"),
    ('"' + ",".join(f"c{i}" for i in range(300)).replace("c5", '\\"c5') + '"\n1\n'),
    ("a,b\n" + '"' + "\\\",".join("x" for _ in range(300)) + '",1\n'),
    ("\\\"" + ",".join(f"c{i}" for i in range(300)) + "\n" + ",".join("1" for _ in range(300)) + "\n"),
], ids=["aspa_simples", "aspa_simples_dados", "escape_barra_no_cab", "escape_barra_nos_dados", "barra_aspa_inicio"])
def test_dialeto_divergente_nao_abre_mais_de_200_colunas(conteudo: str) -> None:
    try:
        colunas = sessions.criar_de_csv("a.csv", conteudo.encode()).tabelas[0]["colunas"]
        assert len(colunas) <= 200
    except ErroUsuario:
        pass
