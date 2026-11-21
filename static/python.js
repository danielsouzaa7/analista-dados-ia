// Cliente do Python no navegador: um worker novo por execução, mais uma reserva já carregada.
// Sem efeito colateral no import: nada é criado até alguém chamar preaquecer() ou executarPython().

const CARGA_MS = 45_000;
const EXECUCAO_MS = 30_000;
const MAX_SAIDA = 10_000;
const MAX_ERRO = 2_000;
const LINHAS_ERRO = 6;
const ERRO_CARGA = "Não consegui carregar o Python no seu navegador";
const ERRO_FALHA = "O Python do seu navegador falhou.";

let reserva = null;

const criarWorker = () => new Worker(new URL("./python-worker.js", import.meta.url), { type: "module" });

// deviceMemory não existe no Firefox nem no Safari: ausente não é pouca memória. pointer coarse cobre o celular.
const semReserva = () => (navigator.deviceMemory ?? Infinity) < 4 || matchMedia("(pointer: coarse)").matches;

// Array.from conta pontos de código: não parte um par UTF-16 ao meio.
const cortar = (s, max) => {
  const pontos = Array.from(String(s));
  return pontos.length > max ? pontos.slice(0, max).join("") : String(s);
};

const limpar = ({ saida, erro }) => ({
  saida: cortar(saida ?? "", MAX_SAIDA),
  erro: erro == null ? null : cortar(String(erro).split("\n").slice(-LINHAS_ERRO).join("\n"), MAX_ERRO),
});

/** Cria o worker e já escuta "pronto"/"falhou". Correlação pela instância: cada worker tem o seu handler. */
function abrir(criar) {
  const worker = criar();
  const inst = { worker, carregou: false, aoEvento: null };
  inst.carga = new Promise((resolve) => {
    worker.onmessage = ({ data }) => {
      if (data?.tipo === "pronto") { inst.carregou = true; resolve(true); }
      else if (data?.tipo === "falhou") { resolve(false); if (inst.carregou) inst.aoEvento?.(data); }
      else if (data?.tipo === "resultado") inst.aoEvento?.(data);
    };
    worker.onerror = () => { resolve(false); if (inst.carregou) inst.aoEvento?.({ tipo: "falhou" }); };
  });
  return inst;
}

export function preaquecer(criar = criarWorker) {
  if (reserva || semReserva() || navigator.connection?.saveData) return;
  reserva = abrir(criar);
}

export const estaPronto = () => Boolean(reserva?.carregou);

/** Roda o código no navegador. Devolve {saida, erro}; rejeita com AbortError se o sinal abortar. */
export function executarPython(pedido, { signal, criar = criarWorker, cargaMs = CARGA_MS, execucaoMs = EXECUCAO_MS } = {}) {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) return reject(new DOMException("Execução cancelada.", "AbortError"));
    const inst = reserva ?? abrir(criar);
    reserva = null;
    let acabou = false;
    let timer = setTimeout(() => acabar(() => resolve({ saida: "", erro: `${ERRO_CARGA} em 45 s.` })), cargaMs);
    const aoAbortar = () => acabar(() => reject(new DOMException("Execução cancelada.", "AbortError")));

    function acabar(entrega) {
      if (acabou) return;
      acabou = true;
      clearTimeout(timer);
      signal?.removeEventListener("abort", aoAbortar);
      inst.aoEvento = inst.worker.onmessage = inst.worker.onerror = null;
      inst.worker.terminate();
      if (!semReserva()) reserva = abrir(criar); // só depois do terminate: nunca dois workers vivos
      entrega();
    }

    signal?.addEventListener("abort", aoAbortar);
    inst.aoEvento = (msg) =>
      acabar(() => resolve(msg.tipo === "resultado" ? limpar(msg) : { saida: "", erro: ERRO_FALHA }));
    inst.carga.then((ok) => {
      if (acabou) return;
      clearTimeout(timer); // o prazo de execução só conta depois de carregar
      if (!ok) return acabar(() => resolve({ saida: "", erro: `${ERRO_CARGA}.` }));
      timer = setTimeout(() => acabar(() => resolve({ saida: "", erro: "Tempo limite de 30 s excedido." })), execucaoMs);
      inst.worker.postMessage(pedido);
    });
  });
}

/** Roda o pedido e devolve o resultado ao servidor. `postar` rejeita com `.rede` verdadeiro em erro de rede. */
export async function responderPython(pedido, { sessao, signal, postar, executar = executarPython }) {
  let r;
  try {
    r = await executar({ codigo: pedido.codigo, csv: pedido.csv, preludio: pedido.preludio }, { signal });
  } catch (e) {
    if (e?.name === "AbortError") return; // aba parada: nada é postado
    throw e;
  }
  // String(...): um objeto vindo do worker daria 422 e deixaria o visitante esperando o prazo do servidor.
  const corpo = { sessao, id: String(pedido.id), nonce: String(pedido.nonce), saida: String(r.saida), erro: r.erro == null ? null : String(r.erro) };
  for (let tentativa = 0; tentativa < 2 && !signal?.aborted; tentativa++) {
    try { return await postar(corpo); } catch (e) { if (!e?.rede) return; } // 400/422: o servidor já fechou a execução
  }
}
