"""Small shared helpers used by multiple MCP servers and ingestion scripts."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import Neighborhood


def get_or_create_neighborhood(session: Session, zip_code: str) -> Neighborhood:
    """Every enrichment source (Census, FBI, Redfin, Realtor.com) is
    keyed by ZIP code and needs a Neighborhood row to attach its data
    to — this is the one place that lookup-or-create logic lives."""
    neighborhood = session.execute(
        select(Neighborhood).where(Neighborhood.zip_code == zip_code)
    ).scalar_one_or_none()
    if neighborhood is None:
        neighborhood = Neighborhood(zip_code=zip_code)
        session.add(neighborhood)
        session.commit()
        session.refresh(neighborhood)
    return neighborhood
