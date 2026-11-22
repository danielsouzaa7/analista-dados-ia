"""Icones SVG do README: leves, acessiveis, sem recurso externo, contraste >= 3:1 nos dois fundos."""
import re
from pathlib import Path

import pytest

IMG = Path(__file__).resolve().parent.parent / "docs" / "img"
NOMES = ["navegador", "ao-vivo", "avaliacao", "seguranca"]
FUNDOS = {"branco": "#ffffff", "escuro": "#0d1117"}


def _luminancia(hexcor: str) -> float:
    canais = [int(hexcor[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in canais]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _contraste(a: str, b: str) -> float:
    claro, escuro = sorted((_luminancia(a), _luminancia(b)), reverse=True)
    return (claro + 0.05) / (escuro + 0.05)


def _svg(nome: str) -> str:
    return (IMG / f"icone-{nome}.svg").read_text(encoding="utf-8")


@pytest.mark.parametrize("nome", NOMES)
def test_icone_leve_acessivel_e_sem_recurso_externo(nome):
    svg = _svg(nome)
    assert len(svg.encode()) <= 3072
    assert 'role="img"' in svg and "<title>" in svg
    assert svg.count("<style") == 1
    assert "prefers-reduced-motion" in svg
    assert not re.search(r"<script|foreignObject|@import|url\(|href=\"?https?:", svg)


@pytest.mark.parametrize("fundo", FUNDOS)
@pytest.mark.parametrize("nome", NOMES)
def test_icone_tem_contraste_minimo_de_3_para_1(nome, fundo):
    cor = re.search(r"stroke:\s*(#[0-9a-fA-F]{6})", _svg(nome)).group(1)
    assert _contraste(cor, FUNDOS[fundo]) >= 3.0
