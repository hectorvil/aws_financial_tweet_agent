import pandas as pd
import streamlit as st

from src.vector_db import VectorDB
from src.data_pipeline import add_labels
from src.bedrock_client import claude_chat


class FinancialTweetAgent:
    """Administra corpus, vector DB y consultas RAG."""

    def __init__(self):
        self.db = VectorDB()
        self.df = pd.DataFrame()

    # ─── Ingesta local ────────────────────────────────────────────
    def ingest(self, parquet_file):
        df = pd.read_parquet(parquet_file)
        if "clean" not in df:
            df = add_labels(df, skip_if_present=True)
        if "doc_id" not in df:
            df["doc_id"] = df.index.astype(str)
        self.db.add(df["doc_id"].tolist(), df["clean"].tolist())
        self.df = pd.concat([self.df, df], ignore_index=True)

    # ─── Ingesta desde S3 (NUEVO) ────────────────────────────────
    def ingest_s3_prefix(self, bucket: str, prefix: str = "tweets/"):
        import s3fs, pyarrow.parquet as pq, pyarrow as pa

        fs = s3fs.S3FileSystem()
        files = fs.glob(f"{bucket}/{prefix}**/*.parquet")
        if not files:
            st.warning("No se encontraron Parquets en S3.")
            return pd.DataFrame()

        tables = [pq.read_table(fs.open(f)) for f in files]
        df = pa.concat_tables(tables).to_pandas()
        if "doc_id" not in df:
            df["doc_id"] = df.index.astype(str)
        new = df[~df["doc_id"].isin(self.df.get("doc_id", []))]
        if not new.empty:
            self.db.add(new["doc_id"].tolist(), new["clean"].tolist())
            self.df = pd.concat([self.df, new], ignore_index=True)
        return new

    # ─── Pivot de sentimiento por ticker ─────────────────────────
    def pivot(self, min_mentions: int = 20):
        if self.df.empty:
            return pd.DataFrame()
        piv = (
            self.df.explode("tickers")
                   .query("tickers != ''")
                   .groupby(["tickers", "sentiment"]).size()
                   .unstack(fill_value=0)
                   .reset_index()
        )
        for col in ("positive", "neutral", "negative"):
            if col not in piv:
                piv[col] = 0
        piv["total"] = piv[["positive", "neutral", "negative"]].sum(axis=1)
        piv = piv[piv["total"] >= min_mentions]
        piv["pos_ratio"] = piv["positive"] / piv["total"]
        piv["neg_ratio"] = piv["negative"] / piv["total"]
        return piv

    # ─── RAG histórico ───────────────────────────────────────────
    def insight_hist(self, query: str, k: int = 30):
        docs = self.db.query(query, k)
        context = "\n".join(docs)
        prompt = f"Contexto:\n{context}\n\nPregunta: {query}"
        return claude_chat(prompt)
