import json
import re
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))
import orquestracao as oq  # noqa: E402

T0 = datetime(2026, 11, 19, 12, 0, 0, tzinfo=UTC)
SEGREDO = "TEXTO-SECRETO-DA-MENSAGEM"


def ts(m):
    return (T0 + timedelta(minutes=m)).isoformat().replace("+00:00", "Z")


def chamada(m, i=0, o=0, cl=0, cc=0, mid=None):
    usage = {"input_tokens": i, "output_tokens": o, "cache_read_input_tokens": cl,
             "cache_creation_input_tokens": cc}
    return {"type": "assistant", "timestamp": ts(m),
            "message": {"id": mid or f"m{m}-{i}-{o}", "content": [{"type": "text", "text": SEGREDO}],
                        "usage": usage}}


def dispara(m, tool_use):
    """Evento do assistente que chama a ferramenta Agent (o registro do pai guarda o id da chamada)."""
    return {"type": "assistant", "timestamp": ts(m), "message": {
        "id": f"d{m}-{tool_use}", "usage": {},
        "content": [{"type": "tool_use", "id": tool_use, "name": "Agent", "input": {}}]}}


def compacta(m, pre):
    return {"type": "system", "subtype": "compact_boundary", "timestamp": ts(m),
            "compactMetadata": {"preTokens": pre}}


def grava(caminho, eventos):
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text("\n".join(json.dumps(e) for e in eventos), encoding="utf-8")


def agente(pasta, sessao, nome, tipo, eventos, descricao="", tool_use=None):
    a = pasta / sessao / "subagents" / f"agent-{nome}.jsonl"
    grava(a, eventos)
    meta = {"agentType": tipo, "description": descricao, "toolUseId": tool_use or f"tu-{nome}", "spawnDepth": 1}
    a.with_suffix(".meta.json").write_text(json.dumps(meta), encoding="utf-8")


def test_soma_tokens_e_pico_do_agente(tmp_path):
    grava(tmp_path / "s1.jsonl", [chamada(0, i=1)])
    agente(tmp_path, "s1", "a", "plugin:tdd-guide",
           [chamada(1, i=10, o=5, cl=100, cc=20), chamada(2, i=30, o=7, cl=200, cc=0)])
    r = oq.medir(tmp_path)
    assert r["n_agentes"] == 1
    a = r["agentes"][0]
    assert (a["entrada"], a["saida"], a["cache_lido"], a["cache_criado"]) == (40, 12, 300, 20)
    assert a["pico"] == 230  # max(10+100+20, 30+200+0)
    assert a["papel"] == oq.IMPLEMENTADOR


def test_linhas_duplicadas_do_mesmo_message_id_contam_uma_vez(tmp_path):
    grava(tmp_path / "s1.jsonl", [chamada(0, i=5, o=9, mid="x"), chamada(0, i=5, o=9, mid="x")])
    r = oq.medir(tmp_path)
    assert r["orquestrador"]["saida"] == 9


def test_orquestrador_pico_totais_e_compactacoes(tmp_path):
    grava(tmp_path / "s1.jsonl", [chamada(0, i=1, cl=50, cc=9), chamada(1, i=2, cl=400_000, cc=8),
                                  compacta(2, 400_010), chamada(3, i=3, cl=10)])
    grava(tmp_path / "s2.jsonl", [chamada(5, i=1, cl=20)])
    o = oq.medir(tmp_path)["orquestrador"]
    assert o["pico"] == 400_010
    assert o["entrada"] == 7
    assert o["cache_lido"] == 400_080
    assert o["compactacoes"] == 1
    assert o["pre_compactacao_max"] == 400_010
    assert o["n_sessoes"] == 2
    assert o["sessoes_acima"] == 1


def test_limite_da_zona_e_300_mil_e_configuravel(tmp_path):
    assert oq.LIMITE_ZONA == 300_000
    grava(tmp_path / "s1.jsonl", [chamada(0, i=1)])
    agente(tmp_path, "s1", "a", "plugin:planner", [chamada(1, i=1, cl=1_000)])
    r = oq.medir(tmp_path, zona=500)
    assert r["zona"] == 500 and r["fora_zona"] == 1 and r["dentro_zona"] == 0


def test_corte_ate_ignora_eventos_e_agentes_depois(tmp_path):
    grava(tmp_path / "s1.jsonl", [chamada(0, i=1), chamada(60, i=1000)])
    agente(tmp_path, "s1", "a", "plugin:planner", [chamada(1, i=2)])
    agente(tmp_path, "s1", "b", "plugin:planner", [chamada(90, i=5000)])
    r = oq.medir(tmp_path, ate=T0 + timedelta(minutes=30))
    assert r["n_agentes"] == 1
    assert r["orquestrador"]["entrada"] == 1
    assert r["agentes"][0]["entrada"] == 2


@pytest.mark.parametrize("tipo,esperado", [
    ("plugin:tdd-guide", "Implementador"), ("outro:tdd-guide", "Implementador"), ("tdd-guide", "Implementador"),
    ("a:b:code-reviewer", "Revisor"), ("x:fastapi-reviewer", "Revisor"),
    ("x:security-reviewer", "Engenheiro de segurança"), ("x:architect", "Arquiteto"),
    ("x:planner", "Planejador"), ("x:e2e-runner", "QA"), ("x:doc-updater", "Documentador"),
    ("x:critic", "Crítico"), ("x:auditor", "Auditor"), ("x:researcher", "Pesquisador"),
    ("general-purpose", "Agente geral"), ("fork", "Agente geral"), (None, "Outros"), ("x:desconhecido", "Outros"),
])
def test_papel_em_portugues_ignora_qualquer_prefixo(tipo, esperado):
    assert oq.papel(tipo) == esperado


def test_papeis_zona_e_ausentes(tmp_path):
    grava(tmp_path / "s1.jsonl", [chamada(0, i=1)])
    agente(tmp_path, "s1", "a", "x:code-reviewer", [chamada(1, i=1, cl=299_999)])
    agente(tmp_path, "s1", "b", "x:security-reviewer", [chamada(1, i=1, cl=300_000)])
    agente(tmp_path, "s1", "c", "x:architect", [chamada(1, i=1)])
    agente(tmp_path, "s1", "d", None, [chamada(1, i=1)])
    r = oq.medir(tmp_path)
    p = r["papeis"]
    assert p["Revisor"]["n"] == 1 and p["Engenheiro de segurança"]["n"] == 1 and p["Arquiteto"]["n"] == 1
    assert p["Crítico"]["n"] == 0  # nunca existiu: não rotular revisores como críticos
    assert p["Revisor"]["pico"] == 300_000 and p["Engenheiro de segurança"]["pico"] == 300_001
    assert r["dentro_zona"] == 3 and r["fora_zona"] == 1  # 300.000 exato fica dentro, 300.001 fora
    assert "Crítico" in oq.markdown(r, hoje=T0).split("Sem registros")[1]


def test_agrupamento_e_por_sessao_do_orquestrador_cronologica(tmp_path):
    grava(tmp_path / "zzz.jsonl", [chamada(0, i=1)])  # nome de arquivo não manda: vale o primeiro instante
    grava(tmp_path / "aaa.jsonl", [chamada(100, i=1)])
    agente(tmp_path, "zzz", "a", "x:tdd-guide", [chamada(1, o=7)])
    agente(tmp_path, "zzz", "b", "x:tdd-guide", [chamada(2, o=3)])
    agente(tmp_path, "aaa", "c", "x:tdd-guide", [chamada(101, o=5)])
    w = oq.medir(tmp_path)["por_sessao"]
    assert [(x["n"], x["agentes"], x["saida"]) for x in w] == [(1, 2, 10), (2, 1, 5)]


def test_pico_de_concorrencia_intervalos_sobrepostos(tmp_path):
    grava(tmp_path / "s1.jsonl", [chamada(0, i=1)])
    agente(tmp_path, "s1", "a", "x:tdd-guide", [chamada(1), chamada(10)])
    agente(tmp_path, "s1", "b", "x:tdd-guide", [chamada(5), chamada(8)])
    agente(tmp_path, "s1", "c", "x:tdd-guide", [chamada(6), chamada(7)])
    agente(tmp_path, "s1", "d", "x:tdd-guide", [chamada(10), chamada(12)])  # começa quando a termina
    assert oq.medir(tmp_path)["concorrencia_max"] == 3


def test_concorrencia_ignora_pausas_longas_entre_eventos(tmp_path):
    grava(tmp_path / "s1.jsonl", [chamada(0, i=1)])
    agente(tmp_path, "s1", "x", "x:tdd-guide", [chamada(0), chamada(40)])  # pausa de 40 min: não ocupa o intervalo
    agente(tmp_path, "s1", "y", "x:tdd-guide", [chamada(10), chamada(20)])
    assert oq.medir(tmp_path)["concorrencia_max"] == 1
    agente(tmp_path, "s1", "z", "x:tdd-guide", [chamada(10), chamada(14), chamada(20)])
    assert oq.medir(tmp_path)["concorrencia_max"] == 2  # y e z trabalham juntos entre 10 e 20


def test_message_id_repetido_em_fork_conta_so_no_pai(tmp_path):
    grava(tmp_path / "s1.jsonl", [chamada(0, o=100, cc=7, mid="comum"), chamada(1, o=1)])
    agente(tmp_path, "s1", "f", "fork", [chamada(2, o=100, cc=7, mid="comum"), chamada(3, o=5, cl=900)])
    r = oq.medir(tmp_path)
    assert r["orquestrador"]["saida"] == 101 and r["orquestrador"]["cache_criado"] == 7
    a = r["agentes"][0]
    assert (a["saida"], a["cache_criado"], a["chamadas"]) == (5, 0, 1)
    assert a["pico"] == 900  # o pico de contexto continua sendo o da janela do próprio arquivo
    assert r["total_agentes"]["saida"] + r["orquestrador"]["saida"] == 106


@pytest.mark.parametrize("descricao,retrabalho", [
    ("Corrigir front", True), ("Fix JS review findings", True), ("Fixes da revisão", True),
    ("Fixar dialeto do CSV", False), ("Prefixo novo", False), ("Lote backend volta 2", True),
    ("Rodada 3 do lote", True), ("Plano v2", False), ("Retomada do lote", True),
])
def test_heuristica_de_retrabalho(descricao, retrabalho):
    assert bool(oq.RETRABALHO.search(descricao)) is retrabalho


def test_agente_aninhado_e_contado_uma_vez(tmp_path):
    grava(tmp_path / "s1.jsonl", [chamada(0, i=1), dispara(0, "tu-pai")])
    agente(tmp_path, "s1", "pai", "x:planner", [chamada(1, o=4), dispara(1, "tu-filho")], tool_use="tu-pai")
    agente(tmp_path, "s1", "filho", "x:tdd-guide", [chamada(2, o=6)], tool_use="tu-filho")
    r = oq.medir(tmp_path)
    assert r["n_agentes"] == 2 and r["aninhados"] == 1
    assert r["total_agentes"]["saida"] == 10  # cada agente soma só o próprio usage


def _lote(tmp_path, nome, tipo, m, desc):
    agente(tmp_path, "s1", nome, tipo, [chamada(m, o=1)], descricao=desc)


def test_agent_loop_voltas_reimplementacao_e_primeira_revisao(tmp_path):
    grava(tmp_path / "s1.jsonl", [chamada(0, i=1)])
    _lote(tmp_path, "a1", "x:tdd-guide", 1, "Fatia 1")
    _lote(tmp_path, "r1", "x:code-reviewer", 2, "Revisão da fatia 1")
    _lote(tmp_path, "a2", "x:tdd-guide", 3, "Corrigir fatia 1 (volta 2)")
    _lote(tmp_path, "r2", "x:code-reviewer", 4, "Revisão 2")
    _lote(tmp_path, "b1", "x:tdd-guide", 5, "Fatia 2")
    _lote(tmp_path, "s1r", "x:security-reviewer", 6, "Segurança da fatia 2")
    _lote(tmp_path, "c1", "x:tdd-guide", 7, "Fatia 3")
    loop = oq.medir(tmp_path)["loop"]
    assert loop["tarefas"] == 3 and loop["sem_revisao"] == 1
    assert loop["ciclos_revisao"] == 3 and loop["reimplementacoes"] == 1
    assert (loop["sem_retrabalho"], loop["com_revisao"]) == (1, 2)  # fatia 2 sem retrabalho; fatia 1 voltou
    assert loop["voltas_media"] == 1.5
    assert loop["criticos"] == 0


def test_agent_loop_revisao_sem_implementacao_antes_e_avulsa(tmp_path):
    grava(tmp_path / "s1.jsonl", [chamada(0, i=1)])
    _lote(tmp_path, "r1", "x:code-reviewer", 1, "Revisar spec")
    loop = oq.medir(tmp_path)["loop"]
    assert loop["tarefas"] == 0 and loop["revisoes_avulsas"] == 1 and loop["voltas_media"] is None


def test_markdown_e_svgs_so_numeros_agregados(tmp_path):
    grava(tmp_path / "s1.jsonl", [chamada(0, i=1, o=2)])
    agente(tmp_path, "s1", "a", "x:tdd-guide", [chamada(1, i=10, o=5, cl=100)], descricao="DESCRICAO-PRIVADA")
    r = oq.medir(tmp_path)
    md = oq.markdown(r, hoje=T0)
    for texto in (md, oq.svg(r), oq.svg(r, celular=True)):
        assert SEGREDO not in texto and "DESCRICAO-PRIVADA" not in texto and "s1" not in texto.replace("s1.", "")
        assert str(tmp_path) not in texto and "e" + "cc" not in texto.lower()
    assert "zona de genialidade" in md.lower() and "Implementador" in md
    assert "Gerado por `scripts/orquestracao.py`" in md
    assert "workflow" not in md.lower() and "Sessão do orquestrador" in md
    assert "agent loop (implementador → revisor; sem papel crítico" in md.lower()
    assert "Lotes sem retrabalho após a revisão" in md and "Aprovadas na 1ª" not in md
    assert "cache criado" in md.lower() and "cache lido" in md.lower() and oq.razao(115, 3) in md  # total bruto: 115 nos agentes contra 3 no orquestrador
    assert "preTokens" in md and "não é limite inferior" in md
    assert "| Métrica | Tipo | Fonte | Fórmula |" in md
    for tipo in ("observada", "calculada", "estimada", "indisponível"):
        assert tipo in md


def test_svgs_paleta_acessibilidade_e_concordancia(tmp_path):
    grava(tmp_path / "s1.jsonl", [chamada(0, i=1)])
    agente(tmp_path, "s1", "a", "x:tdd-guide", [chamada(1, cl=400_000)])
    r = oq.medir(tmp_path)
    for celular in (False, True):
        s = oq.svg(r, celular=celular)
        assert s.startswith("<svg") and 'role="img"' in s and "<title" in s and "<desc" in s
        assert "<script" not in s and "http" not in s.replace("http://www.w3.org/2000/svg", "")
        assert "#131C2E" in s and "#A371F7" in s and "@keyframes" in s and "prefers-reduced-motion" in s
        assert not {"#9085e9", "#7c6fe0", "#f0883e", "#d29922"} & set(re.findall(r"#[0-9a-f]{6}", s.lower()))
        assert len(s.encode()) <= 30_000
        assert "0 agentes ficaram" in s and "1 passou" in s and "1 passaram" not in s
    assert 'viewBox="0 0 400' in oq.svg(r, celular=True)
    assert "pico máximo por papel" in oq.svg(r, celular=True).split("<desc")[1].split("</desc>")[0]
    assert "pico máximo por papel" not in oq.svg(r).split("<desc")[1].split("</desc>")[0]


def test_aviso_de_corte_vem_do_ate_e_do_commit(tmp_path):
    grava(tmp_path / "s1.jsonl", [chamada(0, i=1)])
    ate = T0 + timedelta(minutes=5)
    md = oq.markdown({**oq.medir(tmp_path, ate=ate), "commit": "abc1234"}, hoje=T0)
    assert "até o commit `abc1234`" in md and "cec40ed" not in md
    md = oq.markdown(oq.medir(tmp_path, ate=ate), hoje=T0)
    assert "até 19/11/2026" in md and ":" not in md.split("até 19/11/2026")[1].split(".")[0]  # só data, sem hora
    assert "cec40ed" not in md


def test_ate_respeita_o_fuso_explicito_e_assume_sao_paulo_sem_fuso():
    assert oq.parse_ate("2026-11-21T20:02:20").utcoffset() == timedelta(hours=-3)
    assert oq.parse_ate("2026-11-21T20:02:20+00:00").utcoffset() == timedelta(0)


def test_pasta_vazia(tmp_path):
    r = oq.medir(tmp_path)
    assert r["n_agentes"] == 0 and r["orquestrador"]["pico"] == 0 and r["concorrencia_max"] == 0
    assert oq.markdown(r, hoje=T0) and oq.svg(r) and oq.svg(r, celular=True)


def test_svgs_marcam_a_concorrencia_como_estimada_e_explicam_fork():
    r = oq.medir(Path("pasta-inexistente"))
    assert "agentes ao mesmo tempo (estimado)." in oq.svg(r)  # desktop: a frase cabe numa linha
    assert "(estimado)." in oq.svg(r, celular=True)  # celular: a frase quebra em linhas de 50 caracteres
    assert "(cópia de uma conversa que herda o início dela)" in oq.markdown(r, hoje=T0)


def test_aviso_de_corte_diz_como_reproduzir_sem_publicar_registros():
    r = {**oq.medir(Path("pasta-inexistente")), "ate": T0, "commit": "cec40ed"}
    md = oq.markdown(r, hoje=T0)
    assert ("Para reproduzir (exige os registros locais do Claude Code, que não são publicados): "
            "`python scripts/orquestracao.py --ate-commit cec40ed`.") in md
