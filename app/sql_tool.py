"""SQL só leitura: valida, abre conexão travada, aplica timeout/limite e redige segredos."""
from __future__ import annotations

import ipaddress
import json
import re
import socket
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING
from urllib.parse import unquote, urlsplit

import duckdb

from app import config
from app.errors import ErroUsuario

if TYPE_CHECKING:
    from app.sessions import Sessao

MAX_CHARS = 10_000
LIMITES_DUCKDB = {"memory_limit": "512MB", "threads": 2, "max_temp_directory_size": "0B"}
# Funções que executam SQL escondido em string (postgres_execute contorna o READ_ONLY).
_FUNCOES_PERIGOSAS = re.compile(r"\bpostgres_(execute|query)\b", re.I)


@dataclass
class Resultado:
    colunas: list[str]
    linhas: list[tuple]
    truncado: bool


_FUNCOES_PROIBIDAS = {"query", "query_table", "json_execute_serialized_sql", "json_deserialize_sql", "json_serialize_plan"}


def _funcoes_na_arvore(no: object) -> set[str]:
    if isinstance(no, dict):
        achados = {str(v).lower() for k, v in no.items() if k == "function_name"}
        return achados.union(*(_funcoes_na_arvore(v) for v in no.values()))
    if isinstance(no, list):
        return set().union(*(_funcoes_na_arvore(v) for v in no))
    return set()


def _checar_arvore(sql: str) -> None:
    """Falha fechada: analisa a árvore sintática (o regex sozinho é contornável com aspas, comentários e SQL em string)."""
    con = duckdb.connect(":memory:")
    try:
        arvore = json.loads(con.execute("SELECT json_serialize_sql(?)", [sql]).fetchone()[0])
    except (duckdb.Error, TypeError, ValueError):
        raise ErroUsuario("Não consegui analisar esse SQL. Escreva uma única consulta SELECT simples.") from None
    finally:
        con.close()
    if arvore.get("error"):
        raise ErroUsuario("Não consegui analisar esse SQL. Escreva uma única consulta SELECT simples.")
    if any(f in _FUNCOES_PROIBIDAS or f.startswith("postgres_") for f in _funcoes_na_arvore(arvore)):
        raise ErroUsuario("Funções que executam SQL escondido (postgres_*, query) não são permitidas.")


def validar_sql(sql: str) -> str:
    try:
        comandos = duckdb.extract_statements(sql)
    except duckdb.Error:
        raise ErroUsuario("SQL inválido. Escreva uma única consulta SELECT.") from None
    if len(comandos) != 1 or comandos[0].type != duckdb.StatementType.SELECT:
        raise ErroUsuario("Só é permitido um único comando de leitura (SELECT, inclusive com WITH).")
    if _FUNCOES_PERIGOSAS.search(sql):
        raise ErroUsuario("Funções que executam SQL escondido (postgres_*, query) não são permitidas.")
    _checar_arvore(sql)
    return sql


def redigir(texto: str, sessao: Sessao) -> str:
    for caminho in (config.SESSIONS_DIR, config.RAIZ):  # não revela caminhos do servidor
        texto = texto.replace(str(caminho), ".").replace(caminho.as_posix(), ".")
    if sessao.pg_url:
        senha = urlsplit(sessao.pg_url).password or ""
        for segredo in sorted(filter(None, [sessao.pg_url, senha, unquote(senha)]), key=len, reverse=True):
            texto = texto.replace(segredo, "***")
        texto = re.sub(r"postgres(ql)?://\S+", "***", texto)
    return texto


def abrir(sessao: Sessao) -> duckdb.DuckDBPyConnection:
    """Abre uma conexão só leitura e travada. Falhas viram ErroUsuario sem segredos."""
    try:
        if sessao.tipo == "csv":
            return duckdb.connect(str(sessao.caminho_db), read_only=True, config={
                "enable_external_access": False,
                "autoinstall_known_extensions": False,
                "autoload_known_extensions": False,
                **LIMITES_DUCKDB,
                "lock_configuration": True,
            })
        return _abrir_postgres(sessao.pg_url or "")
    except (duckdb.Error, ValueError):  # ValueError: porta inválida na URL
        # Mensagem fixa: o erro do driver pode conter host/usuário/senha.
        raise ErroUsuario(
            "Não consegui conectar aos dados. Confira a URL, as credenciais e se o banco está no ar."
        ) from None


def parametros_pg(url: str) -> dict:
    u = urlsplit(url)
    return {"host": u.hostname or "", "port": u.port or 5432, "database": unquote(u.path.lstrip("/")),
            "user": unquote(u.username or ""), "password": unquote(u.password or "")}


def _ip_do_destino(host: str) -> str:
    """IP a fixar na conexão. ValueError (mesma resposta) se o host é vazio, não resolve ou não é público."""
    try:
        ips = list(dict.fromkeys(i[4][0].split("%")[0] for i in socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)))
    except OSError:
        ips = []
    # Host vazio viraria o socket local do Postgres, mesmo com a variável de teste ligada.
    if not host or not ips or not (config.PG_PERMITIR_INTERNO or all(ipaddress.ip_address(i).is_global for i in ips)):
        raise ValueError("destino não permitido")
    return ips[0]


def _abrir_postgres(url: str) -> duckdb.DuckDBPyConnection:
    p = parametros_pg(url)
    ip = _ip_do_destino(p["host"])  # o hostaddr abaixo impede DNS rebinding entre a checagem e a conexão
    con = duckdb.connect(config=LIMITES_DUCKDB)
    try:
        con.execute("LOAD postgres")
        # Segredo temporário: a senha não aparece em duckdb_databases() (a URL no ATTACH apareceria).
        con.execute("CREATE TEMPORARY SECRET pgsec (TYPE postgres, HOST ?, PORT ?, DATABASE ?, USER ?, PASSWORD ?)",
                    [p["host"], p["port"], p["database"], p["user"], p["password"]])
        con.execute(f"ATTACH 'connect_timeout=10 hostaddr={ip}' AS pg (TYPE postgres, SECRET pgsec, READ_ONLY)")
        con.execute("USE pg")
        con.execute("SET enable_external_access=false")  # testado: o scanner do Postgres continua funcionando
        con.execute("SET autoload_known_extensions=false")
        con.execute("SET autoinstall_known_extensions=false")
        con.execute("SET lock_configuration=true")
    except duckdb.Error:
        con.close()
        raise
    return con


def executar(sessao: Sessao, sql: str, limite: int = 1000, timeout: float = 30) -> Resultado:
    validar_sql(sql)
    con = abrir(sessao)
    timer = threading.Timer(timeout, con.interrupt)
    timer.start()
    try:
        cur = con.execute(sql)
        colunas = [d[0] for d in cur.description]
        linhas = cur.fetchmany(limite + 1)
    except duckdb.InterruptException:
        raise ErroUsuario("A consulta passou do tempo limite de 30 s e foi interrompida.") from None
    except duckdb.Error as e:
        raise ErroUsuario(redigir(f"Erro ao executar o SQL: {e}", sessao)) from None
    finally:
        timer.cancel()
        con.close()
    return Resultado(colunas, linhas[:limite], len(linhas) > limite)


def para_texto(r: Resultado, max_linhas: int = 50) -> str:
    def cel(v: object) -> str:
        t = "" if v is None else str(v)
        return f'"{t}"' if re.search(r'[,"\n]', t) else t

    linhas = [",".join(r.colunas)] + [",".join(cel(v) for v in lin) for lin in r.linhas[:max_linhas]]
    total = f"{len(r.linhas)}+" if r.truncado else str(len(r.linhas))
    return "\n".join(linhas)[:MAX_CHARS] + f"\n({total} linhas no total)"
