"""Configuração lida do ambiente (.env via python-dotenv). Nunca registre a chave."""
import os
from pathlib import Path

from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parent.parent
load_dotenv(RAIZ / ".env")

LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_BASE_URL = os.environ.get(
    "LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/"
)
LLM_MODEL = os.environ.get("LLM_MODEL", "gemini-3.5-flash-lite")

DATA_DIR = RAIZ / "data"
SESSIONS_DIR = DATA_DIR / "sessions"
SANDBOX_DIR = RAIZ / "sandbox"

# Só para teste local e CI: libera Postgres em endereço interno (sem isso, só IP público: evita SSRF).
PG_PERMITIR_INTERNO = os.environ.get("PG_PERMITIR_INTERNO") == "1"
