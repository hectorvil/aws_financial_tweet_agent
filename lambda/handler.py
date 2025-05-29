"""
Lambda ingest: busca tweets «BBVA», clasifica con Amazon Bedrock,
guarda Parquet y sobreescribe un PNG de tendencia de sentimiento
en s3://<BUCKET_NAME>/charts/sentiment_trend.png
"""

import os, json, boto3, tempfile, datetime as dt
import pandas as pd, pyarrow as pa, pyarrow.parquet as pq
import tweepy, s3fs

# ─── Configuración ─────────────────────────────────────────────────
BUCKET      = os.environ["BUCKET_NAME"]
TW          = tweepy.Client(bearer_token=os.environ["TWITTER_BEARER"],
                            wait_on_rate_limit=True)
BRUNTIME    = boto3.client("bedrock-runtime")
S3          = boto3.client("s3")
MODEL_ID    = "amazon.titan-text-express-v1"

FIN_ACCOUNTS = ["@Reuters", "@Bloomberg", "@CNBC", "@FT", "@WSJmarkets"]

# ─── Helpers sentiment y búsqueda  ────────────────────────────────
def search_tweets(query: str, n: int):
    resp = TW.search_recent_tweets(
        query=query,
        max_results=min(n, 100),
        tweet_fields=["id", "text", "created_at", "author_id"]
    )
    return resp.data or []

def bedrock_sentiment(text: str) -> str:
    prompt = (
        "Clasifica el siguiente tweet en español "
        "como 'positive', 'neutral' o 'negative'. "
        "Devuelve solo esa palabra.\n\nTweet: «"
        + text.replace('\n', ' ') + "»\nSentiment:"
    )
    body = json.dumps({
        "inputText": prompt,
        "textGenerationConfig": {"maxTokenCount": 10, "temperature": 0}
    })
    out = BRUNTIME.invoke_model(
        modelId=MODEL_ID,
        body=body,
        accept="application/json",
        contentType="application/json"
    )
    return json.loads(out["body"].read())["results"][0]["outputText"] \
             .strip().split()[0].lower()

# ─── Helper para gráfico de tendencia  ────────────────────────────
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from io import BytesIO

def build_trend_plot(df_all: pd.DataFrame) -> bytes:
    df_all["ts_hour"] = pd.to_datetime(df_all["created_at"]).dt.floor("H")
    piv = (
        df_all.groupby(["ts_hour", "sentiment"])
              .size()
              .unstack(fill_value=0)
              .sort_index()
    )
    for col in ("positive", "neutral", "negative"):
        if col not in piv:
            piv[col] = 0
    piv["total"] = piv.sum(axis=1).replace(0, 1)
    for col in ("positive", "neutral", "negative"):
        piv[col] = piv[col] / piv["total"]

    fig, ax = plt.subplots(figsize=(8, 3))
    piv[["positive", "neutral", "negative"]].plot(ax=ax)
    ax.set_ylabel("Ratio")
    ax.set_xlabel("Hora UTC")
    ax.set_title("Tendencia sentimiento «BBVA» (últimos 7 días)")
    ax.legend(["Positivo", "Neutral", "Negativo"], loc="upper left")
    fig.tight_layout()

    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=160)
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()

# ─── Lambda handler ───────────────────────────────────────────────
def handler(event, context):
    # 1) Busca noticias en cuentas financieras
    acct_q = " OR ".join([f"from:{a[1:]}" for a in FIN_ACCOUNTS])
    q_news = f'"BBVA" ({acct_q}) -is:retweet lang:es'
    tweets = search_tweets(q_news, 100)

    # 2) Fallback global (máx. 30)
    if not tweets:
        tweets = search_tweets('"BBVA" -is:retweet lang:es', 30)
    if not tweets:
        return {"status": "NO_DATA"}

    # 3) Construye DataFrame y clasifica con Bedrock
    rows = []
    for tw in tweets:
        rows.append({
            "tweet_id"  : tw.id,
            "author_id" : tw.author_id,
            "created_at": tw.created_at,
            "text"      : tw.text,
            "sentiment" : bedrock_sentiment(tw.text),
            "source"    : "news" if f"@{tw.author_id}" in FIN_ACCOUNTS else "twitter"
        })
    df = pd.DataFrame(rows)

    # 4) Guarda Parquet particionado year/month/day/hour
    now = dt.datetime.utcnow()
    key = (f"tweets/year={now.year}/month={now.month:02d}/"
           f"day={now.day:02d}/hour={now.hour:02d}/batch.parquet")
    tmp = tempfile.NamedTemporaryFile(suffix=".parquet", delete=False)
    pq.write_table(pa.Table.from_pandas(df), tmp.name)
    S3.upload_file(tmp.name, BUCKET, key)

    # 5) Genera / sobrescribe gráfico de tendencia (últimos 7 días)
    fs  = s3fs.S3FileSystem()
    objs = S3.list_objects_v2(Bucket=BUCKET, Prefix="tweets/", MaxKeys=700)\
             .get("Contents", [])
    parquet_keys = [o["Key"] for o in objs if o["Key"].endswith(".parquet")]
    if parquet_keys:
        tables = [pq.read_table(fs.open(f"s3://{BUCKET}/{k}"))
                  for k in parquet_keys]
        hist_df = pa.concat_tables(tables).to_pandas()
        png = build_trend_plot(hist_df)
        S3.put_object(
            Bucket=BUCKET,
            Key="charts/sentiment_trend.png",
            Body=png,
            ContentType="image/png"
        )

    return {"status": "OK", "rows": len(df), "parquet_key": key}
