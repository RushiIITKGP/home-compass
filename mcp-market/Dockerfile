# Build context is the repo root (see docker-compose.yml), so this image
# can include both the shared `db` package and this service's own code.

FROM python:3.11-slim

WORKDIR /app

COPY mcp-market/requirements.txt ./mcp-market/requirements.txt
RUN pip install --no-cache-dir -r mcp-market/requirements.txt

COPY db ./db
COPY mcp-market ./mcp-market

ENV MCP_TRANSPORT=streamable-http
ENV MCP_PORT=8002
EXPOSE 8002

CMD ["python", "mcp-market/server.py"]
