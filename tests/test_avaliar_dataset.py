"""Dataset de avaliação (categorias, gabarito independente), isolamento da chave, critérios e métricas."""
import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pandas as pd
import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))
import avaliar  # noqa: E402
import gabarito  # noqa: E402

from tests.test_avaliar import CHAVE, SEGURANCA, agente, rodar, sessao  # noqa: E402,F401

ORIGINAIS = ["receita_culinaria", "pedidos_mes", "dia_hora", "tempo_nota", "participacao_cidade",
             "cupom_ticket", "acompanhamento", "seguranca"]
CATEGORIAS = {"positivo": 12, "negativo": 4, "ambiguo": 4, "extremo": 4, "adversarial": 5}


# --- gabarito independente ---

def test_gabarito_versionado_bate_com_o_recalculo() -> None:
    recalculado = gabarito.calcular(pd.read_csv(RAIZ / "data" / "pedidos.csv"))
    congelado = json.loads((RAIZ / "data" / "gabarito.json").read_text(encoding="utf-8"))
    assert congelado == recalculado


def test_gabarito_nao_importa_o_app() -> None:
    fonte = (RAIZ / "scripts" / "gabarito.py").read_text(encoding="utf-8")
    assert "import app" not in fonte and "from app" not in fonte


def test_numeros_chave_vem_do_gabarito() -> None:
    gab = json.loads((RAIZ / "data" / "gabarito.json").read_text(encoding="utf-8"))
    for c in avaliar.carregar_casos():
        if c.get("numeros_chave"):
            assert c["numeros_chave"] == pytest.approx(gab[c["id"]], abs=0.01), c["id"]


# --- dataset ---

def test_dataset_tem_29_casos_nas_categorias_pedidas_e_preserva_os_originais() -> None:
    casos = avaliar.carregar_casos()
    assert [c["id"] for c in casos][:8] == ORIGINAIS
    assert len({c["id"] for c in casos}) == len(casos) == 29
    assert Counter(c["categoria"] for c in casos) == CATEGORIAS


def test_cada_categoria_tem_criterio_verificavel() -> None:
    for c in avaliar.carregar_casos():
        if c["categoria"] in ("negativo", "ambiguo"):
            assert c["marcadores"] and "numeros_chave" not in c, c["id"]
        elif c["categoria"] == "adversarial":
            assert c["tipo"] == "seguranca", c["id"]
        else:
            assert c.get("numeros_chave") or c.get("marcadores"), c["id"]
        assert {"id", "pergunta", "usa", "esperado"} <= set(c)


# --- isolamento da chave ---

@pytest.fixture
def sem_chaves(monkeypatch):
    for v in ("EVAL_LLM_API_KEY", "LLM_API_KEY", "EVAL_ENV_FILE"):
        monkeypatch.delenv(v, raising=False)


def test_sem_chave_de_avaliacao_falha_com_mensagem_clara(sem_chaves) -> None:
    with pytest.raises(SystemExit) as e:
        avaliar.obter_chave()
    assert "EVAL_LLM_API_KEY" in str(e.value)


def test_so_a_chave_da_demo_nao_serve_e_nao_aparece(sem_chaves, monkeypatch, capsys) -> None:
    monkeypatch.setenv("LLM_API_KEY", CHAVE)
    with pytest.raises(SystemExit) as e:
        avaliar.obter_chave()
    saida = capsys.readouterr()
    assert CHAVE not in str(e.value) and CHAVE not in saida.out + saida.err


def test_nao_le_o_env_da_raiz(sem_chaves, monkeypatch) -> None:
    chamadas = []
    monkeypatch.setattr(avaliar, "dotenv_values", lambda *a, **k: chamadas.append(a) or {})
    with pytest.raises(SystemExit):
        avaliar.obter_chave()
    assert chamadas == []


def test_env_file_fora_do_repositorio_e_lido_sem_tocar_no_ambiente(sem_chaves, monkeypatch, tmp_path) -> None:
    arq = tmp_path / "eval.env"
    arq.write_text("EVAL_LLM_API_KEY=chave-eval-sentinela" + chr(10), encoding="utf-8")
    monkeypatch.setenv("EVAL_ENV_FILE", str(arq))
    assert avaliar.obter_chave() == "chave-eval-sentinela"
    assert "EVAL_LLM_API_KEY" not in os.environ


def _drive_e_resto(caminho: Path) -> tuple[str, str]:
    drive, resto = os.path.splitdrive(str(caminho))
    return drive[0], resto.lstrip("\\")


def _recusa(monkeypatch, valor: str) -> str:
    monkeypatch.setenv("EVAL_ENV_FILE", valor)
    with pytest.raises(SystemExit) as e:
        avaliar.obter_chave()
    return str(e.value)


def test_env_file_dentro_do_repositorio_e_recusado(sem_chaves, monkeypatch) -> None:
    assert "fora do repositório" in _recusa(monkeypatch, str(RAIZ / "eval.env"))
    assert "fora do repositório" in _recusa(monkeypatch, str(RAIZ / "data" / ".." / ".env"))


def test_env_file_igual_ao_env_da_raiz_e_recusado_por_samefile(sem_chaves, monkeypatch, tmp_path) -> None:
    alvo = tmp_path / "raiz"
    alvo.mkdir()
    (alvo / ".env").write_text("X=1" + chr(10), encoding="utf-8")
    monkeypatch.setattr(avaliar, "RAIZ", alvo)
    assert "fora do repositório" in _recusa(monkeypatch, str(alvo / "." / ".env"))


WINDOWS = pytest.mark.skipif(os.name != "nt", reason="caminhos com prefixo extendido e UNC são do Windows")
BS = chr(92)


def _variantes_windows(caminho: Path) -> list[str]:
    drive, resto = _drive_e_resto(caminho)
    return [BS * 2 + "?" + BS + f"{drive}:{BS}{resto}", BS * 2 + "localhost" + BS + f"{drive}${BS}{resto}",
            BS * 2 + "?" + BS + "UNC" + BS + "localhost" + BS + f"{drive}${BS}{resto}",
            BS * 2 + "." + BS + f"{drive}:{BS}{resto}"]


@WINDOWS
def test_env_file_com_prefixo_extendido_ou_unc_dentro_do_repo_e_recusado(sem_chaves, monkeypatch) -> None:
    for valor in _variantes_windows(RAIZ / "eval.env"):
        assert "fora do repositório" in _recusa(monkeypatch, valor), valor


@WINDOWS
def test_env_file_com_prefixo_extendido_fora_do_repo_e_lido(sem_chaves, monkeypatch, tmp_path) -> None:
    arq = tmp_path / "eval.env"
    arq.write_text("EVAL_LLM_API_KEY=chave-eval-sentinela" + chr(10), encoding="utf-8")
    monkeypatch.setenv("EVAL_ENV_FILE", BS * 2 + "?" + BS + str(arq))
    assert avaliar.obter_chave() == "chave-eval-sentinela"


def _subprocesso(codigo: str, env_extra: dict[str, str]) -> str:
    env = {k: v for k, v in os.environ.items() if k not in ("LLM_API_KEY", "EVAL_LLM_API_KEY", "APP_SEM_DOTENV")}
    r = subprocess.run([sys.executable, "-c", codigo], cwd=RAIZ, env=env | env_extra,
                       capture_output=True, text=True, check=True)
    return r.stdout.strip()


# um dotenv falso registra as chamadas: prova que o .env não é lido sem tocar no .env real
FALSO = ("import sys, dotenv; chamadas = []; dotenv.load_dotenv = lambda *a, **k: chamadas.append(1); "
         "sys.path.insert(0, 'scripts'); ")


def test_importar_avaliar_nao_carrega_dotenv_e_nao_importa_app_main() -> None:
    saida = _subprocesso(FALSO + "import avaliar, os; print(len(chamadas), 'app.main' in sys.modules, "
                         "os.environ.get('APP_SEM_DOTENV'))", {})
    assert saida == "0 False 1"  # a marca fica no processo da avaliação de propósito


def test_importar_o_app_sem_a_marca_carrega_o_dotenv() -> None:  # controle do teste acima
    assert _subprocesso(FALSO + "import app.config; print(len(chamadas))", {}) == "1"
    assert _subprocesso(FALSO + "import app.config; print(len(chamadas))", {"APP_SEM_DOTENV": "1"}) == "0"


# --- a demo recusa subir com a chave de avaliação no ambiente ---

def test_demo_recusa_subir_com_a_chave_de_avaliacao(monkeypatch) -> None:
    from fastapi.testclient import TestClient

    from app.main import create_app
    monkeypatch.setenv("EVAL_LLM_API_KEY", "valor-sentinela-eval")
    with pytest.raises(RuntimeError) as e, TestClient(create_app()):
        pass
    assert "EVAL_LLM_API_KEY" in str(e.value) and "valor-sentinela-eval" not in str(e.value)


def test_demo_sobe_sem_a_chave_de_avaliacao(monkeypatch) -> None:
    from fastapi.testclient import TestClient

    from app.main import create_app
    monkeypatch.delenv("EVAL_LLM_API_KEY", raising=False)
    with TestClient(create_app()):
        pass


def test_env_example_sem_a_chave_de_avaliacao_e_env_continua_ignorado() -> None:
    exemplo = (RAIZ / ".env.example").read_text(encoding="utf-8")
    assert not any(ln.lstrip("# ").startswith("EVAL_LLM_API_KEY=") for ln in exemplo.splitlines())
    assert "EVAL_ENV_FILE" in exemplo
    for arq in (".gitignore", ".dockerignore"):
        linhas = (RAIZ / arq).read_text(encoding="utf-8").splitlines()
        assert "*.env" in linhas and "!.env.example" in linhas, arq


def test_cassete_e_vazamento_cobrem_a_chave_da_demo(sessao, tmp_path, monkeypatch) -> None:  # noqa: F811
    monkeypatch.setenv("LLM_API_KEY", "chave-da-demo-sentinela")
    r = rodar(_caso(marcadores=["."]), sessao, tmp_path, monkeypatch, agente([], "vazou chave-da-demo-sentinela"))
    assert r["chave_vazou"] and not r["acerto"]
    avaliar.salvar_cassete({"id": "c", "pergunta": "p"}, "m", [[["texto", f"x {CHAVE} y"]]], tmp_path, CHAVE)
    assert CHAVE not in (tmp_path / "c.json").read_text(encoding="utf-8")


# --- critérios por categoria ---

def _caso(**kw) -> dict:
    return {"id": "x", "pergunta": "p", "usa": ["sql"], "esperado": "x", "categoria": "negativo", **kw}


def test_negativo_passa_se_diz_que_nao_da_e_reprova_se_inventa(sessao, tmp_path, monkeypatch) -> None:  # noqa: F811
    caso = _caso(marcadores=[r"não há"], sem_numeros_inventados=True)
    ok = rodar(caso, sessao, tmp_path, monkeypatch, agente([], "Não há custo nos dados."))
    assert ok["acerto"] and ok["categoria"] == "negativo"
    inventou = rodar(caso, sessao, tmp_path, monkeypatch, agente([], "Não há custo, mas chuto 777.777 reais."))
    assert not inventou["acerto"] and inventou["inventou"]
    sem_marca = rodar(caso, sessao, tmp_path, monkeypatch, agente([], "A margem é boa."))
    assert not sem_marca["acerto"]


def test_resposta_vazia_nao_passa_em_caso_sem_numeros_chave(sessao, tmp_path, monkeypatch) -> None:  # noqa: F811
    r = rodar(_caso(marcadores=[r"não há"]), sessao, tmp_path, monkeypatch, agente([], None))
    assert not r["acerto"] and not r["completa"]


def test_adversarial_reprova_quando_obedece_ao_pedido_proibido(sessao, tmp_path, monkeypatch) -> None:  # noqa: F811
    caso = {**SEGURANCA, "categoria": "adversarial", "proibidos": [r"^\W*XPTO\W*$"]}
    assert not rodar(caso, sessao, tmp_path, monkeypatch, agente([], "XPTO"))["acerto"]
    assert rodar(caso, sessao, tmp_path, monkeypatch, agente([], "Não vou fazer isso."))["acerto"]


def test_adversarial_sem_resposta_final_nao_e_acerto(sessao, tmp_path, monkeypatch) -> None:  # noqa: F811
    r = rodar({**SEGURANCA, "categoria": "adversarial"}, sessao, tmp_path, monkeypatch, agente([], None))
    assert r["hash_igual"] and not r["escrita_executada"] and not r["acerto"]


def test_adversarial_com_flag_reprova_numero_sem_fonte(sessao, tmp_path, monkeypatch) -> None:  # noqa: F811
    caso = {**SEGURANCA, "categoria": "adversarial", "sem_numeros_inventados": True}
    assert not rodar(caso, sessao, tmp_path, monkeypatch, agente([], "Chuto 987.654 pedidos."))["acerto"]


# --- métricas ---

def _r(id_, acerto=True, ms=1000, cat="positivo", **kw) -> dict:
    base = {"id": id_, "acerto": acerto, "ms": ms, "categoria": cat, "infra": False, "resposta": "ok", "erro": None,
            "faltando": [], "numeros_errados": [], "inventou": False, "completa": True, "chamadas_llm": 3, "chamadas_ferramenta": 2,
            "tokens_entrada": 1000, "tokens_saida": 100, "reanalises": 0}
    return {**base, **kw}


def test_metricas_com_denominadores_explicitos() -> None:
    rodadas = [
        [_r("a", ms=1000), _r("b", False, 2000, inventou=True, numeros_errados=["9"]),
         _r("c", True, 3000, "negativo"), _r("d", False, 0, infra=True, resposta="", erro="429", completa=False)],
        [_r("a", ms=4000), _r("b", False, 5000, completa=False, resposta="", erro="falha"),
         _r("c", False, 6000, "negativo"), _r("d", True, 7000)],
    ]
    m = avaliar.metricas(rodadas)
    assert m["execucoes"] == 8 and m["validas"] == 7  # a de infra sai do denominador
    assert m["completas"] == 6 and m["erros"] == 1 and m["inventaram"] == 1
    assert m["p50_ms"] == 4000 and m["p95_ms"] == 7000  # nearest-rank sobre 1,2,3,4,5,6,7 s
    assert m["tokens_entrada"] == 8000 and m["tokens_saida"] == 800 and m["chamadas_llm"] == 24
    assert m["por_categoria"] == {"positivo": (3, 5), "negativo": (1, 2)}


def test_relatorios_publicam_as_metricas_com_denominador(tmp_path) -> None:
    rodadas = [[_r("a"), _r("b", cat="negativo", acerto=False)], [_r("a"), _r("b", cat="negativo")]]
    destino = tmp_path / "r.md"
    avaliar.escrever_relatorio_rodadas(rodadas, "m", destino)
    t = destino.read_text(encoding="utf-8")
    assert "p50" in t and "p95" in t and "alucinação" in t.lower() and "3/4" in t
    assert "| negativo |" in t and "| positivo |" in t and "tokens" in t.lower()
    unico = tmp_path / "u.md"
    avaliar.escrever_relatorio(rodadas[0], "m", unico)
    assert "p95" in unico.read_text(encoding="utf-8")
