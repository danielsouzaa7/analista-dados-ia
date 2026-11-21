// Worker de módulo: roda o Python da IA (Pyodide + pandas) no navegador. Um worker por execução.
// Sem nonce: a correlação é pela instância do worker (ver docs/decisoes.md, ADR 13).
import { loadPyodide } from "https://cdn.jsdelivr.net/pyodide/v0.28.3/full/pyodide.mjs";

// ~2x o corte do cliente (10 mil pontos de código = até 20 mil unidades): acima disso só gastaria memória.
const MAX_SAIDA = 20_000;

let pyodide;
try {
  pyodide = await loadPyodide();
  await pyodide.loadPackage(["pandas"], { messageCallback: () => {}, errorCallback: () => {} });
  postMessage({ tipo: "pronto" });
} catch {
  postMessage({ tipo: "falhou" });
}

onmessage = async ({ data }) => {
  if (!pyodide) return;
  const { codigo, csv, preludio = "" } = data;
  const saida = [];
  let usado = 0;
  const guardar = (s) => {
    if (usado >= MAX_SAIDA) return;
    const parte = s.slice(0, MAX_SAIDA - usado);
    saida.push(parte);
    usado += parte.length + 1;
  };
  pyodide.setStdout({ batched: guardar });
  pyodide.setStderr({ batched: guardar });
  pyodide.globals.set("_csv_texto", csv);
  let erro = null;
  try {
    await pyodide.runPythonAsync(preludio);
    await pyodide.runPythonAsync("import io, pandas as pd\ndf = pd.read_csv(io.StringIO(_csv_texto))");
    await pyodide.runPythonAsync(codigo);
  } catch (e) {
    erro = String(e?.message ?? e).trim().split("\n").slice(-6).join("\n");
  }
  postMessage({ tipo: "resultado", saida: saida.map((l) => l + "\n").join(""), erro });
};
