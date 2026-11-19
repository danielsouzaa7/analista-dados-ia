"""Mede as horas reais de construção a partir dos registros locais do Claude Code.

Uso: python scripts/tempo_construcao.py [--dir PASTA] [--saida docs/tempo-de-construcao.md]
Lê só timestamps, tipos e metadados; nunca copia texto de mensagens.
"""
import argparse
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

RAIZ = Path(__file__).resolve().parent.parent
PASTA_PADRAO = Path.home() / ".claude" / "projects" / "C--Users-Daniel-Desktop-analista-dados-ia"
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


def _ler(caminho: Path) -> list[dict]:
    """Eventos com timestamp válido; linhas quebradas ou sem timestamp são puladas."""
    eventos = []
    for linha in caminho.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            d = json.loads(linha)
            if isinstance(d, dict) and d.get("timestamp"):
                eventos.append({**d, "_ts": datetime.fromisoformat(d["timestamp"])})
        except (ValueError, TypeError):
            continue
    return eventos


def _humano(e: dict) -> bool:
    if e.get("type") != "user" or e.get("isMeta"):
        return False
    c = (e.get("message") or {}).get("content")
    if isinstance(c, str):
        return True
    blocos = [b.get("type") for b in c if isinstance(b, dict)] if isinstance(c, list) else []
    return "text" in blocos and "tool_result" not in blocos


def _esperas(eventos: list[dict]) -> list[tuple[datetime, datetime]]:
    """Do fim de um turno sem agentes pendentes até a próxima mensagem humana (ou sem fim)."""
    esperas, inicio = [], None
    for e in sorted(eventos, key=lambda x: x["_ts"]):
        if inicio is None:
            if e.get("type") == "system" and e.get("subtype") == "turn_duration" \
                    and not e.get("pendingBackgroundAgentCount"):
                inicio = e["_ts"]
        elif _humano(e):
            esperas.append((inicio, e["_ts"]))
            inicio = None
    if inicio is not None:
        esperas.append((inicio, datetime.max.replace(tzinfo=UTC)))
    return esperas


def _ativo(instantes: list[datetime], esperas=()) -> timedelta:
    total = timedelta(0)
    instantes = sorted(instantes)
    for a, b in zip(instantes, instantes[1:], strict=False):
        if b - a > OCIOSO_MAX:
            continue
        total += (b - a) - sum((max(timedelta(0), min(b, f) - max(a, i)) for i, f in esperas), timedelta(0))
    return total


def _meta(caminho: Path) -> str | None:
    try:
        return json.loads(caminho.with_suffix(".meta.json").read_text(encoding="utf-8")).get("agentType")
    except (OSError, ValueError):
        return None


def medir(pasta: Path) -> dict:
    todos, esperas, sessoes = [], [], sorted(pasta.glob("*.jsonl"))
    por_categoria = {c: [0, timedelta(0)] for c in ORDEM_CATEGORIAS}
    agentes = timedelta(0)
    n_agentes = 0
    for s in sessoes:
        eventos = _ler(s)
        todos += [e["_ts"] for e in eventos]
        esperas += _esperas(eventos)
        for a in sorted((s.parent / s.stem / "subagents").glob("agent-*.jsonl")):
            instantes = [e["_ts"] for e in _ler(a)]
            tempo = _ativo(instantes)
            todos += instantes
            agentes += tempo
            n_agentes += 1
            por_categoria[categoria(_meta(a))][0] += 1
            por_categoria[categoria(_meta(a))][1] += tempo
    ativo = _ativo(todos, esperas)
    corrido = max(todos) - min(todos) if todos else timedelta(0)
    return {
        "ativo": ativo, "corrido": corrido, "parado": corrido - ativo, "agentes": agentes,
        "paralelismo": agentes / ativo if ativo else 0, "n_sessoes": len(sessoes), "n_agentes": n_agentes,
        "categorias": por_categoria,
        "inicio": min(todos) if todos else None, "fim": max(todos) if todos else None,
    }


def hm(td: timedelta) -> str:
    minutos = round(td.total_seconds() / 60)
    return f"{minutos // 60}h{minutos % 60:02d}"


def _data(d: datetime | None) -> str:
    return d.astimezone(FUSO).strftime("%d/%m/%Y %H:%M") if d else "—"


def markdown(r: dict, hoje: datetime | None = None) -> str:
    hoje = hoje or datetime.now(FUSO)
    linhas = [
        "# Tempo de construção", "",
        f"Período (horário de São Paulo): {_data(r['inicio'])} a {_data(r['fim'])}.", "",
        "| Medida | Valor |", "|---|---|",
        f"| Tempo ativo de relógio | {hm(r['ativo'])} |",
        f"| Relógio corrido | {hm(r['corrido'])} |",
        f"| Horas paradas excluídas | {hm(r['parado'])} |",
        f"| Tempo somado dos agentes | {hm(r['agentes'])} |",
        f"| Paralelismo médio | {r['paralelismo']:.1f}x |",
        f"| Sessões | {r['n_sessoes']} |",
        f"| Agentes | {r['n_agentes']} |", "",
        "| Categoria de agente | Agentes | Tempo somado |", "|---|---|---|",
        *[f"| {c} | {n} | {hm(t)} |" for c, (n, t) in r["categorias"].items()], "",
        "## Como foi medido", "",
        "1. Todos os eventos (conversa principal e subagentes) entram numa linha do tempo única.",
        f"2. Tempo ativo = soma dos intervalos entre eventos consecutivos de até {int(OCIOSO_MAX.total_seconds() // 60)}"
        " minutos; intervalos maiores são parada e não contam.",
        "3. A espera pela resposta do Daniel (do fim de um turno até a próxima mensagem dele) não conta, "
        "salvo se havia agentes em segundo plano trabalhando.",
        "4. Tempo dos agentes = tempo ativo de cada subagente na sua própria linha do tempo, somado e agrupado "
        "por tipo; paralelismo = tempo somado dos agentes / tempo ativo de relógio.",
        "5. Período = primeiro e último evento, em horário de São Paulo; relógio corrido = último menos primeiro.",
        "", "Limites: o tempo que o Daniel gastou pensando fora da tela não é medido; o horário vem dos registros "
        "locais do Claude Code; os números exatos dependem do limite de ociosidade (5 minutos).", "",
        f"Gerado em {hoje.strftime('%d/%m/%Y')}.", "",
    ]
    return "\n".join(linhas)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dir", type=Path, default=PASTA_PADRAO)
    p.add_argument("--saida", type=Path, default=SAIDA_PADRAO)
    args = p.parse_args()
    r = medir(args.dir)
    args.saida.parent.mkdir(parents=True, exist_ok=True)
    args.saida.write_text(markdown(r), encoding="utf-8")
    print(f"Ativo {hm(r['ativo'])} | corrido {hm(r['corrido'])} | parado {hm(r['parado'])} | "
          f"agentes {hm(r['agentes'])} ({r['paralelismo']:.1f}x) | {r['n_sessoes']} sessões, "
          f"{r['n_agentes']} agentes\nEscrito em {args.saida}")


if __name__ == "__main__":
    main()
