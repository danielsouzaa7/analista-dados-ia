import pytest

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
