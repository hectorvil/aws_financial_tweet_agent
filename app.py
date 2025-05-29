import os
import streamlit as st
from src.agent import FinancialTweetAgent
from src.plotting import build_sentiment_bar

# ──────────────────────────────────────────────────────────────────
# Configuración general de la página
# ──────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Financial-Tweet Agent", layout="wide", page_icon="💸")
st.title("💸 Financial-Tweet Agent")

# Bucket S3 para sincronizar
bucket_name = os.getenv("BUCKET_NAME")          # debe venir en variables de entorno

# Crea / recupera el agente en la sesión
if "agent" not in st.session_state:
    st.session_state.agent = FinancialTweetAgent()
agent: FinancialTweetAgent = st.session_state.agent

# ──────────────────────────────────────────────────────────────────
# Sidebar – carga de datos
# ──────────────────────────────────────────────────────────────────
st.sidebar.header("📥 Datos")

# 1) Sincronizar Parquets desde S3
if bucket_name and st.sidebar.button("🔄 Sincronizar S3"):
    with st.spinner("Descargando Parquets de S3…"):
        agent.ingest_s3_prefix(bucket_name)          # añade nuevos registros
    st.sidebar.success("✅ Datos sincronizados")

# 2) Subir archivo local (Parquet)
uploaded = st.sidebar.file_uploader("o sube un archivo .parquet", type="parquet")
if uploaded is not None:
    with st.spinner("Procesando Parquet…"):
        agent.ingest(uploaded)
    st.sidebar.success("✅ Archivo cargado")

# Si aún no hay datos, muestra aviso y detiene
if agent.df.empty:
    st.info("Aún no hay tweets cargados. Sincroniza S3 o sube un Parquet para continuar.")
    st.stop()

# ──────────────────────────────────────────────────────────────────
# Pestañas principales
# ──────────────────────────────────────────────────────────────────
tab_dash, tab_chat = st.tabs(["📊 Dashboard", "🤖 Chat histórico"])

# ------------------------------------------------------------------
# 1️⃣ Dashboard
# ------------------------------------------------------------------
with tab_dash:
    st.subheader("Sentimiento por ticker (único ticker: BBVA)")
    piv = agent.pivot(min_mentions=1)               # tendrá sólo “BBVA”
    if not piv.empty:
        st.plotly_chart(
            build_sentiment_bar(piv, metric="neg_ratio"),
            use_container_width=True
        )
    else:
        st.warning("No hay suficientes datos para graficar.")

    # ── Ratio fijo BBVA ───────────────────────────────────────────
    st.subheader("Sentimiento global «BBVA» (acumulado)")
    bbva = agent.df[agent.df["text"].str.contains("BBVA", case=False, na=False)]
    pos = (bbva["sentiment"] == "positive").sum()
    neg = (bbva["sentiment"] == "negative").sum()
    total = pos + neg or 1
    col1, col2 = st.columns(2)
    col1.metric("Ratio positivo", f"{pos/total:.1%}")
    col2.metric("Ratio negativo", f"{neg/total:.1%}")

    # ── Tendencia 7-días (imagen PNG generada por Lambda) ─────────
    st.subheader("📈 Tendencia 7 días – sentimiento «BBVA»")
    if bucket_name:
        img_url = f"https://{bucket_name}.s3.amazonaws.com/charts/sentiment_trend.png"
        st.image(img_url, caption="Se actualiza automáticamente cada 6 h")
    else:
        st.info("Define BUCKET_NAME en variables de entorno para cargar la gráfica.")

# ------------------------------------------------------------------
# 2️⃣ Chat histórico (RAG sobre corpus almacenado)
# ------------------------------------------------------------------
with tab_chat:
    st.subheader("Haz una pregunta sobre los tweets almacenados")
    query = st.text_input("Pregunta", placeholder="¿Qué opinan sobre la fortaleza financiera de BBVA?")
    if query:
        with st.spinner("Consultando corpus…"):
            answer = agent.insight_hist(query)
        st.write(answer)
