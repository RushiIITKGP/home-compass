# Build context is the repo root (see docker-compose.yml), so this image
# can include the shared `db` package, this service's own code, and
# mcp-property's embedding logic (seed_kaggle.py now auto-backfills
# embeddings after seeding, reusing mcp-property/backfill_embeddings.py
# rather than duplicating it).

FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY mcp-property/requirements.txt ./mcp-property/requirements.txt
RUN pip install --no-cache-dir -r mcp-property/requirements.txt

COPY db ./db
COPY ingest-worker ./ingest-worker
COPY mcp-property ./mcp-property

# Overridden per-run via `docker compose run ingest-worker python <script>`
# — see README.md for the Phase 1 commands (create_tables.py, then
# seed_kaggle.py, which now embeds automatically unless you pass
# --skip-embeddings). No default long-running process yet; the cron
# scheduling for the recurring Realtor.com/Redfin pulls is Phase 5.
CMD ["python", "ingest-worker/seed_kaggle.py"]
