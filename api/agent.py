"""
Home Compass — the LangGraph agent.

Flow: intake -> confidence -> [gate] -> clarify|retrieve -> tools ->
synthesis -> present -> compliance -> score -> END. Search returns
exactly what was asked; demographics/crime/market are fetched only
when the user asks (direct tool call). See GRAPH_REFERENCE.md for the
full node-by-node story.
"""

from __future__ import annotations

import json
import os
from typing import Annotated, Literal, Optional, Union

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from pydantic import BaseModel, Field, field_validator
from typing_extensions import TypedDict

# --------------------------------------------------------------- state --


class UserSlots(TypedDict, total=False):
    budget_min: Optional[float]
    budget_max: Optional[float]
    location: Optional[str]
    property_type: Optional[str]
    beds: Optional[int]
    baths: Optional[float]
    must_haves: Optional[list[str]]
    timeline: Optional[str]


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    slots: UserSlots
    confidence_score: float
    missing_slot: Optional[str]
    enrichment: dict  # per-ZIP cached enrichment (rarely populated)
    recommendations: list[dict]
    compliance_status: Optional[str]  # "passed" | "revised" | None
    answer_confidence: Optional[dict]


# ------------------------------------------------- confidence scoring --

# Deterministic on purpose: the score is shown to the user, so it must
# be reproducible and auditable. property_type isn't gated — the seed
# data has no type column, so the answer couldn't change results.
SLOT_WEIGHTS: dict[str, float] = {
    "budget": 0.30,
    "location": 0.30,
    "beds_baths": 0.20,
    "must_haves": 0.10,
    "timeline": 0.10,
}

CONFIDENCE_THRESHOLD = float(os.environ.get("CONFIDENCE_THRESHOLD", "0.8"))
MAX_RECENT_TURNS = int(os.environ.get("CONTEXT_WINDOW_TURNS", "8"))


def _status(text: str) -> None:
    """Live progress line for the frontend; cosmetic, must never fail a
    node (newer langgraph raises when called outside a run)."""
    try:
        get_stream_writer()({"status": text})
    except Exception:
        pass


def _llm_safe(message: BaseMessage) -> BaseMessage:
    """Normalize ToolMessage content to a non-empty string — providers
    differ (Groq 400s on empty content; some return content-block lists)."""
    if not isinstance(message, ToolMessage):
        return message
    content = message.content
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        parts = [
            item if isinstance(item, str) else item.get("text", "")
            for item in content
            if isinstance(item, (str, dict))
        ]
        text = "\n".join(p for p in parts if isinstance(p, str) and p)
    else:
        text = json.dumps(content, default=str) if content is not None else ""
    if not text.strip():
        text = "[]"
    if text == content:
        return message
    return message.model_copy(update={"content": text})


def _recent_messages(messages: list[BaseMessage]) -> list[BaseMessage]:
    """Trim to the last MAX_RECENT_TURNS user turns — older facts already
    live in slots, so trimming loses tone, not memory."""
    human_indices = [i for i, m in enumerate(messages) if isinstance(m, HumanMessage)]
    if len(human_indices) > MAX_RECENT_TURNS:
        messages = messages[human_indices[-MAX_RECENT_TURNS]:]
    return [_llm_safe(m) for m in messages]


def _slot_groups_filled(slots: UserSlots) -> dict[str, bool]:
    return {
        "budget": slots.get("budget_min") is not None or slots.get("budget_max") is not None,
        "location": bool(slots.get("location")),
        "beds_baths": slots.get("beds") is not None or slots.get("baths") is not None,
        "must_haves": bool(slots.get("must_haves")),
        "timeline": bool(slots.get("timeline")),
    }


def compute_confidence(slots: UserSlots) -> tuple[float, Optional[str]]:
    """Returns (score, highest-weight missing group). A conflicting
    budget (min > max) counts as unfilled — it's unusable information."""
    filled = _slot_groups_filled(slots)
    budget_min, budget_max = slots.get("budget_min"), slots.get("budget_max")
    conflict = budget_min is not None and budget_max is not None and budget_min > budget_max
    if conflict:
        filled["budget"] = False

    score = max(0.0, min(1.0, sum(w for name, w in SLOT_WEIGHTS.items() if filled[name])))

    missing = None
    if score < CONFIDENCE_THRESHOLD:
        unfilled = [(n, w) for n, w in SLOT_WEIGHTS.items() if not filled[n]]
        if unfilled:
            missing = max(unfilled, key=lambda item: item[1])[0]
    elif conflict:
        missing = "budget"
    return score, missing


# ------------------------------------------------------ slot extraction --


def _coerce_number(value) -> Optional[float]:
    """'$500,000' / '500k' / '3' -> float; junk -> None. Open models on
    strict providers emit numbers as strings; normalize here."""
    if value is None or isinstance(value, (int, float)):
        return None if value is None else float(value)
    if not isinstance(value, str):
        return None
    s = value.strip().lower().replace("$", "").replace(",", "")
    if not s or s in ("null", "none", "n/a"):
        return None
    multiplier = 1.0
    if s.endswith("k"):
        multiplier, s = 1_000.0, s.removesuffix("k")
    elif s.endswith("m"):
        multiplier, s = 1_000_000.0, s.removesuffix("m")
    try:
        return float(s) * multiplier
    except ValueError:
        return None


class ExtractedSlots(BaseModel):
    """Intake extraction schema. Numeric fields accept string OR number
    (so strict providers don't reject sloppy tool calls) and are
    normalized on validation. Set only what the user actually stated."""

    budget_min: Optional[Union[float, str]] = Field(None, description="Minimum budget in USD, if mentioned")
    budget_max: Optional[Union[float, str]] = Field(None, description="Maximum budget in USD, if mentioned")
    location: Optional[str] = Field(None, description="City, neighborhood, or area of interest")
    property_type: Optional[str] = Field(None, description="e.g. house, condo, apartment, townhouse")
    beds: Optional[Union[int, str]] = Field(None, description="Minimum number of bedrooms")
    baths: Optional[Union[float, str]] = Field(None, description="Minimum number of bathrooms")
    must_haves: Optional[Union[list[str], str]] = Field(None, description="Distinct must-have features or lifestyle needs")
    timeline: Optional[str] = Field(None, description="When they want to move / how urgent")

    @field_validator("budget_min", "budget_max", "baths", mode="before")
    @classmethod
    def _numbers(cls, value):
        return _coerce_number(value)

    @field_validator("beds", mode="before")
    @classmethod
    def _whole_number(cls, value):
        number = _coerce_number(value)
        return int(number) if number is not None else None

    @field_validator("must_haves", mode="before")
    @classmethod
    def _listify(cls, value):
        if isinstance(value, str):
            items = [p.strip() for p in value.replace(";", ",").split(",")]
            return [i for i in items if i] or None
        return value


def merge_slots(existing: UserSlots, extracted: ExtractedSlots) -> UserSlots:
    """New values overwrite; must_haves accumulate uniquely across turns."""
    merged: UserSlots = dict(existing)  # type: ignore[assignment]
    for key, value in extracted.model_dump(exclude_none=True).items():
        if key == "must_haves":
            current = merged.get("must_haves") or []
            merged["must_haves"] = list(dict.fromkeys([*current, *value]))
        else:
            merged[key] = value
    return merged


# --------------------------------------------------------------- prompts --

INTAKE_SYSTEM_PROMPT = (
    "You are extracting home-search criteria from a conversation between a "
    "real estate assistant and a user. Extract only what the user has "
    "explicitly stated or clearly implied so far — leave a field unset if "
    "it hasn't come up. Do not guess.\n"
    "Rules that models often get wrong:\n"
    "- `location` must be an actual PLACE NAME (city, neighborhood, metro "
    "area). Descriptive phrases like 'near good schools' or 'somewhere "
    "quiet' are preferences — they belong in must_haves, never in location.\n"
    "- `must_haves`: list each distinct need as its own item ('quiet "
    "area' and 'good schools' are two items, not one)."
)

CLARIFY_SYSTEM_PROMPT = (
    "You are a real estate assistant gathering a user's home-search "
    "criteria before searching. You still need more information about: "
    "{missing_slot}. Ask exactly ONE short, natural, targeted question to "
    "learn that — don't ask about anything else, and don't list multiple "
    "questions."
)

RETRIEVE_SYSTEM_PROMPT = (
    "You have enough information to help with the user's home search. If "
    "this is a new search (or refined criteria), call search_listings "
    "with structured filters built from these criteria: {slots}. Only "
    "pass the free-text `query` parameter for preferences not covered by "
    "a structured filter — lifestyle/descriptive needs, and property type "
    "if the user stated one (there is no structured property-type filter; "
    "the listing data doesn't reliably distinguish types). Never put "
    "beds or baths in `query` — those have dedicated filters. "
    "If instead the user is asking a follow-up question about a specific "
    "listing or area already discussed — its crime rate, demographics, or "
    "market trends — call get_neighborhood_demographics, get_safety_stats, "
    "or get_market_trends directly with that ZIP code rather than "
    "searching again. get_market_trends automatically falls back to a live "
    "Redfin web search when it has no stored data, and those results are "
    "web estimates — cite the source URL and don't present them as verified."
)

PRESENT_SYSTEM_PROMPT = (
    "The user's stated criteria so far: {slots}. Tailor your answer to "
    "them — in particular, if a timeline/urgency was given, frame advice "
    "accordingly (e.g. an urgent mover cares about for-sale inventory "
    "now; someone browsing for next year cares about market direction), "
    "and acknowledge any stated must-haves the results can't verify. "
    "Answer the user using this ranked listing data: "
    "{recommendations} — plus any tool results visible earlier in this "
    "conversation, which may be more specifically relevant if the user "
    "asked a targeted follow-up question rather than requesting a new "
    "search. If this is a fresh set of search results, summarize briefly "
    "and highlight the top 2-3, citing concrete details (address, price, "
    "beds/baths, and any demographics/safety/market context that's "
    "present — there often won't be any for a plain search, and that's "
    "fine, just don't invent it). If the user instead asked a specific "
    "follow-up question, answer that question directly and concisely "
    "rather than re-presenting everything. Don't invent details not "
    "present in the data, and don't present enrichment data that has an "
    "'error' field as if it were real. "
    "When the data is web-sourced (it has an 'evidence' list with 'url' "
    "fields — e.g. live market data), you MUST include the actual source "
    "URL(s) in your answer next to the figures, and call them estimates. "
    "Never give a web-sourced number without its URL."
)


# ---------------------------------------------------------------- nodes --


def make_intake_node(llm):
    extractor = llm.with_structured_output(ExtractedSlots)

    def intake_node(state: AgentState) -> dict:
        _status("Reading your message...")
        prompt = [SystemMessage(content=INTAKE_SYSTEM_PROMPT), *_recent_messages(state["messages"])]
        try:
            extracted = extractor.invoke(prompt)
        except Exception:
            extracted = ExtractedSlots()  # fail soft: keep old slots, gate will clarify
        merged = merge_slots(state.get("slots", {}), extracted)
        # Reset per-turn outputs so last turn's panel never bleeds through.
        return {"slots": merged, "answer_confidence": None, "compliance_status": None}

    return intake_node


def confidence_node(state: AgentState) -> dict:
    score, missing = compute_confidence(state.get("slots", {}))
    return {"confidence_score": score, "missing_slot": missing}


def gate(state: AgentState) -> Literal["retrieve", "clarify"]:
    return "retrieve" if state["confidence_score"] >= CONFIDENCE_THRESHOLD else "clarify"


CLARIFY_FALLBACK_QUESTIONS = {
    "budget": "What's your budget range?",
    "location": "Which city or area are you looking in?",
    "beds_baths": "How many bedrooms and bathrooms do you need?",
    "must_haves": "Any must-have features?",
    "timeline": "What's your timeline for moving?",
}


def make_clarify_node(llm):
    def clarify_node(state: AgentState) -> dict:
        _status("Preparing a follow-up question...")
        missing_slot = state.get("missing_slot")
        prompt_text = CLARIFY_SYSTEM_PROMPT.format(missing_slot=missing_slot or "their needs")
        response = llm.invoke([SystemMessage(content=prompt_text), *_recent_messages(state["messages"])])
        if not response.text.strip():
            response = AIMessage(content=CLARIFY_FALLBACK_QUESTIONS.get(
                missing_slot, "Could you tell me a bit more about what you're looking for?"
            ))
        return {"messages": [response]}

    return clarify_node


TOOL_STATUS_MESSAGES = {
    "search_listings": "Searching listings...",
    "get_neighborhood_demographics": "Looking up neighborhood demographics...",
    "get_safety_stats": "Checking crime stats...",
    "get_market_trends": "Checking market trends...",
    "get_market_trends_live": "Searching the web for current market data...",
}


def make_retrieve_node(llm_with_tools):
    def retrieve_node(state: AgentState) -> dict:
        _status("Deciding how to help...")
        prompt_text = RETRIEVE_SYSTEM_PROMPT.format(slots=state.get("slots", {}))
        response = llm_with_tools.invoke(
            [SystemMessage(content=prompt_text), *_recent_messages(state["messages"])]
        )
        for tool_call in getattr(response, "tool_calls", None) or []:
            _status(TOOL_STATUS_MESSAGES.get(tool_call["name"], f"Calling {tool_call['name']}..."))
        return {"messages": [response]}

    return retrieve_node


def _fallback_summary(recommendations: list[dict]) -> str:
    """Deterministic answer for when the LLM returns no usable text —
    never ship an empty bubble."""
    if not recommendations:
        return (
            "I wasn't able to put together a response just now — could you try "
            "rephrasing your last message?"
        )
    lines = ["Here's what I found:"]
    for rec in recommendations[:3]:
        listing = rec.get("listing", {})
        price = listing.get("price")
        price_str = f"${price:,.0f}" if isinstance(price, (int, float)) else "price unavailable"
        lines.append(f"- {listing.get('address', 'Address unavailable')} — {price_str}")
    return "\n".join(lines)


def route_after_retrieve(state: AgentState) -> Literal["tools", "end_turn"]:
    """Tool calls -> execute them; a direct text reply IS the turn's
    answer -> send it down the guarded answer path."""
    last = state["messages"][-1]
    if isinstance(last, AIMessage) and last.tool_calls:
        return "tools"
    return "end_turn"


def route_after_tools(state: AgentState) -> Literal["synthesis", "present"]:
    """Fresh search -> synthesis (format cards). Enrichment-only ->
    present (the ToolMessage is already in the conversation)."""
    for message in reversed(state["messages"]):
        if isinstance(message, AIMessage) and message.tool_calls:
            called = {tc["name"] for tc in message.tool_calls}
            return "synthesis" if "search_listings" in called else "present"
    return "present"


def _extract_listings(messages: list[BaseMessage]) -> list[dict]:
    """Parse the latest search_listings ToolMessage — content may be one
    JSON-array string or a list of content blocks."""
    for message in reversed(messages):
        if not (isinstance(message, ToolMessage) and getattr(message, "name", None) == "search_listings"):
            continue
        texts: list[str] = []
        if isinstance(message.content, str):
            texts = [message.content]
        elif isinstance(message.content, list):
            for item in message.content:
                if isinstance(item, str):
                    texts.append(item)
                elif isinstance(item, dict) and isinstance(item.get("text"), str):
                    texts.append(item["text"])
        listings: list[dict] = []
        for text in texts:
            try:
                data = json.loads(text)
            except (json.JSONDecodeError, TypeError):
                continue
            if isinstance(data, list):
                listings.extend(d for d in data if isinstance(d, dict))
            elif isinstance(data, dict):
                listings.append(data)
        return listings
    return []


# ------------------------------------------------------- fit + synthesis --

# recommendation_confidence: how much VERIFIED data backs a listing
# (0.4 baseline + 0.2 per error-free source). Computed and sent, but
# cards display fit instead.
RECOMMENDATION_WEIGHTS = {"listing_core": 0.4, "demographics": 0.2, "safety": 0.2, "market": 0.2}


def compute_recommendation_confidence(zip_enrichment: dict) -> float:
    score = RECOMMENDATION_WEIGHTS["listing_core"]
    for key in ("demographics", "safety", "market"):
        value = zip_enrichment.get(key)
        if value and "error" not in value:
            score += RECOMMENDATION_WEIGHTS[key]
    return round(score, 3)


# fit: how well a listing matches the USER'S criteria. Graded, not
# binary ($520k vs a $500k max scores ~0.96, not 0); unstated criteria
# drop out and their weight redistributes.
FIT_WEIGHTS = {"budget": 0.35, "location": 0.25, "beds": 0.20, "baths": 0.20}


def compute_fit(slots: UserSlots, listing: dict) -> tuple[Optional[float], dict]:
    components: dict[str, Optional[float]] = {}

    price = listing.get("price")
    budget_min, budget_max = slots.get("budget_min"), slots.get("budget_max")
    if price is not None and (budget_min is not None or budget_max is not None):
        if budget_max is not None and price > budget_max:
            components["budget"] = round(max(0.0, budget_max / price), 3)
        elif budget_min is not None and price < budget_min:
            components["budget"] = round(max(0.0, price / budget_min), 3)
        else:
            components["budget"] = 1.0
    else:
        components["budget"] = None

    location, city = slots.get("location"), listing.get("city") or ""
    if location and city:
        wanted = location.split(",")[0].strip().lower()
        components["location"] = 1.0 if (wanted in city.lower() or city.lower() in wanted) else 0.0
    else:
        components["location"] = None

    for key in ("beds", "baths"):
        wanted, have = slots.get(key), listing.get(key)
        if wanted and have is not None:
            components[key] = 1.0 if have >= wanted else round(max(0.0, float(have) / float(wanted)), 3)
        else:
            components[key] = None

    applicable = {k: w for k, w in FIT_WEIGHTS.items() if components[k] is not None}
    if not applicable:
        return None, components
    score = round(sum(components[k] * w for k, w in applicable.items()) / sum(applicable.values()), 3)
    return score, components


def synthesis_node(state: AgentState) -> dict:
    _status("Ranking results...")
    listings = _extract_listings(state["messages"])
    enrichment = state.get("enrichment", {})
    slots = state.get("slots", {})

    recommendations = []
    for listing in listings:
        zip_enrichment = enrichment.get(listing.get("zip_code"), {})
        fit_score, fit_components = compute_fit(slots, listing)
        recommendations.append({
            "listing": listing,
            "fit_score": fit_score,
            "fit_components": fit_components,
            "recommendation_confidence": compute_recommendation_confidence(zip_enrichment),
            "enrichment": zip_enrichment,
        })

    recommendations.sort(
        key=lambda r: (r["fit_score"] if r["fit_score"] is not None else -1.0, r["recommendation_confidence"]),
        reverse=True,
    )
    return {"recommendations": recommendations}


def _trim_enrichment_dates(data):
    """Shorten a 'fetched_at' ISO timestamp to just its date. Everything
    else in an enrichment sub-dict — source, note, error, evidence/url —
    passes through untouched: present_node's prompt is required to relay
    error fields honestly and to cite web-search URLs verbatim, so those
    can't be trimmed away, only the timestamp precision nobody reads."""
    if not isinstance(data, dict) or "fetched_at" not in data:
        return data
    trimmed = dict(data)
    fetched_at = trimmed.get("fetched_at")
    if isinstance(fetched_at, str) and "T" in fetched_at:
        trimmed["fetched_at"] = fetched_at.split("T")[0]
    return trimmed


def _present_view(recommendations: list[dict]) -> list[dict]:
    """Slims each recommendation to what present_node's prompt actually
    needs to write about — the full listing record, fit_components
    breakdown, and recommendation_confidence still reach the frontend via
    state["recommendations"] unchanged (ListingCard/FitBreakdown render
    from that, not from this); this trims only the copy serialized into
    the LLM prompt itself, since that's what's billed as input tokens on
    every present_node call."""
    view = []
    for rec in recommendations:
        listing = rec.get("listing", {})
        item = {
            "address": listing.get("address"),
            "price": listing.get("price"),
            "beds": listing.get("beds"),
            "baths": listing.get("baths"),
            "sqft": listing.get("sqft"),
            "status": listing.get("status"),
            "fit_score": rec.get("fit_score"),
        }
        enrichment = rec.get("enrichment") or {}
        if enrichment:
            item["enrichment"] = {k: _trim_enrichment_dates(v) for k, v in enrichment.items()}
        view.append(item)
    return view


def make_present_node(llm):
    def present_node(state: AgentState) -> dict:
        _status("Writing response...")
        prompt_text = PRESENT_SYSTEM_PROMPT.format(
            slots=state.get("slots", {}), recommendations=_present_view(state.get("recommendations", []))
        )
        response = llm.invoke([SystemMessage(content=prompt_text), *_recent_messages(state["messages"])])
        if not response.text.strip():
            response = AIMessage(content=_fallback_summary(state.get("recommendations", [])))
        return {"messages": [response]}

    return present_node


# ------------------------------------------- compliance guardrail (RAG) --


class ComplianceVerdict(BaseModel):
    compliant: bool = Field(description="True only if the draft violates none of the provided rules")
    violated_sections: list[str] = Field(default_factory=list, description='e.g. ["§ 12.1"]')
    revised_answer: Optional[str] = Field(
        None,
        description=(
            "Required when compliant=false: the closest compliant version of "
            "the draft — refuse only what the rules prohibit, keep the rest, "
            "briefly cite the section number(s)."
        ),
    )


COMPLIANCE_SYSTEM_PROMPT = (
    "You are the compliance reviewer for an automated real-estate advisory "
    "service. Review the DRAFT RESPONSE against these regulations, retrieved "
    "from the governing rulebook:\n\n{rules}\n\n"
    "Judge only against these rules — do not invent additional restrictions. "
    "If the draft violates a rule, produce a revised_answer that stays as "
    "helpful as the rules allow: refuse or remove only what a rule actually "
    "prohibits, keep the rest, add any disclaimer or source attribution a "
    "rule requires, and cite the section number(s) briefly. If the draft "
    "complies, say so and change nothing."
)


def make_compliance_node(llm, rule_retriever):
    checker = llm.with_structured_output(ComplianceVerdict)

    def compliance_node(state: AgentState) -> dict:
        _status("Checking compliance rules...")
        last = state["messages"][-1]
        draft = last.text
        if not draft.strip():
            return {}
        user_text = next(
            (m.text for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
            "",
        )
        try:
            # Retrieve on question + draft: steering violations are often
            # visible in the question alone.
            rules = rule_retriever(f"{user_text}\n{draft}")
            rules_text = "\n\n".join(f"{r['section']} — {r['title']}: {r['text']}" for r in rules)
            verdict = checker.invoke([
                SystemMessage(content=COMPLIANCE_SYSTEM_PROMPT.format(rules=rules_text)),
                HumanMessage(content=f"USER MESSAGE:\n{user_text}\n\nDRAFT RESPONSE:\n{draft}"),
            ])
        except Exception:
            # Fail-open: a broken guardrail ships the draft rather than
            # blocking every answer. Reverse this for high-stakes domains.
            return {"compliance_status": None}

        if verdict.compliant or not (verdict.revised_answer or "").strip():
            return {"compliance_status": "passed"}

        _status("Revising response to comply with advisory rules...")
        # Same id -> add_messages REPLACES the draft; main.py sends a
        # `replace` SSE event since the draft already streamed.
        return {
            "messages": [AIMessage(content=verdict.revised_answer, id=last.id)],
            "compliance_status": "revised",
        }

    return compliance_node


# ------------------------------------------- answer confidence (score) --

# Per-ANSWER confidence: how good is THIS response to THIS question.
# Non-applicable components drop out; their weight redistributes.
ANSWER_WEIGHTS = {
    "intent_match": 0.25,
    "grounding": 0.30,
    "data_coverage": 0.15,
    "criteria_match": 0.20,
    "compliance": 0.10,
}
ANSWER_CONFIDENCE_THRESHOLD = float(os.environ.get("ANSWER_CONFIDENCE_THRESHOLD", "0.75"))


class AnswerJudgment(BaseModel):
    intent_match: float = Field(
        ge=0.0, le=1.0,
        description="0..1 — how directly and completely the answer addresses the user's actual question",
    )
    grounding: float = Field(
        ge=0.0, le=1.0,
        description=(
            "0..1 — fraction of the answer's specific factual claims supported by "
            "the DATA. 1.0 if no unsupported specifics (hedging is fine)."
        ),
    )


ANSWER_JUDGE_PROMPT = (
    "You are scoring one answer from a real-estate assistant.\n"
    "USER QUESTION:\n{question}\n\n"
    "DATA the assistant had this turn (tool results; may be empty):\n{data}\n\n"
    "Score intent_match and grounding per the schema. Judge only this answer "
    "against this question and data — not overall conversation quality."
)


def _turn_messages(messages: list[BaseMessage]) -> list[BaseMessage]:
    """Messages of the current turn: from the last HumanMessage on."""
    for i in range(len(messages) - 1, -1, -1):
        if isinstance(messages[i], HumanMessage):
            return messages[i:]
    return messages


def _criteria_match_score(slots: UserSlots, recommendations: list[dict]) -> Optional[float]:
    """Fraction of applicable (slot, listing) checks the top results pass —
    a deterministic signal the LLM can't flatter its way around."""
    checks = passed = 0
    for rec in recommendations[:5]:
        listing = rec.get("listing", {})
        price, city = listing.get("price"), listing.get("city") or ""
        if slots.get("budget_max") is not None and price is not None:
            checks += 1
            passed += price <= slots["budget_max"]
        if slots.get("budget_min") is not None and price is not None:
            checks += 1
            passed += price >= slots["budget_min"]
        if slots.get("beds") is not None and listing.get("beds") is not None:
            checks += 1
            passed += listing["beds"] >= slots["beds"]
        if slots.get("baths") is not None and listing.get("baths") is not None:
            checks += 1
            passed += listing["baths"] >= slots["baths"]
        if slots.get("location") and city:
            checks += 1
            loc = slots["location"].split(",")[0].strip().lower()
            passed += loc in city.lower() or city.lower() in loc
    return round(passed / checks, 3) if checks else None


def make_score_node(llm, guarded: bool):
    judge = llm.with_structured_output(AnswerJudgment)

    def score_node(state: AgentState) -> dict:
        _status("Scoring answer confidence...")
        answer = state["messages"][-1].text
        if not answer.strip():
            return {}

        turn = _turn_messages(state["messages"])
        question = turn[0].text if turn else ""
        tool_texts = [
            m.content if isinstance(m.content, str) else str(m.content)
            for m in turn if isinstance(m, ToolMessage)
        ]

        components: dict[str, Optional[float]] = {}
        if tool_texts:
            any_data = any(t.strip() not in ("", "[]", "{}") for t in tool_texts)
            components["data_coverage"] = 1.0 if any_data else 0.3
        else:
            components["data_coverage"] = None

        searched = any(isinstance(m, ToolMessage) and getattr(m, "name", None) == "search_listings" for m in turn)
        components["criteria_match"] = (
            _criteria_match_score(state.get("slots", {}), state.get("recommendations", [])) if searched else None
        )
        components["compliance"] = (
            {"passed": 1.0, "revised": 0.6}.get(state.get("compliance_status")) if guarded else None
        )

        try:
            data_blob = "\n\n".join(tool_texts)[:6000] or "(no tool data this turn)"
            verdict = judge.invoke([
                SystemMessage(content=ANSWER_JUDGE_PROMPT.format(question=question, data=data_blob)),
                HumanMessage(content=f"ANSWER to score:\n{answer}"),
            ])
            components["intent_match"] = round(max(0.0, min(1.0, verdict.intent_match)), 3)
            components["grounding"] = round(max(0.0, min(1.0, verdict.grounding)), 3)
        except Exception:
            components["intent_match"] = None  # fail-open: scoring never kills an answer
            components["grounding"] = None

        applicable = {k: w for k, w in ANSWER_WEIGHTS.items() if components.get(k) is not None}
        if not applicable:
            return {}
        score = round(sum(components[k] * w for k, w in applicable.items()) / sum(applicable.values()), 3)

        return {
            "answer_confidence": {
                "score": score,
                "threshold": ANSWER_CONFIDENCE_THRESHOLD,
                "flagged": score < ANSWER_CONFIDENCE_THRESHOLD,
                "components": components,
                "redistributed": [k for k in ANSWER_WEIGHTS if components.get(k) is None],
            }
        }

    return score_node


# --------------------------------------------------------------- build --


def build_graph(fast_llm, smart_llm, tools: list, checkpointer=None, rule_retriever=None):
    # Task-based model routing (see api/llm.py): fast_llm handles cheap,
    # simple nodes (intake extraction, the clarify question); smart_llm
    # handles anywhere a wrong call is expensive — tool routing in
    # retrieve, the final answer, the compliance verdict, the scoring
    # judge.
    #
    # Only these four are callable by the LLM; get_listing_details is
    # deliberately unbound.
    directly_callable = {
        "search_listings", "get_neighborhood_demographics", "get_safety_stats",
        "get_market_trends", "get_market_trends_live",
    }
    retrieval_tools = [t for t in tools if t.name in directly_callable]
    llm_with_tools = smart_llm.bind_tools(retrieval_tools)

    graph = StateGraph(AgentState)
    graph.add_node("intake", make_intake_node(fast_llm))
    graph.add_node("confidence", confidence_node)
    graph.add_node("clarify", make_clarify_node(fast_llm))
    graph.add_node("retrieve", make_retrieve_node(llm_with_tools))
    graph.add_node("tools", ToolNode(retrieval_tools))
    graph.add_node("synthesis", synthesis_node)
    graph.add_node("present", make_present_node(smart_llm))

    # Answer path: present (or retrieve's direct reply) -> compliance
    # (when rules ingested) -> score (unless disabled) -> END. clarify
    # skips both: a question asserts nothing and isn't an answer.
    guarded = rule_retriever is not None
    scoring = os.environ.get("ANSWER_SCORING", "true").lower() == "true"
    if guarded:
        graph.add_node("compliance", make_compliance_node(smart_llm, rule_retriever))
    if scoring:
        graph.add_node("score", make_score_node(smart_llm, guarded))
    after_score = "score" if scoring else END
    answer_end = "compliance" if guarded else after_score

    graph.add_edge(START, "intake")
    graph.add_edge("intake", "confidence")
    graph.add_conditional_edges("confidence", gate)
    graph.add_edge("clarify", END)
    graph.add_conditional_edges("retrieve", route_after_retrieve, {"tools": "tools", "end_turn": answer_end})
    graph.add_conditional_edges("tools", route_after_tools)
    graph.add_edge("synthesis", "present")
    graph.add_edge("present", answer_end)
    if guarded:
        graph.add_edge("compliance", after_score)
    if scoring:
        graph.add_edge("score", END)

    return graph.compile(checkpointer=checkpointer)
