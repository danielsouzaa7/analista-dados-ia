# Orquestração de agentes

Mede só a construção do agente, até o commit `cec40ed` (mesmo corte das horas de construção).

**58 agentes geraram 2.032.359 tokens de saída; o orquestrador (conversa principal de 7 sessões) gerou 582.779** (3,5x). O pico de contexto do orquestrador foi 505.062 tokens; 57 de 58 agentes ficaram na zona de genialidade (pico até 300.000) e 1 passou(aram) dela.

## Totais

| Medida | Agentes | Orquestrador | Razão agentes ÷ orquestrador |
|---|---:|---:|---:|
| Tokens gerados (saída) | 2.032.359 | 582.779 | 3,5x |
| Entrada nova (`input_tokens`) | 3.492 | 1.298 | 2,7x |
| Cache criado | 8.048.304 | 2.459.595 | 3,3x |
| **Tokens novos** (saída + entrada nova + cache criado) | 10.084.155 | 3.043.672 | 3,3x |
| Cache lido (releitura, não é trabalho novo) | 161.134.310 | 154.529.583 | 1,0x |
| Total bruto (tokens novos + cache lido) | 171.218.465 | 157.573.255 | 1,1x |
| Chamadas ao modelo | 1.662 | 613 | 2,7x |

## Por papel

| Papel | Agentes | Tokens gerados | Tokens novos | Cache lido | Pico máx. | Pico mediano |
|---|---:|---:|---:|---:|---:|---:|
| Revisão | 19 | 730.900 | 3.479.717 | 48.124.401 | 163.876 | 124.648 |
| Implementação | 27 | 951.840 | 4.318.383 | 93.121.957 | 315.969 | 93.690 |
| Spec/plano | 5 | 167.436 | 1.245.497 | 7.344.667 | 225.163 | 112.094 |
| Documentação | 3 | 74.608 | 437.390 | 6.007.786 | 134.541 | 117.037 |
| Testes | 2 | 39.631 | 215.241 | 2.661.231 | 117.641 | 73.396 |
| Outros | 2 | 67.944 | 387.927 | 3.874.268 | 289.166 | 275.133 |

## Zona de genialidade (pico de contexto até 300 mil tokens)

| Quem | Dentro da zona | Fora da zona |
|---|---:|---:|
| Agentes | 57 | 1 |
| Orquestrador (sessões) | 4 | 3 |

## Orquestrador por sessão

| Sessão (ordem cronológica) | Pico de contexto | Compactações | Maior contexto antes de compactar |
|---|---:|---:|---:|
| 1 | 311.740 | 1 | 245.244 |
| 2 | 78.885 | 0 | — |
| 3 | 398.116 | 2 | 398.417 |
| 4 | 81.295 | 0 | — |
| 5 | 82.956 | 0 | — |
| 6 | 505.062 | 0 | — |
| 7 | 82.411 | 0 | — |

**Honestidade:** 3 sessão(ões) do orquestrador passaram de 300.000 tokens de pico; o contexto foi compactado 3 vez(es) (maior contexto antes de compactar: 398.417).

## Como foi medido

1. Lê o `usage` de cada mensagem do assistente na conversa principal (orquestrador) e em cada subagente, até o mesmo corte das horas de construção (`--ate`); eventos depois dele são ignorados.
2. A resposta aparece repetida em várias linhas do registro; conta-se uma vez por `message.id` (o maior valor de cada campo).
3. **Tokens gerados** = `output_tokens`. **Entrada nova** = `input_tokens`. **Cache criado** = `cache_creation_input_tokens` (contexto escrito no cache). **Cache lido** = `cache_read_input_tokens` (o mesmo contexto relido a cada chamada: soma inflada por repetição, por isso fica separado).
4. **Tokens novos** = saída + entrada nova + cache criado. **Total bruto** = tokens novos + cache lido.
5. **Pico de contexto** (por agente ou sessão) = maior valor, numa única chamada, de entrada + cache lido + cache criado: o tamanho da janela de contexto naquela chamada.
6. Zona de genialidade: pico de contexto até 300.000 tokens (convenção de que a qualidade se mantém); o limite é inclusivo.
7. Papel do agente pelo tipo registrado (mesmas categorias do relatório de tempo).
8. Compactações = eventos de compactação de contexto do registro; o contexto antes de compactar vem do próprio evento.

Limites: o orquestrador tem poucas sessões, cada uma longa; papéis diferentes não são comparáveis em custo. Só contagens agregadas: nenhum texto, identificador ou caminho é publicado.

Gerado em 22/11/2026.
