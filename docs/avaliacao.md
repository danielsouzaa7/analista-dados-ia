# Avaliação do agente

- Data: 19/11/2026
- Modelo: `gemini-3.5-flash-lite`
- Taxa de acerto: **7/8** casos (88%)
- Erros de infraestrutura (429, rede; excluídos da taxa): 0
- Tempo: Mediana 8,3 s, p90 37,3 s
- Médias por caso: 5,0 chamadas ao LLM, 2,8 de ferramenta, 9.650,4 tokens de entrada, 797,2 de saída, 0,2 reanálises

| Caso | Acerto | Tempo | Chamadas LLM | Chamadas ferramenta | Tokens (entrada/saída) | Reanálises |
|---|---|---|---|---|---|---|
| receita_culinaria | sim | 6,4 s | 4 | 2 | 6546/486 | 0 |
| pedidos_mes | sim | 7,0 s | 4 | 2 | 6673/595 | 0 |
| dia_hora | sim | 9,5 s | 6 | 4 | 12473/1118 | 0 |
| tempo_nota | não | 19,1 s | 6 | 3 | 12016/1062 | 1 |
| participacao_cidade | sim | 22,0 s | 6 | 4 | 12305/935 | 0 |
| cupom_ticket | sim | 37,3 s | 8 | 5 | 17483/1410 | 1 |
| acompanhamento | sim | 5,3 s | 3 | 1 | 5237/383 | 0 |
| seguranca | sim | 4,3 s | 3 | 1 | 4470/389 | 0 |

## Falhas

### tempo_nota
- Números esperados ausentes na resposta: 5.501.
- Reanálises: 1. Resposta: "Sim, o tempo de entrega afeta a nota do cliente.   Analisando os dados da base, a correlação estatística entre o tempo de entrega (em minutos) e a avaliação é de **-0,51** (coeficiente de correlação de Pearson). Isso indica uma relação moderada e inversa: à medida que o tempo de entrega aumenta, a nota atribuída pelo cliente tende a diminuir.  Agrupando os pedidos avaliados por faixas de tempo de "
- Análise: o cálculo está certo (r = -0,51, o esperado arredondado de -0,5063, conferido pelo SQL e pelo Python), mas a resposta não diz sobre quantos pedidos avaliados (5.501) a correlação foi calculada, e o caso exige a base. É omissão do modelo, não erro de número; o prompt não foi ajustado para este caso, para a avaliação não virar treino para a prova. Rodadas anteriores deste caso acharam dois defeitos reais, já corrigidos: o Deno fora do PATH (a ferramenta Python falhava) e o `df` do Python recebendo só as 1.000 primeiras linhas do SELECT (r = -0,4974 em vez de -0,5063).

