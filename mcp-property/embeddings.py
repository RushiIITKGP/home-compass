"""
Local embeddings via Ollama (nomic-embed-text, 768 dims). Documents and
queries get different task prefixes — asymmetric retrieval, so a short
vague query lands near the listings that SATISFY it, not near other
query-like texts.

Changing the embedding model invalidates every stored vector:
run db/reset_embeddings.py, then backfill_embeddings.py and
compliance/ingest_rules.py.
"""

from __future__ import annotations

import os

from langchain_ollama import OllamaEmbeddings

OLLAMA_EMBEDDING_MODEL = os.environ.get("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text")
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")

_embedder: OllamaEmbeddings | None = None


def _get_embedder() -> OllamaEmbeddings:
    global _embedder
    if _embedder is None:
        _embedder = OllamaEmbeddings(model=OLLAMA_EMBEDDING_MODEL, base_url=OLLAMA_BASE_URL)
    return _embedder


def embed_document(text: str) -> list[float]:
    return _get_embedder().embed_query(f"search_document: {text}")


def embed_query(text: str) -> list[float]:
    return _get_embedder().embed_query(f"search_query: {text}")
