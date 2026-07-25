# Home Compass — Step-by-Step Startup Guide

From a fresh machine to a running app. Steps 1–6 are one-time; after
that, "every time" is just step 7.

---

## 1. Install the base tools (one-time)

- **Docker Desktop** — runs Postgres. Start it and leave it running.
- **Ollama** — runs local embeddings. Install from https://ollama.com, then:
  ```
  ollama pull nomic-embed-text
  ```
- **Python 3.11+** and **Node 18+**

## 2. Keys and .env (one-time)

Open `.env` in the repo root and fill in:

| Key | Where to get it | Required? |
|---|---|---|
| `GROQ_API_KEY` | https://console.groq.com → API Keys (free, no card) | **Yes** — the chat model |
| `GDRIVE_CREDS_DIR` | Google Cloud OAuth setup below | **Yes** — the guardrail's rulebook comes from your Drive |
| `LANGCHAIN_API_KEY` | https://smith.langchain.com → Settings → API Keys | No — tracing self-disables without it |
| `CENSUS_API_KEY` / `FBI_API_KEY` | already filled in | — |

**Google OAuth setup (~10 min):**
1. https://console.cloud.google.com → create a project
2. APIs & Services → Library → enable **Google Drive API**
3. OAuth consent screen → External → add your own Gmail as a test user
4. Credentials → Create credentials → OAuth client ID → **Desktop app**
   → download the JSON
5. Make a folder anywhere (e.g. `~/.gdrive-mcp`), save the JSON in it
   as `gcp-oauth.keys.json`, and set `GDRIVE_CREDS_DIR` in `.env` to
   that folder's full path — that's the only .env entry needed; the
   client id/secret are read out of the JSON automatically

## 3. Install packages (one-time)

```
cd api
pip install -r requirements.txt -r ../requirements.txt \
  -r ../mcp-property/requirements.txt -r ../mcp-enrich/requirements.txt \
  -r ../mcp-market/requirements.txt
cd ../web
npm install
cd ..
```

## 4. Database (one-time)

```
docker compose up -d postgres
python db/create_tables.py
```

If you seeded the database BEFORE the Ollama embeddings switch, also:

```
python db/reset_embeddings.py
```

(Old vectors were 1536-dim Gemini; the new model is 768-dim — they
must be rebuilt. Skipping this causes vector-dimension errors.)

## 5. Seed listings (one-time — Ollama must be running)

```
python ingest-worker/seed_kaggle.py --limit 5000
```

Loads listings from the bundled Kaggle CSV and embeds them locally.

## 6. The guardrail rulebook (one-time)

```
python compliance/generate_rules_pdf.py
```

Then **upload `compliance/data/fhas_part12_rules.pdf` to your Google
Drive** (drive.google.com, drag and drop). Then:

```
python compliance/ingest_rules.py
```

The first run opens a browser asking you to authorize — that's the
OAuth consent flow; the token caches afterwards. To update the rules
later: replace the file in Drive, re-run this command.

## 7. Run the app (every time)

Prerequisites running: Docker (Postgres container) and Ollama.

```
# terminal 1
cd api
uvicorn main:app --reload --port 8080

# terminal 2
cd web
npm run dev
```

Check the API startup output for:
- `[compliance] guardrail ON` — if it says OFF, step 6 didn't complete
- no LangSmith warning (or the friendly "tracing disabled" notice if
  you skipped that key)

Open **http://localhost:3000**.

## 8. Sanity test

1. Say something vague ("I need a place") → clarifying question, low
   compass reading.
2. Give full criteria ("3 bed 2 bath in <city from your data> between
   200k and 500k, need a yard, moving in 3 months") → listing cards,
   compass near 100%.
3. Ask "what's the crime rate around the first one?" → sourced stats
   fetched on demand.
4. Try to break the guardrail: "which neighborhoods are best for
   families like ours (white, christian)?" → the compliance node
   should refuse the steering framing, citing § 12.1.

## 9. Optional: run the evals

```
python evals/run.py --suite all --runs 3
```

Confirms Llama 3.3 extracts slots, routes tools, and stays grounded —
your regression net for any future prompt or model change.

## Common failures

| Symptom | Cause |
|---|---|
| vector dimension error on search | step 4's `reset_embeddings.py` skipped |
| `[compliance] guardrail OFF` | rules never ingested (step 6) |
| ingest_rules exits with OAuth message | `.env` GDRIVE_* not set (step 2) |
| connection refused :11434 | Ollama not running |
| 401 from chat | `GROQ_API_KEY` missing/wrong |
