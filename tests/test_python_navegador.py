import logging
import threading
import time

import pytest

from app import python_navegador as pn
from app import python_tool

CSV = "a\r\n1\r\n"


@pytest.fixture(autouse=True)
def _limpa(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pn, "BATIDA_S", 0.02)
    pn._PENDENTES.clear()


def _executar(sessao: str = "s1", id_: str = "t1", restante: float = 120):
    return pn.executor(sessao)(id_, "print(1)", CSV, restante)


def _drenar(gerador) -> tuple[list[dict], dict]:
    """Consome o gerador: devolve os eventos e o valor de retorno."""
    eventos = []
    while True:
        try:
            eventos.append(next(gerador))
        except StopIteration as fim:
            return eventos, fim.value


def _entregar_depois(sessao, id_, nonce, saida="ok", erro=None, apos=0.05) -> list:
    resp: list = []
    threading.Timer(apos, lambda: resp.append(pn.entregar(sessao, id_, nonce, saida, erro))).start()
    return resp


def test_pedido_traz_id_nonce_codigo_csv_e_preludio() -> None:
    ev = next(_executar())
    assert ev["evento"] == "python_pedido" and ev["id"] == "t1"
    assert ev["codigo"] == "print(1)" and ev["csv"] == CSV and ev["preludio"] == python_tool.PRELUDIO
    assert len(ev["nonce"]) == 32 and int(ev["nonce"], 16) >= 0


def test_resultado_entregue_destrava_e_vira_retorno() -> None:
    g = _executar()
    ev = next(g)
    resp = _entregar_depois("s1", "t1", ev["nonce"], saida="42\n")
    eventos, retorno = _drenar(g)
    assert retorno == {"saida": "42\n", "erro": None}
    assert resp == [True] and pn._PENDENTES == {}
    assert all(e["evento"] == "python_aguardando" for e in eventos)


def test_resultado_aceito_uma_unica_vez() -> None:
    g = _executar()
    nonce = next(g)["nonce"]
    assert pn.entregar("s1", "t1", nonce, "um", None) is True
    assert pn.entregar("s1", "t1", nonce, "dois", None) is False
    assert _drenar(g)[1]["saida"] == "um"


@pytest.mark.parametrize("sessao, id_, errado", [("outra", "t1", False), ("s1", "outro", False), ("s1", "t1", True)])
def test_nonce_sessao_ou_id_errados_recusados_sem_derrubar_a_pendente(sessao, id_, errado) -> None:
    g = _executar()
    certo = next(g)["nonce"]
    assert pn.entregar(sessao, id_, "0" * 32 if errado else certo, "forjado", None) is False
    assert pn._PENDENTES["s1"].resultado is None  # a pendente continua de pé
    assert pn.entregar("s1", "t1", certo, "legitimo", None) is True
    assert _drenar(g)[1]["saida"] == "legitimo"


def test_sem_pendente_recusa() -> None:
    assert pn.entregar("s1", "t1", "0" * 32, "x", None) is False


def test_prazo_estourado_devolve_erro_e_recusa_resultado_atrasado(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pn, "PRAZO_S", 0.1)
    g = _executar()
    nonce = next(g)["nonce"]
    _, retorno = _drenar(g)
    assert retorno == pn.ERRO_PRAZO and "a tempo" in retorno["erro"]
    assert pn.entregar("s1", "t1", nonce, "tarde", None) is False


def test_post_no_fim_do_prazo_nunca_recebe_204_e_some(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pn, "PRAZO_S", 0.03)
    monkeypatch.setattr(pn, "BATIDA_S", 0.005)
    for i in range(40):
        g = _executar()
        nonce = next(g)["nonce"]
        resp = _entregar_depois("s1", "t1", nonce, saida=f"r{i}", apos=0.03 + (i % 5 - 2) * 0.002)
        _, retorno = _drenar(g)
        for _ in range(100):  # espera a thread do POST terminar
            if resp:
                break
            time.sleep(0.01)
        assert resp, "o POST deveria ter respondido"
        # 204 (True) implica resultado usado; 400 (False) implica prazo
        assert retorno == ({"saida": f"r{i}", "erro": None} if resp[0] else pn.ERRO_PRAZO)


def test_fechar_o_gerador_remove_a_pendente() -> None:
    g = _executar()
    nonce = next(g)["nonce"]
    assert "s1" in pn._PENDENTES
    g.close()
    assert pn._PENDENTES == {}
    assert pn.entregar("s1", "t1", nonce, "x", None) is False


def test_batidas_saem_a_cada_intervalo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pn, "PRAZO_S", 0.3)
    monkeypatch.setattr(pn, "BATIDA_S", 0.05)
    eventos, _ = _drenar(_executar())
    batidas = [e for e in eventos[1:] if e["evento"] == "python_aguardando"]
    assert 3 <= len(batidas) <= 7 and all(b["id"] == "t1" for b in batidas)


def test_prazo_respeita_o_restante_da_pergunta() -> None:
    desde = time.monotonic()
    _, retorno = _drenar(_executar(restante=0.1))  # PRAZO_S real (80 s) seria bem maior
    assert retorno == pn.ERRO_PRAZO and time.monotonic() - desde < 2


def test_bytes_do_pedido_vao_para_o_log(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="analista"):
        g = _executar()
        next(g)
    g.close()
    assert f"bytes={len(CSV) + len('print(1)')}" in caplog.text


MIB = 1024 * 1024


def test_python_pedido_tem_teto_em_bytes() -> None:
    # x01 vira  no JSON (6 bytes): 5 Mi caracteres seriam ~30 MiB no fio; o teto é em bytes serializados
    g = _executar_com(csv=chr(1) * 400_000)  # 2,4 MB no fio, com só 400 mil caracteres
    eventos, retorno = _drenar(g)
    assert eventos == [] and "agregue no SQL" in retorno["erro"] and pn._PENDENTES == {}
    ok = pn.executor("s1")("t1", "print(1)", "a" * (pn.MAX_BYTES_PEDIDO_PYTHON - 1000), 120)
    assert next(ok)["evento"] == "python_pedido"
    ok.close()


def test_python_pedido_tem_orcamento_de_bytes_por_pergunta() -> None:
    executor = pn.executor("s1")  # um executor por pergunta: o orçamento vale para a pergunta inteira
    csv = "a" * (3 * MIB // 2)
    for i in range(4):
        g = executor(f"t{i}", "print(1)", csv, 120)
        if i < 3:
            assert next(g)["evento"] == "python_pedido"
            g.close()
        else:
            eventos, retorno = _drenar(g)
            assert eventos == [] and "agregue no SQL" in retorno["erro"]
    assert pn.executor("s1") is not executor
    novo = pn.executor("s1")("t9", "print(1)", csv, 120)  # outra pergunta começa com o orçamento cheio
    assert next(novo)["evento"] == "python_pedido"
    novo.close()


def test_executor_devolve_copia_do_erro_de_prazo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pn, "PRAZO_S", 0.05)
    _, retorno = _drenar(_executar())
    retorno["erro"] = "alterado"
    assert pn.ERRO_PRAZO["erro"].startswith("O navegador não devolveu")


def _executar_com(csv: str):
    return pn.executor("s1")("t1", "print(1)", csv, 120)
