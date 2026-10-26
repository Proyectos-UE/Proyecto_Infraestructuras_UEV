"""Crea configuración privada con secretos aleatorios, sin pisar datos existentes."""
import secrets
from pathlib import Path

raiz = Path(__file__).resolve().parents[1]
env = raiz / ".env"
if env.exists():
    print(".env ya existe; no se ha modificado")
else:
    plantilla = (raiz / ".env.example").read_text(encoding="utf-8")
    plantilla = plantilla.replace("API_KEY=\n", f"API_KEY={secrets.token_urlsafe(32)}\n")
    plantilla = plantilla.replace("POSTGRES_PASSWORD=\n", f"POSTGRES_PASSWORD={secrets.token_hex(24)}\n")
    env.write_text(plantilla, encoding="utf-8")
    env.chmod(0o600)
    print("Archivo .env creado con claves privadas aleatorias")
