"""
Probe the FBI CDE API to find which URL format actually works — run
this on your machine (the API is unreachable from some environments):

    python mcp-enrich/probe_fbi.py MA

It tries every candidate format and prints status + a response preview,
so we can see definitively which one is current instead of guessing
from stale docs. Whichever pattern returns 200 with real numbers is the
one server.py's CANDIDATE_PATTERNS should list first.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

import os  # noqa: E402

API_KEY = os.environ.get("FBI_API_KEY", "")
BASE = "https://api.usa.gov/crime/fbi/cde"
SAPI = "https://api.usa.gov/crime/fbi/sapi"


def main() -> None:
    state = (sys.argv[1] if len(sys.argv) > 1 else "MA").upper()
    year = datetime.now(timezone.utc).year
    f, t = year - 3, year - 1

    candidates = [
        # sanity check: this exact pattern is publicly documented as
        # working (agency list) — if THIS 404s, the key/base is the
        # problem, not the crime endpoints
        ("SANITY: agency list by state (known-good pattern)",
         f"{BASE}/agency/byStateAbbr/{state}?API_KEY={API_KEY}"),
        ("summarized, offense path, MM-YYYY",
         f"{BASE}/summarized/state/{state}/violent-crime?from=01-{f}&to=12-{t}&API_KEY={API_KEY}"),
        ("summarized + type=counts",
         f"{BASE}/summarized/state/{state}/violent-crime?from=01-{f}&to=12-{t}&type=counts&API_KEY={API_KEY}"),
        ("summarized, YYYY params",
         f"{BASE}/summarized/state/{state}/violent-crime?from={f}&to={t}&API_KEY={API_KEY}"),
        ("estimate, offense path, MM-YYYY",
         f"{BASE}/estimate/state/{state}/violent-crime?from=01-{f}&to=12-{t}&API_KEY={API_KEY}"),
        ("old sapi service",
         f"{SAPI}/api/estimates/states/{state}/{f}/{t}?api_key={API_KEY}"),
    ]

    for label, url in candidates:
        try:
            response = requests.get(url, timeout=15)
            body = response.text[:300].replace("\n", " ")
            print(f"\n[{response.status_code}] {label}\n  {url.replace(API_KEY, '***')}\n  {body}")
        except requests.RequestException as exc:
            print(f"\n[ERR] {label}\n  {exc}")


if __name__ == "__main__":
    main()
