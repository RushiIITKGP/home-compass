# Home Compass — AI Real Estate Agent

An AI real estate agent chatbot built with LangGraph, FastAPI, PostgreSQL +
pgvector, and a set of MCP tool servers for listings, market data, and
neighborhood enrichment. The agent gathers a user's needs, computes a
confidence score before recommending anything, and returns sourced
listing + neighborhood recommendations.

This repo is being built following the phased roadmap in the architecture
doc ("Home Compass — Architecture Drawing Set", sheet **A-10**). Each
phase adds one working, testable piece. This commit covers **Phases 0–6**
— the full stack now works end to end, in a browser.

**No cloud LLM lock-in:** the chat model is chosen by `CHAT_MODEL` in
`.env` (format `provider:model`) via the factory in `api/llm.py` —
currently Groq's free `llama-3.3-70b-versatile` — and **embeddings run
locally via Ollama** (`nomic-embed-text`, 768 dims; `ollama pull
nomic-embed-text` once). Gemini is no longer required anywhere; it
remains only as an optional chat fallback. If you change the embedding
model, rebuild vectors: `python db/reset_embeddings.py`, then re-run
`backfill_embeddings.py` and `compliance/ingest_rules.py`.

**Context window management (A-04):** every LLM call trims the message
history to the last `CONTEXT_WINDOW_TURNS` turns (default 8) rather
than replaying the full conversation — see `api/agent.py`'s
`_recent_messages()` and `api/README.md`. What the user stated earlier
isn't lost: it was already captured into structured `slots` at the
time and persists via the checkpointer independent of message trimming.

## What's here right now

**Phase 0 — infra scaffold** · **Phase 1 — database layer** · **Phase 2
— property search** · **Phase 3 — the core agent** · **Phase 4 — HTTP
gateway** · **Phase 5 — full enrichment** (all documented in earlier
sections of this README's history — see `api/`, `mcp-*/`, `db/`,
`ingest-worker/`)

**Phase 6 — frontend**
- `web/` — Next.js + Tailwind chat UI: streams the conversation over
  SSE, shows a compass-needle confidence gauge (always visible, not
  left to the agent's prose), and renders listing cards — with
  per-field source citations (Census, FBI, Redfin/Realtor.com) once
  you actually ask about a listing's demographics, safety, or market
  trends; a plain search shows the listings themselves, nothing more
  (see `api/README.md`'s "Search returns exactly what was asked for")

## Quick start — the whole stack

For a full walkthrough with troubleshooting, see **[RUNNING.md](./RUNNING.md)**.
For a distilled checklist of exactly what you need to do by hand (vs.
what happens automatically), see **[SETUP_CHECKLIST.md](./SETUP_CHECKLIST.md)**.
For a record of the most recent full-project verification pass — what
was tested, what was found and fixed — see **[AUDIT_REPORT.md](./AUDIT_REPORT.md)**.
Short version:

1. Copy env templates:
   ```
   cp .env.example .env
   cp web/.env.local.example web/.env.local
   ```
   Fill in `GEMINI_API_KEY` (chat + embeddings), and — for full
   enrichment — `CENSUS_API_KEY` / `FBI_API_KEY` (free, sign-up links
   in `.env.example`).
2. Database:
   ```
   docker compose up postgres
   docker compose run --rm ingest-worker python db/create_tables.py
   docker compose run --rm ingest-worker python ingest-worker/seed_kaggle.py --limit 5000
   ```
   (embeddings for semantic search are generated automatically as part
   of this last command — no separate backfill step needed)
3. Backend (reads `GEMINI_API_KEY` etc. straight from `.env` — no `export` needed):
   ```
   cd api
   pip install -r requirements.txt -r ../requirements.txt \
     -r ../mcp-property/requirements.txt -r ../mcp-enrich/requirements.txt -r ../mcp-market/requirements.txt
   uvicorn main:app --reload --port 8080
   ```
4. Frontend, in another terminal:
   ```
   cd web
   npm install
   npm run dev
   ```
5. Open http://localhost:3000 and have the conversation — vague input
   should get a clarifying question with a low compass reading; full
   criteria should get listing cards and a confidence near 100%. Then
   ask about one of them — "what's the crime rate there?" — and watch
   the agent fetch and cite that specific data on demand, rather than
   having pre-fetched everything up front.

That full conversation working entirely in the browser is the Phase 6
"done when" check from A-10.

## Project structure

```
home-compass/
├── docker-compose.yml
├── db/, ingest-worker/          → Phases 0–1
├── mcp-property/                → Phase 2
├── mcp-enrich/, mcp-market/, mcp-amenities/  → Phase 5
├── api/                          → Phases 3–5 (agent, gateway)
└── web/                          → Phase 6 (frontend)
    ├── app/                       → chat page, layout, design tokens
    ├── components/                → CompassGauge, ChatMessage, ListingCard, ChatInput
    └── lib/                       → SSE client, shared types
```

## Observability (Phase 7, part 1)

LangSmith tracing is wired in and controlled entirely from `.env` —
see the Observability block there for setup (free key from
https://smith.langchain.com). Once the key is set, every chat turn
shows up as a `home-compass-turn` trace: the full graph-node tree,
every prompt/response verbatim, tool calls with arguments, and
latency + token counts per call. Conversations group together in
LangSmith's Threads view via the `thread_id` metadata set in
`api/main.py`. Without a key, tracing self-disables at startup with a
console notice instead of spamming upload warnings.

Note on the slots: `property_type` no longer gates retrieval — the
seed dataset has no property-type column, so the answer couldn't
change search results; it's still extracted and folded into the
semantic query when stated. `timeline` (and the other slots) now feed
the present step's prompt so answers are framed to the user's urgency.

## Compliance guardrail (RAG)

Every answer is checked against an ingested rulebook before delivery —
a fictional government-style PDF of conduct rules for AI real-estate
advisors (no steering by protected class, sourced statistics only, no
investment promises, ...), chunked by rule section, embedded into
pgvector, and retrieved per-answer for a structured compliance verdict
that can revise the draft. Setup, design notes (fail-open vs
fail-closed, streaming vs revision), and red-team prompts to try:
**[compliance/README.md](./compliance/README.md)**.

## Roadmap

The full phase-by-phase plan, with a "done when" checkpoint for each
phase, lives in the architecture doc's sheet A-10.

**Next up: rest of Phase 7 — the full 8-container Docker Compose — then an eval harness.**
