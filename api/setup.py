"""
Assembles the agent stack in one place: chat model (via llm.py's
factory), the three MCP servers, the compliance rule retriever, and
the Postgres checkpointer. Used by api/main.py so provider wiring
can't drift.
"""

from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

sys.path.append(str(Path(__file__).resolve().parent))  # api/, for agent.py + llm.py
sys.path.append(str(Path(__file__).resolve().parents[1]))  # repo root, for compliance/

from agent import build_graph  # noqa: E402
from llm import build_chat_model  # noqa: E402
from compliance.retriever import build_rule_retriever  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+psycopg://homecompass:homecompass@localhost:5432/homecompass",
)
# The checkpointer wants a plain postgresql:// URL, not the SQLAlchemy dialect string.
CHECKPOINTER_DSN = DATABASE_URL.replace("postgresql+psycopg://", "postgresql://")


@asynccontextmanager
async def agent_graph():
    """Yields a compiled, ready-to-use graph. MCP servers are spawned as
    stdio subprocesses — fine for local development."""
    servers = {
        name: {
            "command": sys.executable,
            "args": [str(REPO_ROOT / directory / "server.py")],
            "transport": "stdio",
        }
        for name, directory in (
            ("property", "mcp-property"),
            ("enrich", "mcp-enrich"),
            ("market", "mcp-market"),
        )
    }
    mcp_client = MultiServerMCPClient(servers)
    tools = await mcp_client.get_tools()

    # Task-based routing (api/llm.py): fast_llm for cheap/simple nodes,
    # smart_llm anywhere a wrong call is expensive. See CHAT_MODEL_FAST /
    # CHAT_MODEL_SMART in .env.example.
    fast_llm = build_chat_model(role="fast", temperature=0.2)
    smart_llm = build_chat_model(role="smart", temperature=0.2)
    print(f"[llm] fast={type(fast_llm).__name__} smart={type(smart_llm).__name__}")

    # Guardrail is on only when rules are ingested — and always says which.
    rule_retriever = build_rule_retriever()
    if rule_retriever is None:
        print(
            "[compliance] guardrail OFF — no rules ingested (run "
            "compliance/generate_rules_pdf.py then compliance/ingest_rules.py)"
        )
    else:
        print("[compliance] guardrail ON — answers are checked against the ingested rulebook")

    async with AsyncPostgresSaver.from_conn_string(CHECKPOINTER_DSN) as checkpointer:
        await checkpointer.setup()  # idempotent
        yield build_graph(fast_llm, smart_llm, tools, checkpointer=checkpointer, rule_retriever=rule_retriever)
