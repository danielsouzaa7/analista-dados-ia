"""Gabarito independente da avaliação: recalcula, em pandas puro sobre data/pedidos.csv (sem importar app/ nem
o agente), os valores esperados dos casos numéricos e os congela em data/gabarito.json.

    python scripts/gabarito.py    # reescreve data/gabarito.json

tests/test_avaliar_dataset.py recalcula tudo e compara com o arquivo versionado e com os `numeros_chave`.
"""
import json
from pathlib import Path

import pandas as pd

DATA = Path(__file__).resolve().parent.parent / "data"
ARQUIVO = DATA / "gabarito.json"


def calcular(df: pd.DataFrame) -> dict[str, list[float]]:
    df = df.assign(data_hora=pd.to_datetime(df["data_hora"]))
    rec = df.groupby("culinaria")["valor_pedido"].sum().sort_values(ascending=False)
    sp = df[df["cidade"] == "São Paulo"].groupby("culinaria")["valor_pedido"].sum().sort_values(ascending=False)
    mes = df.groupby(df["data_hora"].dt.month).size()
    por_dia = df.groupby(df["data_hora"].dt.day_of_week).size()
    celula = df.groupby([df["data_hora"].dt.day_of_week, df["data_hora"].dt.hour]).size()
    nota = df.dropna(subset=["avaliacao"])
    cidade = df.groupby("cidade")["valor_pedido"].sum() / df["valor_pedido"].sum() * 100
    cidade = cidade.sort_values(ascending=False)
    com = df[df["cupom"]]["valor_pedido"].mean()
    sem = df[~df["cupom"]]["valor_pedido"].mean()
    nota_cidade = df.groupby("cidade")["avaliacao"].mean()
    por_restaurante = df.groupby("restaurante").size()
    tempo_regiao = df.groupby("regiao")["tempo_entrega_min"].mean()
    pedido = df[df["pedido_id"] == 100001].iloc[0]
    bruto = {
        "receita_culinaria": rec.iloc[:3].round(2).tolist(),
        "pedidos_mes": [mes.max(), mes.min()],
        "dia_hora": [por_dia.max(), celula.max()],
        "tempo_nota": [nota["tempo_entrega_min"].corr(nota["avaliacao"]), len(nota)],
        "participacao_cidade": cidade.iloc[:2].tolist(),
        "cupom_ticket": [com, sem],
        "acompanhamento": sp.iloc[:2].round(2).tolist(),
        "ticket_medio_geral": [df["valor_pedido"].mean()],
        "cidade_melhor_nota": [nota_cidade.max()],
        "restaurante_mais_pedidos": [por_restaurante.max()],
        "pct_pedidos_cupom": [df["cupom"].mean() * 100],
        "regiao_maior_tempo": [tempo_regiao.max()],
        "ext_sem_avaliacao": [df["avaliacao"].isna().sum()],
        "ext_pedido_unico": [pedido["valor_pedido"]],
    }
    return {k: [round(float(v), 4) for v in vs] for k, vs in bruto.items()}


def main() -> None:
    gab = calcular(pd.read_csv(DATA / "pedidos.csv"))
    ARQUIVO.write_text(json.dumps(gab, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
