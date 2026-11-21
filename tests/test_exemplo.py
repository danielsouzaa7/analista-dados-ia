import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

RAIZ = Path(__file__).resolve().parent.parent
TIPOS = {"ranking", "tendencia", "composicao", "mapa_calor", "dispersao"}


def _gerar() -> tuple[str, str]:
    subprocess.run([sys.executable, str(RAIZ / "scripts" / "gerar_exemplo.py")], check=True)
    h = lambda p: hashlib.sha256((RAIZ / p).read_bytes()).hexdigest()  # noqa: E731
    return h("data/pedidos.csv"), h("data/perguntas.json")


@pytest.fixture(scope="module")
def df() -> pd.DataFrame:
    _gerar()
    return pd.read_csv(RAIZ / "data" / "pedidos.csv", parse_dates=["data_hora"])


@pytest.fixture(scope="module")
def casos(df: pd.DataFrame) -> list[dict]:
    return json.loads((RAIZ / "data" / "perguntas.json").read_text(encoding="utf-8"))


def test_geracao_deterministica() -> None:
    assert _gerar() == _gerar()


def test_csv_formato_e_tamanho(df: pd.DataFrame) -> None:
    caminho = RAIZ / "data" / "pedidos.csv"
    assert caminho.stat().st_size < 2 * 1024 * 1024
    assert not (RAIZ / "data" / "vendas.csv").exists()
    assert list(df.columns) == ["pedido_id", "data_hora", "cidade", "regiao", "culinaria", "restaurante",
                                "valor_pedido", "taxa_entrega", "cupom", "desconto", "distancia_km",
                                "tempo_entrega_min", "avaliacao"]
    assert len(df) == 8000 and df["data_hora"].dt.year.eq(2025).all()
    assert df["cidade"].nunique() == 7 and df["culinaria"].nunique() == 8
    assert 38 <= df["restaurante"].nunique() <= 40
    linhas = caminho.read_text(encoding="utf-8").splitlines()
    assert re.fullmatch(r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d", linhas[1].split(",")[1])
    assert df["cupom"].dtype == bool and set(df["cupom"]) == {True, False}


def test_padroes_dos_dados(df: pd.DataFrame) -> None:
    h = df["data_hora"].dt.hour
    assert h.between(11, 14).mean() + h.between(18, 22).mean() > 0.7  # picos de almoço e jantar
    dia = df.groupby(df["data_hora"].dt.day_of_week).size()
    assert dia[[4, 5, 6]].mean() > dia[[0, 1, 2]].mean() * 1.3
    mes = df.groupby(df["data_hora"].dt.month).size()
    assert mes.idxmax() == 12
    assert df["tempo_entrega_min"].corr(df["distancia_km"]) > 0.5
    nota = df.dropna(subset=["avaliacao"])
    assert nota["tempo_entrega_min"].corr(nota["avaliacao"]) < -0.3
    assert 0.25 < df["avaliacao"].isna().mean() < 0.35
    assert df[df["cupom"]]["valor_pedido"].mean() < df[~df["cupom"]]["valor_pedido"].mean()
    assert (df[df["cupom"]]["desconto"] > 0).all() and (df[~df["cupom"]]["desconto"] == 0).all()


def test_esquema_dos_casos(casos: list[dict]) -> None:
    assert len(casos) == 8
    ids = [c["id"] for c in casos]
    assert len(set(ids)) == len(ids) and all(re.fullmatch(r"[a-z0-9_]+", i) for i in ids)
    for c in casos:
        assert {"id", "pergunta", "usa", "esperado"} <= set(c)
        assert set(c["usa"]) <= {"sql", "python"} and "sql" in c["usa"]
        assert len(c.get("botao", "x")) <= 40
        if c.get("tipo") == "seguranca":
            assert "numeros_chave" not in c
        else:
            assert c["tipo_grafico"] in TIPOS and c["numeros_chave"]
            assert all(isinstance(n, float) for n in c["numeros_chave"])
    assert len({c["tipo_grafico"] for c in casos if "tipo_grafico" in c}) >= 5
    assert sum("python" in c["usa"] for c in casos) >= 2
    seg = next(c for c in casos if c["id"] == "seguranca")
    assert "LLM_API_KEY" in seg["pergunta"]
    assert next(c for c in casos if c["id"] == "acompanhamento")["depende_de"] == ids[0]


def _chaves(casos: list[dict], id_: str) -> list[float]:
    return next(c for c in casos if c["id"] == id_)["numeros_chave"]


def test_numeros_chave_recalculados(df: pd.DataFrame, casos: list[dict]) -> None:
    v = df["valor_pedido"]
    top = df.groupby("culinaria")["valor_pedido"].sum().nlargest(3).round(2).tolist()
    assert _chaves(casos, "receita_culinaria") == pytest.approx(top, abs=0.01)
    sp = df[df["cidade"] == "São Paulo"].groupby("culinaria")["valor_pedido"].sum().nlargest(2)
    assert _chaves(casos, "acompanhamento") == pytest.approx(sp.round(2).tolist(), abs=0.01)
    mes = df["data_hora"].dt.month.value_counts()
    assert _chaves(casos, "pedidos_mes") == [float(mes.max()), float(mes.min())]
    celula = df.groupby([df["data_hora"].dt.day_of_week, df["data_hora"].dt.hour]).size().max()
    dia = df["data_hora"].dt.day_of_week.value_counts().max()
    assert _chaves(casos, "dia_hora") == [float(dia), float(celula)]
    nota = df.dropna(subset=["avaliacao"])
    r = np.corrcoef(nota["tempo_entrega_min"], nota["avaliacao"])[0, 1]
    assert _chaves(casos, "tempo_nota") == pytest.approx([r, len(nota)], abs=1e-3)
    cid = df.groupby("cidade")["valor_pedido"].sum().nlargest(2) / v.sum() * 100
    assert _chaves(casos, "participacao_cidade") == pytest.approx(cid.tolist(), abs=1e-3)
    a, b = v[df["cupom"]].to_numpy(), v[~df["cupom"]].to_numpy()
    assert _chaves(casos, "cupom_ticket") == pytest.approx([a.mean(), b.mean()], abs=1e-2)
