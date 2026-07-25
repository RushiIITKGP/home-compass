# Build context is the repo root (see docker-compose.yml), so this image
# can include both the shared `db` package and this service's own code.

FROM python:3.11-slim

WORKDIR /app

COPY mcp-property/requirements.txt ./mcp-property/requirements.txt
RUN pip install --no-cache-dir -r mcp-property/requirements.txt

COPY db ./db
COPY mcp-property ./mcp-property

ENV MCP_TRANSPORT=streamable-http
ENV MCP_PORT=8000
EXPOSE 8000

CMD ["python", "mcp-property/server.py"]
