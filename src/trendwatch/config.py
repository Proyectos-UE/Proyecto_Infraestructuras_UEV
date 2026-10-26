"""Configuración leída de variables de entorno (ver .env.example)."""
import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/trendwatch.db")
WIKI_USER_AGENT = os.getenv(
    "WIKI_USER_AGENT",
    "TrendWatch/0.1 (proyecto universitario; contacto: cambia_este_email@ejemplo.com)",
)
WIKI_PROJECT = os.getenv("WIKI_PROJECT", "es.wikipedia")
POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "86400"))
HISTORY_DAYS = int(os.getenv("HISTORY_DAYS", "90"))
ENABLE_PYTRENDS = os.getenv("ENABLE_PYTRENDS", "false").lower() == "true"
