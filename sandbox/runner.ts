// Executor Python (Pyodide) rodado pelo Deno SEM permissões de rede/ambiente/escrita.
// Entrada (stdin): {"codigo": str, "csv": str, "nonce": str, "preludio": str}. Saída: uma linha JSON {"saida", "erro"}.
import { loadPyodide } from "npm:pyodide@0.28.3";

// Cópias guardadas antes do código do usuário: ele pode trocar JSON.stringify/console.log via `import js`.
const stringify = JSON.stringify.bind(JSON);
const escrever = Deno.stdout.writeSync.bind(Deno.stdout);
const codificar = new TextEncoder();

const pyodide = await loadPyodide({ packageCacheDir: "./pyodide_cache" });
await pyodide.loadPackage(["pandas"], { messageCallback: () => {}, errorCallback: () => {} });

if (Deno.args.includes("--preparar")) Deno.exit(0);

const { codigo, csv, nonce, preludio } = JSON.parse(await new Response(Deno.stdin.readable).text());
const saida: string[] = [];
pyodide.setStdout({ batched: (s: string) => saida.push(s) });
pyodide.setStderr({ batched: (s: string) => saida.push(s) });
pyodide.globals.set("_csv_texto", csv);

let erro: string | null = null;
try {
  await pyodide.runPythonAsync(preludio);
  await pyodide.runPythonAsync("import io, pandas as pd\ndf = pd.read_csv(io.StringIO(_csv_texto))");
  await pyodide.runPythonAsync(codigo);
} catch (e) {
  erro = String((e as Error).message ?? e).trim().split("\n").slice(-6).join("\n");
}
escrever(codificar.encode(stringify({ nonce, saida: saida.map((l) => l + "\n").join(""), erro }) + "\n"));
