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
from functools import lru_cache

from langchain_ollama import OllamaEmbeddings

OLLAMA_EMBEDDING_MODEL = os.environ.get("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text")
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")


@lru_cache(maxsize=1)
def _get_embedder() -> OllamaEmbeddings:
    return OllamaEmbeddings(model=OLLAMA_EMBEDDING_MODEL, base_url=OLLAMA_BASE_URL)


def embed_document(text: str) -> list[float]:
    return _get_embedder().embed_query(f"search_document: {text}")


def embed_query(text: str) -> list[float]:
    return _get_embedder().embed_query(f"search_query: {text}")
