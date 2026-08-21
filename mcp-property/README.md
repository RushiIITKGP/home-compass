# mcp-property

Property Search MCP server — hybrid SQL prefilter + pgvector rerank
over the `listings` table. See architecture sheets A-03, A-06, A-08.

## Tools

- **`search_listings`** — structured filters (price, beds, baths,
  city, state), plus an optional free-text `query` that reranks
  results by semantic similarity against listing descriptions
- **`get_listing_details`** — full record for one listing by ID

## Known-fixed bug: structured filters used to get silently zeroed out

If the agent passed a free-text `query` (even something as simple as
"house") while `listing_embeddings` was empty or incomplete — the
normal state before you've run `backfill_embeddings.py` — every result
was silently dropped, *including listings that matched every structured
filter perfectly*. The cause: an inner join against the embeddings
table. Fixed to a left join, so structured filters always work
regardless of backfill status; listings with an embedding still rank
first by semantic similarity, listings without one are included rather
than excluded. City matching was also tightened to strip trailing
state/country text (`"Adjuntas, PR"` → `"Adjuntas"`) before matching,
so natural-language variation in what the LLM passes doesn't silently
return zero results either.

## Try it standalone (no agent needed)

Fill in `DATABASE_URL` and (for semantic search) `GEMINI_API_KEY` in
the repo-root `.env` — `server.py` now loads it automatically, no
`export` needed:

```
pip install -r requirements.txt -r ../requirements.txt

npx @modelcontextprotocol/inspector python server.py
```

This opens the MCP Inspector, where you can call `search_listings`
directly and see real results from Phase 1's seeded data.

## Semantic search setup

Structured filtering (price/beds/baths/city/state) works immediately
against seeded listings — no extra setup, and it's never blocked by
missing embeddings (see the fix note above). The `query` parameter
needs embeddings to exist to actually rank results semantically.

**As of this build, `ingest-worker/seed_kaggle.py` runs this
automatically** after seeding — you don't need to run it by hand every
time you add listings. This script still exists for manual catch-up
(e.g. you seeded with `--skip-embeddings`, or added listings some other
way):

```
python backfill_embeddings.py --limit 500
```

Already-embedded listings are always skipped, whether triggered
automatically by seeding or run manually here — safe to re-run anytime.

This synthesizes a short description for each listing (Kaggle's data
has no free-text description field) and embeds it via Gemini's
embedding model — the same `GEMINI_API_KEY` used everywhere else in
this project, no separate provider or key. See `embeddings.py`.

## Running in Docker

```
docker compose up mcp-property
```

Runs the same server over streamable HTTP on port 8000 instead of
stdio, which is how `api` will reach it from Phase 4 onward.
