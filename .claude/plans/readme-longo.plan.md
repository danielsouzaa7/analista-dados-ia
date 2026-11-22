# Plano: README longo e profundo, no padrão do Pulse

Decisão do Daniel em 21/11/2026: o README de uma tela "tá curto"; o padrão do portfólio dele é o README do Pulse (1.225 linhas). As horas e os agentes precisam aparecer com destaque. Este plano **substitui o critério 23 de "uma tela"**.

## Regras

- Português, cerca de 590 linhas (teto 800, piso 350). Denso, sem encher linguiça: detalhes item a item ficam só linkados em `docs/`.
- **Topo intacto** (linhas 1–20 atuais: título, herói, frase, links, 4 diferenciais). Vários literais são amarrados por teste. No row de links, acrescentar `· <a href="#em-números">Em números</a>`.
- Todo número tem par número→fonte em `tests/test_docs.py`. Contagens de testes: registrar com data em `docs/como-rodar.md` ("Testes") e fazer o par README→como-rodar.
- Jargão (pass^N, cassete, prelúdio, grounding, nonce) é permitido **se explicado entre parênteses na 1ª ocorrência**.
- Proibido no README (testes existentes): o literal "6/8" (use "6 dos 8") e a frase "O servidor nunca executa o Python da IA" (use "o servidor não executa o Python da IA em produção").
- Escrever "1.4x" com ponto (como no relatório).
- Nunca publicar a tabela por sessão do relatório de tempo (tem IDs).

## Estrutura (ordem)

| # | Seção | Fonte principal |
|---|---|---|
| 0–1 | Topo + 4 diferenciais (igual) | README atual |
| 2 | **Em números**: tabela Medida / Valor / Fonte (link) | avaliacao (7,0/8, faixa 6–8, 6 dos 8 em todas, 0 números sem fonte, meta não batida, mediana 9,3 s); como-rodar (14 s do GIF, 10 vetores de fuga); ADR 13 (4,5–5,2 s nos 3 motores; 21,4 MB; 0,1 vCPU/512 MB); ADR 14 (R$ 0); seguranca (5 rodadas; contagem de achados [CONFERIR]; Docker 617→433 MB); testes [CONFERIR: `pytest --collect-only -q`, `deno test --allow-read tests/js/`, e2e]; tempo-de-construcao (**11h42 ativas, 67h55 corridas, 56h13 excluídas, 71 agentes, 16h01 somadas, 1.4x, 7 sessões**); 14 ADRs; 13 decisões do Daniel |
| 3 | GIFs (igual, mesma legenda) | README atual |
| 4 | **Como foi construído** (em destaque): frase na voz do Daniel (autoria §1); período "19/11/2026 02:13 a <fim>"; **tabela de horas** (1ª tabela de tempo-de-construcao, linha a linha); **tabela de agentes por tipo** (2ª tabela, linha a linha); "como foi medido" em 2 linhas; 6–8 bullets das decisões do Daniel (dataset de delivery; Gemini grátis; horas sem tempo parado; "um projeto completo"; Render grátis; Cloud Run e os R$180 com a frase literal "acho um absurdo pagar pra expor portfólio"; Python no navegador "entre as opções que os agentes prepararam"; chave de avaliação em projeto separado); o fluxo de 9 etapas em 1 linha com crédito ao ECC; a frase "Não escrevi o código nem fiz as revisões técnicas…" e o link para a autoria | tempo-de-construcao, autoria |
| 5 | Sumário em `<details>` (linha em branco depois de `</summary>` e antes de `</details>`) | — |
| 6 | O problema (e para quem é / não é) | Spec "Problema", "Usuários" |
| 7 | A tese: "o agente pensa no servidor; o Python roda no seu navegador, ao vivo"; 3 apostas (ADR 13; conferência em código, ADR 4; várias rodadas) | Spec "Hipótese"; avaliacao "Uma rodada só é ruído" |
| 8 | Arquitetura: o `<picture>` do `fluxo.svg` sai do topo e vem para cá; visão geral em 4 linhas; tabela curta de componentes; stack em 1 linha. Sem Mermaid | arquitetura "Visão geral", "Componentes", "Módulos" |
| 9 | Como uma pergunta vira resposta: 5 passos; ordem dos eventos SSE + tabela dos 8 principais; limites (8 primeiras linhas); memória de 3 turnos; modelo reserva | arquitetura "O que ele faz", "Contrato de eventos SSE", "Limites", "Memória curta"; ADR 12 |
| 10 | Python no navegador: por quê (5 s e 248 MB por chamada; 30 s estourados no Render); protocolo em 5 passos (nonce fica entre servidor e página; o Worker não o recebe); tabela de medições (spike e fluxo completo, 3 motores); o que o spike descobriu (CSP e `worker-src`); alternativas descartadas; o que o navegador assume em troca; "O WebKit do Playwright não é o Safari nem o iOS" | ADR 13 |
| 11 | Conferência de números e de significância (formato BR, 1%, até 2 reanálises; p-valor só de saída Python; citação precisa bater; o que não cobre: número certo no lugar errado; o bug das 1.000 primeiras linhas: -0,497 vs -0,506) | Spec crit. 7; ADR 4; seguranca 5.18; avaliacao "O que a avaliação pegou" |
| 12 | **Exemplo real de resposta**, entre `<!-- exemplo:inicio -->` e `<!-- exemplo:fim -->`, de `data/gravacoes/cupom_ticket.jsonl`, com o TEXTO EXATO: pergunta; plano; SQL + resultado; código Python + saída; resumo do gráfico; conferência (tentativas descartadas com as falhas e a aprovada; confira em `app/checker.py` o motivo antes de explicar; se não fechar, mostre só os eventos); resposta conferida; trace (tempo, chamadas, ferramentas, tokens, reanálises, R$ 0, versão do prompt). Notas honestas: gravada por `scripts/avaliar.py`, então o Python rodou no executor Deno, no servidor; a resposta copia números com muitas casas (ligar ao "O que eu faria diferente"); tempo acima da mediana por causa das reanálises | a gravação |
| 13 | Avaliação: tabela por caso (pergunta, gráfico, ferramentas, k/5, falha); pass^5 explicado; como um caso passa; "uma rodada só é ruído" (6, 8, 6, 7, 8); meta não batida | perguntas.json; avaliacao |
| 14 | Segurança: modelo de ameaça em 4 bullets; tabela por rodada (R1–R5) com o achado representativo e como fechou; 5 riscos aceitos e link para todos | seguranca |
| 15 | Dados de exemplo (8.000 pedidos fictícios, padrões plantados de propósito, sem marca real) | como-rodar "Dados de exemplo"; Spec "Restrições" |
| 16 | Telas: grade dos PNGs de `docs/img/` com `alt` descritivo ([CONFERIR] se mostram a tela atual) | docs/img |
| 17 | Testes: tabela Suíte / Cobre / Quantos / Onde; os 3 jobs do CI; o CI não usa segredo nem chama o LLM | ci.yml; contagens [CONFERIR] |
| 18 | Reprodutibilidade (semente fixa; regressão sem LLM; `avaliar.py --rodadas 5`; prompt versionado; versões fixas; `fake-stream.html`; commit do GIF) | ADRs 10, 11; avaliacao |
| 19 | Limitações e o que eu faria diferente (sai do `<details>`; + respostas que copiam a saída crua; + trabalho futuro de 25–30 casos) | limitacoes; Spec |
| 20 | Como rodar (Docker em 3 comandos + local + variáveis + Render) | como-rodar |
| 21 | Estrutura do repositório (atualizar também em como-rodar a linha `docs/` com autoria, como-rodar, limitacoes) | como-rodar |
| 22 | Decisões de arquitetura: tabela dos 14 títulos com 1 frase cada; link sem âncora | decisoes |
| 23 | Leitura adicional (inclui link opcional para o Pulse como projeto irmão) | — |

## Spec e testes

- `Spec.md`: critério 23 passa a "README longo no padrão do Pulse, animado (decisão do Daniel em 21/11/2026, que substitui o README de uma tela)": 350–800 linhas; jargão permitido se explicado; exemplo real com texto exato de uma gravação, dizendo onde o Python rodou; mantêm-se as regras dos SVGs e do GIF, "sem rede além do caminho fixo do Pyodide", os pares número→fonte, "nada se perde" e os links. Critério 11: "README longo (critério 23)". Marco 7: "README longo no padrão do Pulse".
- `tests/test_docs.py`: apagar `test_readme_cabe_em_uma_tela` e criar `test_readme_longo_mas_abaixo_do_teto` (350 ≤ linhas ≤ 800); trocar `test_readme_sem_jargao_solto` por `test_jargao_explicado_na_primeira_ocorrencia` (fora de blocos de código, a explicação aparece até 80 caracteres depois da 1ª ocorrência); acrescentar os pares de números novos (horas, agentes por categoria, 9,3 s, 13,8 s, 21,4 MB, 56.229 bytes, 10 vetores de fuga, 433 MB, contagens de testes→como-rodar); criar `test_exemplo_real_e_texto_exato_da_gravacao` (compara com a gravação, normalizando espaços no fim da linha). Os outros testes ficam.

## Riscos

- As horas mudam com este trabalho: regerar o relatório UMA vez no fim e atualizar README e autoria juntos.
- A gravação `tempo_nota` não cita o 5.501 do gabarito, mas a regra diz que só caso aprovado grava. Investigar antes de citar; não usar no exemplo.
- Âncoras com acento: conferir o Sumário no render da API do GitHub.
- PNGs antigos em "Telas": conferir e, se preciso, capturar de novo.
