"""
mcp-market — Market Data MCP server (architecture sheets A-01, A-06, A-08).

Serves the market_stats table that ingest_market_data.py batch-loads
from Redfin and Realtor.com — this server itself only reads, it never
calls either source live.

Run standalone:
    python mcp-market/server.py

Then point an MCP client — or the MCP Inspector CLI — at it:
    npx @modelcontextprotocol/inspector python mcp-market/server.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()  # before the db imports below, which read env vars at module-import time

sys.path.append(str(Path(__file__).resolve().parents[1]))  # repo root, for the shared `db` package

from mcp.server.fastmcp import FastMCP  # noqa: E402
from sqlalchemy import select  # noqa: E402

from db.models import MarketStat, Neighborhood  # noqa: E402
from db.session import get_session  # noqa: E402

mcp = FastMCP("market-data")


def _stat_to_dict(stat: MarketStat) -> dict:
    return {
        "source": stat.source,
        "period_start": stat.period_start.isoformat() if stat.period_start else None,
        "period_end": stat.period_end.isoformat() if stat.period_end else None,
        "median_sale_price": float(stat.median_sale_price) if stat.median_sale_price is not None else None,
        "inventory_count": stat.inventory_count,
        "median_days_on_market": (
            float(stat.median_days_on_market) if stat.median_days_on_market is not None else None
        ),
        "note": (
            "median_sale_price reflects actual sale price for source=redfin, "
            "but LIST price (no sale-price column exists for it) for "
            "source=realtor_com — see ingest_market_data.py."
        ),
    }


@mcp.tool()
def get_market_trends(zip_code: str) -> dict:
    """
    Recent market trend data for a ZIP code — median price, inventory,
    and days-on-market from Redfin and Realtor.com's batch-ingested
    data (A-06). Returns the most recent period from each source that's
    been loaded; run ingest_market_data.py to load newer data.
    """
    session = get_session()
    try:
        neighborhood = session.execute(
            select(Neighborhood).where(Neighborhood.zip_code == zip_code)
        ).scalar_one_or_none()
        if neighborhood is None:
            return {"error": f"No market data loaded for ZIP {zip_code} yet"}

        results = {}
        for source in ("redfin", "realtor_com"):
            latest = (
                session.execute(
                    select(MarketStat)
                    .where(MarketStat.neighborhood_id == neighborhood.id, MarketStat.source == source)
                    .order_by(MarketStat.period_end.desc())
                )
                .scalars()
                .first()
            )
            if latest:
                results[source] = _stat_to_dict(latest)

        if not results:
            return {"error": f"No market data loaded for ZIP {zip_code} yet"}
        return results
    finally:
        session.close()


if __name__ == "__main__":
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    if transport == "streamable-http":
        mcp.run(
            transport="streamable-http",
            host="0.0.0.0",
            port=int(os.environ.get("MCP_PORT", 8002)),
        )
    else:
        mcp.run(transport="stdio")
