// Worker de módulo: roda o Python da IA (Pyodide + pandas) no navegador. Um worker por execução.
// Sem nonce: a correlação é pela instância do worker (ver docs/decisoes.md, ADR 13).
import { loadPyodide } from "https://cdn.jsdelivr.net/pyodide/v0.28.3/full/pyodide.mjs";

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
  pyodide.setStdout({ batched: (s) => saida.push(s) });
  pyodide.setStderr({ batched: (s) => saida.push(s) });
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
