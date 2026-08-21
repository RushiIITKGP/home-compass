"""
Populates listing_embeddings for any listing that doesn't have one yet.
Re-runnable — already-embedded listings are skipped.

Usage:
    python mcp-property/backfill_embeddings.py --limit 500
    python mcp-property/backfill_embeddings.py --limit 0     # all listings

The Kaggle seed data (Phase 1) has no free-text description field, so a
short natural-language blurb is synthesized from structured fields
instead. Swap describe_listing() for the real MLS description once
mcp-property points at licensed listing data (see A-06 / A-09).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()  # before the db/embeddings imports below, which read env vars at module-import time

sys.path.append(str(Path(__file__).resolve().parents[1]))  # repo root, for the shared `db` package
sys.path.append(str(Path(__file__).resolve().parent))  # this dir, for local embeddings.py

from sqlalchemy import select  # noqa: E402
from tqdm import tqdm  # noqa: E402

from db.models import Listing, ListingEmbedding  # noqa: E402
from db.session import get_session  # noqa: E402
from embeddings import embed_document  # noqa: E402


def describe_listing(listing: Listing) -> str:
    bed_bath = " ".join(
        part for part in [
            f"{listing.beds} bed" if listing.beds else None,
            f"{listing.baths} bath" if listing.baths else None,
        ]
        if part
    )
    headline = f"{bed_bath} home" if bed_bath else "Home"
    if listing.city and listing.state:
        headline = f"{headline} in {listing.city}, {listing.state}"

    details = []
    if listing.sqft:
        details.append(f"{listing.sqft} sqft")
    if listing.price:
        details.append(f"listed at ${float(listing.price):,.0f}")

    sentence = headline
    if details:
        sentence += ", " + ", ".join(details)
    if listing.status:
        sentence += f" ({listing.status})"
    return sentence


def backfill(limit: int | None, batch_size: int = 50) -> int:
    with get_session() as session:
        already_embedded = {row[0] for row in session.execute(select(ListingEmbedding.listing_id))}

        stmt = select(Listing)
        listings = session.execute(stmt).scalars().all()

        count = 0
        for listing in tqdm(listings, desc="Embedding listings", unit="listing"):
            if listing.id in already_embedded:
                continue

            text = describe_listing(listing)
            vector = embed_document(text)
            session.add(ListingEmbedding(listing_id=listing.id, embedding=vector, embedded_text=text))
            count += 1

            if count % batch_size == 0:
                session.commit()

            if limit and count >= limit:
                break

        session.commit()
        return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill embeddings for listings.")
    parser.add_argument("--limit", type=int, default=500, help="Listings to embed (0 = all)")
    args = parser.parse_args()

    limit = args.limit or None
    print(f"Backfilling embeddings (limit={limit or 'all listings'})...")
    total = backfill(limit)
    print(f"Done — embedded {total} listings.")


if __name__ == "__main__":
    main()
