"""Panel Streamlit para consultar y gestionar tendencias con clave administrativa."""
import os
from urllib.parse import quote

import pandas as pd
import requests
import streamlit as st

API = os.getenv("API_URL", "http://localhost:8000")
SOURCE = os.getenv("SOURCE_MODE", "wikipedia")

st.set_page_config(page_title="TrendWatch", layout="wide")
st.title("TrendWatch – detección temprana de tendencias")

try:
    response = requests.get(f"{API}/watchlist", timeout=10)
    response.raise_for_status()
    watchlist = response.json()
except (requests.RequestException, ValueError):
    st.error(f"No se puede consultar la API en {API}")
    st.stop()

with st.sidebar:
    key = st.text_input("Clave de administrador (solo para añadir o borrar)", type="password")
    new = st.text_input("Añadir término a la watchlist")
    if st.button("Añadir") and new:
        try:
            resp = requests.post(f"{API}/watchlist", json={"term": new}, headers={"X-API-Key": key}, timeout=10)
            if resp.status_code == 201:
                st.rerun()
            else:
                st.error(f"No se pudo añadir ({resp.status_code}): {resp.text[:150]}")
        except requests.RequestException:
            st.error("No se puede contactar con la API")
    if st.button("Ejecutar ingesta ahora"):
        try:
            resp = requests.post(f"{API}/ingest", headers={"X-API-Key": key}, timeout=120)
            if resp.ok:
                st.success("Ingesta finalizada")
                st.rerun()
            else:
                st.error(f"Error de ingesta ({resp.status_code}): {resp.text[:150]}")
        except requests.RequestException:
            st.error("No se puede contactar con la API")

if not watchlist:
    st.info("La watchlist está vacía. Añade un término en la barra lateral.")
    st.stop()

term = st.selectbox("Término", watchlist)
days = st.slider("Días", 14, 365, 90)
source = st.selectbox("Fuente", ["wikipedia", "demo", "pytrends", "google_trends_csv"], index=["wikipedia", "demo", "pytrends", "google_trends_csv"].index(SOURCE) if SOURCE in ["wikipedia", "demo", "pytrends", "google_trends_csv"] else 0)

try:
    resp = requests.get(f"{API}/trends/{quote(term, safe='')}", params={"days": days, "source": source}, timeout=10)
    resp.raise_for_status()
    points = resp.json()["points"]
    if points:
        df = pd.DataFrame(points).set_index("date")
        st.line_chart(df["value"])
    else:
        st.warning("Aún no hay datos. Ejecuta la ingesta en la barra lateral.")
    spike = requests.get(f"{API}/trends/{quote(term, safe='')}/spike", params={"source": source}, timeout=10)
    if spike.ok:
        s = spike.json()
        c1, c2, c3 = st.columns(3)
        c1.metric("¿Pico?", "SÍ" if s["is_spike"] else "No")
        c2.metric("z-score", f"{s['z_score']:.1f}")
        c3.metric("Crecimiento vs. media", f"{s['growth']:+.0%}")
    st.subheader("Ranking de nichos en ascenso")
    ranking = requests.get(f"{API}/rankings/rising", params={"source": source}, timeout=10)
    ranking.raise_for_status()
    st.dataframe(pd.DataFrame(ranking.json()))
except (requests.RequestException, ValueError, KeyError):
    st.error("No se pudieron cargar los datos de tendencias.")
