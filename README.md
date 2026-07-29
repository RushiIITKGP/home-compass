# Home Compass

An AI real estate agent that says how sure it is before it recommends anything.

You chat with it about the home you want. Instead of guessing, it first
gathers your criteria (budget, location, beds, timeline) and shows a
live confidence score — only searching once it actually understands what
you're looking for. Results come back as ranked listing cards, each with
a **fit** score, and every answer is checked against a compliance
rulebook and graded for how well it's grounded in real data.

Built to learn AI engineering end to end: a LangGraph agent, MCP tool
servers, RAG, evals, tracing, and guardrails.

## How it works

A message flows through a graph of steps:

```
intake → confidence → (clarify | search) → rank results → write answer → compliance check → score
```

- **Agent:** LangGraph state machine (`api/agent.py`)
- **Tools:** three MCP servers — property search (Postgres + pgvector),
  neighborhood enrichment (US Census + FBI APIs), and market data
- **Model:** any provider via one env var (Groq, Gemini, or local Ollama)
- **Embeddings:** local, via Ollama
- **Guardrail:** RAG over a rules PDF checks every answer
- **Frontend:** Next.js chat UI with live streaming

## Tech stack

Python · FastAPI · LangGraph · LangChain · MCP · PostgreSQL + pgvector ·
Ollama · Next.js · TypeScript · Docker

## Run it (Docker)

**Prerequisites:** [Docker](https://www.docker.com/products/docker-desktop)
and [Ollama](https://ollama.com), then `ollama pull nomic-embed-text`.

```bash
# 1. configure — paste a free Groq key (https://console.groq.com)
cp .env.example .env

# 2. set up the database and load sample listings
docker compose up -d postgres
docker compose run --rm tools python db/create_tables.py
docker compose run --rm tools python ingest-worker/seed_kaggle.py --limit 5000

# 3. start everything
docker compose up --build
```

Then open **http://localhost:3000**.
