# ingest-worker

Scheduled ETL container. Two jobs live here:

## Phase 1 (done) — Kaggle seed, with automatic embeddings

Loads the free Kaggle USA Real Estate Dataset into `listings` as a
stand-in for live MLS data (see A-06). As of this build, it also
**automatically generates embeddings** for whatever it just inserted —
no separate manual step needed each time you add more data.

1. Download `realtor-data.csv` from
   https://www.kaggle.com/datasets/ahmedshahriarsakib/usa-real-estate-dataset
   and save it to `ingest-worker/data/realtor-data.csv`
2. Create the tables (once):
   ```
   docker compose run --rm ingest-worker python db/create_tables.py
   ```
3. Seed the listings table (embeddings happen automatically afterward):
   ```
   docker compose run --rm ingest-worker python ingest-worker/seed_kaggle.py --limit 5000
   ```
   (`--limit 0` loads every row — that's ~2.2M rows and will take a
   while; 5,000 is plenty for local development.)

**Re-running this later with more/different data only embeds what's
new** — already-embedded listings are skipped (same idempotent check
`backfill_embeddings.py` always used), so there's no wasted API calls
or re-processing on repeat runs.

Needs `GEMINI_API_KEY` set for the embedding step. Two ways to skip it
when you don't want that right now:
- `--skip-embeddings` — inserts listings only, no embeddings at all,
  and doesn't require the key to be set
- Just don't set `GEMINI_API_KEY` — seeding still succeeds, you get a
  clear message instead of a crash, and can run
  `mcp-property/backfill_embeddings.py` manually whenever you're ready

Either way, structured search (price/beds/baths/city) works
immediately regardless of embedding status — only semantic search (the
`query` parameter) needs embeddings to actually rank results.

Running the scripts directly on your host instead of through Docker
works too, as long as `pip install -r requirements.txt -r ../mcp-property/requirements.txt`
has been run and `DATABASE_URL` in `.env` points at `localhost:5432`.

## Phase 5 (later) — recurring Realtor.com / Redfin pull

The cron job that re-pulls Realtor.com Data Library and Redfin Data
Center files on their weekly/monthly cadence into `market_stats`
(see A-06's update-cadence notes) gets added here in Phase 5.
