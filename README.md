<h1 align="center">Analista de dados com IA</h1>

<!-- heroi -->
<p align="center"><img src="docs/img/conversa.png" width="100%" alt="Conversa do app: pergunta sobre tempo de entrega e nota, com plano, SQL, gráfico e o selo de números conferidos"></p>

<p align="center"><b>Pergunte em português. O agente planeja no servidor, roda o Python no seu navegador e mostra cada passo ao vivo.</b></p>

<p align="center"><a href="https://analista-dados-ia.onrender.com"><b>Experimente ao vivo →</b></a> · <a href="docs/arquitetura.md">Como funciona</a> · <a href="docs/avaliacao.md">Avaliação</a> · <a href="docs/autoria.md">Como foi construído</a><br>
<img src="https://github.com/danielsouzaa7/analista-dados-ia/actions/workflows/ci.yml/badge.svg" alt="CI"></p>

<!-- icone-navegador --> **O Python da IA roda no seu navegador**, num Worker sem rede além do caminho fixo do Pyodide; o servidor de 0,1 vCPU não o executa. [Decisão 13](docs/decisoes.md), [segurança](docs/seguranca.md)

<!-- icone-ao-vivo --> **Cada passo aparece ao vivo**, com tempo e tokens, e cada número da resposta é conferido em código. [Arquitetura](docs/arquitetura.md)

<!-- icone-avaliacao --> **Avaliado contra o modelo real em 5 rodadas**: média 7,0/8 (faixa 6–8), 6/8 em todas; a meta de 8/8 não foi batida. [Avaliação](docs/avaliacao.md)

<!-- icone-seguranca --> **5 rodadas de red team**: cada achado reproduzido, fechado e coberto por teste. [Segurança](docs/seguranca.md)

<!-- fluxo -->
<p align="center"><sub>O servidor nunca executa o Python da IA (o SQL roda nele, só leitura).</sub></p>

<p align="center"><img src="docs/img/demo.gif" width="100%" alt="Gravação de tela do app: o CSV de exemplo é carregado, a pergunta sobre o tempo de entrega e a nota do cliente é digitada, o agente planeja, consulta, roda o Python no navegador e termina com um gráfico de dispersão e a resposta conferida."><br><sub>Pergunta real, rodando localmente no commit 1f8cafe; tomada única (de até 3 permitidas); espera do carregamento inicial cortada.</sub></p>

## Como foi construído

Eu defini o produto e tomei as decisões de custo e risco; o código, os testes e as revisões técnicas foram feitos por agentes de IA (58 agentes, 10h05 de trabalho ativo). Quem decidiu o quê, com fonte: [autoria](docs/autoria.md). Horas: [tempo de construção](docs/tempo-de-construcao.md).

<details>
<summary>Rodar localmente (3 comandos)</summary>

```bash
cp .env.example .env   # preencha LLM_API_KEY (Google AI Studio, plano gratuito)
docker build -t analista-dados-ia .
docker run --rm -p 7860:7860 --env-file .env analista-dados-ia
```

Sem Docker, testes e variáveis: [como rodar](docs/como-rodar.md).

</details>

<details>
<summary>O que eu faria diferente · limitações</summary>

- Uma avaliação maior, com perguntas ambíguas, sem resposta nos dados e conferência contra o gabarito (hoje são 8 casos).
- Medir a CPU da hospedagem antes de escolher onde roda o Python: no servidor gratuito, três chamadas seguidas estouraram 30 s.
- Limitações: cota do Gemini, uma pergunta por vez, hospedagem que dorme, dados enviados ao Google. Lista completa em [limitações](docs/limitacoes.md).

</details>
