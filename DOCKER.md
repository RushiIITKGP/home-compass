# Running Home Compass with Docker

The whole app in a few commands. Docker packages the code + its exact
environment, so this works the same on any machine — no Python/Node/
Postgres version juggling.

## Prerequisites (the two things Docker can't bundle)

1. **Docker Desktop** — https://www.docker.com/products/docker-desktop
2. **Ollama** (for embeddings, runs on your machine, not in a container)
   — https://ollama.com then:
   ```
   ollama pull nomic-embed-text
   ```
   Leave Ollama running. (To also run the chat model locally instead of
   Groq: `ollama pull qwen3.5:9b` and set `CHAT_MODEL=ollama:qwen3.5:9b`.)

## 1. Configure

```
cp .env.example .env
```
Then edit `.env` and paste a free Groq API key (from
https://console.groq.com — no credit card). That's the only required
one. The Census/FBI keys unlock neighborhood data; LangSmith unlocks
tracing; both optional.

## 2. Start the database and load data (one time)

```
docker compose up -d postgres
docker compose run --rm tools python db/create_tables.py
docker compose run --rm tools python ingest-worker/seed_kaggle.py --limit 5000
```
The seed step embeds listings via your local Ollama, so it must be
running. (The compliance guardrail is optional and needs Google Drive
OAuth — see compliance/README.md; skip it and the app runs fine with
the guardrail OFF.)

## 3. Start everything

```
docker compose up --build
```
First run builds the images (a few minutes); later runs are fast. Then
open:

- **http://localhost:3000** — the app
- **http://localhost:8081** — Adminer, to browse the database
  (System *PostgreSQL*, Server `postgres`, user/pass/db `homecompass`)

Stop with Ctrl-C, or `docker compose down`. Add `-v` to also wipe the
database volume for a clean slate.

## What's running

| Service  | Port | What it is |
|----------|------|------------|
| web      | 3000 | Next.js frontend |
| api      | 8080 | FastAPI + LangGraph agent (spawns the MCP servers inside itself) |
| postgres | 5432 | Database with pgvector |
| adminer  | 8081 | Web DB viewer |

## Notes & gotchas

- **Ollama on the host:** the API container reaches it at
  `host.docker.internal` (already set in compose). If embeddings fail
  with a connection error, confirm Ollama is running on your machine.
- **Secrets:** `.env` is gitignored and never baked into an image —
  each person supplies their own keys. Share `.env.example`, not `.env`.
- **The frontend's API URL** is baked in at build time as
  `http://localhost:8080` (the browser calls it from your machine). To
  serve to other devices, rebuild web with
  `NEXT_PUBLIC_API_URL=http://<your-ip>:8080`.
- **No Docker?** The non-Docker path is in STARTUP.md.
