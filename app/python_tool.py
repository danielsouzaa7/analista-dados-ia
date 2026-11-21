"""Roda o Python da IA em Pyodide dentro do Deno, sem rede, sem ambiente e sem leitura fora do cache."""
import json
import os
import secrets
import shutil
import subprocess
import sys
import threading
import time

from app import config

PRELUDIO = (config.SANDBOX_DIR / "preludio.py").read_text(encoding="utf-8")
MAX_CHARS = 10_000
MAX_STDOUT_BYTES = 1024 * 1024  # teto do que lemos do processo Deno
SEMAFORO = threading.BoundedSemaphore(2)  # no máximo 2 sandboxes ao mesmo tempo


def _env_minimo() -> dict[str, str]:
    # Nunca repasse os.environ: lá está a LLM_API_KEY.
    chaves = ["PATH", "DENO_DIR", "SYSTEMROOT", "LOCALAPPDATA", "USERPROFILE", "HOME"]
    return {k: os.environ[k] for k in chaves if k in os.environ}


def _matar(proc: subprocess.Popen) -> None:
    if sys.platform == "win32":  # /T mata a árvore inteira
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
    else:
        proc.kill()


def _ler_saida(proc: subprocess.Popen, buf: bytearray, estado: dict) -> None:
    while chunk := proc.stdout.read(65536):
        buf.extend(chunk)
        if len(buf) > MAX_STDOUT_BYTES:
            estado["estourou"] = True
            _matar(proc)
            return


def _escrever_entrada(proc: subprocess.Popen, dados: bytes) -> None:
    try:
        proc.stdin.write(dados)
        proc.stdin.close()
    except OSError:  # processo morreu antes de ler a entrada
        pass


def _executar(cmd: list[str], dados: bytes, timeout: float) -> tuple[bytes, dict]:
    proc = subprocess.Popen(cmd, cwd=config.SANDBOX_DIR, env=_env_minimo(), stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    # RLIMIT_AS foi testado no Linux e quebra o V8 (reserva muito espaço virtual): o teto de memória vem do contêiner.
    buf, estado = bytearray(), {"estourou": False, "timeout": False}
    leitor = threading.Thread(target=_ler_saida, args=(proc, buf, estado), daemon=True)
    escritor = threading.Thread(target=_escrever_entrada, args=(proc, dados), daemon=True)
    prazo = time.monotonic() + timeout
    leitor.start()
    escritor.start()
    leitor.join(timeout)
    if leitor.is_alive():
        estado["timeout"] = True
        _matar(proc)
        leitor.join()
    try:  # o stdout pode fechar com o processo ainda vivo
        proc.wait(timeout=max(0.0, prazo - time.monotonic()))
    except subprocess.TimeoutExpired:
        estado["timeout"] = True
        _matar(proc)
        proc.wait()
    return bytes(buf), estado


def rodar(codigo: str, csv: str, timeout: float = 30) -> dict:
    deno = shutil.which("deno")
    if deno is None:
        return {"saida": "", "erro": "O ambiente de execução Python (Deno) não está disponível."}
    sandbox = config.SANDBOX_DIR
    cmd = [
        deno, "run", "--no-prompt", "--cached-only",
        f"--allow-read={sandbox / 'node_modules'},{sandbox / 'pyodide_cache'}",
        "--v8-flags=--max-old-space-size=512", "runner.ts",
    ]
    nonce = secrets.token_hex(16)  # o código do usuário não o conhece, então não forja a saída
    dados = json.dumps({"codigo": codigo, "csv": csv, "nonce": nonce, "preludio": PRELUDIO}).encode()
    if not SEMAFORO.acquire(timeout=timeout):
        return {"saida": "", "erro": "O ambiente de execução está ocupado. Tente de novo."}
    try:
        saida, estado = _executar(cmd, dados, timeout)
    finally:
        SEMAFORO.release()
    if estado["timeout"]:
        return {"saida": "", "erro": "Tempo limite de 30 s excedido."}
    if estado["estourou"]:
        return {"saida": "", "erro": "Saída grande demais (mais de 1 MB); o código foi interrompido."}
    for linha in reversed(saida.decode("utf-8", errors="replace").splitlines()):
        try:
            r = json.loads(linha)
        except json.JSONDecodeError:
            continue
        if isinstance(r, dict) and r.get("nonce") == nonce:
            return {"saida": (r.get("saida") or "")[:MAX_CHARS], "erro": r.get("erro") or None}
    return {"saida": "", "erro": "Falha ao executar o código Python."}
