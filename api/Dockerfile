# API image — the FastAPI + LangGraph agent.
#
# Self-contained: it spawns the three MCP servers as stdio subprocesses
# internally (exactly like local dev via api/setup.py), so this one
# image carries all the code and dependencies they need. Fewer moving
# parts than networking four separate containers together — the right
# tradeoff for a shareable, one-command app.
#
# Build context is the repo root (see docker-compose.yml) so the image
# can include the shared db/ package, the mcp-*/ servers, and compliance/.

FROM python:3.11-slim

WORKDIR /app

# Install every requirement the API + its spawned MCP servers need, in
# one layer. Copy just the requirements files first so Docker can cache
# this step and skip re-installing when only source code changes.
COPY requirements.txt ./requirements.txt
COPY api/requirements.txt ./api/requirements.txt
COPY mcp-property/requirements.txt ./mcp-property/requirements.txt
COPY mcp-enrich/requirements.txt ./mcp-enrich/requirements.txt
COPY mcp-market/requirements.txt ./mcp-market/requirements.txt
RUN pip install --no-cache-dir \
    -r requirements.txt \
    -r api/requirements.txt \
    -r mcp-property/requirements.txt \
    -r mcp-enrich/requirements.txt \
    -r mcp-market/requirements.txt \
    langchain-ollama>=0.2.0

# Now the code (changes here don't bust the dependency cache above).
COPY db ./db
COPY compliance ./compliance
COPY mcp-property ./mcp-property
COPY mcp-enrich ./mcp-enrich
COPY mcp-market ./mcp-market
COPY api ./api

WORKDIR /app/api
EXPOSE 8080
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
