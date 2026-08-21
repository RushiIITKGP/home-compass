"""
Phase 1 seed job: loads the free Kaggle USA Real Estate Dataset into
the `listings` table, then automatically generates embeddings for
whatever was just inserted (reusing mcp-property/backfill_embeddings.py
rather than duplicating that logic) — see architecture sheet A-06. This
is the stand-in for live MLS data until a real feed is connected
(A-08/A-09).

The CSV isn't bundled here (it's a few hundred MB) — get it manually:

  1. https://www.kaggle.com/datasets/ahmedshahriarsakib/usa-real-estate-dataset
  2. Download `realtor-data.csv` and save it to ingest-worker/data/
     (or point --csv-path somewhere else)

Usage:
    python ingest-worker/seed_kaggle.py --limit 5000
    python ingest-worker/seed_kaggle.py --limit 0                 # load all rows
    python ingest-worker/seed_kaggle.py --csv-path /some/other/path.csv
    python ingest-worker/seed_kaggle.py --skip-embeddings          # fast, no GEMINI_API_KEY needed
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import insert

load_dotenv()  # before the db/mcp-property imports below, which read env vars at module-import time

# Make the repo-root `db` package importable, and mcp-property importable
# too (for the embedding backfill step below) — whether this runs from
# the repo root, from ingest-worker/, or inside the Docker image.
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(REPO_ROOT))
sys.path.append(str(REPO_ROOT / "mcp-property"))

from db.models import Listing  # noqa: E402
from db.session import get_session  # noqa: E402

# Kaggle's realtor-data.csv columns as of the current dataset version —
# update this map if Kaggle renames columns upstream.
COLUMN_MAP = {
    "status": "status",
    "price": "price",
    "bed": "beds",
    "bath": "baths",
    "house_size": "sqft",
    "street": "street",
    "city": "city",
    "state": "state",
    "zip_code": "zip_code",
}

# The dataset's `state` column has been observed as full names ("New
# Jersey") in some snapshots and 2-letter codes in others — normalize
# both rather than assuming one, since naively slicing the first two
# characters of a full name silently corrupts it ("New Jersey" -> "Ne").
US_STATE_ABBREVIATIONS = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
    "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
    "vermont": "VT", "virginia": "VA", "washington": "WA", "west virginia": "WV",
    "wisconsin": "WI", "wyoming": "WY", "district of columbia": "DC",
    "puerto rico": "PR", "virgin islands": "VI", "guam": "GU",
}


def normalize_state(raw: str | float | None) -> str | None:
    """Return a 2-letter state code from either a full name or an
    existing code. Returns None (rather than a truncated guess) for
    anything unrecognized, so bad data is visibly missing, not silently wrong."""
    if raw is None or (isinstance(raw, float)):
        return None
    text = str(raw).strip()
    if not text or text.lower() == "nan":
        return None
    if len(text) == 2 and text.isalpha():
        return text.upper()
    return US_STATE_ABBREVIATIONS.get(text.lower())


def _clean_zip(raw) -> str | None:
    if pd.isna(raw):
        return None
    text = str(raw).split(".")[0].strip()
    if not text or text.lower() == "nan":
        return None
    return text.zfill(5)

def _clean_numeric(raw):
    """Pandas represents a missing numeric cell as NaN, not None — passed
    straight through to a psycopg-bound INTEGER/NUMERIC parameter, that
    raw NaN fails with a cryptic "integer out of range" error instead of
    a clearer "invalid input" one. Converts NaN (and None) to a clean
    SQL NULL instead — safe since price/beds/baths/sqft are all
    nullable in the schema."""
    return None if pd.isna(raw) else raw


def load_and_clean(csv_path: Path, limit: int | None) -> pd.DataFrame:
    # zip_code must be read as a string — otherwise pandas infers it as
    # numeric and silently drops leading zeros (e.g. "00901" -> 901),
    # corrupting every Northeast/Puerto Rico zip in the dataset.
    df = pd.read_csv(csv_path, low_memory=False, dtype={"zip_code": str})

    missing = [c for c in COLUMN_MAP if c not in df.columns]
    if missing:
        raise ValueError(
            f"Expected columns not found in {csv_path.name}: {missing}. "
            "Kaggle may have renamed columns — update COLUMN_MAP at the top of this file."
        )

    df = df.rename(columns=COLUMN_MAP)
    df = df.dropna(subset=["price", "city", "state"])
    df["zip_code"] = df["zip_code"].apply(_clean_zip)

    if limit:
        df = df.head(limit)

    return df


def to_listing_rows(df: pd.DataFrame) -> list[dict]:
    rows = []
    for record in df.to_dict(orient="records"):
        street = record.get("street") or ""
        city = record.get("city") or ""
        state_raw = record.get("state")
        state = normalize_state(state_raw)
        zip_code = record.get("zip_code") or ""
        address = ", ".join(
            part for part in [str(street), str(city), f"{state or ''} {zip_code}".strip()] if part and part != "nan"
        )

        rows.append(
            {
                "address": address or "Address unavailable",
                "city": city or None,
                "state": state,
                "zip_code": zip_code or None,
                "price": _clean_numeric(record.get("price")),
                "beds": _clean_numeric(record.get("beds")),
                "baths": _clean_numeric(record.get("baths")),
                "sqft": _clean_numeric(record.get("sqft")),
                "status": record.get("status"),
                "source": "kaggle_seed",
                "raw_attributes": {k: v for k, v in record.items() if pd.notna(v)},
            }
        )
    return rows


def seed(csv_path: Path, limit: int | None, batch_size: int = 1000) -> int:
    df = load_and_clean(csv_path, limit)
    rows = to_listing_rows(df)

    total = 0
    with get_session() as session:
        for i in range(0, len(rows), batch_size):
            batch = rows[i : i + batch_size]
            session.execute(insert(Listing), batch)
            session.commit()
            total += len(batch)
            print(f"  inserted {total}/{len(rows)}")

    return total


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the listings table from the Kaggle dataset.")
    parser.add_argument(
        "--csv-path",
        type=Path,
        default=Path(__file__).parent / "data" / "realtor-data.csv",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5000,
        help="Rows to load (default 5000 — fast for local dev; use 0 to load all ~2.2M rows)",
    )
    parser.add_argument(
        "--skip-embeddings",
        action="store_true",
        help="Only insert raw listing rows — skip generating embeddings for them. "
        "Useful for fast structural testing without needing GEMINI_API_KEY set, "
        "or to defer embedding cost/time on a very large load. Semantic search "
        "(the `query` parameter) just won't rank these listings until embeddings "
        "exist — structured search still works fine either way (see the fix in "
        "mcp-property/server.py: results are never silently dropped for lacking one).",
    )
    args = parser.parse_args()

    if not args.csv_path.exists():
        print(f"CSV not found at {args.csv_path}")
        print("Download it from https://www.kaggle.com/datasets/ahmedshahriarsakib/usa-real-estate-dataset")
        print(f"and save it as {args.csv_path}")
        raise SystemExit(1)

    limit = args.limit or None
    print(f"Seeding listings from {args.csv_path} (limit={limit or 'all rows'})...")
    total = seed(args.csv_path, limit)
    print(f"Done — inserted {total} listings.")

    if args.skip_embeddings:
        print("\nSkipped embeddings (--skip-embeddings). Run mcp-property/backfill_embeddings.py "
              "later to enable semantic search for these listings.")
        return

    if not os.environ.get("GEMINI_API_KEY"):
        print(
            "\nGEMINI_API_KEY isn't set, so embeddings can't be generated right now. "
            "Structured search (price/beds/baths/city) will still work fine for these "
            "listings — semantic search just won't rank them until you set the key and "
            "run: cd mcp-property && python backfill_embeddings.py"
        )
        return

    # Reuse mcp-property's embedding logic rather than duplicating it —
    # imported lazily so --skip-embeddings and the no-API-key path above
    # never require langchain-google-genai to even be installed.
    print("\nGenerating embeddings for the listings just seeded (this calls the Gemini API)...")
    import backfill_embeddings  # noqa: E402  (mcp-property/, added to sys.path above)

    embedded_count = backfill_embeddings.backfill(limit=None)
    print(f"Done — embedded {embedded_count} listings (skipped any already embedded).")


if __name__ == "__main__":
    main()
