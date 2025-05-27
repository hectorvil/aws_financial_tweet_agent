import streamlit as st
from chromadb import PersistentClient
from sentence_transformers import SentenceTransformer
from src.bedrock_client import titan_embed          # ← Bedrock Titan

# ───────────────────────────────────────────────────────────────────
# 1) Modelo local (backup, CPU)
# ───────────────────────────────────────────────────────────────────
@st.cache_resource
def load_embedder() -> SentenceTransformer:
    # Mini-LM en CPU como plan B
    return SentenceTransformer("all-MiniLM-L6-v2", device="cpu")


class VectorDB:
    def __init__(self, path: str = "chroma_db"):
        self.client = PersistentClient(path)
        self.collection = self.client.get_or_create_collection(
            name="tweets", metadata={"hnsw:space": "cosine"}
        )
        self.embedder = load_embedder()   # por si Titan falla

    # ── helper deduplicación ───────────────────────────────────────
    def _filter_new(self, ids, texts, embeds):
        existing = set(self.collection.get(ids=ids, include=[])["ids"])
        out_ids, out_txt, out_emb = [], [], []
        for i, t, e in zip(ids, texts, embeds):
            if i not in existing:
                out_ids.append(i), out_txt.append(t), out_emb.append(e)
        return out_ids, out_txt, out_emb

    # ── Añadir documentos ──────────────────────────────────────────
    def add(self, ids, texts, embeddings=None):
        """
        Inserta documentos:
        • Si embeddings==None → llama Titan Embed (Bedrock).
        • Deduplica por doc_id para evitar duplicados.
        """
        if embeddings is None:
            try:
                embeddings = titan_embed(texts)
            except Exception as e:
                st.warning(f"Titan Embed falló ({e}); uso Mini-LM local.")
                embeddings = self.embedder.encode(texts, batch_size=64, device="cpu").tolist()

        ids, texts, embeddings = self._filter_new(ids, texts, embeddings)
        if ids:
            self.collection.add(ids=ids, documents=texts, embeddings=embeddings)

    # ── Consulta semántica ─────────────────────────────────────────
    def query(self, query_text: str, k: int = 30):
        try:
            q_emb = titan_embed([query_text])
        except Exception:
            q_emb = self.embedder.encode([query_text], device="cpu").tolist()

        res = self.collection.query(query_embeddings=q_emb, n_results=k)
        return res["documents"][0]
