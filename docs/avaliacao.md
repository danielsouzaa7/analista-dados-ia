# Avaliação do agente

- Data: 21/11/2026
- Modelo: `gemini-3.5-flash-lite`
- Taxa de acerto: **5/8** casos (62%)
- Erros de infraestrutura (429, rede; excluídos da taxa): 0
- Tempo: Mediana 13,1 s, p90 28,1 s
- Médias por caso: 5,2 chamadas ao LLM, 2,9 de ferramenta, 13.861,0 tokens de entrada, 1.311,0 de saída, 0,5 reanálises

| Caso | Acerto | Tempo | Chamadas LLM | Chamadas ferramenta | Tokens (entrada/saída) | Reanálises |
|---|---|---|---|---|---|---|
| receita_culinaria | sim | 8,3 s | 4 | 2 | 9300/1025 | 0 |
| pedidos_mes | sim | 5,7 s | 4 | 2 | 8121/618 | 0 |
| dia_hora | não | 13,2 s | 4 | 2 | 10683/1593 | 0 |
| tempo_nota | não | 21,6 s | 6 | 4 | 15031/868 | 1 |
| participacao_cidade | sim | 13,0 s | 5 | 3 | 13173/1449 | 0 |
| cupom_ticket | não | 28,1 s | 9 | 5 | 22795/1215 | 2 |
| acompanhamento | sim | 9,6 s | 4 | 2 | 13939/1924 | 0 |
| seguranca | sim | 15,0 s | 6 | 3 | 17846/1796 | 1 |

## Falhas

### dia_hora
- Números esperados ausentes na resposta: 1.611.
- Reanálises: 0. Resposta: "1. Agrupar os pedidos por dia da semana e hora da data_hora. 2. Contar a quantidade de pedidos em cada combinação de dia e horário. 3. Identificar os momentos de maior concentração de pedidos. 4. Gerar o mapa de calor para visualizar os horários de pico.  Os pedidos concentram-se fortemente nos fins de semana e nos horários de almoço e jantar. O maior pico de pedidos de toda a base de dados ocorre"
- Análise: o modelo omitiu o total do sábado (1.611) nesta rodada; o número aparece nas rodadas em que o caso passou. Omissão do modelo, não erro de número.

### tempo_nota
- Números esperados ausentes na resposta: 5.501.
- Reanálises: 1. Resposta: "Sim, o tempo de entrega afeta a nota do cliente. Ao analisar os dados dos pedidos que possuem avaliação, encontramos uma correlação de -0,5063 entre o tempo de entrega em minutos e a avaliação. O p-valor obtido foi 0,0."
- Análise: mesma omissão de antes (5.501 pedidos avaliados), agora com o p-valor impresso e citado (p < 0,001). Omissão do modelo.

### cupom_ticket
- Números esperados ausentes na resposta: 15,6.
- Reanálises: 2. Resposta: "Os pedidos com cupom têm ticket médio de R$ 52,01, enquanto os pedidos sem cupom têm ticket médio de R$ 63,90.   Aplicando o teste t de Welch, o resultado mostra que a diferença é estatisticamente expressiva, com $p < 0,001$."
- Análise: a resposta traz as duas médias e o p-valor (p < 0,001), sem erro de Python e sem afirmar significância sem teste. O esperado 15,6 é a estatística t, que o modelo deixou de citar ao priorizar o p-valor pedido pelo prompt: o critério do caso, e não a resposta, ficou desatualizado.

## Variação entre rodadas (21/11/2026, prompt 2026-11-21.1)

Cinco rodadas seguidas com o mesmo prompt deram 4/8, 7/8, 6/7 (1 erro de infraestrutura), 5/8 e esta (5/8): o modelo `gemini-3.5-flash-lite` varia bastante. A rodada anterior à mudança (19/11) deu 7/8. As falhas são números esperados que o modelo omite, não números errados nem afirmação de significância sem p-valor. Os cassetes guardam, por caso, a última rodada em que ele passou.
