"""Dashboard mínimo: `streamlit run dashboard/app.py`."""
import os

import pandas as pd
import requests
import streamlit as st

API = os.getenv("API_URL", "http://localhost:8000")

st.set_page_config(page_title="TrendWatch", layout="wide")
st.title("TrendWatch – detección temprana de tendencias")

try:
    watchlist = requests.get(f"{API}/watchlist", timeout=10).json()
except requests.RequestException:
    st.error(f"No se puede conectar con la API en {API}")
    st.stop()

with st.sidebar:
    new = st.text_input("Añadir término a la watchlist")
    if st.button("Añadir") and new:
        requests.post(f"{API}/watchlist", json={"term": new}, timeout=10)
        st.rerun()

if not watchlist:
    st.info("La watchlist está vacía. Añade un término en la barra lateral.")
    st.stop()

term = st.selectbox("Término", watchlist)
days = st.slider("Días", 14, 365, 90)
points = requests.get(f"{API}/trends/{term}", params={"days": days}, timeout=10).json()["points"]
if points:
    df = pd.DataFrame(points).set_index("date")
    st.line_chart(df["value"])
else:
    st.warning("Aún no hay datos. El worker los recogerá en la próxima ejecución.")

spike = requests.get(f"{API}/trends/{term}/spike", timeout=10)
if spike.ok:
    s = spike.json()
    c1, c2, c3 = st.columns(3)
    c1.metric("¿Pico?", "SÍ" if s["is_spike"] else "No")
    c2.metric("z-score", f"{s['z_score']:.1f}")
    c3.metric("Crecimiento vs. media", f"{s['growth']:+.0%}")

st.subheader("Ranking de nichos en ascenso")
st.dataframe(pd.DataFrame(requests.get(f"{API}/rankings/rising", timeout=10).json()))
