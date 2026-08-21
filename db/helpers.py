"""Small shared helpers used by multiple MCP servers and ingestion scripts."""

from __future__ import annotations

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from db.models import Neighborhood


def get_or_create_neighborhood(session: Session, zip_code: str) -> Neighborhood:
    """Every enrichment source (Census, FBI, Redfin, Realtor.com) is
    keyed by ZIP code and needs a Neighborhood row to attach its data
    to — this is the one place that lookup-or-create logic lives.

    Uses Postgres's native INSERT ... ON CONFLICT upsert rather than a
    select-then-insert: the latter isn't atomic, so two concurrent
    requests enriching the same brand-new ZIP would both see "not
    found" and both try to insert, crashing the second one on the
    unique constraint. The ON CONFLICT DO UPDATE (a no-op re-set of
    zip_code) is what makes RETURNING always yield a row, whether this
    call inserted it or another connection already had."""
    stmt = pg_insert(Neighborhood).values(zip_code=zip_code)
    stmt = stmt.on_conflict_do_update(
        index_elements=["zip_code"],
        set_={"zip_code": stmt.excluded.zip_code},
    ).returning(Neighborhood)
    neighborhood = session.execute(stmt).scalar_one()
    session.commit()
    session.refresh(neighborhood)  # re-load post-commit-expired attributes before the caller's session closes
    return neighborhood
