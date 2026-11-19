// Cliente SSE sobre fetch + ReadableStream (EventSource não faz POST).

export class ErroStream extends Error {
  constructor(mensagem, { queda = false, status = 0 } = {}) {
    super(mensagem);
    this.queda = queda; // true: a conexão caiu no meio; a tela oferece "Tentar de novo"
    this.status = status;
  }
}

/** Parser incremental de SSE: aceita pedaços quebrados em qualquer ponto, \r\n e comentários. */
export class ParserSSE {
  constructor(aoEvento) {
    this.aoEvento = aoEvento;
    this.buffer = "";
    this.resto = "";
  }

  push(texto) {
    // Um "\r" no fim do pedaço pode ser o começo de "\r\n": espera o próximo pedaço antes de normalizar.
    const bruto = this.resto + texto;
    this.resto = bruto.endsWith("\r") ? "\r" : "";
    this.buffer += (this.resto ? bruto.slice(0, -1) : bruto).replace(/\r\n?/g, "\n");
    let i;
    while ((i = this.buffer.indexOf("\n\n")) !== -1) {
      this.#bloco(this.buffer.slice(0, i));
      this.buffer = this.buffer.slice(i + 2);
    }
  }

  fim() {
    if (this.resto) this.buffer += "\n";
    this.resto = "";
    if (this.buffer.trim()) this.#bloco(this.buffer);
    this.buffer = "";
  }

  #bloco(bloco) {
    let tipo = "message";
    const dados = [];
    for (const linha of bloco.split("\n")) {
      if (!linha || linha.startsWith(":")) continue;
      const k = linha.indexOf(":");
      const campo = k === -1 ? linha : linha.slice(0, k);
      const valor = k === -1 ? "" : linha.slice(k + 1).replace(/^ /, "");
      if (campo === "event") tipo = valor;
      else if (campo === "data") dados.push(valor);
    }
    if (!dados.length) return;
    try {
      const obj = JSON.parse(dados.join("\n"));
      if (obj && typeof obj === "object") this.aoEvento(tipo, obj);
    } catch {
      // bloco com JSON inválido é ignorado: um evento ruim não derruba a conversa
    }
  }
}

async function detalheDoErro(resp) {
  const corpo = await resp.json().catch(() => ({}));
  const d = corpo && corpo.detail;
  if (typeof d === "string") return d;
  return "Entrada inválida. Confira os dados e tente de novo.";
}

/**
 * Faz POST /api/perguntar e entrega cada evento a `aoEvento(tipo, dados)`.
 * Resolve quando o servidor manda `fim`. Rejeita com ErroStream (pt-BR) se algo falhar.
 */
export async function perguntarStream(corpo, aoEvento, { signal } = {}) {
  let resp;
  try {
    resp = await fetch("/api/perguntar", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify(corpo),
      signal,
    });
  } catch (e) {
    if (e && e.name === "AbortError") throw e;
    throw new ErroStream("Não consegui falar com o servidor. Confira sua conexão e tente de novo.", { queda: true });
  }
  if (!resp.ok) throw new ErroStream(await detalheDoErro(resp), { status: resp.status });
  if (!resp.body) throw new ErroStream("Este navegador não suporta resposta em streaming.");

  let recebeuFim = false;
  const parser = new ParserSSE((tipo, dados) => {
    if (tipo === "fim") recebeuFim = true;
    aoEvento(tipo, dados);
  });
  const leitor = resp.body.getReader();
  const decoder = new TextDecoder("utf-8");
  try {
    for (;;) {
      const { done, value } = await leitor.read();
      if (done) break;
      parser.push(decoder.decode(value, { stream: true }));
    }
    parser.push(decoder.decode());
    parser.fim();
  } catch (e) {
    if (e && e.name === "AbortError") throw e;
    throw new ErroStream("A conexão caiu antes de a resposta terminar.", { queda: true });
  }
  if (!recebeuFim) throw new ErroStream("A conexão caiu antes de a resposta terminar.", { queda: true });
}
