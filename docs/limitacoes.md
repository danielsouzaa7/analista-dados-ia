# Limites conhecidos

- O plano gratuito do Gemini tem limite de requisições; o app avisa quando a cota acaba e, nos exemplos, cai na gravação.
- Uma pergunta por vez no servidor inteiro, com teto diário; os contadores ficam em memória (1 worker) e reiniciam com o processo.
- A hospedagem gratuita (decisão de custo zero) "dorme": a primeira visita pode demorar a acordar. Há teto diário de perguntas; quando ele ou a cota do modelo acaba, as perguntas de exemplo reproduzem uma gravação, marcada como tal na tela. Cada execução de Python leva alguns segundos no navegador (carregar Pyodide e pandas), e a primeira baixa cerca de 21 MB do jsDelivr.
- Uma rede que bloqueia o jsDelivr fica sem Python; o agente responde com SQL.
- O resultado do Python vem do navegador e não é confiável: um visitante pode forjá-lo, mas só na própria sessão (e nas métricas globais). Ver [seguranca.md](seguranca.md).
- **Os dados e as perguntas vão para o Google Gemini** (plano gratuito, que pode usar os dados para melhorar produtos). Não envie dados sensíveis.
- Risco aceito: a URL do Postgres informada faz o servidor abrir uma conexão de rede (SSRF): só IPs públicos são aceitos e a conexão é fixada no IP checado; resta a Internet pública, com `READ_ONLY` e timeout de até 20 s. Use um usuário só com `GRANT SELECT`.
- A conferência verifica que o número existe nos resultados (ou no SQL e no código enviados), não que está no lugar certo.
- A detecção de dado pessoal é por nome da coluna e padrão (CPF, e-mail, telefone); não cobre outros tipos, e não impede que o visitante digite o dado na pergunta.
- Memória de 3 turnos por sessão, sem memória entre sessões. Sessões expiram em 10 min sem pergunta e em 1 h depois da primeira pergunta; com o servidor lotado, sai a sessão sem pergunta parada há mais de 150 s.
- Avaliação: 35 de 40 respostas completas (87,5%) e 0 números sem fonte; 5 respostas omitiram um número do gabarito. Mitigação prevista: o prompt pedir sempre o "n" de cada análise. Ver [avaliacao.md](avaliacao.md).
