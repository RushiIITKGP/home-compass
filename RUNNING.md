# Running Home Compass — Step by Step

This walks through getting the whole stack running from a clean
checkout: database → backend → frontend. Every command here has
actually been run and verified against a real Postgres instance while
building this project — see the phase READMEs (`api/README.md`,
`mcp-property/README.md`, etc.) if you want the "why" behind any step;
this doc is just the "what, in order."

## 0. Prerequisites

- **Docker Desktop** (for Postgres)
- **Python 3.11+**
- **Node.js 24+** — needed for the frontend (`mcp-amenities` also
  needs it, but that server isn't part of the live agent right now —
  see `mcp-amenities/README.md`)
- **A free Gemini API key** — https://aistudio.google.com/apikey
  (covers both the chat model and embeddings — no second key needed)
- Optional, for full neighborhood enrichment:
  - Census API key — https://api.census.gov/data/key_signup.html
  - FBI API key (via api.data.gov) — https://api.data.gov/signup

## 1. Environment variables

From the repo root:

```bash
cp .env.example .env
cp web/.env.local.example web/.env.local
```

Open `.env` and fill in at minimum:

```
GEMINI_API_KEY=your-key-here
```

Add `CENSUS_API_KEY` and `FBI_API_KEY` too if you want neighborhood
enrichment (demographics/crime) working — the app runs fine without
them, those two pieces just return an error field until you add keys.

`web/.env.local` should already point at the right place
(`NEXT_PUBLIC_API_URL=http://localhost:8080`) — no changes needed
unless you're running the backend on a different port.

## 2. Start the database

```bash
docker compose up postgres
```

Leave this running in its own terminal. In another terminal, confirm
it's healthy:

```bash
docker exec -it home-compass-postgres psql -U homecompass -d homecompass -c "\dx"
```

You should see `vector` in the extension list.

## 3. Create the tables

```bash
docker compose run --rm ingest-worker python db/create_tables.py
```

## 4. Seed listings (embeddings happen automatically)

Download the free Kaggle dataset:
https://www.kaggle.com/datasets/ahmedshahriarsakib/usa-real-estate-dataset

Save `realtor-data.csv` to `ingest-worker/data/realtor-data.csv`, then
make sure `GEMINI_API_KEY` is in `.env` (already done in step 1), and:

```bash
docker compose run --rm ingest-worker python ingest-worker/seed_kaggle.py --limit 5000
```

This inserts the listings **and** generates their embeddings in the
same command — semantic search (e.g. "quiet street near good coffee")
works immediately afterward; structured search (price/beds/baths/city)
always works regardless. Re-running this later with more data only
embeds what's new, not everything again.

Don't want embeddings generated right now (no key handy, or just want
a fast load)? Add `--skip-embeddings` — structured search still works
fine, you can backfill embeddings later with
`mcp-property/backfill_embeddings.py` whenever you're ready.

Verify real rows landed:

```bash
docker exec -it home-compass-postgres psql -U homecompass -d homecompass -c "SELECT count(*) FROM listings;"
```

## 5. Load market data (optional)

Only needed if you want the market-trend line (median price, inventory)
in results. Skip this for now if you just want the app running —
demographics/safety/market simply won't appear in cards without it.

```bash
cd mcp-market
pip install -r requirements.txt -r ../requirements.txt
python ingest_market_data.py --source redfin --file data/zip_code_market_tracker.tsv000.gz
cd ..
```

(Download link and column notes are in `mcp-market/README.md`.)

## 6. Run the backend

```bash
cd api
pip install -r requirements.txt -r ../requirements.txt \
  -r ../mcp-property/requirements.txt \
  -r ../mcp-enrich/requirements.txt \
  -r ../mcp-market/requirements.txt

uvicorn main:app --reload --port 8080
```

No need to `export` anything here — `main.py` calls `load_dotenv()`,
which finds and loads the repo-root `.env` file automatically (it
searches upward from `main.py`'s own location, not just the current
directory, so this works correctly even though you're running the
command from inside `api/`, not the repo root). Just make sure `.env`
actually has real values filled in from step 1. If you ever want to
override something for one command without editing `.env` — testing a
different model, say — `export`ing it first still works fine and takes
priority.

**Important:** you do **not** need to separately run
`docker compose up mcp-property` (or `mcp-enrich` / `mcp-market`) for
the app to work. `api/setup.py` automatically spawns all three as
local Python subprocesses the moment the backend starts — the
Docker Compose entries for those three exist so you *can* test each
one standalone/containerized if you want to, but they're not part of
the live request path yet. That full container wiring is Phase 7.

`mcp-amenities` is **not** spawned automatically — it's the one
server this app doesn't currently call at all, on purpose (searches
return exactly what was asked for; see `api/README.md`). Nothing to
configure for it unless you specifically want to re-enable it.

Leave this running. Confirm it's up:

```bash
curl http://localhost:8080/health
```

## 7. Run the frontend

In a new terminal:

```bash
cd web
npm install
npm run dev
```

## 8. Open it

http://localhost:3000

Try three things:
- A vague first message ("I'm looking for a place") — should get back
  exactly one targeted clarifying question, with a low compass reading.
- Full criteria up front ("3 bed house in Newark NJ, 300–500k, quiet
  street, moving soon") — should search immediately, show listing
  cards, and the compass should read close to 100%. No source
  citations on the cards yet at this point — that's by design (see
  `api/README.md`), not a missing step.
- A follow-up — "what's the crime rate there?" — should fetch and cite
  that specific data on demand, without re-running the search.

## Troubleshooting

**Zero results even though listings clearly exist in the database.**
Fixed as of this build — search used to silently return nothing if the
agent's search included descriptive text (e.g. "house") while
embeddings hadn't been backfilled yet. If you're on an older copy of
this code, pull the latest `mcp-property/server.py`, or run
`mcp-property/backfill_embeddings.py` to backfill embeddings if you
seeded with `--skip-embeddings` earlier.

**`Connection refused` talking to Postgres.**
Make sure `docker compose up postgres` (step 2) is still running in its
own terminal — it's not a one-shot command.

**Gemini errors on startup.**
Double check `.env` actually has a real `GEMINI_API_KEY` filled in —
`main.py` and `cli.py` both call `load_dotenv()` before importing
anything else, so the repo-root `.env` loads automatically regardless
of which directory you run the command from; no manual `export` needed.
If you're deliberately overriding a value for one run instead of
editing `.env`, `export`ing it first still works and takes priority.

**Enrichment fields show an `error` instead of data.**
Expected if `CENSUS_API_KEY` / `FBI_API_KEY` aren't set — those two
sources just degrade gracefully rather than blocking the rest of the
response. Add the keys (both free) to fix.

**`mcp-amenities` never contributes amenity data.**
Expected — it's not currently wired into the agent at all (see
`mcp-amenities/README.md`), not a configuration issue on your end.

## What's running where, at a glance

| Piece | How it runs | Port |
|---|---|---|
| Postgres | Docker (`docker compose up postgres`) | 5432 |
| `mcp-property` / `mcp-enrich` / `mcp-market` | Spawned automatically by `api/setup.py` (local Python subprocess, stdio) | — |
| `mcp-amenities` | Not spawned — not currently used by the live agent | — |
| Backend (`api/main.py`) | `uvicorn`, run manually | 8080 |
| Frontend (`web/`) | `npm run dev`, run manually | 3000 |

Nothing here is containerized end-to-end yet except Postgres — that's
intentional, and matches the roadmap in the architecture doc's sheet
A-10 (full Docker Compose is Phase 7, not done yet).
