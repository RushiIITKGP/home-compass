"""
Drops and recreates the two tables that store vectors — required when
the embedding model (and therefore vector dimension) changes, e.g. the
Gemini (1536) -> Ollama nomic-embed-text (768) migration.

Postgres won't alter a vector column's dimension in place, and old
vectors would be meaningless in the new model's space anyway — vectors
from different models aren't comparable, even at the same dimension.
So: drop, recreate at the new EMBEDDING_DIM, re-embed.

    python db/reset_embeddings.py
    python mcp-property/backfill_embeddings.py --limit 0
    python compliance/ingest_rules.py

Listings themselves are untouched — only their embeddings (and the
compliance rules, whose text lives in the same row as its vector and
is cheaply re-ingested from the PDF).
"""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

sys.path.append(str(Path(__file__).resolve().parents[1]))

from db.models import Base, ComplianceRule, ListingEmbedding  # noqa: E402
from db.session import engine  # noqa: E402

TABLES = [ListingEmbedding.__table__, ComplianceRule.__table__]


def main() -> None:
    Base.metadata.drop_all(engine, tables=TABLES)
    Base.metadata.create_all(engine, tables=TABLES)
    from db.models import EMBEDDING_DIM

    print(f"recreated {', '.join(t.name for t in TABLES)} at {EMBEDDING_DIM} dims")
    print("now re-embed: python mcp-property/backfill_embeddings.py --limit 0")
    print("        and: python compliance/ingest_rules.py")


if __name__ == "__main__":
    main()
