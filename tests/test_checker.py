import json
from pathlib import Path

import pytest

from app import prompts
from app.checker import (
    afirma_significancia,
    conferir_numeros,
    sem_citacoes_de_p,
    significancia_sem_p_valor,
    tem_p_valor,
)
from app.checker import numeros_nao_conferidos as nc


@pytest.mark.parametrize("resposta,resultado", [
    ("A receita foi de R$ 1.234,56.", "1234.56"),
    ("Cerca de 1.235 reais.", "1234.56"),
    ("Participação de 15,3%.", "0.153"),
    ("Participação de 15,3%.", "15.3"),
    ("Em 2024-03-15 houve vendas.", "data\n2024-03-15"),
    ("Total de 1.200.000.", "1.2e+06"),
    ("Caiu 3 pontos.", "x"),
    ("Valor negativo: 3,5.", "-3.5"),
])
def test_confere(resposta: str, resultado: str) -> None:
    assert nc(resposta, [resultado], "pergunta") == []


def test_numero_errado_falha() -> None:
    assert nc("O total foi 999.", ["1234.56"], "pergunta") == ["999"]


def test_porcentagem_errada_devolve_texto_original() -> None:
    assert nc("Subiu 50,5%.", ["1234.56"], "x") == ["50,5%"]


def test_inteiros_pequenos_ignorados() -> None:
    assert nc("Os top 5 e 10 itens, 0 erros.", ["1234.56"], "x") == []


def test_decimal_pequeno_nao_ignorado() -> None:
    assert nc("Valor 5,5.", ["1234.56"], "x") == ["5,5"]


def test_numero_da_pergunta_ignorado() -> None:
    assert nc("Em 2023 foi 777.", ["1234.56"], "Como foi 777 em 2023?") == []


def test_zero_ambos() -> None:
    assert nc("Valor 0,0.", ["0.0"], "x") == []


def test_varios_resultados() -> None:
    assert nc("Houve 150 e 300.", ["a\n150", "b\n300.2"], "x") == []


@pytest.mark.parametrize("resposta,resultado", [
    ("A receita foi de R$ 1,23 milhão.", "1234567.89"),
    ("Vendas de 12,5 mil.", "12500"),
    ("Valor de 2 bilhões.", "2000000000"),
    ("O total foi 1.234.567,89.", "Total: 1,234,567.89"),
    ("O total foi R$ 1.234,56.", "Total: 1.234,56"),
    ("Participação de 15,3 %.", "15.3"),
])
def test_confere_abreviacoes_e_formatos(resposta: str, resultado: str) -> None:
    assert nc(resposta, [resultado], "x") == []


def test_abreviacao_errada_falha() -> None:
    assert nc("Foram 3 milhões.", ["1234567"], "x") == ["3 milhões"]


def test_mil_nao_confunde_com_palavra_maior() -> None:
    assert nc("Foram 999 milhas.", ["1234567"], "x") == ["999"]


# ---------- significância sem p-valor ----------
RAIZ = Path(__file__).resolve().parent.parent
SEM_P = ["Estatística t: -15.5570\nGraus de liberdade: 2976.68"]
COM_P = ["t = -2.0\np_valor = 0.0805"]

DISPARAM = [
    "A diferença é significativa.",
    "A diferença é estatisticamente significativa.",
    "O efeito é estatisticamente relevante.",
    "Não é significativa.",
    "A diferença entre os grupos não é significativa.",
    "Não foi possível calcular o p-valor, mas a diferença é estatisticamente significativa.",
    "Não testei a correlação; contudo a correlação é significativa.",
    "Faltou o teste. No entanto, a associação é significativa.",
    "A diferença significativa entre os grupos é clara.",
    "Não foi possível testar, portanto a diferença é significativa.",
    # Predicativo ("foi significativa") lê-se como afirmação estatística, mesmo sendo uma queda; o atributivo
    # ("aumento significativo", em NAO_DISPARAM) é só magnitude. Decisão: o predicativo dispara.
    "A queda foi significativa",
]
NAO_DISPARAM = [
    "Não foi possível calcular a significância estatística.",
    "Não foi possível testar se a diferença é estatisticamente significativa.",
    "Não posso afirmar se a diferença é significativa.",
    "Não dá para dizer se a diferença é estatisticamente significativa.",
    "Seria preciso um teste para dizer se o efeito é significativo.",
    "Sem um teste, a diferença não é estatisticamente comprovada.",
    "O resultado foi um aumento significativo de receita.",
    "Os resultados mostram um crescimento significativo.",
    "Houve quedas significativas em março.",
    "Não foi possível testar se a diferença de R$ 1.234,56 é significativa.",
    "Não consegui rodar o teste; não sei se a diferença é significativa.",
    "O valor por pedido é de R$ 61,49.",
    "O valor pago foi alto.",
    "SP valoriza o ticket maior.",
    "A significância e o p-valor ficaram de fora.",
    prompts.INCAPACIDADE_SIGNIFICANCIA,
]


@pytest.mark.parametrize("frase", DISPARAM)
def test_significancia_afirmada_ou_negada_sem_p_valor_falha(frase: str) -> None:
    assert afirma_significancia(frase)
    assert significancia_sem_p_valor(frase, SEM_P)
    assert significancia_sem_p_valor(frase, [])


@pytest.mark.parametrize("frase", NAO_DISPARAM)
def test_mencao_incapacidade_e_uso_coloquial_nao_disparam(frase: str) -> None:
    assert not afirma_significancia(frase)
    assert not significancia_sem_p_valor(frase, SEM_P)


def test_modelo_de_incapacidade_do_prompt_nao_dispara() -> None:
    assert not afirma_significancia(prompts.INCAPACIDADE_SIGNIFICANCIA)
    assert prompts.INCAPACIDADE_SIGNIFICANCIA in prompts.SISTEMA


@pytest.mark.parametrize("saida", [
    "p_valor = 1.2e-54", "p < 0.001", "ResultadoTeste(t=-2.0, gl=8.0, p_valor=0.0805)", "p-valor (bicaudal): 0.08",
    "valor-p: 0.03", "p = .04",
])
def test_p_valor_impresso_passa(saida: str) -> None:
    assert not significancia_sem_p_valor("A diferença é significativa.", [saida])


@pytest.mark.parametrize("saida", ["valor por pedido = 5", "SP valoriza = 3", "Estatística t: -15.5", "p", ""])
def test_saida_sem_p_valor_de_verdade_nao_conta(saida: str) -> None:
    assert significancia_sem_p_valor("A diferença é significativa.", [saida])


def test_p_valor_so_no_codigo_nao_conta() -> None:
    # o agente passa só as saídas Python: o `if p < 0.05` do código não entra (ver test_agent)
    assert significancia_sem_p_valor("A diferença é significativa.", ["sim"])


@pytest.mark.parametrize("saida", [
    "o p-valor e o ticket = 45,90", "Sem p-valor; ticket = 45.9", "grupo p: 12 pedidos", "p_valor = 12", "p = 1,5",
])
def test_so_rotulo_colado_ao_comparador_e_valor_em_0_1_conta_como_p(saida: str) -> None:
    assert not tem_p_valor([saida])


def test_p_valor_citado_em_formato_br_nao_reprova_numeros() -> None:
    resposta = "A diferença é significativa (p < 0,001; no teste, p = 1,2 × 10⁻⁵⁴)."
    saidas = ["p_valor = 1.2e-54"]
    assert nc(resposta, saidas, "pergunta") != []
    assert nc(sem_citacoes_de_p(resposta, saidas), saidas, "pergunta") == []
    assert conferir_numeros(resposta, saidas, saidas, "pergunta") == []


@pytest.mark.parametrize("citacao, p, some", [
    ("p = 0,01", "p_valor = 0.2", False),            # valor diferente do da saída: continua a conferir
    ("p = 0,0805", "p_valor = 0.0805", True),
    ("p = 0,08", "p_valor = 0.0805", True),          # arredondamento da citação
    ("p = 0,0809", "p_valor = 0.0805", True),        # dentro de 1%
    ("p < 0,001", "p_valor = 0.0805", False),        # nenhum p é < 0,001
    ("p < 0,001", "p_valor = 1.2e-54", True),
    ("p < 0,05", "p_valor = 0.2", False),
    ("p = 1,2 × 10⁻⁵⁴", "p_valor = 1.2e-54", True),
    ("p = 1,2 × 10⁻⁵⁴", "p_valor = 3.4e-54", False),
    ("p = 0,03", "Sem teste aqui", False),
])
def test_so_some_a_citacao_de_p_que_a_saida_sustenta(citacao: str, p: str, some: bool) -> None:
    resposta = f"Deu significativo ({citacao})."
    assert (citacao not in sem_citacoes_de_p(resposta, [p])) is some


def test_p_que_nao_bate_vira_numero_nao_conferido() -> None:
    saidas = ["p_valor = 0.2"]
    assert conferir_numeros("Significativa (p = 0,01).", saidas, saidas, "x") == ["0,01"]
    assert conferir_numeros("Significativa (p < 0,001).", saidas, saidas, "x") == ["0,001"]


def test_cita_p_nao_engole_numero_que_nao_e_p_valor() -> None:
    assert "45,90" in sem_citacoes_de_p("O p-valor e o ticket = 45,90 reais.", ["p = 0.03"])
    assert "0,03" not in sem_citacoes_de_p("O p-valor (Welch) = 0,03.", ["p = 0.03"])


def _resposta_final(caminho: Path) -> str:
    if caminho.suffix == ".jsonl":
        eventos = [json.loads(linha) for linha in caminho.read_text(encoding="utf-8").splitlines()]
        return next(e["texto"] for e in eventos if e["evento"] == "resposta")
    ultima = json.loads(caminho.read_text(encoding="utf-8"))["respostas"][-1]
    return "".join(v for k, v in ultima if k == "texto")


# Esperado por caso: só o cupom_ticket afirma significância (agora com p-valor impresso na saída).
ESPERADO_AFIRMA = {"cupom_ticket": True}
CORPUS = sorted([*(RAIZ / "data" / "gravacoes").glob("*.jsonl"), *(RAIZ / "tests" / "cassetes").glob("*.json")])


@pytest.mark.parametrize("caminho", CORPUS, ids=[f"{c.parent.name}/{c.name}" for c in CORPUS])
def test_corpus_real_das_gravacoes_e_cassetes(caminho: Path) -> None:
    assert afirma_significancia(_resposta_final(caminho)) is ESPERADO_AFIRMA.get(caminho.stem, False)


FRASE_CASSETE = "O p-valor de $1,58 \\times 10^{-52}$ (ou seja, $p < 0,001$)."


def test_frase_do_cassete_com_p_em_latex_sai_conferida() -> None:
    saidas = ["media = 52.0\np_valor = 1.579e-52\n"]
    assert conferir_numeros(FRASE_CASSETE, saidas, saidas, "x") == []


def test_p_em_latex_que_nao_bate_com_a_saida_continua_reprovando() -> None:
    saidas = ["p_valor = 0.2\n"]
    assert conferir_numeros(FRASE_CASSETE, saidas, saidas, "x") != []


@pytest.mark.parametrize("numero", [
    "1,58 × 10^-52", "1,58 x 10^{-52}", "1,58 \\times 10^{-52}", "$1,58 \\times 10^{-52}$", "1,58·10⁻⁵²",
    "1.58e-52", "1,58 \\cdot 10^{-52}",
])
def test_notacao_cientifica_e_um_numero_so(numero: str) -> None:
    fontes = ["p_valor = 1.579e-52"]
    assert nc(f"O valor foi {numero}.", fontes, "x") == []  # confere como UM número, não 1,58 e 52
    assert nc(f"O valor foi {numero}.", ["p_valor = 0.2"], "x") != []


@pytest.mark.parametrize("frase", ["O p-valor de 0,03 foi baixo.", "O p-valor igual a 0,03 foi baixo.", "p de $0,03$."])
def test_p_valor_de_e_igual_a_sao_citacao(frase: str) -> None:
    assert "0,03" not in sem_citacoes_de_p(frase, ["p_valor = 0.03"])
    assert "0,03" in sem_citacoes_de_p(frase, ["p_valor = 0.2"])


def test_ticket_de_reais_nao_vira_citacao_de_p() -> None:
    assert "45,90" in sem_citacoes_de_p("O ticket de R$ 45,90 e o p-valor de 0,03.", ["p_valor = 0.03"])


@pytest.mark.parametrize("comparador", ["inferior a", "menor que", "menor do que", "abaixo de", "≤", "<"])
def test_limiar_em_palavras_vale_como_menor_que(comparador: str) -> None:
    frase = f"O p-valor foi {comparador} 1e-15."
    assert nc(sem_citacoes_de_p(frase, ["p_valor = 1.579e-52"]), [], "x") == []
    assert conferir_numeros(frase, ["p_valor = 1.579e-52"], ["p_valor = 1.579e-52"], "x") == []
    assert conferir_numeros(frase, ["p_valor = 0.2"], ["p_valor = 0.2"], "x") == ["1e-15"]


def test_limiar_maior_que_o_menor_p_e_o_unico_que_sustenta() -> None:
    saidas = ["p_valor = 0.2"]
    assert conferir_numeros("O p-valor foi menor que 0,5.", saidas, saidas, "x") == []
    assert conferir_numeros("O p-valor foi menor que 0,05.", saidas, saidas, "x") == ["0,05"]
