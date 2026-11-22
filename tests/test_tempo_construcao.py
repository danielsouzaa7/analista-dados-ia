import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))
import tempo_construcao as tc  # noqa: E402

T0 = datetime(2026, 11, 19, 12, 0, 0, tzinfo=UTC)
SEGREDO = "TEXTO-SECRETO-DA-MENSAGEM"


def ts(minutos):
    return (T0 + timedelta(minutes=minutos)).isoformat().replace("+00:00", "Z")


def humano(m):
    return {"type": "user", "timestamp": ts(m), "message": {"content": SEGREDO}}


def ferramenta(m):
    return {"type": "user", "timestamp": ts(m), "message": {"content": [{"type": "tool_result", "content": SEGREDO}]}}


def assistente(m):
    return {"type": "assistant", "timestamp": ts(m), "message": {"content": [{"type": "text", "text": SEGREDO}]}}


def fim_turno(m, pendentes=0):
    return {"type": "system", "subtype": "turn_duration", "timestamp": ts(m), "durationMs": 1,
            "pendingBackgroundAgentCount": pendentes}


def escrever(caminho, eventos, extra=""):
    caminho.parent.mkdir(parents=True, exist_ok=True)
    linhas = [json.dumps(e) for e in eventos]
    caminho.write_text("\n".join(linhas) + "\n" + extra, encoding="utf-8")


def subagente(pasta, sessao, id_, tipo, eventos):
    escrever(pasta / sessao / "subagents" / f"agent-{id_}.jsonl", eventos)
    (pasta / sessao / "subagents" / f"agent-{id_}.meta.json").write_text(json.dumps({"agentType": tipo}))


def test_gap_maior_que_cinco_minutos_nao_conta(tmp_path):
    escrever(tmp_path / "s1.jsonl", [humano(0), assistente(2), assistente(20), assistente(21)])
    r = tc.medir(tmp_path)
    assert r["ativo"] == timedelta(minutes=3)
    assert r["corrido"] == timedelta(minutes=21)


def test_gap_de_exatos_cinco_minutos_conta(tmp_path):
    escrever(tmp_path / "s1.jsonl", [humano(0), assistente(5)])
    assert tc.medir(tmp_path)["ativo"] == timedelta(minutes=5)


def test_espera_pelo_humano_apos_fim_de_turno_nao_conta(tmp_path):
    escrever(tmp_path / "s1.jsonl", [humano(0), assistente(1), fim_turno(1), humano(4), assistente(5)])
    # conta 0-1 e 4-5; os 3 min de espera nao contam
    assert tc.medir(tmp_path)["ativo"] == timedelta(minutes=2)


def test_agente_em_segundo_plano_mantem_o_tempo_contando(tmp_path):
    escrever(tmp_path / "s1.jsonl", [humano(0), fim_turno(1, pendentes=1), humano(4)])
    subagente(tmp_path, "s1", "a1", "ecc:code-reviewer", [assistente(1), assistente(3), assistente(4)])
    r = tc.medir(tmp_path)
    assert r["ativo"] == timedelta(minutes=4)
    assert r["agentes"] == timedelta(minutes=3)
    assert r["paralelismo"] == 0.75
    assert r["n_agentes"] == 1 and r["n_sessoes"] == 1


def test_linha_sem_timestamp_ou_json_quebrado_e_ignorada(tmp_path):
    escrever(tmp_path / "s1.jsonl", [humano(0), {"type": "mode"}, assistente(2)], extra="{quebrado\n")
    assert tc.medir(tmp_path)["ativo"] == timedelta(minutes=2)


def test_mensagem_meta_nao_e_humana(tmp_path):
    meta = humano(4) | {"isMeta": True}
    escrever(tmp_path / "s1.jsonl", [humano(0), fim_turno(1), meta, assistente(5)])
    # sem mensagem humana apos o fim do turno, a espera so termina no proximo humano: nada depois
    assert tc.medir(tmp_path)["ativo"] == timedelta(minutes=1)


def test_resultado_de_ferramenta_nao_e_humano(tmp_path):
    escrever(tmp_path / "s1.jsonl", [humano(0), fim_turno(1), ferramenta(3), humano(4)])
    assert tc.medir(tmp_path)["ativo"] == timedelta(minutes=1)


def test_categoria_por_agent_type():
    c = tc.categoria
    assert c("ecc:security-reviewer") == c("ecc:typescript-reviewer") == "Revisão"
    assert c("ecc:tdd-guide") == c("build-error-resolver") == c("general-purpose") == "Implementação"
    assert c("ecc:architect") == c("ecc:planner") == c("ecc:code-architect") == "Spec/plano"
    assert c("ecc:doc-updater") == "Documentação"
    assert c("ecc:e2e-runner") == c("ecc:browser-qa") == "Testes"
    assert c("algo-novo") == "Outros"
    assert c(None) == "Outros"


def test_markdown_tem_numeros_e_nenhum_texto_de_mensagem(tmp_path):
    escrever(tmp_path / "s1.jsonl", [humano(0), assistente(60), assistente(63)])
    subagente(tmp_path, "s1", "a1", "ecc:planner", [assistente(60), assistente(62)])
    md = tc.markdown(tc.medir(tmp_path), hoje=datetime(2026, 11, 19, tzinfo=UTC))
    assert SEGREDO not in md
    assert "| Tempo ativo de relógio | 0h03 |" in md
    assert "| Relógio corrido | 1h03 |" in md
    assert "| Horas paradas excluídas | 1h00 |" in md
    assert "| Spec/plano | 1 | 0h02 |" in md
    assert "| Paralelismo médio | 0,7x |" in md
    assert "Como foi medido" in md and "19/11/2026" in md


def test_pasta_vazia_nao_quebra(tmp_path):
    r = tc.medir(tmp_path)
    assert r["ativo"] == timedelta(0) and r["paralelismo"] == 0
    assert "Como foi medido" in tc.markdown(r)


def texto(m, conteudo):
    return {"type": "user", "timestamp": ts(m), "message": {"content": conteudo}}


def test_comandos_do_dono_e_lembretes_nao_encerram_a_espera(tmp_path):
    neutras = ["<bash-input>ls</bash-input>", "<bash-stdout>x</bash-stdout>", "<system-reminder>x</system-reminder>"]
    for i, c in enumerate(neutras):
        pasta = tmp_path / str(i)
        escrever(pasta / "s1.jsonl", [humano(0), fim_turno(1), texto(3, c), humano(4)])
        assert tc.medir(pasta)["ativo"] == timedelta(minutes=1), c


def test_notificacao_automatica_dispara_trabalho_e_encerra_a_espera(tmp_path):
    for i, c in enumerate(["<task-notification>x</task-notification>", "[SYSTEM NOTIFICATION - NOT USER INPUT] x"]):
        pasta = tmp_path / str(i)
        escrever(pasta / "s1.jsonl", [humano(0), fim_turno(1), texto(30, c), assistente(32), fim_turno(32)])
        assert tc.medir(pasta)["ativo"] == timedelta(minutes=3), c  # 0-1 e 30-32; a espera 1-30 e ociosa


def test_trabalho_apos_notificacao_conta_mesmo_com_espera_curta(tmp_path):
    escrever(tmp_path / "s1.jsonl", [humano(0), fim_turno(1), texto(3, "<task-notification>x"), assistente(5)])
    assert tc.medir(tmp_path)["ativo"] == timedelta(minutes=3)  # 0-1 e 3-5


def test_espera_aberta_de_uma_sessao_nao_apaga_o_trabalho_de_outra(tmp_path):
    escrever(tmp_path / "s1.jsonl", [humano(0), fim_turno(1)])  # sessao termina esperando o dono
    escrever(tmp_path / "s2.jsonl", [humano(100), assistente(102)])
    assert tc.medir(tmp_path)["ativo"] == timedelta(minutes=3)


def test_sessoes_sobrepostas_nao_contam_o_mesmo_tempo_duas_vezes(tmp_path):
    escrever(tmp_path / "s1.jsonl", [humano(0), assistente(4)])
    escrever(tmp_path / "s2.jsonl", [humano(2), assistente(6)])
    assert tc.medir(tmp_path)["ativo"] == timedelta(minutes=6)


def test_agente_trabalhando_cobre_a_espera_da_conversa_principal(tmp_path):
    escrever(tmp_path / "s1.jsonl", [humano(0), fim_turno(1, pendentes=1), texto(7, "<task-notification>x"), humano(9)])
    subagente(tmp_path, "s1", "a1", "ecc:planner", [assistente(2), assistente(4), assistente(6)])
    # pendentes=1: nao ha espera; a notificacao nao muda nada e todo o intervalo (0-9) e continuo
    assert tc.medir(tmp_path)["ativo"] == timedelta(minutes=9)


def test_eventos_depois_do_corte_sao_ignorados(tmp_path):
    escrever(tmp_path / "s1.jsonl", [humano(0), assistente(2), assistente(4), assistente(6)])
    subagente(tmp_path, "s1", "a", "tdd-guide", [assistente(1), assistente(3)])
    r = tc.medir(tmp_path, ate=T0 + timedelta(minutes=3))
    assert r["ativo"] == timedelta(minutes=3)
    assert r["corrido"] == timedelta(minutes=3)
    assert r["agentes"] == timedelta(minutes=2)


def test_agente_que_comecou_depois_do_corte_nao_conta(tmp_path):
    escrever(tmp_path / "s1.jsonl", [humano(0), assistente(2)])
    escrever(tmp_path / "s2.jsonl", [humano(10), assistente(11)])
    subagente(tmp_path, "s1", "a", "tdd-guide", [assistente(1), assistente(2)])
    subagente(tmp_path, "s1", "b", "planner", [assistente(10), assistente(11)])
    r = tc.medir(tmp_path, ate=T0 + timedelta(minutes=5))
    assert r["n_agentes"] == 1
    assert r["n_sessoes"] == 1
    assert r["categorias"][tc.SPEC][0] == 0
    assert r["ativo"] == timedelta(minutes=2)
