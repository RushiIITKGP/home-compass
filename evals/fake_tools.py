"""
Fixture versions of the agent's tools — exact names and signatures,
canned data. Keeps the routing suite isolated: a failure can only mean
the LLM chose wrong, not that Postgres/MCP/government APIs broke.
"""

from __future__ import annotations

import json
from typing import Optional

from langchain_core.tools import tool

FAKE_LISTINGS = [
    {
        "id": "eval-listing-1",
        "address": "101 Maple St",
        "city": "Austin",
        "state": "TX",
        "zip_code": "78701",
        "price": 350000.0,
        "beds": 3,
        "baths": 2.0,
        "sqft": 1500,
        "status": "for_sale",
        "source": "eval_fixture",
    },
    {
        "id": "eval-listing-2",
        "address": "202 Oak Ave",
        "city": "Austin",
        "state": "TX",
        "zip_code": "78702",
        "price": 425000.0,
        "beds": 3,
        "baths": 2.5,
        "sqft": 1850,
        "status": "for_sale",
        "source": "eval_fixture",
    },
    {
        "id": "eval-listing-3",
        "address": "303 Pecan Blvd",
        "city": "Austin",
        "state": "TX",
        "zip_code": "78704",
        "price": 480000.0,
        "beds": 4,
        "baths": 3.0,
        "sqft": 2200,
        "status": "for_sale",
        "source": "eval_fixture",
    },
]


@tool
def search_listings(
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    beds: Optional[int] = None,
    baths: Optional[float] = None,
    city: Optional[str] = None,
    state: Optional[str] = None,
    query: Optional[str] = None,
    limit: int = 10,
) -> str:
    """
    Search listings by structured filters. Pass a free-text `query`
    (e.g. "quiet street near good coffee, walkable") to additionally
    rerank the filtered results by semantic similarity — omit it for
    pure structured search.
    """
    results = [
        listing
        for listing in FAKE_LISTINGS
        if (min_price is None or listing["price"] >= min_price)
        and (max_price is None or listing["price"] <= max_price)
        and (beds is None or listing["beds"] >= beds)
        and (baths is None or listing["baths"] >= baths)
        and (city is None or city.split(",")[0].strip().lower() in listing["city"].lower())
        and (state is None or listing["state"] == state.upper())
    ]
    return json.dumps(results[: max(1, min(limit, 50))])


@tool
def get_neighborhood_demographics(zip_code: str) -> str:
    """Median household income and median age for a ZIP code (US Census ACS)."""
    return json.dumps(
        {
            "zip_code": zip_code,
            "median_household_income": 85000,
            "median_age": 34.2,
            "source": "eval_fixture (census)",
        }
    )


@tool
def get_safety_stats(zip_code: str, state: str) -> str:
    """Violent and property crime counts for a ZIP code's state (FBI Crime Data API)."""
    return json.dumps(
        {
            "zip_code": zip_code,
            "state": state,
            "year": 2024,
            "violent_crime_count": 412,
            "property_crime_count": 1893,
            "source": "eval_fixture (fbi)",
        }
    )


@tool
def get_market_trends(zip_code: str) -> str:
    """Recent market trend data for a ZIP code — median price, inventory, days on market."""
    return json.dumps(
        {
            "zip_code": zip_code,
            "redfin": {
                "source": "redfin",
                "median_sale_price": 455000.0,
                "inventory_count": 132,
                "median_days_on_market": 21.0,
            },
        }
    )


FAKE_TOOLS = [search_listings, get_neighborhood_demographics, get_safety_stats, get_market_trends]
