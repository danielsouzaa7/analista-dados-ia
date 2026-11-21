// Cliente do Python no navegador: um worker novo por execução, mais uma reserva já carregada.
// Sem efeito colateral no import: nada é criado até alguém chamar preaquecer() ou executarPython().

const CARGA_MS = 45_000;
const EXECUCAO_MS = 30_000;
const MAX_SAIDA = 10_000;
const MAX_ERRO = 2_000;
const LINHAS_ERRO = 6;
const ESPERA_REENVIO_MS = 1_000;
const ERRO_CARGA = "Não consegui carregar o Python no seu navegador";
const ERRO_FALHA = "O Python do seu navegador falhou.";

let reserva = null;
let emCurso = null; // a execução viva: { inst, cancelar }

const criarWorker = () => new Worker(new URL("./python-worker.js", import.meta.url), { type: "module" });

// deviceMemory não existe no Firefox nem no Safari: ausente não é pouca memória. pointer coarse cobre o celular.
const semReserva = () =>
  (navigator.deviceMemory ?? Infinity) < 4 || matchMedia("(pointer: coarse)").matches || Boolean(navigator.connection?.saveData);

const prazo = (ms) => (ms >= 1000 ? `${Math.round(ms / 1000)} s` : `${ms} ms`);

// Corta por unidades UTF-16 antes do Array.from (que é O(n) e congelaria a aba numa saída gigante).
// Array.from conta pontos de código: o meio-par que sobrar no fim do corte cai além de `max` e sai no slice.
const cortar = (s, max) => {
  const texto = String(s);
  const t = texto.length > max * 2 ? texto.slice(0, max * 2) : texto;
  return Array.from(t).slice(0, max).join("");
};

const limpar = ({ saida, erro }) => ({
  saida: cortar(saida ?? "", MAX_SAIDA),
  erro: erro == null ? null : cortar(String(erro).split("\n").slice(-LINHAS_ERRO).join("\n"), MAX_ERRO),
});

/** Cria o worker e já escuta "pronto"/"falhou". Correlação pela instância: cada worker tem o seu handler. */
function abrir(criar) {
  const worker = criar();
  const inst = { worker, carregou: false, aoEvento: null };
  const falhouAntes = () => { // reserva que falhou na carga não pode ser reaproveitada
    worker.terminate();
    if (reserva === inst) reserva = null;
  };
  inst.carga = new Promise((resolve) => {
    worker.onmessage = ({ data }) => {
      if (data?.tipo === "pronto") { inst.carregou = true; resolve(true); }
      else if (data?.tipo === "falhou") { resolve(false); if (inst.carregou) inst.aoEvento?.(data); else falhouAntes(); }
      else if (data?.tipo === "resultado") inst.aoEvento?.(data);
    };
    worker.onerror = () => { resolve(false); if (inst.carregou) inst.aoEvento?.({ tipo: "falhou" }); else falhouAntes(); };
  });
  return inst;
}

export function preaquecer(criar = criarWorker) {
  if (reserva || semReserva()) return;
  reserva = abrir(criar);
}

/** A reserva, ou o worker da execução em curso, já carregou o Python. */
export const estaPronto = () => Boolean((emCurso?.inst ?? reserva)?.carregou);

export const statusPython = () =>
  estaPronto() ? "Rodando o Python no seu navegador…"
    : semReserva() ? "Carregando o Python no seu navegador…"
    : "Carregando o Python no seu navegador (só na primeira vez)…";

/** Roda o código no navegador. Devolve {saida, erro}; rejeita com AbortError se o sinal abortar. */
export function executarPython(pedido, { signal, criar = criarWorker, cargaMs = CARGA_MS, execucaoMs = EXECUCAO_MS } = {}) {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) return reject(new DOMException("Execução cancelada.", "AbortError"));
    emCurso?.cancelar(); // uma execução sobreposta (o servidor já desistiu da anterior) não pode deixar o worker dela vivo
    const inst = reserva ?? abrir(criar);
    reserva = null;
    let acabou = false;
    let timer = setTimeout(() => acabar(() => resolve({ saida: "", erro: `${ERRO_CARGA} em ${prazo(cargaMs)}.` })), cargaMs);
    const cancelar = () => acabar(() => reject(new DOMException("Execução cancelada.", "AbortError")));
    emCurso = { inst, cancelar };

    function acabar(entrega) {
      if (acabou) return;
      acabou = true;
      clearTimeout(timer);
      signal?.removeEventListener("abort", cancelar);
      inst.aoEvento = inst.worker.onmessage = inst.worker.onerror = null;
      inst.worker.terminate();
      if (emCurso?.inst === inst) emCurso = null;
      entrega(); // antes da reserva: criar() pode lançar e a promessa já tem de estar resolvida
      if (!reserva && !semReserva()) {
        try { reserva = abrir(criar); } catch { /* a reserva é opcional: a próxima execução abre o seu worker */ }
      }
    }

    signal?.addEventListener("abort", cancelar);
    inst.aoEvento = (msg) =>
      acabar(() => resolve(msg.tipo === "resultado" ? limpar(msg) : { saida: "", erro: ERRO_FALHA }));
    inst.carga.then((ok) => {
      if (acabou) return;
      clearTimeout(timer); // o prazo de execução só conta depois de carregar
      if (!ok) return acabar(() => resolve({ saida: "", erro: `${ERRO_CARGA}.` }));
      timer = setTimeout(() => acabar(() => resolve({ saida: "", erro: `Tempo limite de ${prazo(execucaoMs)} excedido.` })), execucaoMs);
      inst.worker.postMessage(pedido);
    });
  });
}

const pausa = (ms) => new Promise((r) => setTimeout(r, ms));

/** Roda o pedido e devolve o resultado ao servidor. `postar` rejeita com `.rede` verdadeiro em erro de rede. */
export async function responderPython(pedido, { sessao, signal, postar, executar = executarPython, esperaMs = ESPERA_REENVIO_MS }) {
  let r;
  try {
    r = await executar({ codigo: pedido.codigo, csv: pedido.csv, preludio: pedido.preludio }, { signal });
  } catch (e) {
    if (e?.name === "AbortError") return; // aba parada: nada é postado
    r = { saida: "", erro: ERRO_FALHA }; // o servidor está esperando: um erro postado vale mais que o prazo dele
  }
  // String(...): um objeto vindo do worker daria 422 e deixaria o visitante esperando o prazo do servidor.
  const corpo = { sessao, id: String(pedido.id), nonce: String(pedido.nonce), saida: String(r.saida), erro: r.erro == null ? null : String(r.erro) };
  for (let tentativa = 0; tentativa < 2 && !signal?.aborted; tentativa++) {
    if (tentativa) { await pausa(esperaMs); if (signal?.aborted) return; } // dá tempo à rede de voltar
    try { return await postar(corpo); } catch (e) { if (!e?.rede) return; } // 400/422: o servidor já fechou a execução
  }
}
