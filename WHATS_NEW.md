# What We Added — Plain-English Summary

Everything added to Home Compass since the original version, in the
order we built it, with the new files each change brought.

---

## 1. Fixed the "fake" questions (slot fix)

**The problem:** the agent asked "house or condo?" and "what's your
timeline?" — but the answers changed nothing. The dataset has no
property-type column, so that answer could never affect search. And
timeline was collected but never looked at again.

**What we did:** property type no longer counts toward the confidence
score (it's still noted and folded into the semantic search text).
Timeline and all other criteria are now given to the answer-writing
step, so replies are framed around your urgency.

**Files changed:** `api/agent.py`

---

## 2. Tracing (seeing inside the agent)

**What it is:** with a free LangSmith key in `.env`, every chat turn
appears as a tree in LangSmith: every graph step, every exact prompt
and response, every tool call, with timing and token counts. Whole
conversations group together in their Threads view.

**Why it matters:** when the agent does something weird, you open the
trace and see exactly which step went wrong instead of guessing.

**Files changed:** `api/main.py` (metadata + a guard so a missing key
doesn't spam warnings), `.env`, `README.md`

---

## 3. Eval harness (tests for AI behavior)

**What it is:** normal tests check code; evals check *model behavior*.
`evals/` has 23 scripted scenarios in four suites: does the math of
the confidence score hold (exact checks), does the model extract
criteria correctly ("3 bed in Austin under 500k" → the right slots),
does it make the right decision (clarify vs search, and which tool),
and does it invent facts (an LLM "judge" grades the answer against the
data it was given).

**Why it matters:** when you edit a prompt or swap models, run
`python evals/run.py --suite all --runs 3` and see what broke —
before a user does. The searches run against fake in-memory tools, so
no database is needed.

**New files:** `evals/run.py`, `evals/cases.py`, `evals/fake_tools.py`,
`evals/README.md`

---

## 4. Free chat model (Groq) + one-line model switching

**What it is:** the chat model is no longer hard-coded to Gemini.
A small factory (`api/llm.py`) reads `CHAT_MODEL` from `.env` —
currently `groq:llama-3.3-70b-versatile`, Groq's free tier (sign up at
console.groq.com, no card, ~1,000 requests/day). Switch providers by
editing one line in `.env`; the API, CLI, and evals all follow.

**Why it matters:** teaches provider abstraction — and lets you run
the eval suite under two models and compare, a zero-code bake-off.

**New file:** `api/llm.py` · **Changed:** `api/setup.py`,
`evals/run.py`, `.env`, `api/requirements.txt`

---

## 5. Compliance guardrail (RAG over a rules PDF)

**What it is:** a 7-page government-style rulebook PDF (fictional, but
modeled on real fair-housing law): no steering by race/religion/family
status, statistics must carry sources, no investment promises, no
invented listing details, privacy rules, "I'm an AI" disclosure.

The PDF is split into its numbered rules, each rule is embedded and
stored in the database. Before any answer reaches you, a new
"compliance" step in the graph pulls the 4 most relevant rules and has
the LLM check the draft against them. If it violates a rule, the draft
is replaced with a compliant version that cites the rule number — and
since the draft may have already streamed to the browser, a new
`replace` event swaps the chat bubble's text.

**Why it matters:** this is the "RAG as guardrail" pattern — the
rulebook can grow or be swapped for the real HUD regulations without
touching prompts. Try to break it with the red-team prompts in
`compliance/README.md`.

**New files:** `compliance/generate_rules_pdf.py`,
`compliance/data/fhas_part12_rules.pdf`, `compliance/ingest_rules.py`,
`compliance/retriever.py`, `compliance/README.md` ·
**Changed:** `db/models.py` (new table), `api/agent.py` (new node),
`api/setup.py`, `api/main.py`, `web/lib/types.ts`, `web/app/page.tsx`

---

## 6. Local embeddings (Ollama) — no Gemini needed anywhere

**What it is:** the semantic-search embeddings (listings + rules) now
come from `nomic-embed-text` running locally in Ollama instead of
Gemini's API. Free forever, no key, no rate limits. Gemini is now
purely an optional fallback chat provider.

**The catch (worth understanding):** vectors from different models
live in different mathematical spaces, so every stored embedding had
to be rebuilt — `db/reset_embeddings.py` drops and recreates the
vector tables at the new size (768 instead of 1536), then you re-run
the backfill and ingestion scripts.

**Changed:** `mcp-property/embeddings.py`, `db/models.py` ·
**New:** `db/reset_embeddings.py`

---

## 7. Google Drive connection (via MCP)

**What it is:** the rules PDF lives in your Google Drive — that's the
only ingestion source (no local-folder path). `compliance/drive_fetch.py`
connects to Drive using
a third-party MCP server (`@isaacphi/mcp-gdrive`) through the exact
same client machinery the project already uses for its own MCP servers
— which is the lesson: to an agent, "your Google Drive" and "your own
database" look identical once each is behind an MCP server.

Needs a one-time ~10-minute Google OAuth setup (steps in
`compliance/README.md`), then:
`python compliance/ingest_rules.py --from-drive "fhas_part12_rules"`.

**New file:** `compliance/drive_fetch.py` · **Changed:**
`compliance/ingest_rules.py`, `.env`, `compliance/README.md`

---

## What you learned along the way

Slot design honesty · tracing/observability · evals (deterministic
scorers, trajectory checks, LLM-as-judge, flakiness) · provider
abstraction and model routing · RAG for guardrails (structure-aware
chunking, retrieval at answer time, fail-open vs fail-closed,
streaming vs revision) · local embedding models and why migrations
force re-embedding · MCP as a universal connector, including OAuth to
a third-party service.

## To get it all running

```
ollama pull nomic-embed-text                      # local embeddings
pip install langchain-groq langchain-ollama       # new deps
# .env: GROQ_API_KEY (console.groq.com), LANGCHAIN_API_KEY (smith.langchain.com)
python db/create_tables.py
python db/reset_embeddings.py
python mcp-property/backfill_embeddings.py --limit 0
python compliance/generate_rules_pdf.py           # then upload the PDF to your Google Drive
python compliance/ingest_rules.py                 # fetches from Drive (OAuth setup required first)
python evals/run.py --suite all --runs 3          # regression check
```
