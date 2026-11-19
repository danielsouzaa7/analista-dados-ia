"""Sessões isoladas: cada uma tem o próprio banco DuckDB (CSV) ou a própria URL Postgres (só em memória)."""
import re
import secrets
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

import duckdb

from app import config, perfil, sql_tool
from app.errors import ErroUsuario

MAX_CSV_BYTES = 20 * 1024 * 1024
TTL_SEGUNDOS = 3600


@dataclass
class Sessao:
    id: str
    tipo: str  # "csv" | "postgres"
    caminho_db: Path | None = None
    pg_url: str | None = field(default=None, repr=False)  # nunca em disco nem em log
    ultimo_uso: float = field(default_factory=time.time)
    tabelas: list[dict] = field(default_factory=list)
    historico: list[dict] = field(default_factory=list)  # últimos turnos (memória da conversa), só no servidor
    turnos: int = 0  # respostas dadas na conversa atual (índice do feedback)
    grounding: str = ""  # valores das colunas categóricas, para o prompt


SESSOES: dict[str, Sessao] = {}


def _nome_tabela(nome_arquivo: str) -> str:
    nome = re.sub(r"[^a-z0-9_]", "_", Path(nome_arquivo).stem.lower()).strip("_")
    if not nome:
        return "dados"
    return nome if nome[0].isalpha() else f"t_{nome}"


def criar_de_csv(nome_arquivo: str, conteudo: bytes) -> Sessao:
    if len(conteudo) > MAX_CSV_BYTES:
        raise ErroUsuario("O arquivo passa de 20 MB. Envie um CSV menor.")
    sid = secrets.token_urlsafe(16)
    pasta = config.SESSIONS_DIR / sid
    pasta.mkdir(parents=True)
    tabela = _nome_tabela(nome_arquivo)
    try:
        csv = pasta / "origem.csv"
        csv.write_bytes(conteudo)
        con = duckdb.connect(str(pasta / "dados.duckdb"))
        try:
            con.execute(f'CREATE TABLE "{tabela}" AS SELECT * FROM read_csv_auto(?)', [str(csv)])
            colunas = con.execute(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_name = ? ORDER BY ordinal_position", [tabela]).fetchall()
            linhas = con.execute(f'SELECT count(*) FROM "{tabela}"').fetchone()[0]
            dados_perfil, grounding = perfil.perfilar(con, tabela)
        finally:
            con.close()
        csv.unlink()
        if not colunas or linhas == 0:
            raise duckdb.Error("sem dados")
    except (duckdb.Error, UnicodeDecodeError):
        shutil.rmtree(pasta, ignore_errors=True)
        raise ErroUsuario("Não consegui ler esse CSV. Confira se é um arquivo CSV válido com cabeçalho.") from None
    sessao = Sessao(id=sid, tipo="csv", caminho_db=pasta / "dados.duckdb", tabelas=[
        {"nome": tabela, "colunas": [{"nome": n, "tipo": t} for n, t in colunas], "linhas": linhas,
         "perfil": dados_perfil}], grounding=grounding)
    SESSOES[sid] = sessao
    return sessao


def criar_de_postgres(url: str) -> Sessao:
    if not url.startswith(("postgres://", "postgresql://")):
        raise ErroUsuario("A URL precisa começar com postgresql://")
    sessao = Sessao(id=secrets.token_urlsafe(16), tipo="postgres", pg_url=url)
    con = sql_tool.abrir(sessao)  # levanta ErroUsuario (já sem segredos) se falhar
    try:
        rows = con.execute(
            "SELECT table_name, column_name, data_type FROM information_schema.columns "
            "WHERE table_catalog = 'pg' AND table_schema = 'public' "
            "ORDER BY table_name, ordinal_position").fetchall()
    except duckdb.Error as e:
        raise ErroUsuario(sql_tool.redigir(f"Não consegui listar as tabelas: {e}", sessao)) from None
    finally:
        con.close()
    tabelas: dict[str, dict] = {}
    for tabela, coluna, tipo in rows:
        tabelas.setdefault(tabela, {"nome": tabela, "colunas": [], "linhas": None})["colunas"].append(
            {"nome": coluna, "tipo": tipo})
    if not tabelas:
        raise ErroUsuario("Conectei, mas não há tabelas no schema public desse banco.")
    sessao.tabelas = list(tabelas.values())
    _perfilar_postgres(sessao)
    SESSOES[sessao.id] = sessao
    return sessao


def _perfilar_postgres(sessao: Sessao) -> None:
    """Perfil com amostra limitada e tempo limite; falhas não impedem a sessão."""
    try:
        con = sql_tool.abrir(sessao)
    except ErroUsuario:
        return
    try:
        grounding = []
        for t in sessao.tabelas[:perfil.MAX_TABELAS_PERFIL]:
            t["perfil"], g = perfil.perfilar(con, t["nome"], t["colunas"], amostra=5000)
            grounding.append(g)
        sessao.grounding = chr(10).join(filter(None, grounding))
    finally:
        con.close()


def limpar_expiradas() -> None:
    agora = time.time()
    for sid, s in list(SESSOES.items()):
        if agora - s.ultimo_uso <= TTL_SEGUNDOS:
            continue
        sessao = SESSOES.pop(sid, None)  # outra requisição pode ter removido antes
        if sessao and sessao.caminho_db:
            shutil.rmtree(sessao.caminho_db.parent, ignore_errors=True)


def obter(sid: str) -> Sessao:
    limpar_expiradas()
    sessao = SESSOES.get(sid)
    if sessao is None:
        raise ErroUsuario("Sessão expirada. Carregue seus dados de novo.")
    sessao.ultimo_uso = time.time()
    return sessao


def limpar_tudo() -> None:
    SESSOES.clear()
    shutil.rmtree(config.SESSIONS_DIR, ignore_errors=True)
