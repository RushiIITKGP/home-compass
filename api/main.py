"""
FastAPI gateway: POST /chat streams the agent's turn as SSE events, in
order: {thread_id} once, {status} lines as nodes run, {token} chunks
from user-facing LLM calls, possibly one {replace} (compliance revised
after streaming), then {done} with scores + recommendations.
"""

from __future__ import annotations

import json
import os
import uuid
from contextlib import asynccontextmanager
from typing import Optional

from dotenv import load_dotenv

load_dotenv()  # must run before imports below that read env at import time

# Tracing enabled without a key would spam upload failures — disable cleanly.
if os.environ.get("LANGCHAIN_TRACING_V2", "").lower() == "true" and not (
    os.environ.get("LANGCHAIN_API_KEY") or os.environ.get("LANGSMITH_API_KEY")
):
    os.environ["LANGCHAIN_TRACING_V2"] = "false"
    print(
        "[observability] LANGCHAIN_TRACING_V2=true but no LANGCHAIN_API_KEY set — "
        "tracing disabled for this run. Get a free key at https://smith.langchain.com"
    )

from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from langchain_core.messages import HumanMessage  # noqa: E402
from pydantic import BaseModel  # noqa: E402
from sse_starlette.sse import EventSourceResponse  # noqa: E402

from setup import agent_graph  # noqa: E402

# Only stream tokens from user-facing nodes — the others would leak
# structured-output JSON or tool-call internals.
STREAMABLE_NODES = {"clarify", "present"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with agent_graph() as graph:
        app.state.graph = graph
        yield


app = FastAPI(title="Home Compass", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten to the real frontend origin once deployed
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str
    thread_id: Optional[str] = None


async def stream_chat(app: FastAPI, message: str, thread_id: str):
    graph = app.state.graph
    config = {
        "configurable": {"thread_id": thread_id},
        "run_name": "home-compass-turn",
        "metadata": {"thread_id": thread_id},  # groups LangSmith's Threads view
    }

    yield json.dumps({"thread_id": thread_id})

    streamed_text = ""
    async for mode, chunk in graph.astream(
        {"messages": [HumanMessage(content=message)]},
        config=config,
        stream_mode=["custom", "messages"],
    ):
        if mode == "custom":
            status = chunk.get("status") if isinstance(chunk, dict) else None
            if status:
                yield json.dumps({"status": status})
        elif mode == "messages":
            message_chunk, metadata = chunk
            if metadata.get("langgraph_node") in STREAMABLE_NODES:
                text = message_chunk.text
                if text:
                    streamed_text += text
                    yield json.dumps({"token": text})

    final_state = await graph.aget_state(config)
    values = final_state.values
    final_messages = values.get("messages", [])
    final_text = final_messages[-1].text if final_messages else ""

    if not streamed_text and final_text:
        # Fallback answers never streamed — send once so the bubble isn't empty.
        yield json.dumps({"token": final_text})
    elif final_text and final_text != streamed_text:
        # Compliance revised the draft after it streamed — swap the bubble.
        yield json.dumps({"replace": final_text})

    yield json.dumps({
        "done": True,
        "confidence_score": values.get("confidence_score", 0.0),
        "missing_slot": values.get("missing_slot"),
        "recommendations": values.get("recommendations", []),
        "answer_confidence": values.get("answer_confidence"),
    })


@app.post("/chat")
async def chat(request: ChatRequest):
    thread_id = request.thread_id or str(uuid.uuid4())
    # sep="\n" (not sse-starlette's CRLF default) to match the frontend's
    # hand-parsed "data: {...}\n\n" SSE wire format in web/lib/streamChat.ts.
    return EventSourceResponse(stream_chat(app, request.message, thread_id), sep="\n")


@app.get("/health")
async def health():
    return {"status": "ok"}
