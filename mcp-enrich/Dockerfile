# Build context is the repo root (see docker-compose.yml), so this image
# can include both the shared `db` package and this service's own code.

FROM python:3.11-slim

WORKDIR /app

COPY mcp-enrich/requirements.txt ./mcp-enrich/requirements.txt
RUN pip install --no-cache-dir -r mcp-enrich/requirements.txt

COPY db ./db
COPY mcp-enrich ./mcp-enrich

ENV MCP_TRANSPORT=streamable-http
ENV MCP_PORT=8001
EXPOSE 8001

CMD ["python", "mcp-enrich/server.py"]
