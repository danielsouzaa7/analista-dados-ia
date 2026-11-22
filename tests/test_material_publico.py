"""O nome do framework de orquestração nunca aparece em arquivo versionado ou prestes a ser versionado."""
import re
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
# Padrão montado em partes: este arquivo não contém o literal que proíbe.
SIGLA = re.compile(r"\b" + "E" + "CC" + r"\b", re.IGNORECASE)
PREFIXO = re.compile("e" + "cc:|everything-" + "claude-code", re.IGNORECASE)
NOME_POR_EXTENSO = re.compile("every" + "thing" + r"\s+" + "claude" + r"\s+" + "code", re.IGNORECASE)
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE)
PASTA_PESSOAL = re.compile(r"[A-Za-z]:" + r"\\" + r"Users" + r"\\" + r"[A-Za-z]|/Users/[A-Za-z]")
MADRUGADA = re.compile(r"\b0[0-5]:[0-5]\d\b")
EXCECOES: set[str] = set()  # nenhuma: toda exceção aqui esconderia uma regressão
# Exceções por padrão e arquivo (cada uma com o motivo); valem só para o arquivo citado.
EXCECOES_PADRAO = {
    "pasta_pessoal": {
        "tests/test_tempo_construcao.py": "caminhos sintéticos (Fulano, Ana Maria) que testam a conversão de pasta",
    },
    "nome_por_extenso": {},
}


def _git(*args):
    return subprocess.run(["git", *args], cwd=RAIZ, capture_output=True, text=True, check=True).stdout.splitlines()


def _arquivos():
    nomes = set(_git("ls-files")) | set(_git("ls-files", "--others", "--exclude-standard"))
    for rel in sorted(nomes - EXCECOES):
        if (RAIZ / rel).is_file():
            yield rel


def _texto(rel):
    dados = (RAIZ / rel).read_bytes()
    if b"\0" in dados:
        return None  # binário (PNG, GIF, fonte)
    return dados.decode("utf-8", errors="replace")


def test_material_publico_nao_cita_o_framework():
    achados = []
    for rel in _arquivos():
        texto = _texto(rel)
        if texto is not None and (PREFIXO.search(texto) or SIGLA.search(texto)):
            achados.append(rel)
    assert not achados, achados


def _linhas_com(padrao, extensoes=None, excecoes=()):
    """Lista 'arquivo:linha' dos achados; nunca devolve o valor achado."""
    achados = []
    for rel in _arquivos():
        if rel in excecoes or (extensoes and not rel.endswith(extensoes)):
            continue
        texto = _texto(rel)
        if texto is None:
            continue
        achados += [f"{rel}:{i}" for i, ln in enumerate(texto.splitlines(), 1) if padrao.search(ln)]
    return achados


def test_material_publico_nao_tem_uuid_de_sessao():
    assert not _linhas_com(UUID)


def test_material_publico_nao_tem_caminho_de_pasta_pessoal_com_nome():
    assert not _linhas_com(PASTA_PESSOAL, excecoes=EXCECOES_PADRAO["pasta_pessoal"])


def test_material_publico_nao_escreve_o_nome_do_framework_por_extenso():
    assert not _linhas_com(NOME_POR_EXTENSO, excecoes=EXCECOES_PADRAO["nome_por_extenso"])


def test_docs_e_svgs_nao_citam_horario_de_madrugada():
    assert not _linhas_com(MADRUGADA, extensoes=(".md", ".svg"))


# Prova de que cada guarda fica vermelha: um arquivo sintético injetado na lista de arquivos.
_BS = chr(92)
SINTETICOS = {
    "uuid": ("x.md", "sessao " + "12345678-1234-4abc-8def-" + "ABCDEF123456", test_material_publico_nao_tem_uuid_de_sessao),
    "pasta_windows": ("x.py", "C:" + _BS + "Users" + _BS + "Fulano", test_material_publico_nao_tem_caminho_de_pasta_pessoal_com_nome),
    "pasta_unix": ("x.py", "/Users/" + "fulano/proj", test_material_publico_nao_tem_caminho_de_pasta_pessoal_com_nome),
    "nome": ("x.md", "Every" + "thing  Claude" + " Code", test_material_publico_nao_escreve_o_nome_do_framework_por_extenso),
    "madrugada": ("x.svg", "feito as 03" + ":15", test_docs_e_svgs_nao_citam_horario_de_madrugada),
}


@pytest.mark.parametrize("caso", SINTETICOS)
def test_cada_guarda_fica_vermelha_com_arquivo_sintetico(caso, tmp_path, monkeypatch):
    nome, conteudo, guarda = SINTETICOS[caso]
    (tmp_path / nome).write_text(conteudo, encoding="utf-8")
    monkeypatch.setattr(sys.modules[__name__], "RAIZ", tmp_path)
    monkeypatch.setattr(sys.modules[__name__], "_arquivos", lambda: iter([nome]))
    with pytest.raises(AssertionError):
        guarda()


def test_pasta_pessoal_sem_nome_e_horario_fora_da_madrugada_sao_permitidos(tmp_path, monkeypatch):
    (tmp_path / "x.md").write_text("em C:" + _BS + "Users e 06" + ":00 e 12:30", encoding="utf-8")
    monkeypatch.setattr(sys.modules[__name__], "RAIZ", tmp_path)
    monkeypatch.setattr(sys.modules[__name__], "_arquivos", lambda: iter(["x.md"]))
    test_material_publico_nao_tem_caminho_de_pasta_pessoal_com_nome()
    test_docs_e_svgs_nao_citam_horario_de_madrugada()
