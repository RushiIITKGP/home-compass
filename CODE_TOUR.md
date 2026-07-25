# Code Tour — How to Read This Entire Project

Read in this order. Each stop builds on the previous one, and each has
a "you understand it when" check — don't move on until you can answer
it without looking. Total: ~15 files of real code, 5 sittings.

The single best companion trick: keep a LangSmith trace of one real
conversation open in a browser tab the whole time. The trace is the
runtime story; the files are the script. Match them line by line.

---

## Sitting 1 — The data layer (what exists)

Every system is nouns + verbs. Start with the nouns.

**1. `db/models.py`** — the schema. Read every class docstring; they
say which service writes each table. Notice: `Listing` vs
`ListingEmbedding` (why a separate table?), `ComplianceRule` keeps its
embedding inline (the comment says why the difference), and
`EMBEDDING_DIM` is env-driven (the Ollama migration).
*You understand it when:* you can draw the tables and their foreign
keys from memory, and explain why changing the embedding model forces
`reset_embeddings.py`.

**2. `db/session.py` + `db/create_tables.py`** — tiny; how a
connection and the tables come to exist. Note the import-time engine
creation (it bit us once in the sandbox).

**3. `ingest-worker/seed_kaggle.py`** — how listings get in. Worth
noting: the state-name normalization map (defensive data cleaning) and
that it calls the embedding backfill at the end.

**4. `mcp-property/embeddings.py`** — 50 lines that carry the whole
semantic-search concept: one model, two prefixes
(`search_document:` / `search_query:`), asymmetric retrieval. Read the
migration note in the docstring.
*Check:* why do documents and queries get different prefixes?

---

## Sitting 2 — The tools (what the agent can do)

**5. `mcp-property/server.py`** — the most instructive server. Focus
on `_build_search_query`: hybrid retrieval = structured SQL filters +
optional vector rerank, in one statement. Note the two short why-notes —
the LEFT join (listings without embeddings must still match) and the
city-name suffix stripping — both are fixes for real bugs this project
shipped with.
*Check:* what happens to a listing with no embedding when a semantic
query is used? Why?

**6. `mcp-enrich/server.py`** — pattern: wrap a government API, cache
in Postgres, fail soft with `{"error": ...}`. The FBI section is a
museum of this conversation: `probe_fbi.py`, the format fallbacks,
counts-vs-rates, partial years. Read `_find_time_series` — defensive
parsing of an API that restructures itself.

**7. `mcp-market/server.py`** — quick read; serves batch-loaded data,
never calls sources live. Note the honesty `note` field about
sale-vs-list price.
*Check:* why do these run as separate processes speaking MCP instead
of being functions imported by the agent?

---

## Sitting 3 — The agent (the heart)

**8. `api/llm.py`** — the provider factory. Small file, big idea:
exactly one place where providers are chosen. Note `_EXTRA_PROVIDERS`
(escape hatch for init_chat_model's registry) and the Ollama
`num_ctx` guard.

**9. `api/agent.py`** — THE file. Read it in this order, not top to
bottom:
   a. `AgentState` — the data flowing between nodes. Everything else
      reads/writes this.
   b. `SLOT_WEIGHTS` + `compute_confidence` + `gate` — the
      deterministic core. Why deterministic? (The comment answers.)
   c. `ExtractedSlots` + `merge_slots` + `intake_node` — structured
      output, string-coercion validators (the Groq lesson), slot
      accumulation across turns.
   d. `clarify_node` — the low-confidence path.
   e. `retrieve_node` + `route_after_retrieve` + `route_after_tools`
      — the LLM-decides-tools turn and the two routing functions.
      Design note worth knowing: enrichment used to run automatically
      after every search and was deliberately removed — a search
      returns exactly what was asked; neighborhood data is fetched
      only when the user asks about it.
   f. `compute_fit` + `synthesis_node` — fit vs confidence, graded
      not binary, weight redistribution.
   g. `present_node` + `_fallback_summary` + `extract_text_content` —
      the answer, and two layers of defense against empty/weird LLM
      output.
   h. `make_compliance_node` — the RAG guardrail. Fail-open comment
      is the key design decision.
   i. `make_score_node` — answer confidence: judge + deterministic
      components, weight redistribution.
   j. `build_graph` — NOW read the wiring. Every edge should feel
      inevitable after a–i. Compare against the diagram we made.
*Check:* trace "3 bed in Ponce under 200k" through every node on
paper, then verify against a real LangSmith trace. They must match.

**10. `api/setup.py`** — how llm + MCP servers + checkpointer +
retriever assemble into a graph, and how the guardrail announces
ON/OFF at startup instead of degrading silently.

**11. `api/main.py`** — the HTTP/SSE gateway. Read the module
docstring (it documents the event protocol), then `stream_chat`:
which nodes stream (`STREAMABLE_NODES` — why not all?), the
empty-stream fallback, and the `replace` event (compliance revised
after streaming — the streaming-vs-guardrail tension).
*Check:* why does the frontend need a `replace` event at all?

---

## Sitting 4 — The frontend (how it reaches a human)

**12. `web/lib/types.ts`** — mirrors the SSE protocol; fast read.
**13. `web/lib/streamChat.ts`** — hand-parsing SSE from a POST fetch;
the buffer-splitting comment is the interesting bit.
**14. `web/app/page.tsx`** — one state machine: how each event type
mutates the messages array. This is the client half of main.py.
**15. `web/components/`** — ChatMessage (composition), ListingCard
(fit badge + sourced enrichment rows), FitBreakdown +
AnswerConfidencePanel (the two "show the math" panels), CompassGauge.
*Check:* an SSE `token` event arrives — walk it from streamChat to
pixels.

---

## Sitting 5 — The quality infrastructure (how we know it works)

**16. `evals/`** — read `cases.py` first (the dataset IS the spec of
correct behavior), then `fake_tools.py` (isolation), then `run.py`
suite by suite. You watched this suite catch a rate limit, a
dependency-upgrade bug, and a prompt weakness in one run.
**17. `compliance/`** — `generate_rules_pdf.py` (the fictional
rulebook), `ingest_rules.py` (section-aware chunking — read the
docstring on why not fixed-size chunks), `retriever.py` (why NOT an
LLM tool — guardrails must always run), `drive_fetch.py` (MCP client
to a third-party server + OAuth).
*Check:* why does the guardrail retrieve on question+draft rather
than just the draft?

---

## After the tour: three exercises that prove understanding

1. **Break it on purpose:** delete the follow-up sentence from
   `RETRIEVE_SYSTEM_PROMPT`, run `evals/run.py --suite routing`, watch
   the crime-follow-up case fail, restore it. You now understand
   prompt-behavior coupling and regression testing viscerally.
2. **Add a slot end to end:** e.g. `max_hoa_fee` — schema field,
   weights decision, search filter, fit component, eval case. Touches
   every layer; nothing teaches the architecture faster.
3. **Explain the graph diagram to someone** (or to a rubber duck)
   without notes. Every box and edge, including why clarify skips the
   guardrail and score.

## The one-paragraph mental model to keep

A user message becomes structured `slots` (intake); a deterministic
score decides ask-or-act (confidence/gate); an LLM picks tools from
MCP servers that wrap Postgres and government APIs (retrieve/tools);
results get fit-scored into cards (synthesis); an answer is written
(present), checked against an embedded rulebook (compliance), and
graded (score); everything streams to the browser as SSE events, is
persisted by a checkpointer, traced in LangSmith, and held to account
by an offline eval suite with a golden dataset.
