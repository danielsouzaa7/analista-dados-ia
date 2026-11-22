"""Métricas de orquestração de agentes a partir dos registros locais do Claude Code.

Uso: python scripts/orquestracao.py [--dir PASTA] [--saida docs/orquestracao.md]
    [--svg docs/img/orquestracao.svg] [--ate AAAA-MM-DDTHH:MM (horário de São Paulo)]
Lê só timestamps, tipos e contagens de `usage`; nunca copia texto de mensagens, IDs ou caminhos.
"""
import argparse
import statistics
from datetime import datetime
from pathlib import Path

from tempo_construcao import (
    DOCS,
    FUSO,
    IMPLEMENTACAO,
    ORDEM_CATEGORIAS,
    OUTROS,
    PASTA_PADRAO,
    RAIZ,
    REVISAO,
    SPEC,
    TESTES,
    _ler,
    _meta,
    categoria,
)

CATEGORIAS = (DOCS, IMPLEMENTACAO, OUTROS, REVISAO, SPEC, TESTES)  # reexportadas para os testes
SAIDA_PADRAO = RAIZ / "docs" / "orquestracao.md"
SVG_PADRAO = RAIZ / "docs" / "img" / "orquestracao.svg"
LIMITE_ZONA = 300_000  # "zona de genialidade": contexto de pico até aqui mantém a qualidade
ENTRADA, SAIDA, CACHE_LIDO, CACHE_CRIADO = (
    "input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")
CORTE_AVISO = "Mede só a construção do agente, até o commit `cec40ed` (mesmo corte das horas de construção)."
SOMAS = ("entrada", "saida", "cache_lido", "cache_criado")


def _uso(eventos: list[dict]) -> dict:
    """Soma o `usage` das chamadas do assistente, uma vez por message.id (o registro repete a mesma
    resposta em várias linhas), e acha o pico de contexto e as compactações."""
    chamadas, compactacoes = {}, []
    for i, e in enumerate(eventos):
        if e.get("type") == "system" and e.get("subtype") == "compact_boundary":
            compactacoes.append((e.get("compactMetadata") or {}).get("preTokens") or 0)
        m = e.get("message")
        if e.get("type") != "assistant" or not isinstance(m, dict) or not isinstance(m.get("usage"), dict):
            continue
        atual = chamadas.setdefault(m.get("id") or f"sem-id-{i}", dict.fromkeys((ENTRADA, SAIDA, CACHE_LIDO, CACHE_CRIADO), 0))
        for campo in atual:
            v = m["usage"].get(campo)
            atual[campo] = max(atual[campo], v if isinstance(v, int) else 0)
    cs = list(chamadas.values())
    return {
        "entrada": sum(c[ENTRADA] for c in cs), "saida": sum(c[SAIDA] for c in cs),
        "cache_lido": sum(c[CACHE_LIDO] for c in cs), "cache_criado": sum(c[CACHE_CRIADO] for c in cs),
        "pico": max((c[ENTRADA] + c[CACHE_LIDO] + c[CACHE_CRIADO] for c in cs), default=0),
        "chamadas": len(cs), "compactacoes": len(compactacoes),
        "pre_compactacao_max": max(compactacoes, default=0),
    }


def _novos(u: dict) -> int:
    """Tokens novos: saída + entrada nova + cache criado (exclui o cache lido, que é releitura)."""
    return u["entrada"] + u["cache_criado"] + u["saida"]


def medir(pasta: Path, ate: datetime | None = None) -> dict:
    agentes, sessoes = [], []
    for s in sorted(pasta.glob("*.jsonl")):
        eventos = _ler(s, ate)
        if not eventos:
            continue
        sessoes.append((min(e["_ts"] for e in eventos), _uso(eventos)))
        for a in sorted((s.parent / s.stem / "subagents").glob("agent-*.jsonl")):
            ev = _ler(a, ate)
            if ev:
                agentes.append({**_uso(ev), "categoria": categoria(_meta(a))})
    sessoes = [u for _, u in sorted(sessoes, key=lambda x: x[0])]
    orq = {k: sum(u[k] for u in sessoes) for k in (*SOMAS, "chamadas", "compactacoes")}
    orq |= {"pico": max((u["pico"] for u in sessoes), default=0), "n_sessoes": len(sessoes),
            "pre_compactacao_max": max((u["pre_compactacao_max"] for u in sessoes), default=0),
            "sessoes_acima": sum(u["pico"] > LIMITE_ZONA for u in sessoes), "sessoes": sessoes}
    categorias = {}
    for c in ORDEM_CATEGORIAS:
        g = [a for a in agentes if a["categoria"] == c]
        categorias[c] = {
            "n": len(g), "pico": max((a["pico"] for a in g), default=0),
            "pico_mediano": int(statistics.median(a["pico"] for a in g)) if g else 0,
            **{k: sum(a[k] for a in g) for k in SOMAS},
            "agentes": sorted(g, key=lambda a: -a["pico"]),
        }
    return {
        "ate": ate, "n_agentes": len(agentes), "agentes": agentes,
        "total_agentes": {k: sum(a[k] for a in agentes) for k in (*SOMAS, "chamadas")},
        "orquestrador": orq, "categorias": categorias,
        "dentro_zona": sum(a["pico"] <= LIMITE_ZONA for a in agentes),
        "fora_zona": sum(a["pico"] > LIMITE_ZONA for a in agentes),
    }


def n(v: int) -> str:
    return f"{v:,}".replace(",", ".")


def mi(v: float) -> str:
    return f"{v / 1e6:.1f}".replace(".", ",") + " mi" if v >= 1e6 else f"{round(v / 1e3)} mil"


def razao(a: int, b: int) -> str:
    return f"{a / b:.1f}".replace(".", ",") + "x" if b else "—"


def _linha(nome: str, t: int, o: int) -> str:
    return f"| {nome} | {n(t)} | {n(o)} | {razao(t, o)} |"


def markdown(r: dict, hoje: datetime | None = None) -> str:
    hoje = hoje or datetime.now(FUSO)
    o, t = r["orquestrador"], r["total_agentes"]
    corte = [CORTE_AVISO, ""] if r.get("ate") else []
    linhas = [
        "# Orquestração de agentes", "", *corte,
        f"**{r['n_agentes']} agentes geraram {n(t['saida'])} tokens de saída; o orquestrador (conversa "
        f"principal de {o['n_sessoes']} sessões) gerou {n(o['saida'])}** ({razao(t['saida'], o['saida'])}). "
        f"O pico de contexto do orquestrador foi {n(o['pico'])} tokens; "
        f"{r['dentro_zona']} de {r['n_agentes']} agentes ficaram na zona de genialidade "
        f"(pico até {n(LIMITE_ZONA)}) e {r['fora_zona']} passou(aram) dela.", "",
        "## Totais", "",
        "| Medida | Agentes | Orquestrador | Razão agentes ÷ orquestrador |", "|---|---:|---:|---:|",
        _linha("Tokens gerados (saída)", t["saida"], o["saida"]),
        _linha("Entrada nova (`input_tokens`)", t["entrada"], o["entrada"]),
        _linha("Cache criado", t["cache_criado"], o["cache_criado"]),
        _linha("**Tokens novos** (saída + entrada nova + cache criado)", _novos(t), _novos(o)),
        _linha("Cache lido (releitura, não é trabalho novo)", t["cache_lido"], o["cache_lido"]),
        _linha("Total bruto (tokens novos + cache lido)", _novos(t) + t["cache_lido"], _novos(o) + o["cache_lido"]),
        _linha("Chamadas ao modelo", t["chamadas"], o["chamadas"]), "",
        "## Por papel", "",
        "| Papel | Agentes | Tokens gerados | Tokens novos | Cache lido | Pico máx. | Pico mediano |",
        "|---|---:|---:|---:|---:|---:|---:|",
        *[f"| {c} | {g['n']} | {n(g['saida'])} | {n(_novos(g))} | {n(g['cache_lido'])} "
          f"| {n(g['pico'])} | {n(g['pico_mediano'])} |" for c, g in r["categorias"].items()],
        "", "## Zona de genialidade (pico de contexto até 300 mil tokens)", "",
        "| Quem | Dentro da zona | Fora da zona |", "|---|---:|---:|",
        f"| Agentes | {r['dentro_zona']} | {r['fora_zona']} |",
        f"| Orquestrador (sessões) | {o['n_sessoes'] - o['sessoes_acima']} | {o['sessoes_acima']} |", "",
        "## Orquestrador por sessão", "",
        "| Sessão (ordem cronológica) | Pico de contexto | Compactações | Maior contexto antes de compactar |",
        "|---|---:|---:|---:|",
        *[f"| {i} | {n(u['pico'])} | {u['compactacoes']} | "
          f"{n(u['pre_compactacao_max']) if u['compactacoes'] else '—'} |" for i, u in enumerate(o["sessoes"], 1)],
        "",
    ]
    if o["sessoes_acima"]:
        linhas += [f"**Honestidade:** {o['sessoes_acima']} sessão(ões) do orquestrador passaram de "
                   f"{n(LIMITE_ZONA)} tokens de pico; o contexto foi compactado {o['compactacoes']} "
                   f"vez(es) (maior contexto antes de compactar: {n(o['pre_compactacao_max'])}).", ""]
    linhas += [
        "## Como foi medido", "",
        "1. Lê o `usage` de cada mensagem do assistente na conversa principal (orquestrador) e em cada "
        "subagente, até o mesmo corte das horas de construção (`--ate`); eventos depois dele são ignorados.",
        "2. A resposta aparece repetida em várias linhas do registro; conta-se uma vez por `message.id` "
        "(o maior valor de cada campo).",
        "3. **Tokens gerados** = `output_tokens`. **Entrada nova** = `input_tokens`. **Cache criado** = "
        "`cache_creation_input_tokens` (contexto escrito no cache). **Cache lido** = `cache_read_input_tokens` "
        "(o mesmo contexto relido a cada chamada: soma inflada por repetição, por isso fica separado).",
        "4. **Tokens novos** = saída + entrada nova + cache criado. **Total bruto** = tokens novos + cache lido.",
        "5. **Pico de contexto** (por agente ou sessão) = maior valor, numa única chamada, de entrada + cache "
        "lido + cache criado: o tamanho da janela de contexto naquela chamada.",
        f"6. Zona de genialidade: pico de contexto até {n(LIMITE_ZONA)} tokens (convenção de que a qualidade se "
        "mantém); o limite é inclusivo.",
        "7. Papel do agente pelo tipo registrado (mesmas categorias do relatório de tempo).",
        "8. Compactações = eventos de compactação de contexto do registro; o contexto antes de compactar vem do "
        "próprio evento.", "",
        "Limites: o orquestrador tem poucas sessões, cada uma longa; papéis diferentes não são comparáveis em "
        "custo. Só contagens agregadas: nenhum texto, identificador ou caminho é publicado.", "",
        f"Gerado em {hoje.strftime('%d/%m/%Y')}.", "",
    ]
    return "\n".join(linhas)


# ---- gráfico ----
COR = {REVISAO: "#9085e9", IMPLEMENTACAO: "#58A6FF", SPEC: "#39C5CF", DOCS: "#3FB950", TESTES: "#d29922",
       OUTROS: "#8b949e"}
FUNDO, LARG, X0, X1, LIN = "#131C2E", 1200, 230, 1130, 7


def svg(r: dict) -> str:
    o, t = r["orquestrador"], r["total_agentes"]
    maximo = max(LIMITE_ZONA * 1.25, o["pico"] * 1.05, *(a["pico"] for a in r["agentes"]))

    def px(v: float) -> float:
        return X0 + (X1 - X0) * v / maximo

    y, corpo = 150, []

    def barra(rotulo: str, v: int, cor: str, atraso: float) -> None:
        nonlocal y
        corpo.append(f'<rect class="b" style="animation-delay:{atraso:.2f}s" x="{X0}" y="{y}" '
                     f'width="{px(v) - X0:.1f}" height="{LIN - 1}" rx="1" fill="{cor}"/>')
        if rotulo:
            corpo.append(f'<text class="s" x="{X0 - 8}" y="{y + 6}" text-anchor="end" font-size="9" '
                         f'fill="#C9D1D9">{rotulo}</text>')
        corpo.append(f'<text class="m" x="{px(v) + 6:.1f}" y="{y + 6}" font-size="10" fill="#8b949e">{n(v)}</text>')
        y += LIN + 3

    corpo.append(f'<text class="s" x="40" y="{y - 14}" font-size="13" font-weight="700" fill="#E6EDF3">'
                 f'Orquestrador (conversa principal, {o["n_sessoes"]} sessões)</text>')
    for i, u in enumerate(o["sessoes"], 1):
        barra(f"sessão {i}", u["pico"], "#E6EDF3", 0.05 * i)
    y += 10
    for k, (c, g) in enumerate((c, g) for c, g in r["categorias"].items() if g["n"]):
        corpo.append(f'<text class="s" x="40" y="{y + 4}" font-size="13" font-weight="700" fill="{COR[c]}">'
                     f'{c} ({g["n"]} agentes)</text>')
        y += 12
        for j, a in enumerate(g["agentes"]):
            barra("", a["pico"], COR[c], 0.4 + 0.05 * k + 0.005 * j)
        y += 10
    altura, xz, topo = y + 20, px(LIMITE_ZONA), 138
    desc = (f"Barras horizontais com o pico de contexto de cada agente, agrupadas por papel, e de cada sessão do "
            f"orquestrador. {r['n_agentes']} agentes geraram {n(t['saida'])} tokens; o orquestrador gerou "
            f"{n(o['saida'])} (razão {razao(t['saida'], o['saida'])}). {r['dentro_zona']} agentes ficaram na zona "
            f"de genialidade (até {n(LIMITE_ZONA)} tokens) e {r['fora_zona']} passaram. "
            f"Pico do orquestrador: {n(o['pico'])}.")
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {LARG} {altura}" width="{LARG}" height="{altura}" '
        f'role="img" aria-labelledby="t d"><title id="t">Orquestração: pico de contexto por agente</title>'
        f'<desc id="d">{desc}</desc>'
        '<style>.s{font-family:system-ui,-apple-system,"Segoe UI",sans-serif}'
        '.m{font-family:ui-monospace,"Cascadia Mono",Consolas,monospace}'
        '.b{transform-box:fill-box;transform-origin:0 50%;animation:g .8s ease-out backwards}'
        '@keyframes g{from{transform:scaleX(0)}}'
        '@media (prefers-reduced-motion:reduce){.b{animation:none}}</style>'
        f'<rect width="{LARG}" height="{altura}" rx="14" fill="{FUNDO}"/>'
        f'<text class="s" x="40" y="44" font-size="22" font-weight="700" fill="#E6EDF3">'
        f'{r["n_agentes"]} agentes geraram {mi(t["saida"])} tokens; o orquestrador, {mi(o["saida"])}</text>'
        f'<text class="s" x="40" y="70" font-size="14" fill="#8b949e">Razão {razao(t["saida"], o["saida"])} em '
        f'tokens gerados. Cada barra é o pico de contexto de um agente: {r["dentro_zona"]} dentro da zona, '
        f'{r["fora_zona"]} fora.</text>'
        f'<text class="s" x="40" y="92" font-size="14" fill="#C9D1D9">Orquestrador: pico de {n(o["pico"])} '
        f'tokens, {o["compactacoes"]} compactações de contexto.</text>'
        f'<rect x="{X0}" y="{topo}" width="{xz - X0:.1f}" height="{altura - topo - 20}" fill="#3FB950" opacity=".08"/>'
        + "".join(corpo) +
        f'<line x1="{xz:.1f}" y1="{topo - 8}" x2="{xz:.1f}" y2="{altura - 20}" stroke="#3FB950" '
        f'stroke-width="1.5" stroke-dasharray="5 4"/>'
        f'<text class="s" x="{xz + 6:.1f}" y="{topo - 12}" font-size="12" fill="#3FB950">'
        f'zona de genialidade: até {n(LIMITE_ZONA)} tokens</text></svg>')


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dir", type=Path, default=PASTA_PADRAO)
    p.add_argument("--saida", type=Path, default=SAIDA_PADRAO)
    p.add_argument("--svg", type=Path, default=SVG_PADRAO)
    p.add_argument("--ate", type=lambda t: datetime.fromisoformat(t).replace(tzinfo=FUSO),
                   help="corte: eventos depois deste instante (horário de São Paulo) são ignorados")
    a = p.parse_args()
    r = medir(a.dir, a.ate)
    for caminho, texto in ((a.saida, markdown(r)), (a.svg, svg(r))):
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_text(texto, encoding="utf-8")
    o, t = r["orquestrador"], r["total_agentes"]
    print(f"{r['n_agentes']} agentes: saída {n(t['saida'])} | orquestrador: saída {n(o['saida'])}, "
          f"pico {n(o['pico'])} | dentro da zona {r['dentro_zona']}, fora {r['fora_zona']}")


if __name__ == "__main__":
    main()
