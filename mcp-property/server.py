"""
mcp-property — hybrid SQL + pgvector listing search, exposed as MCP
tools. Run standalone: python mcp-property/server.py
(MCP_TRANSPORT=streamable-http serves it over HTTP instead of stdio.)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()  # before the db/embeddings imports below, which read env vars at module-import time

sys.path.append(str(Path(__file__).resolve().parents[1]))  # repo root, for the shared `db` package
sys.path.append(str(Path(__file__).resolve().parent))  # this dir, for local embeddings.py

from mcp.server.fastmcp import FastMCP  
from sqlalchemy import nulls_last, select  

from db.models import Listing, ListingEmbedding  
from db.session import get_session  
from embeddings import embed_query  

mcp = FastMCP("property-search")


def _listing_to_dict(listing: Listing) -> dict:
    return {
        "id": str(listing.id),
        "address": listing.address,
        "city": listing.city,
        "state": listing.state,
        "zip_code": listing.zip_code,
        "price": float(listing.price) if listing.price is not None else None,
        "beds": listing.beds,
        "baths": float(listing.baths) if listing.baths is not None else None,
        "sqft": listing.sqft,
        "status": listing.status,
        "source": listing.source,
    }


def _build_search_query(
    min_price: Optional[float],
    max_price: Optional[float],
    beds: Optional[int],
    baths: Optional[float],
    city: Optional[str],
    state: Optional[str],
    query: Optional[str],
    limit: int,
):
    """Builds the SQLAlchemy statement (split out so it's unit-testable
    without a live DB)."""
    limit = max(1, min(limit, 50))

    if query:
        query_vector = embed_query(query)
        distance = ListingEmbedding.embedding.cosine_distance(query_vector)
        # LEFT join: listings without embeddings must still match on the
        # structured filters (an inner join zeroes ALL results whenever
        # the embeddings table is incomplete). They just sort last.
        stmt = (
            select(Listing)
            .outerjoin(ListingEmbedding, ListingEmbedding.listing_id == Listing.id)
            .order_by(nulls_last(distance))
        )
    else:
        stmt = select(Listing).order_by(Listing.price.asc())

    if min_price is not None:
        stmt = stmt.where(Listing.price >= min_price)
    if max_price is not None:
        stmt = stmt.where(Listing.price <= max_price)
    if beds is not None:
        stmt = stmt.where(Listing.beds >= beds)
    if baths is not None:
        stmt = stmt.where(Listing.baths >= baths)
    if city:
        # Strip ", PR"-style suffixes the LLM adds — the DB's clean city
        # name can never contain the longer string as a substring.
        city_clean = city.split(",")[0].strip()
        stmt = stmt.where(Listing.city.ilike(f"%{city_clean}%"))
    if state:
        stmt = stmt.where(Listing.state == state.upper())

    return stmt.limit(limit)


@mcp.tool()
def search_listings(
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    beds: Optional[int] = None,
    baths: Optional[float] = None,
    city: Optional[str] = None,
    state: Optional[str] = None,
    query: Optional[str] = None,
    limit: int = 10,
) -> list[dict]:
    """
    Search listings by structured filters. Pass a free-text `query`
    (e.g. "quiet street near good coffee, walkable") to additionally
    rerank the filtered results by semantic similarity against listing
    embeddings (A-03's hybrid retrieval pattern) — omit it for pure
    structured search.
    """
    with get_session() as session:
        stmt = _build_search_query(min_price, max_price, beds, baths, city, state, query, limit)
        results = session.execute(stmt).scalars().all()
        return [_listing_to_dict(listing) for listing in results]


@mcp.tool()
def get_listing_details(listing_id: str) -> dict:
    """Fetch full details for a single listing by ID, including its raw source attributes."""
    with get_session() as session:
        listing = session.get(Listing, listing_id)
        if listing is None:
            return {"error": f"No listing found with id {listing_id}"}
        data = _listing_to_dict(listing)
        data["raw_attributes"] = listing.raw_attributes
        return data


if __name__ == "__main__":
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    if transport == "streamable-http":
        mcp.run(
            transport="streamable-http",
            host="0.0.0.0",
            port=int(os.environ.get("MCP_PORT", 8000)),
        )
    else:
        mcp.run(transport="stdio")
