import pandas as pd
import streamlit as st

from src.vector_db import VectorDB
from src.data_pipeline import add_labels, clean
from src.bedrock_client import claude_chat          # ← Bedrock Claude-3

class FinancialTweetAgent:
    """
    Orquesta la ingesta de Parquet, gestiona la base vectorial ChromaDB
    y expone utilidades para chat histórico, live search y dashboard.
    """

    def __init__(self, model: str = "anthropic.claude-3-sonnet-20240229-v1:0"):
        self.model = model            # se conserva por si quisieras cambiarlo
        self.db = VectorDB()
        self.df = pd.DataFrame()

    # ────────────────────────────────────────────────────────────────
    # Ingesta única por sesión
    # ────────────────────────────────────────────────────────────────
    def ingest(self, parquet_file) -> None:
        """
        Carga un Parquet y lo añade a la base vectorial.
        - Si ya trae clean, sentiment, tickers y embedding, no recalcula.
        - Si falta algo, lo calcula en CPU (puede tardar).
        """
        df = pd.read_parquet(parquet_file)

        required = {"clean", "sentiment", "tickers", "embedding"}
        incomplete = required.difference(df.columns)

        if incomplete:
            st.info(
                f"El archivo no contiene {', '.join(incomplete)}. "
                "Se calcularán ahora (puede tardar)."
            )
            df = add_labels(df, skip_if_present=True)
            has_embed = False
        else:
            has_embed = True

        if "doc_id" not in df:
            df["doc_id"] = df.index.astype(str)

        if has_embed:
            self.db.add(
                ids=df["doc_id"].tolist(),
                texts=df["clean"].tolist(),
                embeddings=df["embedding"].tolist(),
            )
        else:
            self.db.add(df["doc_id"].tolist(), df["clean"].tolist())

        self.df = pd.concat([self.df, df], ignore_index=True)
        st.success(f"✅ Ingesta completada: {len(df):,} documentos añadidos.")

    # ────────────────────────────────────────────────────────────────
    # Dashboard helper
    # ────────────────────────────────────────────────────────────────
    def pivot(self, min_m: int = 20) -> pd.DataFrame:
        """Devuelve un DataFrame agregado por ticker y sentimiento."""
        if self.df.empty or "tickers" not in self.df:
            return pd.DataFrame()

        piv = (
            self.df.explode("tickers")
            .query("tickers != ''")
            .groupby(["tickers", "sentiment"])
            .size()
            .unstack(fill_value=0)
            .reset_index()
        )

        for col in ("positive", "neutral", "negative"):
            if col not in piv:
                piv[col] = 0

        piv["total"] = piv[["positive", "neutral", "negative"]].sum(axis=1)
        piv = piv[piv["total"] >= min_m]
        piv["pos_ratio"] = piv["positive"] / piv["total"]
        piv["neg_ratio"] = piv["negative"] / piv["total"]
        return piv.sort_values("neg_ratio", ascending=False)

    # ────────────────────────────────────────────────────────────────
    # Chat histórico (RAG sobre corpus)
    # ────────────────────────────────────────────────────────────────
    def insight_hist(self, query: str, k: int = 30) -> str:
        docs = self.db.query(query, k)

        subset = self.df[self.df["clean"].isin(docs)]
        pos = (subset["sentiment"] == "positive").sum()
        neu = (subset["sentiment"] == "neutral").sum()
        neg = (subset["sentiment"] == "negative").sum()
        total = max(pos + neu + neg, 1)
        ratios = f"(+ {pos/total:.2f} | = {neu/total:.2f} | − {neg/total:.2f})"

        context = "\n".join(t[:280] for t in docs)
        prompt = f"""
Usa SOLO el contexto siguiente para responder.
Contexto:
{context}

Pregunta: {query}
Responde en español de forma clara, cita tweet_id cuando corresponda y menciona si predomina un tono positivo o negativo.
""".strip()

        answer = claude_chat(prompt)
        return f"{answer}\n\n📊 Sentiment {ratios}"

    # ────────────────────────────────────────────────────────────────
    # Live search (Twitter) + ingest
    # ────────────────────────────────────────────────────────────────
    def live_search(self, query: str, n: int = 30) -> pd.DataFrame:
        from src.twitter_live import search

        live = pd.DataFrame(search(query, n=n))
        if live.empty:
            return pd.DataFrame()

        if "doc_id" not in live:
            live["doc_id"] = live.index.astype(str)

        live = add_labels(live)  # siempre etiqueta porque viene sin procesar
        self.db.add(live["doc_id"].tolist(), live["clean"].tolist())
        self.df = pd.concat([self.df, live], ignore_index=True)
        return live

    def insight_live(self, query: str, n: int = 30) -> str:
        recent = self.live_search(query, n=n)
        if not recent.empty:
            context = "\n".join(recent["clean"].tolist()[:30])
        else:
            context = "\n".join(self.db.query(query, k=30))

        prompt = f"""
Con base en el contexto, responde a la pregunta.
Contexto:
{context}

Pregunta: {query}
""".strip()

        return claude_chat(prompt)
