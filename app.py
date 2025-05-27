import os
import streamlit as st
import pandas as pd
from src.agent import FinancialTweetAgent
from src.plotting import build_sentiment_bar

# ── Config inicial ────────────────────────────────────────────────
st.set_page_config(page_title="Financial-Tweet Agent", layout="wide")
st.title("Financial-Tweet Agent")

# ── Claves necesarias ────────────────────────────────────────────
aws_region  = os.getenv("AWS_REGION")          # para Bedrock
twitter_key = os.getenv("TWITTER_BEARER")

if not aws_region:
    st.warning("AWS_REGION no está configurada: Bedrock podría fallar.")
if not twitter_key:
    st.warning("TWITTER_BEARER no configurada. La búsqueda en vivo no funcionará.")

# ── Crea el agente (solo una vez) ────────────────────────────────
if "agent" not in st.session_state:
    st.session_state.agent = FinancialTweetAgent()
agent: FinancialTweetAgent = st.session_state.agent

# ── Sidebar: carga de parquet ────────────────────────────────────
st.sidebar.header("Cargar archivo")
parquet_file = st.sidebar.file_uploader("Sube un archivo .parquet", type="parquet")

if parquet_file and "processed" not in st.session_state:
    st.sidebar.success("✅ Archivo subido")
    with st.spinner("🧠 Procesando: limpiando, clasificando, generando embeddings..."):
        agent.ingest(parquet_file)
    st.session_state.processed = True

elif "processed" in st.session_state:
    st.sidebar.info("Usando dataset ya cargado en memoria")

else:
    st.stop()               # espera a que suban un archivo

# ── Tabs principales ─────────────────────────────────────────────
tab1, tab2, tab3 = st.tabs(["🤖 Chat histórico", "⚡ Live", "📊 Dashboard"])

# ── Tab 1: Chat histórico (Bedrock RAG) ──────────────────────────
with tab1:
    st.subheader("Haz una pregunta sobre el corpus histórico")
    question = st.text_input("Pregunta (ej. ¿Qué se dice de NVIDIA?)")
    if question:
        with st.spinner("🧠 Pensando..."):
            answer = agent.insight_hist(question)
            st.success(answer)

# ── Tab 2: Live Search ───────────────────────────────────────────
with tab2:
    st.subheader("🔍 Buscar tweets en vivo")
    live_query = st.text_input("Consulta live (ej. TSLA OR NVDA)")
    if live_query:
        if twitter_key:
            with st.spinner("Buscando tweets recientes..."):
                live_df = agent.live_search(live_query)
            if not live_df.empty:
                st.dataframe(live_df[["text", "topic", "sentiment"]])
            else:
                st.info("No se encontraron tweets en vivo.")
        else:
            st.error("No tienes TWITTER_BEARER configurado.")

# ── Tab 3: Dashboard ─────────────────────────────────────────────
with tab3:
    st.subheader("Análisis de sentimiento por ticker")

    # Recuento rápido de menciones
    with st.expander("Ver recuento de menciones por ticker"):
        ticker_counts = (
            agent.df.explode("tickers")
                    .dropna(subset=["tickers"])
                    .value_counts("tickers")
        )
        top_n = st.slider("Top-N", 5, 50, 20, key="topn_slider")
        st.dataframe(ticker_counts.head(top_n), use_container_width=True)

    # Gráfica de barras
    min_m  = st.slider("Mínimo de menciones por ticker", 10, 300, 50, 10)
    metric = st.selectbox("Métrica a mostrar", ["neg_ratio", "pos_ratio", "total"])

    piv = agent.pivot(min_m)
    if not piv.empty:
        st.plotly_chart(build_sentiment_bar(piv, metric), use_container_width=True)
    else:
        st.warning("No hay suficientes datos para mostrar.")
