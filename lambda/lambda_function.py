"""
Lambda ingest: busca tweets sobre «BBVA», clasifica sentimiento
con Claude-3 Sonnet en Amazon Bedrock y guarda un Parquet NUEVO
en s3://<BUCKET_NAME>/tweets/… (no se sobrescribe nada).
"""

import os, json, time, uuid, tempfile, datetime as dt
import boto3, botocore
import pandas as pd
import pyarrow as pa, pyarrow.parquet as pq
import tweepy

# ── Configuración ─────────────────────────────────────────────────
BUCKET = os.environ["BUCKET_NAME"]

TW = tweepy.Client(
    bearer_token=os.environ["TWITTER_BEARER"],
    wait_on_rate_limit=True
)

BRUNTIME = boto3.client("bedrock-runtime", region_name="us-east-1")
MODEL_ID = "anthropic.claude-3-sonnet-20240229-v1:0"

FIN_ACCOUNTS = [
    "@Reuters", "@Bloomberg", "@CNBC", "@FT", "@WSJmarkets"
]

FUTBOL_TERMS = [
    "liga", "fútbol", "futbol", "jornada", "torneo", "balón", "balon", "penal",
    "gol", "partido", "club", "afición", "equipo", "árbitro", "jugador", "estadio",
    "guard1anes", "apertura", "clausura", "liga mx", "futbolista", "selección",
    "pumas", "lainez", "reimers", "tigres", "américa", "toluca",
    "monterrey", "chivas", "atlas", "xolos", "santos", "necaxa", "león", "cruz azul"
]

APP_TERMS = [
    "app", "aplicación", "no abre", "no me deja", "error", "fallando",
    "se cerró", "no puedo entrar", "pantalla blanca", "no inicia", "bug",
    "actualicé", "crashea", "no funciona", "se traba", "no responde",
    "login", "contrasena", "transferencia", "cierre inesperado"
]

# ── Helpers ───────────────────────────────────────────────────────
def is_futbol_related(text: str) -> bool:
    text = text.lower()
    return any(term in text for term in FUTBOL_TERMS)

def is_app_related(text: str) -> bool:
    text = text.lower()
    return any(term in text for term in APP_TERMS)

def search_tweets(query: str, n: int):
    resp = TW.search_recent_tweets(
        query=query,
        max_results=min(n, 30),
        tweet_fields=["id", "text", "created_at", "author_id"]
    )
    return resp.data or []

def bedrock_sentiment(text: str, max_retries: int = 5) -> str:
    prompt = (
        "Clasifica el **sentimiento** del siguiente tweet en español como "
        "'positive', 'neutral' o 'negative'. Devuelve solo esa palabra.\n\n"
        f"Tweet: «{text.replace(chr(10), ' ')}»\nSentiment:"
    )

    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 10,
        "temperature": 0
    })

    for attempt in range(max_retries):
        try:
            resp = BRUNTIME.invoke_model(
                modelId=MODEL_ID,
                body=body,
                accept="application/json",
                contentType="application/json"
            )
            result = json.loads(resp["body"].read())
            return result["content"][0]["text"].strip().split()[0].lower()
        except botocore.exceptions.ClientError as e:
            if e.response["Error"]["Code"] == "ThrottlingException" and attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
            raise

# ── Lambda handler ───────────────────────────────────────────────
def lambda_handler(event, context):
    # 1) Búsqueda principal
    acct_q = " OR ".join([f"from:{a[1:]}" for a in FIN_ACCOUNTS])
    q_news = f'"BBVA" ({acct_q}) -is:retweet lang:es'
    tweets = search_tweets(q_news, 30)

    # 2) Fallback si no hay resultados
    if not tweets:
        tweets = search_tweets('"BBVA" -is:retweet lang:es', 30)
    if not tweets:
        return {"status": "NO_DATA"}

    # 3) Procesamiento: etiqueta y clasifica
    rows = []
    for tw in tweets:
        futbol_flag = is_futbol_related(tw.text)
        app_flag    = is_app_related(tw.text)
        sentiment   = None if futbol_flag else bedrock_sentiment(tw.text)

        rows.append({
            "tweet_id"  : tw.id,
            "author_id" : tw.author_id,
            "created_at": tw.created_at,
            "text"      : tw.text,
            "sentiment" : sentiment,
            "tickers"   : ["BBVA"],
            "source"    : "news" if tw.text.startswith(tuple(FIN_ACCOUNTS)) else "twitter",
            "is_futbol" : futbol_flag,
            "is_app"    : app_flag
        })

    df = pd.DataFrame(rows)

    # 4) Escribe Parquet con timestamp y UUID
    now = dt.datetime.utcnow()
    ts = now.strftime("%Y%m%dT%H%M%S")
    uid = uuid.uuid4().hex[:8]
    key = (
        f"tweets/year={now.year}/month={now.month:02d}/"
        f"day={now.day:02d}/hour={now.hour:02d}/"
        f"batch_{ts}_{uid}.parquet"
    )

    tmp = tempfile.NamedTemporaryFile(suffix=".parquet", delete=False)
    pq.write_table(pa.Table.from_pandas(df), tmp.name)
    boto3.client("s3").upload_file(tmp.name, BUCKET, key)

    return {
        "status": "OK",
        "rows": int(len(df)),
        "classified": int(df["sentiment"].notna().sum()),
        "app_tweets": int(df["is_app"].sum()),
        "futbol_tweets": int(df["is_futbol"].sum()),
        "parquet_key": key
    }
