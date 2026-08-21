"""
mcp-market — Market Data MCP server. Two tools:
  get_market_trends       — reads the batch-loaded market_stats table
  get_market_trends_live  — searches Redfin's public pages live via
                            Tavily (web estimates, cite the source)
Run standalone: python mcp-market/server.py
"""

from __future__ import annotations

import os
import re
import sys
from datetime import date
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()  # before the db imports below, which read env vars at module-import time

sys.path.append(str(Path(__file__).resolve().parents[1]))  # repo root, for the shared `db` package

from mcp.server.fastmcp import FastMCP  # noqa: E402
from sqlalchemy import select  # noqa: E402

from db.models import MarketStat, Neighborhood  # noqa: E402
from db.session import get_session  # noqa: E402

mcp = FastMCP("market-data")

TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY", "")
TAVILY_URL = "https://api.tavily.com/search"


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
def get_market_trends(zip_code: str, city: str = "", state: str = "") -> dict:
    """
    Recent market trend data for a ZIP code — median price, inventory,
    and days-on-market. Prefers Redfin/Realtor.com batch-ingested data;
    if none is loaded for the ZIP, automatically falls back to a live
    Redfin web search (Tavily). Live results are web estimates — present
    them as such and cite the source URL.
    """
    with get_session() as session:
        neighborhood = session.execute(
            select(Neighborhood).where(Neighborhood.zip_code == zip_code)
        ).scalar_one_or_none()

        results = {}
        if neighborhood is not None:
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

        if results:
            return results

    # No batch data — fall back to live web search inside the tool, so the
    # fallback doesn't need a second LLM tool-calling turn (the graph only
    # gives the model one).
    return _live_market_lookup(zip_code, city, state)


# ---------------------------------------------------- live web search --

_PRICE_RE = re.compile(r"\$\s?([\d,]{4,})")


def _extract_price_hint(text: str) -> int | None:
    """Best-effort: pull the first plausible home-price figure ($100k-$10M)
    out of a search snippet. A HINT only — the source URL is authoritative;
    the agent must cite it and treat this as an estimate, not a fact."""
    for match in _PRICE_RE.finditer(text):
        value = int(match.group(1).replace(",", ""))
        if 100_000 <= value <= 10_000_000:
            return value
    return None


def _live_market_lookup(zip_code: str, city: str = "", state: str = "") -> dict:
    """Search Redfin's public pages via Tavily and return web-sourced
    evidence (snippets + URLs). Shared by get_market_trends' fallback and
    the standalone get_market_trends_live tool."""
    if not TAVILY_API_KEY:
        return {"error": "TAVILY_API_KEY not set — get a free key at https://tavily.com"}

    where = ", ".join(part for part in (city, state) if part) or "USA"
    query = f"Redfin {zip_code} {where} housing market median sale price days on market"
    try:
        response = requests.post(
            TAVILY_URL,
            json={
                "api_key": TAVILY_API_KEY,
                "query": query,
                "search_depth": "basic",
                "include_domains": ["redfin.com"],  # keep it to Redfin's public pages
                "max_results": 3,
            },
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        return {"error": f"live market lookup failed: {exc}"}

    evidence = []
    for item in payload.get("results") or []:
        snippet = (item.get("content") or "").strip()
        if not snippet:
            continue
        evidence.append({
            "url": item.get("url"),
            "snippet": snippet[:500],
            "median_price_hint": _extract_price_hint(snippet),
        })

    if not evidence:
        return {"error": f"no reliable Redfin market data found online for ZIP {zip_code}"}

    return {
        "zip_code": zip_code,
        "source": "Redfin public pages via live web search (Tavily)",
        "as_of": date.today().isoformat(),
        "evidence": evidence,
        "note": (
            "These are figures read from public web pages, NOT a verified "
            "dataset. Present any number as an estimate, cite the source URL, "
            "and note it may be out of date."
        ),
    }


@mcp.tool()
def get_market_trends_live(zip_code: str, city: str = "", state: str = "") -> dict:
    """
    Force a LIVE Redfin web search (Tavily) for a ZIP's market data,
    bypassing the batch dataset — use when the user explicitly wants the
    latest figures. (get_market_trends already falls back to this
    automatically when it has no batch data.) Results are web estimates:
    present them as such and cite the source URL.
    """
    return _live_market_lookup(zip_code, city, state)


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
