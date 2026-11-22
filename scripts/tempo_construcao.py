"""Mede as horas reais de construção a partir dos registros locais do Claude Code.

Uso: python scripts/tempo_construcao.py [--dir PASTA] [--saida docs/tempo-de-construcao.md]
    [--ate AAAA-MM-DDTHH:MM[:SS] (horário de São Paulo) | --ate-commit SHA (horário do commit, via git)]
Lê só timestamps, tipos e metadados; nunca copia texto de mensagens.
"""
import argparse
import json
import re
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

RAIZ = Path(__file__).resolve().parent.parent


def pasta_do_projeto(raiz: Path) -> Path:
    """Pasta dos registros do Claude Code: o caminho absoluto do projeto com todo caractere não alfanumérico trocado por `-`."""
    return Path.home() / ".claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(raiz))


PASTA_PADRAO = pasta_do_projeto(RAIZ)
SAIDA_PADRAO = RAIZ / "docs" / "tempo-de-construcao.md"

# Intervalo maior que isso entre dois eventos é parada (Daniel fora, sessão caída), não trabalho.
OCIOSO_MAX = timedelta(minutes=5)
# Fuso de exibição do período.
FUSO = ZoneInfo("America/Sao_Paulo")

REVISAO, IMPLEMENTACAO, SPEC, DOCS, TESTES, OUTROS = (
    "Revisão", "Implementação", "Spec/plano", "Documentação", "Testes", "Outros")
ORDEM_CATEGORIAS = [REVISAO, IMPLEMENTACAO, SPEC, DOCS, TESTES, OUTROS]
POR_NOME = {
    "tdd-guide": IMPLEMENTACAO, "build-error-resolver": IMPLEMENTACAO, "gan-generator": IMPLEMENTACAO,
    "general-purpose": IMPLEMENTACAO,  # shortcut: assume implementação; ajustar se houver uso de pesquisa
    "architect": SPEC, "planner": SPEC, "code-architect": SPEC,
    "doc-updater": DOCS, "e2e-runner": TESTES,
}


def categoria(agent_type: str | None) -> str:
    nome = (agent_type or "").split(":")[-1]
    if "reviewer" in nome:
        return REVISAO
    if "qa" in nome.split("-"):
        return TESTES
    return POR_NOME.get(nome, OUTROS)


def _ler(caminho: Path, ate: datetime | None = None) -> list[dict]:
    """Eventos com timestamp válido (até o corte, se houver); linhas quebradas ou sem timestamp são puladas."""
    eventos = []
    for linha in caminho.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            d = json.loads(linha)
            if isinstance(d, dict) and d.get("timestamp"):
                ts = datetime.fromisoformat(d["timestamp"])
                if ate is None or ts <= ate:
                    eventos.append({**d, "_ts": ts})
        except (ValueError, TypeError):
            continue
    return eventos


# role=user que NÃO encerram a espera: comandos `!` do dono (o tempo do comando não é construção),
# lembretes e hooks. Já as notificações automáticas (tarefa, agente, outra sessão) iniciam trabalho: encerram.
NEUTRAS = ("<bash-input", "<bash-stdout", "<bash-stderr", "<local-command", "<system-reminder",
           "<user-prompt-submit-hook")


def _retoma(e: dict) -> bool:
    """Evento de usuário que volta a pôr a conversa para trabalhar (dono digitando ou notificação)."""
    if e.get("type") != "user" or e.get("isMeta"):
        return False
    c = (e.get("message") or {}).get("content")
    if isinstance(c, list):
        if any(isinstance(b, dict) and b.get("type") == "tool_result" for b in c):
            return False
        c = next((b.get("text") for b in c if isinstance(b, dict) and b.get("type") == "text"), None)
    return isinstance(c, str) and not c.lstrip().startswith(NEUTRAS)


def _esperas(eventos: list[dict]) -> list[tuple[datetime, datetime]]:
    """Do fim de um turno sem agentes pendentes até a próxima mensagem humana (ou sem fim)."""
    esperas, inicio = [], None
    for e in sorted(eventos, key=lambda x: x["_ts"]):
        if inicio is None:
            if e.get("type") == "system" and e.get("subtype") == "turn_duration" \
                    and not e.get("pendingBackgroundAgentCount"):
                inicio = e["_ts"]
        elif _retoma(e):
            esperas.append((inicio, e["_ts"]))
            inicio = None
    if inicio is not None:  # a espera aberta vai até o último evento desta sessão, não além
        esperas.append((inicio, max(e["_ts"] for e in eventos)))
    return esperas


def _segmentos(instantes: list[datetime], esperas=()) -> list[tuple[datetime, datetime]]:
    """Trechos entre eventos consecutivos (até OCIOSO_MAX) menos as esperas do dono."""
    segs = []
    instantes = sorted(instantes)
    for a, b in zip(instantes, instantes[1:], strict=False):
        if b - a > OCIOSO_MAX:
            continue
        partes = [(a, b)]
        for i, f in esperas:
            partes = [p for x, y in partes for p in ((x, min(y, i)), (max(x, f), y)) if p[0] < p[1]]
        segs += partes
    return segs


def _soma(segs: list[tuple[datetime, datetime]]) -> timedelta:
    """Duração da união dos trechos (sessões sobrepostas não contam duas vezes)."""
    total, fim = timedelta(0), None
    for a, b in sorted(segs):
        if fim is None or a > fim:
            total += b - a
        elif b > fim:
            total += b - fim
        fim = b if fim is None else max(fim, b)
    return total


def _ativo(instantes: list[datetime], esperas=()) -> timedelta:
    return _soma(_segmentos(instantes, esperas))


def _meta(caminho: Path) -> str | None:
    try:
        return json.loads(caminho.with_suffix(".meta.json").read_text(encoding="utf-8")).get("agentType")
    except (OSError, ValueError):
        return None


def medir(pasta: Path, ate: datetime | None = None) -> dict:
    todos, segmentos, sessoes = [], [], sorted(pasta.glob("*.jsonl"))
    por_categoria = {c: [0, timedelta(0)] for c in ORDEM_CATEGORIAS}
    agentes = timedelta(0)
    n_agentes = 0
    por_sessao = []
    lidas = [(s, _ler(s, ate)) for s in sessoes]
    # Sessões numeradas por ordem cronológica: o ID real não é publicado.
    lidas.sort(key=lambda p: min((e["_ts"] for e in p[1]), default=datetime.max.replace(tzinfo=FUSO)))
    for s, eventos in lidas:
        da_sessao = [e["_ts"] for e in eventos]
        for a in sorted((s.parent / s.stem / "subagents").glob("agent-*.jsonl")):
            instantes = [e["_ts"] for e in _ler(a, ate)]
            if not instantes:  # começou depois do corte
                continue
            tempo = _ativo(instantes)
            da_sessao += instantes
            agentes += tempo
            n_agentes += 1
            por_categoria[categoria(_meta(a))][0] += 1
            por_categoria[categoria(_meta(a))][1] += tempo
        if not da_sessao:
            continue
        todos += da_sessao
        segs = _segmentos(da_sessao, _esperas(eventos))
        segmentos += segs
        por_sessao.append((f"Sessão {len(por_sessao) + 1}", _soma(segs)))
    ativo = _soma(segmentos)
    corrido = max(todos) - min(todos) if todos else timedelta(0)
    return {
        "ate": ate, "ativo": ativo, "corrido": corrido, "parado": corrido - ativo, "agentes": agentes,
        "paralelismo": agentes / ativo if ativo else 0, "n_sessoes": len(por_sessao), "n_agentes": n_agentes,
        "categorias": por_categoria, "por_sessao": por_sessao,
        "inicio": min(todos) if todos else None, "fim": max(todos) if todos else None,
    }


COMMIT_CORTE = "cec40ed"


def corte_do_commit(sha: str, cwd: Path = RAIZ) -> datetime:
    """Horário (com fuso) do commit, lido do git."""
    saida = subprocess.run(["git", "show", "-s", "--format=%cI", sha], cwd=cwd, capture_output=True,
                           text=True, check=True).stdout.strip()
    return datetime.fromisoformat(saida)


CORTE_AVISO = ("Mede só a construção do agente, até o commit `cec40ed` (agente pronto e publicado). "
               "Para reproduzir (exige os registros locais do Claude Code, que não são publicados): "
               "`python scripts/tempo_construcao.py --ate-commit cec40ed`. "
               "O trabalho de apresentação feito depois (README, animações, autoria, perfil) não está incluído.")


def hm(td: timedelta) -> str:
    minutos = round(td.total_seconds() / 60)
    return f"{minutos // 60}h{minutos % 60:02d}"


def _x(valor: float) -> str:
    return f"{valor:.1f}".replace(".", ",") + "x"


def _data(d: datetime | None) -> str:
    return d.astimezone(FUSO).strftime("%d/%m/%Y") if d else "—"


def _periodo(ini: datetime | None, fim: datetime | None) -> str:
    if ini and fim and ini.year == fim.year:
        return f"{_data(ini)[:5]} a {_data(fim)}"
    return f"{_data(ini)} a {_data(fim)}"


def markdown(r: dict, hoje: datetime | None = None) -> str:
    hoje = hoje or datetime.now(FUSO)
    corte = [CORTE_AVISO, ""] if r.get("ate") else []
    linhas = [
        "# Tempo de construção", "", *corte,
        f"Período (datas em horário de São Paulo): {_periodo(r['inicio'], r['fim'])}.", "",
        "| Medida | Valor |", "|---|---|",
        f"| Tempo ativo de relógio | {hm(r['ativo'])} |",
        f"| Relógio corrido | {hm(r['corrido'])} |",
        f"| Horas paradas excluídas | {hm(r['parado'])} |",
        f"| Tempo somado dos agentes | {hm(r['agentes'])} |",
        f"| Paralelismo médio | {_x(r['paralelismo'])} |",
        f"| Sessões | {r['n_sessoes']} |",
        f"| Agentes | {r['n_agentes']} |", "",
        "| Categoria de agente | Agentes | Tempo somado |", "|---|---|---|",
        *[f"| {c} | {n} | {hm(t)} |" for c, (n, t) in r["categorias"].items()], "",
        "| Sessão | Ativo |", "|---|---|", *[f"| {n} | {hm(t)} |" for n, t in r["por_sessao"]], "",
        "## Como foi medido", "",
        "1. Todos os eventos (conversa principal e subagentes) entram numa linha do tempo única.",
        f"2. Tempo ativo = soma dos intervalos entre eventos consecutivos de até {int(OCIOSO_MAX.total_seconds() // 60)}"
        " minutos; intervalos maiores são parada e não contam.",
        "3. A espera pelo Daniel (do fim de um turno, sem agentes em segundo plano pendentes, até a próxima "
        "mensagem que ponha a conversa para trabalhar) não conta. A espera é por sessão: o fim de uma sessão "
        "não desconta o trabalho de outra, e sessões sobrepostas não contam o mesmo minuto duas vezes.",
        "3a. Notificações automáticas (fim de tarefa ou de agente, mensagem de outra sessão) chegam como "
        "role=user, mas não são o Daniel; como disparam trabalho do Claude, encerram a espera, e o tempo "
        "trabalhado depois delas conta. Resultados de ferramenta, lembretes do sistema e mensagens de hook "
        "nunca encerram a espera.",
        "3b. Comandos `!` do Daniel (entrada e saída) são ações dele, mas o tempo do comando não é "
        "construção: não encerram a espera, que só acaba na próxima mensagem digitada ou notificação. Se o "
        "comando ocorrer com a conversa ou um agente já trabalhando, esse trabalho continua contando.",
        "4. Tempo dos agentes = tempo ativo de cada subagente na sua própria linha do tempo, somado e agrupado "
        "por tipo; paralelismo = tempo somado dos agentes / tempo ativo de relógio.",
        "5. Período = data do primeiro e do último evento, em horário de São Paulo (só datas são publicadas); "
        "relógio corrido = último menos primeiro. As sessões são numeradas pela ordem cronológica.",
        "6. As horas paradas somam a espera pelo Daniel e o tempo ocioso, e os registros não os separam com "
        "exatidão: sessões se sobrepõem, e uma espera de uma sessão pode coincidir com trabalho de outra. "
        "Por isso o total parado é publicado sem divisão.",
        "", "Limites: o tempo que o Daniel gastou pensando fora da tela não é medido; o horário vem dos registros "
        "locais do Claude Code; os números exatos dependem do limite de ociosidade (5 minutos).", "",
        f"Gerado por `scripts/tempo_construcao.py` em {hoje.strftime('%d/%m/%Y')}.", "",
    ]
    return "\n".join(linhas)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dir", type=Path, default=PASTA_PADRAO)
    p.add_argument("--saida", type=Path, default=SAIDA_PADRAO)
    p.add_argument("--ate", type=lambda t: datetime.fromisoformat(t).replace(tzinfo=FUSO),
                   help="corte: eventos depois deste instante (horário de São Paulo) são ignorados")
    p.add_argument("--ate-commit", metavar="SHA", help="corte: horário deste commit, lido do git")
    args = p.parse_args()
    ate = corte_do_commit(args.ate_commit) if args.ate_commit else args.ate
    r = medir(args.dir, ate)
    args.saida.parent.mkdir(parents=True, exist_ok=True)
    args.saida.write_text(markdown(r), encoding="utf-8")
    print(f"Ativo {hm(r['ativo'])} | corrido {hm(r['corrido'])} | parado {hm(r['parado'])} | "
          f"agentes {hm(r['agentes'])} ({_x(r['paralelismo'])}) | {r['n_sessoes']} sessões, "
          f"{r['n_agentes']} agentes\nEscrito em {args.saida}")


if __name__ == "__main__":
    main()
