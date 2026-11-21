import importlib

from app import config


def test_sessions_dir_padrao_e_override_por_ambiente(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("SESSIONS_DIR", raising=False)
    assert importlib.reload(config).SESSIONS_DIR == config.DATA_DIR / "sessions"
    monkeypatch.setenv("SESSIONS_DIR", str(tmp_path))
    try:
        assert importlib.reload(config).SESSIONS_DIR == tmp_path
    finally:
        monkeypatch.delenv("SESSIONS_DIR")
        importlib.reload(config)
