# Como o projeto foi construído por dentro

Arquitetei a solução e o processo; um time de agentes de IA especializados implementou sob portões de qualidade que eu defini. Este documento mostra a lógica primeiro e as ferramentas depois, e cada afirmação aponta para um commit ou um documento do repositório. Os agentes não foram criados por mim: usei agentes prontos, configurados para este fluxo. Quem decidiu o quê: [autoria](autoria.md).

## 1. O fluxo de 9 etapas

Defini o fluxo; os agentes o seguiram sem pedir confirmação até a etapa 8.

1. Pedido.
2. Spec com critérios de aceite (`Spec.md`).
3. Revisão independente da spec.
4. Plano em fatias (`.claude/plans/`).
5. Implementação com testes primeiro.
6. Revisão do código por especialistas.
7. Teste, build e navegador.
8. Minha aprovação.
9. Deploy.

Regras do fluxo: o laço de revisão (etapas 3 e 6) volta no máximo 3 vezes; se não resolver, para e volta para mim. Um commit a cada lote de testes verde. Push e deploy só depois da minha aprovação. Fonte: [autoria](autoria.md), tabela de decisões (19/11).

## 2. O time, por papel

| Papel | O que fez aqui | Exemplo |
|---|---|---|
| Planejamento | Desenhou o plano e o protocolo do Python no navegador | O protocolo `python_pedido` / `POST /api/python/resultado`, com nonce e espera no servidor ([ADR 13](decisoes.md)) |
| Arquitetura e revisão da spec | Revisou o plano antes de haver código | Encontrou furos na regex de significância: casava com "valor por pedido" e disparava com "não foi possível calcular a significância" (H1 e H2 em `.claude/plans/python-no-navegador.plan.md`) |
| Implementação com testes primeiro | Escreveu o teste antes do código, em lotes | Worker do Pyodide com CSP própria e testes de fuga nos três motores (commit `b140d08`; [decisão 13](decisoes.md)) |
| Revisão de código Python | Revisou o servidor e o conferidor | Um p-valor inventado passava como conferido (5.18 em [segurança](seguranca.md)) |
| Revisão de JavaScript | Revisou o worker e o cliente | Saída gigante congelava a aba (5.16) e execuções sobrepostas vazavam um worker de cerca de 250 MB (5.17) |
| Segurança (red team) | 5 rodadas de ataque ao código vigente | Rodada 5: vetores de fuga do Worker (`fetch`, WebSocket, `importScripts`, `eval`) testados nos três motores ([segurança](seguranca.md)) |
| Testes de ponta a ponta | Rodou o fluxo real no navegador | Playwright em Chromium, Firefox e WebKit, com o CSV de exemplo (`tests/e2e/`) |
| Documentação | Manteve README e docs alinhados ao código | Relatório de red team e relatório de avaliação |
| Verificação de fatos independente | Conferiu a autoria e o README contra as fontes | Achados aplicados no commit `0f86d70` |

Por categoria (58 agentes, 14h12 somadas, em 10h06 de relógio ativo): implementação 27 (8h15), revisão 19 (4h37), spec/plano 5 (0h35), documentação 3 (0h18), testes 2 (0h16), outros 2 (0h10). Fonte: [tempo de construção](tempo-de-construcao.md).

## 3. Capacidades usadas, pelo que fazem

- **Spec com critérios de aceite:** o pedido vira `Spec.md`, com o que fazer, para quem, o que fica fora e critérios verificáveis (a Spec tem 24 critérios).
- **Plano em fatias verticais:** cada fatia entrega algo que roda de ponta a ponta, e o plano é o contrato entre os agentes ([planos](../.claude/plans/)).
- **Testes primeiro (TDD, na sigla em inglês):** escreve o teste, vê falhar, faz passar, depois limpa o código.
- **Revisão por linguagem e por segurança:** um revisor para Python, outro para JavaScript, outro para segurança (injeção de SQL e de prompt, SSRF, que é fazer o servidor chamar um endereço que o atacante escolhe, fuga de sandbox).
- **Spike de viabilidade:** um experimento curto para provar que a ideia roda antes de ela virar produto.
- **Teste no navegador:** Playwright, em Chromium, Firefox e WebKit.
- **Laço de verificação:** `ruff`, `pytest`, `deno test` e os testes de ponta a ponta, rodados a cada lote.
- **Avaliação do LLM em várias rodadas:** média, faixa e pass^N, que é a fração dos casos certos em todas as N rodadas ([avaliação](avaliacao.md)).
- **Cassetes:** respostas do LLM gravadas, para a regressão rodar sem chamar o modelo (`tests/cassetes/`).
- **Verificação de fatos da documentação:** um agente só de leitura confere cada afirmação contra a fonte; um teste confere os pares número e arquivo (`tests/test_docs.py`).
- **Medição de horas a partir dos registros** das sessões ([tempo de construção](tempo-de-construcao.md)).

## 4. Orquestração

- Agentes em paralelo, cada um com um conjunto de arquivos próprio, para não haver conflito: o plano da experiência de portfólio divide o trabalho em 3 frentes com arquivos disjuntos ([plano](../.claude/plans/experiencia-portfolio.plan.md)).
- Modelo escolhido por tarefa: o mais forte para planejar e revisar, o mais rápido para implementar (regra do meu fluxo; o registro da conversa não está publicado).
- Planos como contrato de passagem entre agentes (`.claude/plans/`).
- Revisões independentes: o revisor recebe o código, não a conclusão de quem o escreveu.
- **Em números:** 58 agentes, 57 deles dentro da zona de qualidade (pico de contexto até 300 mil tokens). Os agentes processaram 10,1 milhões de tokens novos contra 3,0 milhões do orquestrador (3,3x) e geraram 2,03 milhões de tokens (3,5x o orquestrador). Em 3 das 7 sessões o orquestrador passou de 300 mil; a lição aplicada é delegar mais e compactar. Gráfico: [orquestração](img/orquestracao.svg). Metodologia, incluindo o que conta como token: [orquestração](orquestracao.md).

## 5. Guardrails

- O valor da chave do LLM nunca foi mostrado aos agentes; o script de avaliação e o do GIF a leem do `.env` sem imprimir ([autoria](autoria.md)).
- Chave de avaliação num projeto Google separado do da demo ([avaliação](avaliacao.md)).
- Commit por lote verde; push e deploy só com a minha aprovação ([autoria](autoria.md)).

## 6. Na prática: histórias com resultado

1. **O spike derrubou a CSP do plano antes de virar produto.** A política de segurança prevista (`worker-src 'none'`) não carregava o Pyodide em nenhum dos três motores; o spike mediu e a política foi corrigida sem abrir exfiltração ([ADR 13](decisoes.md), commits `b140d08` e `051f741`).
2. **A revisão da spec achou furos na regex de significância antes de haver código.** Achados H1 a H3 ("valor por pedido" casava como p-valor; a frase honesta "não foi possível calcular a significância" disparava; a citação de p reprovava a conferência de números), todos incorporados ao plano ([plano](../.claude/plans/python-no-navegador.plan.md)).
3. **Red team em 5 rodadas.** Da escrita no Postgres por `postgres_execute` à fuga do Worker no navegador ([segurança](seguranca.md), commit `7d8f254` para a rodada 5).
4. **A revisão de JavaScript achou a aba congelando e o worker vazando.** Saída gigante congelava a aba e execuções sobrepostas vazavam um worker de cerca de 250 MB; as duas foram corrigidas com teste ([segurança](seguranca.md), 5.16 e 5.17, commit `04a91e3`).
5. **A revisão de Python achou um p-valor inventado passando como conferido.** Corrigido: a citação de p só sai da verificação se bater com uma saída de Python (5.18; commit `6ab18e4`).
6. **A verificação de fatos corrigiu o README:** números, contagem de testes, jobs de CI e legenda de GIF (commit `0f86d70`).

## 7. Números do processo

58 agentes em 7 sessões; 10h06 de tempo ativo de relógio; 14h12 somadas; paralelismo médio de 1,4x ([tempo de construção](tempo-de-construcao.md)). Agentes: 10,1 milhões de tokens novos contra 3,0 milhões do orquestrador (3,3x) e 2,03 milhões de tokens gerados (3,5x); em 3 das 7 sessões o orquestrador passou de 300 mil tokens de contexto ([gráfico](img/orquestracao.svg), [metodologia](orquestracao.md)). Avaliação final: 35 de 40 respostas completas e 0 números sem fonte ([avaliação](avaliacao.md)). O red team teve 5 rodadas, com cada achado corrigido ou publicado como risco aceito ([segurança](seguranca.md)).
