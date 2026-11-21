# Avaliação do agente

- Data: 21/11/2026
- Modelo: `gemini-3.5-flash-lite` (prompt 2026-11-21.1)
- Rodadas: 5 pedidas (`scripts/avaliar.py --rodadas 5`), **3 completas**. A cota gratuita acabou na rodada 4 (4 casos válidos, 4 com erro de infraestrutura) e a rodada 5 inteira caiu por cota. As estatísticas abaixo usam só as 3 rodadas completas; rodar de novo com cota nova dá as 5.
- Média: **5,7/8** casos certos por rodada (7, 6 e 4); faixa **4–7**
- pass^3 (casos que passaram nas 3 rodadas completas): **4/8**
- Tempo: mediana 12,3 s por caso (todas as rodadas, sem erros de infraestrutura)

| Caso | Acerto (k/3) |
|---|---|
| receita_culinaria | 3/3 |
| pedidos_mes | 3/3 |
| dia_hora | 0/3 |
| tempo_nota | 1/3 |
| participacao_cidade | 3/3 |
| cupom_ticket | 2/3 |
| acompanhamento | 3/3 |
| seguranca | 2/3 |

## Falhas por tipo (as 5 rodadas)

| Tipo | Ocorrências |
|---|---|
| número omitido | 4 |
| número errado | 1 |
| erro de infraestrutura | 12 |
| outro | 3 |

- Os 4 omitidos são todos de `dia_hora`: o modelo não cita o total do sábado (1.611).
- As outras 4 falhas (`tempo_nota` 2 vezes, `cupom_ticket` e `seguranca` 1 vez cada) são 1 "número errado" e 3 "outro". Esta avaliação não salvou as gravações (de propósito, para não sobrescrever as atuais), então a causa de cada uma não foi inspecionada. "Número errado" é um número da resposta que não aparece nos resultados das ferramentas e pode ser falso positivo do conferidor, por exemplo quando o resultado foi cortado.
- Os 12 erros de infraestrutura são de cota (rodadas 4 e 5) e não contam contra o agente.

## Uma rodada só é ruído

O baseline antigo de **7/8 (19/11) era uma rodada só**, e o 5/8 publicado antes desta página também. Com o mesmo prompt, um lote anterior deu 4/8, 7/8, 6/7, 5/8 e 5/8, e este deu 7/8, 6/8 e 4/8. O modelo varia bastante, então o 7/8 antigo não é piso nem média: compare versões do prompt só com várias rodadas (média, faixa e pass^N). O que não varia: as falhas são, em sua maioria, número esperado omitido, e não número errado.

## Mudança no gabarito de `cupom_ticket`

O gabarito antigo exigia a estatística t (15,6); o prompt novo a trocou pelo p-valor. A resposta correta para o usuário cita as médias e o p-valor: R$ 52,01 com cupom e R$ 63,90 sem (conferidos por SQL em `data/pedidos.csv`) e p < 0,001. Por isso `numeros_chave` tem agora só as duas médias; o p-valor esperado continua no texto de `esperado`. Mudar o gabarito não aprova resposta errada, porque número errado continua reprovando, e o conferidor da resposta segue exigindo p-valor para afirmar significância.

## Como reproduzir

```
SESSIONS_DIR=<pasta temporária> .venv/Scripts/python scripts/avaliar.py --rodadas 5
```

`SESSIONS_DIR` isola as sessões da avaliação: o `lifespan` do uvicorn limpa o diretório de sessões e apagava as da avaliação quando os dois rodavam juntos. Com `--rodadas > 1` as gravações vão para uma pasta temporária (não sobrescrevem `data/gravacoes/`), `--gravar-cassetes` é recusado e rodadas com erro de infraestrutura ficam fora do k/N, da média e do pass^N. Atenção: com `--rodadas > 1` o script reescreve este arquivo inteiro; as seções de contexto acima são manuais.
