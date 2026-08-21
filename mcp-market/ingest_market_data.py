"""
mcp-market batch ingestion — loads Redfin Data Center and Realtor.com
Data Library files into market_stats (architecture sheet A-06).

Unlike mcp-property's Kaggle seed (a one-time load), this is meant to be
re-run on the weekly/monthly cadence those two sources actually publish
on (see A-06's update-cadence notes) — the recurring cron job for that
is Phase 7's job; this script is what that job would call.

Files aren't bundled here — download manually:
  Redfin:    https://www.redfin.com/news/data-center
             -> "Zip Code" market tracker (weekly & monthly TSV, gzipped)
  Realtor:   https://www.realtor.com/research/data/
             -> "Zip Code" inventory history CSV

Usage:
    python ingest_market_data.py --source redfin --file data/zip_code_market_tracker.tsv000.gz
    python ingest_market_data.py --source realtor --file data/RDC_Inventory_Core_Metrics_Zip_History.csv

NOTE: both sources' exact column names have been observed to shift
between releases (Realtor.com changed its inventory methodology in 2021
and 2022, for instance). The column maps below reflect commonly
documented shapes for each — if a file fails to parse, check its actual
header row against COLUMN-something below and adjust, same pattern as
ingest-worker/seed_kaggle.py's COLUMN_MAP for the Kaggle dataset.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from tqdm import tqdm

load_dotenv()  # before the db imports below, which read env vars at module-import time

sys.path.append(str(Path(__file__).resolve().parents[1]))  # repo root, for the shared `db` package

from db.helpers import get_or_create_neighborhood  # noqa: E402
from db.models import MarketStat  # noqa: E402
from db.session import get_session  # noqa: E402


# ------------------------------------------------------------------ redfin --


def parse_redfin(path: Path, limit: int | None) -> list[dict]:
    df = pd.read_csv(path, sep="\t", compression="infer", low_memory=False)

    # The file covers every region type (state, metro, county, zip) and
    # every property type mixed together — filter down to one row per
    # ZIP per period, all-residential, to match our schema (which is
    # ZIP-keyed and doesn't split out property type).
    if "region_type" in df.columns:
        df = df[df["region_type"] == "zip code"]
    if "property_type" in df.columns:
        df = df[df["property_type"] == "All Residential"]

    df["zip_code"] = df["region"].astype(str).str.extract(r"(\d{5})")
    df = df.dropna(subset=["zip_code", "median_sale_price"])

    if limit:
        df = df.head(limit)

    rows = []
    for r in df.to_dict(orient="records"):
        rows.append(
            {
                "zip_code": r["zip_code"],
                "source": "redfin",
                "period_start": r.get("period_begin"),
                "period_end": r.get("period_end"),
                "median_sale_price": r.get("median_sale_price"),
                "inventory_count": r.get("inventory"),
                "median_days_on_market": r.get("median_dom"),
            }
        )
    return rows


# ---------------------------------------------------------------- realtor --


def parse_realtor(path: Path, limit: int | None) -> list[dict]:
    df = pd.read_csv(path, dtype={"postal_code": str}, low_memory=False)
    df = df.dropna(subset=["postal_code", "median_listing_price"])

    if limit:
        df = df.head(limit)

    rows = []
    for r in df.to_dict(orient="records"):
        try:
            period = datetime.strptime(str(r.get("month_date_yyyymm", "")), "%Y%m").date().isoformat()
        except ValueError:
            period = None

        rows.append(
            {
                "zip_code": str(r["postal_code"]).zfill(5),
                "source": "realtor_com",
                "period_start": period,
                "period_end": period,  # monthly snapshot — treat start == end
                # Realtor.com's data library reports LIST price, not sale
                # price — there's no separate list-price column in our
                # schema, so it's stored here too. Always check `source`
                # before comparing this column across rows from different
                # sources: redfin rows are sale price, realtor_com rows
                # are list price.
                "median_sale_price": r.get("median_listing_price"),
                "inventory_count": r.get("active_listing_count"),
                "median_days_on_market": r.get("median_days_on_market"),
            }
        )
    return rows


PARSERS = {"redfin": parse_redfin, "realtor": parse_realtor}


# --------------------------------------------------------------- loading --


def load(rows: list[dict], source: str) -> int:
    total = 0
    with get_session() as session:
        for row in tqdm(rows, desc=f"Loading {source} market stats", unit="row"):
            neighborhood = get_or_create_neighborhood(session, row["zip_code"])
            session.add(
                MarketStat(
                    neighborhood_id=neighborhood.id,
                    source=source,
                    period_start=row["period_start"],
                    period_end=row["period_end"],
                    median_sale_price=row["median_sale_price"],
                    inventory_count=row["inventory_count"],
                    median_days_on_market=row["median_days_on_market"],
                )
            )
            total += 1
            if total % 200 == 0:
                session.commit()
        session.commit()
    return total


def main() -> None:
    parser = argparse.ArgumentParser(description="Load Redfin or Realtor.com market data into market_stats.")
    parser.add_argument("--source", choices=["redfin", "realtor"], required=True)
    parser.add_argument("--file", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=2000, help="Rows to load (0 = all)")
    args = parser.parse_args()

    if not args.file.exists():
        print(f"File not found: {args.file}")
        print("See this script's module docstring for where to download it from.")
        raise SystemExit(1)

    limit = args.limit or None
    rows = PARSERS[args.source](args.file, limit)
    print(f"Parsed {len(rows)} rows from {args.file.name} (source={args.source})")

    total = load(rows, "redfin" if args.source == "redfin" else "realtor_com")
    print(f"Done — inserted {total} market_stats rows.")


if __name__ == "__main__":
    main()
