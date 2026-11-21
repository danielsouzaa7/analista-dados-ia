// Worker falso para os testes: mesma superfície que python.js usa (postMessage, terminate, onmessage, onerror).
export class FalsoWorker {
  constructor({ inicio = "pronto", aoPedido = null } = {}) {
    this.onmessage = null;
    this.onerror = null;
    this.encerrado = false;
    this.aoPedido = aoPedido;
    if (inicio) setTimeout(() => this.emitir({ tipo: inicio }), 0);
  }
  emitir(data) {
    if (!this.encerrado) this.onmessage?.({ data });
  }
  postMessage(msg) {
    this.aoPedido?.(this, msg);
  }
  terminate() {
    this.encerrado = true;
  }
}

/** Fábrica que guarda os workers criados e, a cada criação, quais já estavam encerrados. */
export function fabrica(opcoes = {}) {
  const workers = [];
  const encerradosNaCriacao = [];
  const criar = () => {
    encerradosNaCriacao.push(workers.map((w) => w.encerrado));
    const w = new FalsoWorker(opcoes);
    workers.push(w);
    return w;
  };
  return { criar, workers, encerradosNaCriacao };
}

export const responde = (data) => (w) => w.emitir({ tipo: "resultado", ...data });

export function ambiente({ deviceMemory, grosso = false, saveData = false } = {}) {
  Object.defineProperty(globalThis, "navigator", {
    value: { deviceMemory, connection: { saveData } },
    configurable: true,
  });
  globalThis.matchMedia = () => ({ matches: grosso });
}
