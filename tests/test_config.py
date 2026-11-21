import os
import subprocess
import sys
from pathlib import Path

from app import config

RAIZ = Path(__file__).resolve().parent.parent


def _sessions_dir_num_processo_novo(env_extra: dict[str, str], tmp: Path) -> str:
    """Importa o config num subprocesso: recarregar o módulo compartilhado deixaria o estado vazar para outros testes."""
    env = {k: v for k, v in os.environ.items() if k != "SESSIONS_DIR"} | env_extra
    r = subprocess.run([sys.executable, "-c", "from app import config; print(config.SESSIONS_DIR)"],
                       cwd=RAIZ, env=env, capture_output=True, text=True, check=True)
    return r.stdout.strip()


def test_sessions_dir_padrao_e_override_por_ambiente(tmp_path) -> None:
    assert _sessions_dir_num_processo_novo({}, tmp_path) == str(config.DATA_DIR / "sessions")
    assert _sessions_dir_num_processo_novo({"SESSIONS_DIR": str(tmp_path)}, tmp_path) == str(tmp_path)
