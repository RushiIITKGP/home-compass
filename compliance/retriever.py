"""
Rule retrieval for the compliance guardrail. Deliberately a plain
function, NOT an LLM-bound tool — a guardrail the model could decline
to consult isn't one. Returns None when no rules are ingested so
setup.py can announce guardrail ON/OFF explicitly.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(REPO_ROOT))  # db package
sys.path.append(str(REPO_ROOT / "mcp-property"))  # embeddings.py

from sqlalchemy import func, select  # noqa: E402

from db.models import ComplianceRule  # noqa: E402
from db.session import get_session  # noqa: E402

RuleRetriever = Callable[[str], list[dict]]


def build_rule_retriever(k: int = 4) -> Optional[RuleRetriever]:
    """Returns a query -> top-k rules function, or None if no rules are
    ingested (run compliance/ingest_rules.py) or the DB is unreachable."""
    try:
        with get_session() as session:
            count = session.execute(select(func.count()).select_from(ComplianceRule)).scalar()
    except Exception:
        return None
    if not count:
        return None

    from embeddings import embed_query  # deferred: needs GEMINI_API_KEY

    def retrieve(query: str) -> list[dict]:
        vector = embed_query(query)
        with get_session() as session:
            stmt = (
                select(ComplianceRule)
                .order_by(ComplianceRule.embedding.cosine_distance(vector))
                .limit(k)
            )
            rows = session.execute(stmt).scalars().all()
            return [{"section": r.section, "title": r.title, "text": r.text} for r in rows]

    return retrieve
