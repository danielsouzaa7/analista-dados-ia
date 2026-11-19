from pathlib import Path

import pytest

from app import config, sessions


@pytest.fixture(autouse=True)
def pasta_sessoes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    destino = tmp_path / "sessions"
    monkeypatch.setattr(config, "SESSIONS_DIR", destino)
    sessions.SESSOES.clear()
    return destino
