"""Testes da documentação: README longo, links, números e autoria (Spec, critérios 23 e 24)."""

import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
README = RAIZ / "README.md"
DOCS = RAIZ / "docs"
AUTORIA = DOCS / "autoria.md"

MIN_LINHAS_README = 350
MAX_LINHAS_README = 800
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
    ("6 dos 8 casos certos em todas as rodadas", "docs/avaliacao.md", "6/8"),
    ("35 de 40", "docs/avaliacao.md", None),
    ("87,5%", "docs/avaliacao.md", None),
    ("Avaliado contra o modelo real em 5 rodadas", "docs/avaliacao.md", "as 5 rodadas acima deram"),
    ("0,1 vCPU", "docs/decisoes.md", None),
    ("5 rodadas de red team", "docs/seguranca.md", "### Rodada 5"),
    ("10h06", "docs/tempo-de-construcao.md", None),
    ("58 agentes", "docs/tempo-de-construcao.md", "| Agentes | 58 |"),
    # Em números e Como foi construído
    ("mediana de 9,3 s", "docs/avaliacao.md", "mediana 9,3 s"),
    ("21,4 MB", "docs/decisoes.md", "cerca de 21,4 MB decodificados"),
    ("56.229 bytes", "docs/decisoes.md", None),
    ("10 vetores de fuga", "docs/como-rodar.md", None),
    ("617 para 433 MB", "docs/seguranca.md", None),
    ("4,5–5,2 s", "docs/decisoes.md", "Chromium 5,0 s na 1ª execução e 4,5 s na 2ª; Firefox 5,1 s e 5,0 s; WebKit 5,2 s e 4,6 s"),
    ("cerca de 5 s e 248 MB por chamada", "docs/decisoes.md", None),
    ("0,1 vCPU e 512 MB", "docs/decisoes.md", "(0,1 vCPU, 512 MB)"),
    ("três chamadas seguidas estouraram o limite de 30 s", "docs/decisoes.md", None),
    ("r = -0,497 em vez de -0,506", "docs/avaliacao.md", None),
    ("6, 8, 6, 7 e 8", "docs/avaliacao.md", None),
    ("8.000 pedidos fictícios", "docs/como-rodar.md", None),
    ("R$ 0", "docs/arquitetura.md", "R$ 0 (plano gratuito)"),
    ("14 decisões de arquitetura", "docs/decisoes.md", "## 14. Hospedagem"),
    ("19/11/2026 02:13", "docs/tempo-de-construcao.md", None),
    ("| Tempo ativo de relógio | 10h06 |", "docs/tempo-de-construcao.md", None),
    ("| Relógio corrido | 65h49 |", "docs/tempo-de-construcao.md", None),
    ("| Horas paradas excluídas | 55h43 |", "docs/tempo-de-construcao.md", None),
    ("| Tempo somado dos agentes | 14h12 |", "docs/tempo-de-construcao.md", None),
    ("| Paralelismo médio | 1,4x |", "docs/tempo-de-construcao.md", None),
    ("| Sessões | 7 |", "docs/tempo-de-construcao.md", None),
    ("| Agentes | 58 |", "docs/tempo-de-construcao.md", None),
    ("| Revisão | 19 | 4h37 |", "docs/tempo-de-construcao.md", None),
    ("| Implementação | 27 | 8h15 |", "docs/tempo-de-construcao.md", None),
    ("| Spec/plano | 5 | 0h35 |", "docs/tempo-de-construcao.md", None),
    ("| Documentação | 3 | 0h18 |", "docs/tempo-de-construcao.md", None),
    ("| Testes | 2 | 0h16 |", "docs/tempo-de-construcao.md", None),
    ("| Outros | 2 | 0h10 |", "docs/tempo-de-construcao.md", None),
    # contagens de testes, registradas com data em como-rodar
    ("42 no `deno test`", "docs/como-rodar.md", None),
    ("50 no e2e", "docs/como-rodar.md", None),
    ("97% (run #6", "docs/como-rodar.md", "97% de `app/`"),
    ("657 passed, 50 skipped", "docs/como-rodar.md", None),
    # um nome só para cada medida de horas (README e autoria)
    ("10h06 de tempo ativo de relógio", "docs/tempo-de-construcao.md", "| Tempo ativo de relógio | 10h06 |"),
    ("14h12 de trabalho somado dos agentes (em paralelo)", "docs/tempo-de-construcao.md", "| Tempo somado dos agentes | 14h12 |"),
]
NUMEROS_AUTORIA = [
    ("10h06 de tempo ativo de relógio", "docs/tempo-de-construcao.md", "| Tempo ativo de relógio | 10h06 |"),
    ("58 agentes", "docs/tempo-de-construcao.md", "| Agentes | 58 |"),
    ("14h12 de trabalho somado dos agentes (em paralelo)", "docs/tempo-de-construcao.md", "| Tempo somado dos agentes | 14h12 |"),
]

# termo -> começo da explicação entre parênteses logo depois da 1ª ocorrência (fora de blocos de código)
JARGAO = {
    "pass^": "casos que passaram em todas as",
    "cassete": "respostas do llm gravadas",
    "prelúdio": "funções de estatística",
    "grounding": "valores reais das colunas",
    "nonce": "código de uso único",
    "sri": "o navegador confere o hash",
    "spike": "teste rápido de viabilidade",
    "wasm": "webassembly",
    "coop/coep": "cabeçalhos que isolam",
    "ssrf": "o servidor é levado a conectar",
}
JANELA_JARGAO = 80

GRAVACAO_EXEMPLO = RAIZ / "data" / "gravacoes" / "cupom_ticket.jsonl"
PERGUNTAS = RAIZ / "data" / "perguntas.json"

ICONES = ["navegador", "ao-vivo", "avaliacao", "seguranca"]
MARCADORES = ["heroi"]

IMG = DOCS / "img"
MAX_BYTES_SVG = 30 * 1024
SVGS_ANIMADOS = sorted([*IMG.glob("heroi*.svg"), *IMG.glob("fluxo*.svg")])
RAW = "https://github.com/danielsouzaa7/analista-dados-ia/raw/main/docs/img/"
SVG_NS = "{http://www.w3.org/2000/svg}"


def _ler(caminho: Path) -> str:
    return caminho.read_text(encoding="utf-8")


def _doc(rel: str) -> str:
    return _ler(RAIZ / rel)


def _todo_docs() -> str:
    return "\n".join(_ler(p) for p in sorted(DOCS.glob("*.md")))


def _sem_blocos_de_codigo(texto: str) -> str:
    return re.sub(r"```.*?```", "", texto, flags=re.S)


def test_readme_longo_mas_abaixo_do_teto():
    linhas = _ler(README).splitlines()
    assert MIN_LINHAS_README <= len(linhas) <= MAX_LINHAS_README, len(linhas)


def test_links_e_imagens_relativos_existem():
    faltando = []
    for arquivo in [README, *sorted(DOCS.glob("*.md"))]:
        texto = _sem_blocos_de_codigo(_ler(arquivo))
        alvos = re.findall(r"\]\(([^)\s]+)", texto)
        alvos += re.findall(r'(?:src|srcset|href)="([^"]+)"', texto)
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


@pytest.mark.parametrize("termo", JARGAO)
def test_jargao_explicado_na_primeira_ocorrencia(termo):
    texto = _sem_blocos_de_codigo(_ler(README)).lower()
    achado = re.search(rf"\b{re.escape(termo)}", texto)
    if not achado:
        return  # termo ausente: nada a explicar
    i = achado.start()
    depois = texto[i : i + len(termo) + JANELA_JARGAO]
    assert f"({JARGAO[termo]}" in depois, f"{termo} sem explicação logo depois: {depois!r}"


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


def test_readme_mostra_o_heroi_com_variante_de_celular():
    texto = _ler(README)
    assert f'<source media="(max-width: 600px)" srcset="{RAW}heroi-celular.svg">' in texto
    assert '<img src="docs/img/heroi.svg" width="100%" alt="Ilustração do fluxo: ' in texto
    assert "docs/img/conversa.png" not in texto  # o herói provisório saiu
    for nome in ("heroi.svg", "heroi-celular.svg"):
        assert (IMG / nome).exists(), nome


def test_ha_quatro_svgs_animados():
    assert len(SVGS_ANIMADOS) == 4


def test_readme_diagrama_com_srcset_absoluto_e_sem_legenda_duplicada():
    texto = _ler(README)
    assert f'srcset="{RAW}fluxo-celular.svg"' in texto
    assert '<img src="docs/img/fluxo.svg"' in texto
    assert "O servidor nunca executa o Python da IA" not in texto


def test_readme_textos_do_resultado_sem_exagero():
    texto = _ler(README)
    assert "6 dos 8 casos certos em todas as rodadas" in texto and "6/8 em todas" not in texto
    assert "cada achado corrigido (quase todos com teste automatizado) ou publicado como risco aceito" in texto
    assert "cada achado corrigido com teste" not in texto
    assert "cada achado com teste ou risco aceito" not in texto
    assert "reproduzido, fechado" not in texto


def test_cada_icone_do_readme_esta_dentro_do_link_do_seu_diferencial():
    texto = _ler(README)
    for nome in ICONES:
        assert re.search(rf'<a href="docs/[^"]+\.md"><img src="docs/img/icone-{nome}\.svg"[^>]*></a>', texto), nome


def test_svgs_sem_codigo_de_escape_no_texto():
    for svg in sorted(IMG.glob("*.svg")):
        raiz = ET.fromstring(_ler(svg))
        for el in [*raiz.iter(f"{SVG_NS}text"), *raiz.iter(f"{SVG_NS}tspan")]:
            conteudo = "".join(el.itertext())
            for ruim in ("00a0", "\\u"):
                assert ruim not in conteudo, f"{svg.name}: {ruim} em {conteudo!r}"
        assert "&amp;#" not in _ler(svg), svg.name


@pytest.mark.parametrize("svg", SVGS_ANIMADOS, ids=lambda p: p.name)
def test_reduced_motion_mostra_o_quadro_final(svg):
    texto = _ler(svg)
    bloco = texto[texto.index("@media (prefers-reduced-motion") : texto.index("</style>")]
    resto = bloco.replace("*{animation:none!important}", "")
    assert "animation:none" in bloco and "opacity:1" in resto, svg.name


@pytest.mark.parametrize("svg", SVGS_ANIMADOS, ids=lambda p: p.name)
def test_svgs_leves_acessiveis_e_sem_recurso_externo(svg):
    assert svg.stat().st_size <= MAX_BYTES_SVG
    texto = _ler(svg)
    raiz = ET.fromstring(texto)  # XML válido
    assert raiz.get("role") == "img"
    assert raiz.find(f"{SVG_NS}title") is not None
    assert raiz.find(f"{SVG_NS}desc") is not None
    assert len(raiz.findall(f".//{SVG_NS}style")) == 1
    assert "prefers-reduced-motion" in texto
    assert raiz.find(f".//{SVG_NS}script") is None
    assert raiz.find(f".//{SVG_NS}foreignObject") is None
    assert not re.search(r'href="\s*https?:', texto)
    assert not re.search(r"url\(\s*['\"]?(?!#)", texto)  # só url(#id) local
    assert "@import" not in texto
    assert "animation-delay" not in texto  # loop numa linha do tempo única


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
    assert "Eu não criei esses agentes" in texto
    assert "Papel | O que fez aqui | Exemplo" in texto
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


def test_demo_animada_existe_e_pesa_menos_de_5_mb():
    gif = DOCS / "img" / "demo.gif"
    assert gif.exists() and gif.stat().st_size < 5 * 1024 * 1024
    assert gif.read_bytes()[:6] in (b"GIF87a", b"GIF89a")
    assert "docs/img/demo.gif" in README.read_text(encoding="utf-8")


def test_tempo_do_heroi_tem_fonte_em_como_rodar():
    assert "17 s" in _ler(IMG / "heroi.svg")
    assert "cerca de 17 s (`/api/metricas` da sessão de gravação)" in _doc("docs/como-rodar.md")
    assert "mediana de uma pergunta" not in _ler(README) and "17,1" not in _ler(README)


def test_readme_nao_descreve_a_vitrine_antiga_e_cita_a_licenca():
    texto = _ler(README)
    for velho in ("-0,91", "-0,51", "8350309", "cerca de 14 s", "13,8 s"):
        assert velho not in texto, velho
    assert "cupom" in texto and "17 s" in texto
    assert "MIT" in texto and (RAIZ / "LICENSE").exists()


def _normalizar(texto: str) -> str:
    return "\n".join(linha.rstrip() for linha in texto.splitlines())


def _bloco_do_exemplo() -> str:
    texto = _ler(README)
    inicio, fim = "<!-- exemplo:inicio -->", "<!-- exemplo:fim -->"
    assert inicio in texto and fim in texto
    return _normalizar(texto[texto.index(inicio) : texto.index(fim)])


def test_exemplo_real_e_texto_exato_da_gravacao():
    eventos = [json.loads(linha) for linha in _ler(GRAVACAO_EXEMPLO).splitlines() if linha.strip()]
    pergunta = next(c["pergunta"] for c in json.loads(_ler(PERGUNTAS)) if c["id"] == "cupom_ticket")
    ultimo = {e["evento"]: e for e in eventos}  # o último de cada tipo: a tentativa aprovada
    python = [e for e in eventos if e["evento"] == "ferramenta_inicio" and e["tipo"] == "python"][-1]
    saida = next(e["saida"] for e in eventos if e["evento"] == "ferramenta_fim" and e["id"] == python["id"])
    sql = next(e["sql"] for e in eventos if e["evento"] == "ferramenta_inicio" and e["tipo"] == "sql")
    grafico = next(e["grafico"] for e in eventos if e["evento"] == "ferramenta_fim" and "grafico" in e)
    m = ultimo["metricas"]
    trechos = [
        pergunta,
        ultimo["plano"]["texto"],
        sql,
        python["codigo"],
        saida,
        grafico["resumo"],
        ultimo["resposta"]["texto"],
        m["trace_id"],
        m["versao_prompt"],
        f"{m['chamadas_llm']} chamadas ao LLM",
        f"{m['chamadas_ferramenta']} chamadas de ferramenta",
        f"{m['tokens_entrada']:,}".replace(",", "."),
        f"{m['tokens_saida']:,}".replace(",", "."),
    ]
    bloco = _bloco_do_exemplo()
    for trecho in trechos:
        assert _normalizar(trecho) in bloco, trecho[:60]
    assert ultimo["resposta"]["reanalises"] == 2 and "2 reanálises" in bloco
    assert "executor Deno" in bloco  # onde o Python da gravação rodou


def test_readme_conta_as_decisoes_da_autoria():
    linhas = [ln for ln in _ler(AUTORIA).splitlines() if re.match(r"\| \d\d/\d\d ", ln)]
    assert f"{len(linhas)} decisões minhas" in _ler(README)


def test_tabela_da_avaliacao_por_caso_bate_com_o_relatorio():
    linhas_readme = _ler(README).splitlines()
    casos = re.findall(r"^\| (\w+) \| (\d/5) \|$", _doc("docs/avaliacao.md"), flags=re.M)
    assert len(casos) == 8
    for caso, k in casos:
        assert any(f"`{caso}`" in ln and f"| {k} |" in ln for ln in linhas_readme), caso


def test_readme_nao_publica_a_tabela_por_sessao():
    texto = _ler(README)
    assert "| Sessão | Ativo |" not in texto
    for sessao in re.findall(r"^\| ([0-9a-f]{8}) \|", _doc("docs/tempo-de-construcao.md"), flags=re.M):
        assert sessao not in texto, sessao


def _contagem_pytest() -> int:
    saida = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "--ignore=tests/e2e", "-p", "no:cacheprovider"],
        cwd=RAIZ, capture_output=True, text=True, check=True,
    ).stdout
    return int(re.search(r"(\d+) tests? collected", saida).group(1))


def test_contagem_de_testes_do_pytest_e_a_real():
    n = _contagem_pytest()
    assert f"{n} testes no pytest" in _ler(README)
    assert f"{n} testes no pytest" in _doc("docs/como-rodar.md")


def test_conferencia_diz_que_sql_e_codigo_enviados_tambem_sao_fonte():
    texto = _ler(README)
    assert "ou do SQL e do código enviados, desta pergunta ou dos últimos 3 turnos" in texto
    assert "(ou no SQL/código que o gerou)" in texto
    assert "um número escrito no próprio SQL ou código conta como fonte" in texto
    assert "precisa existir num resultado de ferramenta." not in texto


def test_risco_aceito_do_teto_em_disco_das_sessoes():
    riscos = _doc("docs/seguranca.md").split("## Riscos aceitos")[1]
    assert "200 sessões de 20 MB" in riscos and "teto de bytes em disco" in riscos


def test_spec_aceita_gif_de_ate_30_s():
    spec = _doc("Spec.md")
    assert "15 a 25 s" not in spec and "até cerca de 30 s" in spec


def test_legenda_do_gif_aponta_para_a_ancora_de_como_rodar():
    assert "(docs/como-rodar.md#como-o-gif-foi-gravado)" in _ler(README)
    assert "\n## Como o GIF foi gravado\n" in _doc("docs/como-rodar.md")


def test_adrs_explicadas_na_primeira_vez():
    texto = _ler(README)
    assert "registros de decisão (ADRs)" in texto and "as 14 ADRs" not in texto


def test_estrutura_cita_os_arquivos_novos_e_so_existentes():
    for rel in ("scripts/tempo_construcao.py", "static/dom.js", "static/marcas.js", "static/fake-api.js"):
        assert (RAIZ / rel).exists(), rel
        nome = rel.split("/")[-1]
        assert nome in _ler(README) and nome in _doc("docs/como-rodar.md"), nome
    assert ".claude/plans/" in _ler(README)


def test_heroi_mostra_count_no_sql():
    for nome in ("heroi.svg", "heroi-celular.svg"):
        textos = ["".join(t.itertext()) for t in ET.fromstring(_ler(IMG / nome)).iter(f"{SVG_NS}text")]
        assert any("SELECT cupom, COUNT(*)," in t for t in textos), nome


def test_readme_e_autoria_nao_citam_o_framework_nem_a_meta_como_manchete():
    for caminho in (README, AUTORIA, DOCS / "processo.md"):
        texto = _ler(caminho)
        assert "ECC" not in texto
        assert "Everything Claude Code" not in texto
    assert "não batida" not in _ler(README)
    assert "Papel | O que fez aqui | Exemplo" in _ler(README)
