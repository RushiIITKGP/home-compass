# Graph Reference — Every Node, In Full Detail

Companion to the diagram and `api/agent.py`. For each node: when it
runs, what it reads, every function/LLM call it makes, what it writes
back to state, where control goes next, and how it fails. State fields
refer to `AgentState`; a "turn" is one user message through the graph.

The graph is compiled in `build_graph(llm, tools, checkpointer,
rule_retriever)` and persisted per-`thread_id` by the Postgres
checkpointer — state survives between turns, which is why slots
accumulate across messages.

---

## START → `intake`

**Triggered:** first, on every single turn, unconditionally — the
entry edge is `START → intake`.

**Reads:** `state["messages"]` (full history incl. the new
HumanMessage), `state["slots"]` (whatever previous turns extracted).

**Does, in order:**
1. `_status("Reading your message...")` → emits an SSE status line
   via LangGraph's custom stream channel (guarded try/except — newer
   langgraph raises outside a run context).
2. Builds a prompt: `SystemMessage(INTAKE_SYSTEM_PROMPT)` (extraction
   rules, incl. the "location must be a PLACE, not a preference"
   clause) + `_recent_messages(messages)`.
   - `_recent_messages` trims to the last `CONTEXT_WINDOW_TURNS` (8)
     user turns AND passes every message through `_llm_safe`, which
     normalizes ToolMessage content to non-empty strings (the Groq
     empty-content 400 fix).
3. `extractor.invoke(prompt)` — **LLM call #1** of the turn, via
   `llm.with_structured_output(ExtractedSlots)`. The model returns the
   schema; Pydantic validators then coerce sloppy types:
   `_coerce_number` ("$500k" → 500000.0) on budgets/baths, int
   coercion on beds, comma-string → list on must_haves.
   Wrapped in try/except: on ANY failure, `extracted =
   ExtractedSlots()` (empty) — the turn proceeds with old slots
   rather than crashing (fail-soft).
4. `merge_slots(old, extracted)` — new values overwrite old;
   `must_haves` accumulates uniquely across turns instead of being
   replaced.

**Writes:** `slots` (merged), `answer_confidence=None`,
`compliance_status=None` (resets per-turn outputs so last turn's
panel never bleeds into this turn).

**Next:** always `confidence`.

---

## `confidence`

**Triggered:** always, immediately after intake.

**Reads:** `slots`. **No LLM call — pure function.**

**Does:** `compute_confidence(slots)`:
- `_slot_groups_filled` maps slots to 5 boolean groups: budget (.30),
  location (.30), beds_baths (.20), must_haves (.10), timeline (.10).
- Budget conflict rule: if `budget_min > budget_max`, budget counts
  as NOT filled (a contradictory range is unusable information, not a
  small deduction).
- Score = sum of weights of filled groups, clamped 0..1.
- `missing_slot` = highest-weight unfilled group (the question that
  raises the score most), or "budget" if a conflict needs resolving
  even at high score.

**Writes:** `confidence_score`, `missing_slot`.

**Next:** the conditional edge `gate`.

---

## `gate` (conditional edge, not a node)

**Triggered:** after confidence, every turn.

**Does:** one comparison: `confidence_score >= CONFIDENCE_THRESHOLD`
(env, default 0.8). This is the product's core bet: the agent must
EARN the right to search by understanding you first.

**Routes:** `≥ 0.8 → retrieve` · `< 0.8 → clarify`.

---

## `clarify`

**Triggered:** only when the gate fails (score < 0.8).

**Reads:** `missing_slot`, `messages`.

**Does:**
1. `_status("Preparing a follow-up question...")`.
2. Prompt: `CLARIFY_SYSTEM_PROMPT` formatted with `missing_slot` —
   instructs the LLM to ask exactly ONE targeted question — +
   `_recent_messages`.
3. `llm.invoke(prompt)` — **LLM call** (streams to the browser:
   clarify is in `STREAMABLE_NODES`).
4. Empty-output guard: if `extract_text_content(response)` is blank
   (provider filtered/weird content), substitutes a canned question
   from `CLARIFY_FALLBACK_QUESTIONS[missing_slot]` — the user never
   gets an empty bubble.

**Writes:** the question as an AIMessage in `messages`.

**Next:** `END`. Deliberately skips compliance and score: a
clarifying question asserts no facts to guard and isn't an answer to
grade. The turn's SSE `done` event still carries `confidence_score`,
so the compass updates.

---

## `retrieve`

**Triggered:** only when the gate passes (score ≥ 0.8).

**Reads:** `slots`, `messages`.

**Does:**
1. `_status("Deciding how to help...")`.
2. Prompt: `RETRIEVE_SYSTEM_PROMPT` formatted with the slots —
   instructs: new search → call `search_listings` with structured
   filters (free-text `query` only for lifestyle needs + property
   type); follow-up about a known listing → call the matching
   enrichment tool directly with that ZIP instead of re-searching.
3. `llm_with_tools.invoke(prompt)` — **LLM call**, where
   `llm_with_tools = llm.bind_tools([search_listings,
   get_neighborhood_demographics, get_safety_stats,
   get_market_trends])`. The model sees these four JSON schemas and
   decides: emit tool_calls, or answer directly in text.
   (`get_listing_details` exists on mcp-property but is deliberately
   NOT in this list — nothing binds it, so the LLM can never call it.)
4. For each tool_call emitted: `_status(TOOL_STATUS_MESSAGES[name])`
   ("Searching listings..." / "Checking crime stats..." etc.).

**Writes:** the AIMessage (with or without tool_calls) to `messages`.

**Next:** conditional edge `route_after_retrieve`:
- has `tool_calls` → `tools`
- no tool_calls (the model chose to reply directly, e.g. a
  confirmation) → the dashed "direct reply" path: straight to
  `compliance` (or `score` if guardrail off) — its text IS the
  turn's answer, so it still gets guarded and graded.

---

## `tools` (prebuilt `ToolNode`)

**Triggered:** only when retrieve emitted tool_calls.

**Does:** LangGraph's ToolNode executes each requested tool. The
tools are LangChain adapters around MCP servers spawned as
subprocesses by `api/setup.py` (`MultiServerMCPClient`, stdio
transport) — the call crosses process boundaries via the MCP
protocol:
- `search_listings(filters…)` → mcp-property: `_build_search_query`
  composes SQL (price/beds/baths/city/state filters; if free-text
  `query` present, `embed_query` via Ollama + pgvector
  `cosine_distance` rerank with LEFT join so unembedded listings
  still return). Returns JSON list of listings.
- `get_neighborhood_demographics(zip)` → mcp-enrich: Postgres cache
  check → else Census ACS API → cache → return income/age.
- `get_safety_stats(zip, state)` → mcp-enrich: cache check → else
  FBI CDE `summarized/state/{st}/{offense}` (MM-YYYY params),
  `_find_time_series` + `_latest_annual_value` parsing (actuals
  preferred over rates, latest COMPLETE year), cache counts (never
  rates) → return.
- `get_market_trends(zip)` → mcp-market: reads batch-ingested
  Redfin/Realtor rows. Never calls sources live.

**Writes:** one ToolMessage per call into `messages` (raw JSON
results).

**Next:** conditional edge `route_after_tools`: if the executed calls
included `search_listings` → `synthesis` (results need formatting
into cards); enrichment-only → `present` directly (the ToolMessage is
already in the conversation for present to read; nothing to make
cards from).

---

## `synthesis`

**Triggered:** only after a `search_listings` call.

**Reads:** `messages` (to find the search results), `slots`,
`enrichment` (usually empty — kept for ZIPs cached by past turns).
**No LLM call — pure function.**

**Does:**
1. `_status("Ranking results...")`.
2. `_extract_listings(messages)` — finds the latest search_listings
   ToolMessage, parses its JSON (string or content-block list).
3. Per listing: `compute_fit(slots, listing)` → graded 0..1 score
   (budget .35 / location .25 / beds .20 / baths .20; over-budget
   scales down proportionally, unstated criteria drop out with weight
   redistribution) + per-component breakdown; and
   `compute_recommendation_confidence(zip_enrichment)` → 0.4 baseline
   + 0.2 per verified data source (computed, sent, not displayed).
4. Sorts by fit desc (None last), tiebreak by recommendation
   confidence.

**Writes:** `recommendations` — the list the frontend renders as
cards with fit badges and the FitBreakdown panel.

**Next:** always `present`.

---

## `present`

**Triggered:** after synthesis (search path) or straight from tools
(enrichment-only path).

**Reads:** `slots`, `recommendations`, `messages` (incl. any
ToolMessages from this turn).

**Does:**
1. `_status("Writing response...")`.
2. Prompt: `PRESENT_SYSTEM_PROMPT` formatted with slots +
   recommendations — tailor to timeline/urgency, summarize fresh
   results OR answer the specific follow-up from tool results in the
   conversation, never invent data, never present `error` fields as
   real. Plus `_recent_messages`.
3. `llm.invoke(prompt)` — **LLM call** (streams: present is in
   `STREAMABLE_NODES` — tokens reach the browser as they generate).
4. Empty-output guard: blank content → `_fallback_summary
   (recommendations)` builds a deterministic templated answer (top-3
   listings with prices) rather than shipping silence.

**Writes:** the answer AIMessage to `messages`.

**Next:** `compliance` if the guardrail is on (rules ingested), else
`score`, else END.

---

## `compliance`

**Triggered:** on every ANSWER path (present output, or retrieve's
direct reply) — but only wired into the graph at all when
`build_rule_retriever()` found ingested rules at startup
(`[compliance] guardrail ON`).

**Reads:** last message (the draft answer), `messages` (for the
user's question).

**Does:**
1. `_status("Checking compliance rules...")`.
2. `rule_retriever(question + "\n" + draft)` — embeds via
   `embed_query` (Ollama), pgvector cosine search over
   `compliance_rules`, returns top-4 rules. Retrieval runs on
   question+draft because steering violations are often visible in
   the QUESTION alone. Deliberately a plain function, not an LLM
   tool: a guardrail the model could decline to consult isn't one.
3. `checker.invoke(...)` — **LLM call** via
   `with_structured_output(ComplianceVerdict)`: system prompt embeds
   the retrieved rules verbatim; user content is USER MESSAGE +
   DRAFT. Verdict: `{compliant, violated_sections, revised_answer}`.
4. Outcomes:
   - compliant → writes `compliance_status="passed"`, changes
     nothing.
   - violation → `_status("Revising…")`, replaces the draft IN PLACE
     (`AIMessage(content=revised, id=last.id)` — same id makes
     `add_messages` substitute, not append), writes
     `compliance_status="revised"`. Because the draft already
     streamed, `api/main.py` detects final-text ≠ streamed-text and
     sends a `replace` SSE event; the frontend swaps the bubble.
   - any exception (DB down, judge failed) → **fail-open**: returns
     `compliance_status=None`, the draft ships. Documented choice:
     right for this domain, reversed (fail-closed) for
     payments/medical.

**Next:** `score` (or END if scoring disabled).

---

## `score`

**Triggered:** last node on every answer path; skipped for clarify
turns; removable via `ANSWER_SCORING=false` (saves one LLM call/turn).

**Reads:** `messages` (final answer + this turn's ToolMessages via
`_turn_messages` — everything since the last HumanMessage), `slots`,
`recommendations`, `compliance_status`.

**Does:**
1. `_status("Scoring answer confidence...")`.
2. Deterministic components:
   - `data_coverage`: 1.0 if this turn's tools returned non-empty
     data, 0.3 if they returned empty, None (excluded) if no tools
     ran.
   - `criteria_match`: `_criteria_match_score(slots,
     recommendations)` — fraction of (slot, listing) checks the top-5
     results pass; only when a search happened this turn.
   - `compliance`: passed=1.0, revised=0.6, None if guardrail off.
3. `judge.invoke(...)` — **LLM call** via
   `with_structured_output(AnswerJudgment)`: given the question, this
   turn's tool data, and the answer, scores `intent_match` and
   `grounding` 0..1. Try/except: on failure both become None
   (fail-open — scoring must never kill an answer).
4. Weighted average over the components that apply (weights: grounding
   .30, intent .25, criteria .20, coverage .15, compliance .10),
   missing components' weight redistributed; flagged if below
   `ANSWER_CONFIDENCE_THRESHOLD` (0.75).

**Writes:** `answer_confidence` = {score, threshold, flagged,
components, redistributed} → rides the SSE `done` event → the
AnswerConfidencePanel under the message.

**Next:** END.

---

## END — what the frontend receives, in order

Over one turn's SSE stream (`api/main.py: stream_chat`):
1. `{thread_id}` — once (client stores it; resend to continue the
   conversation via the checkpointer).
2. `{status}` × N — every `_status()` line, live.
3. `{token}` × N — only from clarify/present LLM calls
   (`STREAMABLE_NODES`; intake/retrieve/compliance/score would leak
   JSON or tool-call internals).
4. Possibly `{token: full_text}` once — if nothing streamed
   (fallback answers), or `{replace: full_text}` — if compliance
   revised after streaming.
5. `{done, confidence_score, missing_slot, recommendations,
   answer_confidence}` — once; populates the compass, cards, fit
   panel, and answer-confidence panel.

## LLM call budget per turn (why turns cost ~8–15k tokens)

Clarify turn: intake + clarify = **2 calls**.
Search turn (guarded, scored): intake + retrieve + present +
compliance + score = **5 calls** (+1 embedding call inside
search_listings if a free-text query was used, +1 embedding inside
the rule retriever).
Every call re-sends its prompt package — see the trimming in
`_recent_messages` for why that stays bounded.
