"""
mcp-enrich — wraps the US Census ACS API (demographics) and FBI Crime
Data API (crime) as MCP tools, cached in Postgres (this data updates
annually). Run standalone: python mcp-enrich/server.py
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()  # before the db imports below, which read env vars at module-import time

sys.path.append(str(Path(__file__).resolve().parents[1]))  # repo root, for the shared `db` package

from mcp.server.fastmcp import FastMCP  # noqa: E402
from sqlalchemy import select  # noqa: E402

from db.helpers import get_or_create_neighborhood  # noqa: E402
from db.models import CrimeStat, Demographics  # noqa: E402
from db.session import get_session  # noqa: E402

mcp = FastMCP("neighborhood-enrichment")

CENSUS_API_KEY = os.environ.get("CENSUS_API_KEY", "")
CENSUS_ACS_YEAR = os.environ.get("CENSUS_ACS_YEAR", "2023")
FBI_API_KEY = os.environ.get("FBI_API_KEY", "")
FBI_CDE_BASE = "https://api.usa.gov/crime/fbi/cde"

# Census ACS 5-Year variable codes -> our Demographics columns.
# See https://api.census.gov/data/{year}/acs/acs5/variables.html
# (Population and population-density aren't fetched: ACS reports raw
# population but density needs land-area data from a separate Census
# Gazetteer file, which is out of scope for this simple version — see
# db/models.py's Demographics.population_density, left null here.)
CENSUS_VARIABLES = {
    "B19013_001E": "median_household_income",
    "B01002_001E": "median_age",
}


# ------------------------------------------------------------ demographics --


def _fetch_census(zip_code: str) -> dict:
    variables = ",".join(["NAME", *CENSUS_VARIABLES.keys()])
    url = (
        f"https://api.census.gov/data/{CENSUS_ACS_YEAR}/acs/acs5"
        f"?get={variables}&for=zip%20code%20tabulation%20area:{zip_code}&key={CENSUS_API_KEY}"
    )
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
    except requests.RequestException as exc:
        return {"error": f"Census API request failed: {exc}"}

    rows = response.json()
    if len(rows) < 2:
        return {"error": f"No Census data found for ZIP {zip_code}"}

    header, values = rows[0], rows[1]
    raw = dict(zip(header, values))

    result = {}
    for code, field_name in CENSUS_VARIABLES.items():
        raw_value = raw.get(code)
        # Census uses -666666666 as a "data unavailable" sentinel for some ZCTAs.
        try:
            result[field_name] = float(raw_value) if raw_value not in (None, "-666666666") else None
        except (TypeError, ValueError):
            result[field_name] = None
    return result


def _demographics_to_dict(record: Demographics) -> dict:
    return {
        "median_household_income": record.median_household_income,
        "median_age": float(record.median_age) if record.median_age is not None else None,
        "fetched_at": record.fetched_at.isoformat() if record.fetched_at else None,
        "source": "US Census Bureau ACS 5-Year Estimates",
    }


@mcp.tool()
def get_neighborhood_demographics(zip_code: str) -> dict:
    """
    Median household income and median age for a ZIP code, from the US
    Census Bureau's ACS 5-Year estimates. Cached in Postgres after the
    first fetch — this data only updates annually.
    """
    session = get_session()
    try:
        neighborhood = get_or_create_neighborhood(session, zip_code)

        cached = (
            session.execute(
                select(Demographics)
                .where(Demographics.neighborhood_id == neighborhood.id)
                .order_by(Demographics.fetched_at.desc())
            )
            .scalars()
            .first()
        )
        if cached:
            return _demographics_to_dict(cached)

        if not CENSUS_API_KEY:
            return {
                "error": "CENSUS_API_KEY not set — get a free key at "
                "https://api.census.gov/data/key_signup.html"
            }

        data = _fetch_census(zip_code)
        if "error" in data:
            return data

        record = Demographics(
            neighborhood_id=neighborhood.id,
            median_household_income=data.get("median_household_income"),
            median_age=data.get("median_age"),
        )
        session.add(record)
        session.commit()
        session.refresh(record)
        return _demographics_to_dict(record)
    finally:
        session.close()


# --------------------------------------------------------------- crime --


def _find_time_series(payload, depth: int = 0) -> dict | None:
    """Recursively find the first dict of 'YYYY'/'MM-YYYY' keys mapping
    to numbers — survives the CDE API's shifting response nestings."""
    if depth > 5 or not isinstance(payload, dict):
        return None
    import re

    key_pattern = re.compile(r"^(\d{4}|\d{2}-\d{4})$")
    numeric_items = {
        k: v for k, v in payload.items()
        if isinstance(k, str) and key_pattern.match(k) and isinstance(v, (int, float))
    }
    if numeric_items:
        return numeric_items
    for value in payload.values():
        found = _find_time_series(value, depth + 1)
        if found:
            return found
    return None


def _latest_annual_value(series: dict) -> tuple[int, float]:
    """Annual keys -> that year's value; monthly keys -> summed per year,
    preferring the latest COMPLETE year (a partial year would understate)."""
    annual: dict[int, float] = {}
    month_counts: dict[int, int] = {}
    monthly = False
    for key, value in series.items():
        if "-" in key:
            monthly = True
            year = int(key.split("-")[1])
            annual[year] = annual.get(year, 0) + value
            month_counts[year] = month_counts.get(year, 0) + 1
        else:
            annual[int(key)] = value
    if monthly:
        complete_years = [y for y, n in month_counts.items() if n >= 12]
        year = max(complete_years) if complete_years else max(annual)
    else:
        year = max(annual)
    return year, annual[year]


def _fetch_fbi_offense_count(state: str, offense: str, from_year: int, to_year: int):
    """Fetch one offense series, returning (year, value, metric) —
    metric 'count' or 'rate_per_100k' — or an error string.

    URL format verified live via probe_fbi.py (2026-07): summarized/
    state/{state}/{offense} with MM-YYYY params. Responses carry both
    'actuals' (counts) and 'rates' (per 100k) series — units differing
    ~700x — so prefer actuals and label rates explicitly; prefer the
    state's series over the 'United States' comparison series."""
    candidates = [
        f"{FBI_CDE_BASE}/summarized/state/{state}/{offense}?from=01-{from_year}&to=12-{to_year}&API_KEY={FBI_API_KEY}",
        f"{FBI_CDE_BASE}/estimate/state/{state}/{offense}?from=01-{from_year}&to=12-{to_year}&API_KEY={FBI_API_KEY}",
    ]
    last_error = None
    for url in candidates:
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            continue

        offenses = payload.get("offenses") if isinstance(payload, dict) else None
        if isinstance(offenses, dict):
            for group_key, metric in (("actuals", "count"), ("rates", "rate_per_100k")):
                group = offenses.get(group_key)
                if not isinstance(group, dict):
                    continue
                # State series first, "United States ..." comparison series last.
                ordered = sorted(group.items(), key=lambda kv: "united states" in str(kv[0]).lower())
                for _, series_container in ordered:
                    series = _find_time_series(series_container)
                    if series:
                        year, value = _latest_annual_value(series)
                        return year, value, metric

        series = _find_time_series(payload)  # unknown envelope — best effort
        if series:
            year, value = _latest_annual_value(series)
            return year, value, "count"
        last_error = f"no time series in response: {str(payload)[:150]}"
    return str(last_error)


def _fetch_fbi_state_estimate(state: str) -> dict:
    """Statewide violent/property crime estimate for the most recent
    available year (the FBI CDE API's estimate endpoint reports by
    state/agency, not ZIP code — see the caveat in get_safety_stats).

    The FBI has restructured this API more than once, so this tries the
    CURRENT format first (from/to as MM-YYYY query params — the old
    /{from}/{to} path-segment style now 404s; found via a LangSmith
    trace of a live failure), then falls back to the legacy style, and
    parses whichever known response shape comes back. Note territories:
    FBI estimates cover the 50 states + DC; Puerto Rico ZIPs will
    usually get a clean 'no data' answer, which the agent should relay
    honestly rather than substitute."""
    current_year = datetime.now(timezone.utc).year
    from_year, to_year = current_year - 3, current_year - 1  # FBI data lags ~1-2 years
    state_code = state.upper()

    violent = _fetch_fbi_offense_count(state_code, "violent-crime", from_year, to_year)
    prop = _fetch_fbi_offense_count(state_code, "property-crime", from_year, to_year)

    result: dict = {}
    for offense_result, count_key, rate_key in (
        (violent, "violent_crime_count", "violent_crime_rate_per_100k"),
        (prop, "property_crime_count", "property_crime_rate_per_100k"),
    ):
        if isinstance(offense_result, tuple):
            year, value, metric = offense_result
            result.setdefault("year", year)
            if metric == "count":
                result[count_key] = int(round(value))
            else:
                result[rate_key] = round(value, 1)

    if result:
        return result

    return {
        "error": (
            f"No FBI crime data available for state {state_code} "
            f"(FBI estimates cover the 50 states + DC; territories like PR "
            f"are typically not included). Run mcp-enrich/probe_fbi.py "
            f"{state_code} to see which URL format the API currently "
            f"accepts. Last error: {violent}"
        )
    }


def _crime_stat_to_dict(record: CrimeStat) -> dict:
    return {
        "year": record.year,
        "violent_crime_count": record.violent_crime_count,
        "property_crime_count": record.property_crime_count,
        "fetched_at": record.fetched_at.isoformat() if record.fetched_at else None,
        "source": "FBI Crime Data API — statewide estimate (see note)",
        "note": (
            "Crime is reported by police agency, not ZIP code, so this is a "
            "statewide estimate used as a practical proxy, not a "
            "neighborhood-specific figure."
        ),
    }


@mcp.tool()
def get_safety_stats(zip_code: str, state: str) -> dict:
    """
    Statewide violent/property crime estimates for the most recent
    available year (FBI Crime Data API). Cached per ZIP in Postgres.
    Note: true ZIP/neighborhood-level crime data isn't available for
    free — see the `note` field in the result.
    """
    session = get_session()
    try:
        neighborhood = get_or_create_neighborhood(session, zip_code)

        cached = (
            session.execute(
                select(CrimeStat)
                .where(CrimeStat.neighborhood_id == neighborhood.id)
                .order_by(CrimeStat.fetched_at.desc())
            )
            .scalars()
            .first()
        )
        if cached:
            return _crime_stat_to_dict(cached)

        if not FBI_API_KEY:
            return {
                "error": "FBI_API_KEY not set — get a free key at https://api.data.gov/signup"
            }

        data = _fetch_fbi_state_estimate(state)
        if "error" in data:
            return data

        if data.get("violent_crime_count") is None and data.get("property_crime_count") is None:
            # Rates-only — never cache rates into count columns.
            return {
                **data,
                "source": "FBI Crime Data API — statewide rate per 100,000 residents",
                "note": (
                    "Figures are rates per 100,000 residents statewide (counts "
                    "were unavailable), reported by police agencies — not "
                    "neighborhood-specific."
                ),
            }

        record = CrimeStat(
            neighborhood_id=neighborhood.id,
            year=data["year"],
            violent_crime_count=data.get("violent_crime_count"),
            property_crime_count=data.get("property_crime_count"),
        )
        session.add(record)
        session.commit()
        session.refresh(record)
        return _crime_stat_to_dict(record)
    finally:
        session.close()


if __name__ == "__main__":
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    if transport == "streamable-http":
        mcp.run(
            transport="streamable-http",
            host="0.0.0.0",
            port=int(os.environ.get("MCP_PORT", 8001)),
        )
    else:
        mcp.run(transport="stdio")
