"""
Ingests the rules PDF (fetched from Google Drive — the single source
of truth; no local-folder path) into compliance_rules: chunk by rule
section -> embed -> store.

    python compliance/generate_rules_pdf.py               # once; then upload the PDF to Drive
    python compliance/ingest_rules.py [--from-drive NAME] # fetch -> chunk -> embed -> store

Chunks split on "§ N.N" markers — one chunk per rule, so retrieval
returns whole citable rules instead of arbitrary text windows. For a
different rulebook, adjust SECTION_PATTERN to its heading style.
Re-runnable: a document's rows are replaced wholesale.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pdfplumber
from dotenv import load_dotenv

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(REPO_ROOT))  # db package
sys.path.append(str(REPO_ROOT / "mcp-property"))  # embeddings.py (Gemini, same as listings)

from sqlalchemy import delete  # noqa: E402

from db.models import ComplianceRule  # noqa: E402
from db.session import get_session  # noqa: E402
from embeddings import embed_document  # noqa: E402

DATA_DIR = Path(__file__).resolve().parent / "data"

# Matches "§ 12.1" and "§ 12.0.1" at the start of a line. Titles run to
# the end of that line; body is everything until the next marker.
SECTION_PATTERN = re.compile(r"^(§ \d+\.\d+(?:\.\d+)?)\s+(.+)$", re.MULTILINE)


def extract_rules(pdf_path: Path) -> list[dict]:
    with pdfplumber.open(pdf_path) as pdf:
        full_text = "\n".join(page.extract_text() or "" for page in pdf.pages)

    matches = list(SECTION_PATTERN.finditer(full_text))
    rules = []
    for i, match in enumerate(matches):
        body_start = match.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(full_text)
        body = re.sub(r"\s+", " ", full_text[body_start:body_end]).strip()
        # Page furniture (SUBPART headings etc.) can trail into a chunk;
        # harmless for retrieval, so keep the chunker simple.
        rules.append({"section": match.group(1), "title": match.group(2).strip(), "text": body})
    return rules


def ingest(pdf_path: Path) -> int:
    rules = extract_rules(pdf_path)
    if not rules:
        print(f"  no § sections found in {pdf_path.name} — check SECTION_PATTERN")
        return 0

    session = get_session()
    try:
        session.execute(delete(ComplianceRule).where(ComplianceRule.document == pdf_path.name))
        for rule in rules:
            # Embed section + title + body together so a query like
            # "can I say a neighborhood is safe?" lands on § 12.3 even
            # though the word "safety" mostly appears in its title.
            embedded_text = f"{rule['section']} {rule['title']}. {rule['text']}"
            session.add(
                ComplianceRule(
                    document=pdf_path.name,
                    section=rule["section"],
                    title=rule["title"],
                    text=rule["text"],
                    embedding=embed_document(embedded_text),
                )
            )
        session.commit()
    finally:
        session.close()
    return len(rules)


def main() -> None:
    import argparse
    import asyncio
    import os

    parser = argparse.ArgumentParser(description="Fetch the rules PDF from Google Drive and ingest it")
    parser.add_argument(
        "--from-drive",
        metavar="NAME",
        default="fhas_part12_rules",
        help="name of the rules PDF in your Google Drive (default: fhas_part12_rules)",
    )
    args = parser.parse_args()

    from drive_fetch import fetch_pdf_from_drive, resolve_creds

    creds = resolve_creds()
    if not (creds["CLIENT_ID"] and creds["CLIENT_SECRET"]):
        raise SystemExit(
            "Google Drive is the only ingestion source for the rulebook, and it "
            "isn't configured yet.\nDo the one-time OAuth setup in "
            "compliance/README.md: save Google's OAuth JSON as "
            "gcp-oauth.keys.json inside GDRIVE_CREDS_DIR (default ~/.gdrive-mcp) "
            f"— currently looking in: {creds['GDRIVE_CREDS_DIR']}\n"
            "(Setting GDRIVE_CLIENT_ID/GDRIVE_CLIENT_SECRET in .env also works, "
            "but isn't needed when the JSON is in place.)"
        )

    pdf_path = asyncio.run(fetch_pdf_from_drive(args.from_drive))
    count = ingest(pdf_path)
    print(f"ingested {count} rules from {pdf_path.name} (source: Google Drive)")


if __name__ == "__main__":
    main()
