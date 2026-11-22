import os
from pathlib import Path

import pytest

os.environ.setdefault("APP_SEM_DOTENV", "1")  # suíte hermética: o .env de quem roda não entra nos testes
from app import config, sessions  # noqa: E402


@pytest.fixture(autouse=True)
def pasta_sessoes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    destino = tmp_path / "sessions"
    monkeypatch.setattr(config, "SESSIONS_DIR", destino)
    sessions.SESSOES.clear()
    return destino
