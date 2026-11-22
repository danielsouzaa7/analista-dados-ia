"""Os GIFs do app real existem, têm o peso combinado e o README os usa."""
from pathlib import Path

IMG = Path(__file__).resolve().parent.parent / "docs" / "img"
MB = 1024 * 1024


def test_gifs_existem_e_cabem_no_peso():
    assert (IMG / "demo.gif").stat().st_size <= 5 * MB
    assert (IMG / "demo-celular.gif").stat().st_size <= 3 * MB


def test_readme_usa_os_dois_gifs():
    readme = (IMG.parent.parent / "README.md").read_text(encoding="utf-8")
    assert "docs/img/demo.gif" in readme
    assert "raw/main/docs/img/demo-celular.gif" in readme
