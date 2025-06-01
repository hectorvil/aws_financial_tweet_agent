import os
import pandas as pd
import pyarrow.parquet as pq
import matplotlib.pyplot as plt
import matplotlib
import boto3
import s3fs
from io import BytesIO
from datetime import datetime
import time

os.environ["MPLCONFIGDIR"] = "/tmp"
matplotlib.use("Agg")

S3 = boto3.client("s3")
fs = s3fs.S3FileSystem()
BUCKET = os.environ["BUCKET_NAME"]

# ── Listar todos los archivos parquet ─────────────────────────────
def list_all_parquet_keys(bucket, prefix):
    paginator = boto3.client("s3").get_paginator("list_objects_v2")
    page_iterator = paginator.paginate(Bucket=bucket, Prefix=prefix)

    keys = []
    for page in page_iterator:
        for obj in page.get("Contents", []):
            if obj["Key"].endswith(".parquet"):
                keys.append(obj["Key"])
    return keys

# ── Cargar últimos 30 archivos ───────────────────────────────────
def load_all_tweets():
    keys = list_all_parquet_keys(BUCKET, prefix="tweets/")
    print(f"Total .parquet encontrados: {len(keys)}")
    keys = sorted(keys)[-30:]

    tables = []
    for k in keys:
        try:
            with fs.open(f"s3://{BUCKET}/{k}") as f:
                tables.append(pq.read_table(f))
        except Exception as e:
            print(f"Error leyendo {k}: {e}")
    if not tables:
        return pd.DataFrame()
    return pd.concat([t.to_pandas() for t in tables], ignore_index=True)

# ── Función para graficar tendencias ─────────────────────────────
def build_trend_plot(df, filename):
    if df.empty:
        print(f"Sin datos para {filename}")
        return None

    df["ts_hour"] = pd.to_datetime(df["created_at"]).dt.floor("H")
    grouped = (
        df.groupby(["ts_hour", "sentiment"])
          .size()
          .unstack(fill_value=0)
          .reindex(columns=["positive", "neutral", "negative"], fill_value=0)
          .sort_index()
    )

    fig, ax = plt.subplots(figsize=(8, 4))
    grouped.plot(ax=ax)
    ax.set_title(f"Tendencia de sentimiento: {filename}")
    ax.set_ylabel("Cantidad de tweets")
    ax.set_xlabel("Hora UTC")
    ax.legend(["Positive", "Neutral", "Negative"], loc="upper left")
    fig.tight_layout()

    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=160)
    plt.close(fig)
    buf.seek(0)

    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
    key = f"charts/{filename}_{timestamp}.png"

    S3.put_object(
        Bucket=BUCKET,
        Key=key,
        Body=buf.getvalue(),
        ContentType="image/png"
    )

    print(f"Gráfico guardado: {key}")
    return key

# ── Lambda handler principal ─────────────────────────────────────
def lambda_handler(event, context):
    t0 = time.time()
    df = load_all_tweets()
    print(f"Datos cargados: {len(df)} filas")

    if df.empty or "sentiment" not in df.columns:
        return {"status": "NO_DATA"}

    df = df[df["sentiment"].isin(["positive", "neutral", "negative"])]

    # ── Gráfica general (excluye is_futbol=True si existe) ────────
    if "is_futbol" in df.columns:
        df_general = df[df["is_futbol"] != True]
    else:
        df_general = df.copy()

    out_general = build_trend_plot(df_general, "general")

    # ── Gráfica app (solo si is_app está disponible) ──────────────
    out_app = None
    if "is_app" in df.columns:
        df_app = df[df["is_app"] == True]
        out_app = build_trend_plot(df_app, "app")

    return {
        "status": "OK",
        "records_total": int(len(df)),
        "records_general": int(len(df_general)),
        "records_app": int(len(df_app)) if out_app else 0,
        "charts": [out for out in [out_general, out_app] if out]
    }
