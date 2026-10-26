"""Configuración local y para Docker. Las claves reales no se incluyen en Git."""
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/trendwatch.db")
API_KEY = os.getenv("API_KEY", "")
WIKI_USER_AGENT = os.getenv(
    "WIKI_USER_AGENT",
    "TrendWatch/0.1 (https://github.com/Proyectos-UE/Proyecto_Infraestructuras_6_7)",
)
WIKI_PROJECT = os.getenv("WIKI_PROJECT", "es.wikipedia")
SOURCE_MODE = os.getenv("SOURCE_MODE", "wikipedia").lower()
DEMO_SOURCE_URL = os.getenv("DEMO_SOURCE_URL", "http://127.0.0.1:8001/datos")
POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "86400"))
HISTORY_DAYS = int(os.getenv("HISTORY_DAYS", "90"))
ENABLE_PYTRENDS = os.getenv("ENABLE_PYTRENDS", "false").lower() == "true"
