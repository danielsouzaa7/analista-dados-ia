"""Testes da documentação: README de uma tela, links, números e autoria (Spec, critérios 23 e 24)."""

import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
README = RAIZ / "README.md"
DOCS = RAIZ / "docs"
AUTORIA = DOCS / "autoria.md"

MAX_LINHAS_README = 80
MAX_LINHAS_AUTORIA = 85  # "até cerca de 80 linhas"

URL_APP = "https://analista-dados-ia.onrender.com"

# Frases do README antigo que precisam continuar em docs/ (nada se perde).
SENTINELAS = [
    "DEMO_TETO_DIARIO",
    "LLM_MODEL_FALLBACK",
    "PG_TEST_URL",
    "E2E_URL",
    "INSTALL postgres",
    "New → Blueprint",
    "10 vetores de fuga",
    "BroadcastChannel",
    "1.000 primeiras linhas",
    "fake-stream.html",
    "SSRF",
    "150 s",
    "deno test --allow-read tests/js/",
]

# Lista explícita: (número literal no texto, arquivo onde ele aparece, trecho de lá se for outro literal).
NUMEROS_README = [
    ("7,0/8", "docs/avaliacao.md", None),
    ("faixa 6–8", "docs/avaliacao.md", None),
    ("6/8", "docs/avaliacao.md", None),
    ("5 rodadas", "docs/avaliacao.md", None),
    ("0,1 vCPU", "docs/decisoes.md", None),
    ("5 rodadas de red team", "docs/seguranca.md", "### Rodada 5"),
    ("10h05", "docs/tempo-de-construcao.md", None),
    ("58 agentes", "docs/tempo-de-construcao.md", "| Agentes | 58 |"),
]
NUMEROS_AUTORIA = [
    ("10h05", "docs/tempo-de-construcao.md", None),
    ("58 agentes", "docs/tempo-de-construcao.md", "| Agentes | 58 |"),
    ("14h12", "docs/tempo-de-construcao.md", None),
]

JARGAO = ["pass^", "cassete", "prelúdio", "prelude", "grounding"]

ICONES = ["navegador", "ao-vivo", "avaliacao", "seguranca"]
MARCADORES = ["heroi", "fluxo", "demo"] + [f"icone-{i}" for i in ICONES]


def _ler(caminho: Path) -> str:
    return caminho.read_text(encoding="utf-8")


def _doc(rel: str) -> str:
    return _ler(RAIZ / rel)


def _todo_docs() -> str:
    return "\n".join(_ler(p) for p in sorted(DOCS.glob("*.md")))


def _sem_blocos_de_codigo(texto: str) -> str:
    return re.sub(r"```.*?```", "", texto, flags=re.S)


def test_readme_cabe_em_uma_tela():
    linhas = _ler(README).splitlines()
    assert len(linhas) <= MAX_LINHAS_README


def test_links_e_imagens_relativos_existem():
    faltando = []
    for arquivo in [README, *sorted(DOCS.glob("*.md"))]:
        texto = _sem_blocos_de_codigo(_ler(arquivo))
        alvos = re.findall(r"\]\(([^)\s]+)", texto)
        alvos += re.findall(r'(?:src|srcset)="([^"]+)"', texto)
        for alvo in alvos:
            if alvo.startswith(("http://", "https://", "mailto:", "#")):
                continue
            caminho = alvo.split("#")[0]
            if caminho and not (arquivo.parent / caminho).exists():
                faltando.append(f"{arquivo.name}: {alvo}")
    assert faltando == []


@pytest.mark.parametrize("frase", SENTINELAS)
def test_conteudo_do_readme_antigo_continua_em_docs(frase):
    assert frase in _todo_docs()


def test_readme_sem_jargao_solto():
    texto = _ler(README).lower()
    for termo in JARGAO:
        assert termo not in texto, termo
    for achado in re.finditer(r"nonce", texto):
        depois = texto[achado.end() : achado.end() + 30]
        assert depois.startswith(" (código de uso único)"), "nonce sem explicação"


def test_readme_linka_app_autoria_e_avaliacao():
    texto = _ler(README)
    assert URL_APP in texto
    assert "](docs/autoria.md)" in texto
    assert "](docs/avaliacao.md)" in texto


def test_readme_diz_sem_rede_alem_do_pyodide():
    texto = _ler(README)
    assert "sem rede além do caminho fixo do Pyodide" in texto
    assert "sem acesso à rede" not in texto


def test_readme_marca_onde_entram_as_imagens_futuras():
    texto = _ler(README)
    for marcador in MARCADORES:
        assert f"<!-- {marcador} -->" in texto, marcador
    assert "docs/img/conversa.png" in texto  # herói provisório


def test_readme_usa_p_em_vez_de_h3_e_details_com_linhas_em_branco():
    linhas = _ler(README).splitlines()
    assert "<h3" not in "\n".join(linhas)
    for i, linha in enumerate(linhas):
        if "</summary>" in linha:
            assert linhas[i + 1].strip() == "", "falta linha em branco depois de </summary>"
        if linha.strip() == "</details>":
            assert linhas[i - 1].strip() == "", "falta linha em branco antes de </details>"


def test_icones_do_readme_tem_alt_vazio():
    for tag in re.findall(r"<img[^>]*>", _ler(README)):
        if "icone-" in tag:
            assert 'alt=""' in tag, tag


@pytest.mark.parametrize(("literal", "arquivo", "fonte"), NUMEROS_README)
def test_numeros_do_readme_batem_com_docs(literal, arquivo, fonte):
    assert literal in _ler(README), f"{literal} sumiu do README"
    assert (fonte or literal) in _doc(arquivo)


@pytest.mark.parametrize(("literal", "arquivo", "fonte"), NUMEROS_AUTORIA)
def test_numeros_da_autoria_batem_com_docs(literal, arquivo, fonte):
    assert literal in _ler(AUTORIA), f"{literal} sumiu da autoria"
    assert (fonte or literal) in _doc(arquivo)


def test_autoria_cabe_em_cerca_de_80_linhas():
    assert len(_ler(AUTORIA).splitlines()) <= MAX_LINHAS_AUTORIA


def test_autoria_assume_o_papel_e_o_que_nao_diz():
    texto = _ler(AUTORIA)
    assert "dono do produto" in texto
    assert "Claude Code com o framework ECC" in texto
    assert "O que este documento não diz" in texto
    assert "tech lead" not in texto.lower()


def test_autoria_conta_a_hospedagem_inteira():
    texto = _ler(AUTORIA)
    assert "acho um absurdo pagar pra expor portfólio" in texto
    assert "R$180" in texto
    assert "(decisão do Daniel)" in _doc("docs/avaliacao.md")
    assert "## 14. Hospedagem sem custo: Render grátis" in _doc("docs/decisoes.md")


def test_tabela_de_decisoes_so_com_data_e_com_fonte():
    texto = _ler(AUTORIA)
    linhas = [ln for ln in texto.splitlines() if re.match(r"\| \d\d/\d\d ", ln)]
    assert len(linhas) >= 8
    for linha in linhas:
        assert not re.search(r"\d{1,2}h\d{2}", linha), f"hora na tabela: {linha}"
        ultima = linha.rstrip("| ").split("|")[-1]
        assert "](" in ultima or "registro local da conversa" in ultima, linha
    assert "delivery" in " ".join(linhas)


def test_autoria_nao_vaza_caminho_privado_nem_sessao():
    texto = _ler(AUTORIA)
    for proibido in [".claude/CLAUDE.md", "C:\\", "C:/", "/Users/"]:
        assert proibido not in texto
