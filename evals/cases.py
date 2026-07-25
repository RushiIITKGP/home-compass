"""
The eval dataset — four suites, each measuring exactly one behavior.

How to grow this file: every time a real conversation goes wrong (you'll
see it in LangSmith traces), distill the failure into a case here. A
dataset built from real failures beats a big synthetic one.

Suites
------
CONFIDENCE_CASES   compute_confidence() in/out pairs. Pure function, no
                   LLM — these are exact assertions and should be 100%.
INTAKE_CASES       conversation -> expected extracted slots. Measures the
                   structured-output extraction only.
ROUTING_CASES      conversation -> expected gate decision + tool calls.
                   Measures the trajectory: clarify vs retrieve, and
                   which tool the LLM picks (against fake_tools).
GROUNDEDNESS_CASES fixed recommendation data + question -> the answer is
                   judged (LLM-as-judge) for inventing facts not in the
                   data.

Conventions
-----------
- Intake `expected`: only listed fields are checked. A value of None
  asserts the field must NOT be set (the "don't guess" rule). For
  must_haves, each expected keyword must appear as a substring of some
  extracted item (case-insensitive).
- Routing `expected_gate`: "clarify" | "retrieve" (derived from the
  final turn's confidence score vs the threshold).
  `must_call` / `must_not_call`: tool names checked against the final
  turn's tool calls only.
"""

# Weights reminder (agent.py SLOT_WEIGHTS): budget .30, location .30,
# beds_baths .20, must_haves .10, timeline .10 — threshold 0.8.

CONFIDENCE_CASES = [
    {
        "name": "empty slots -> zero, asks budget first",
        "slots": {},
        "expected_score": 0.0,
        "expected_missing": "budget",
    },
    {
        "name": "budget only -> 0.3, asks location next",
        "slots": {"budget_max": 500000},
        "expected_score": 0.3,
        "expected_missing": "location",
    },
    {
        "name": "budget + location -> 0.6, asks beds/baths next",
        "slots": {"budget_max": 500000, "location": "Austin"},
        "expected_score": 0.6,
        "expected_missing": "beds_baths",
    },
    {
        "name": "budget + location + beds -> exactly at threshold, nothing missing",
        "slots": {"budget_max": 500000, "location": "Austin", "beds": 3},
        "expected_score": 0.8,
        "expected_missing": None,
    },
    {
        "name": "everything filled -> 1.0",
        "slots": {
            "budget_min": 300000,
            "budget_max": 500000,
            "location": "Austin",
            "beds": 3,
            "baths": 2,
            "must_haves": ["yard"],
            "timeline": "3 months",
        },
        "expected_score": 1.0,
        "expected_missing": None,
    },
    {
        "name": "conflicting budget (min > max) doesn't count as filled",
        "slots": {
            "budget_min": 500000,
            "budget_max": 300000,
            "location": "Austin",
            "beds": 3,
            "baths": 2,
            "must_haves": ["yard"],
            "timeline": "3 months",
        },
        "expected_score": 0.7,
        "expected_missing": "budget",
    },
]


INTAKE_CASES = [
    {
        "name": "one-shot with beds, type, location, max budget",
        "conversation": [
            {"role": "user", "text": "I'm looking for a 3 bedroom house in Austin under $500k"},
        ],
        "expected": {
            "beds": 3,
            "property_type": "house",
            "location": "Austin",
            "budget_max": 500000,
            "budget_min": None,
        },
    },
    {
        "name": "budget range parsing (k-suffix, both ends)",
        "conversation": [
            {"role": "user", "text": "My budget is between 300k and 450k"},
        ],
        "expected": {"budget_min": 300000, "budget_max": 450000},
    },
    {
        "name": "lifestyle needs land in must_haves, no location guessed",
        "conversation": [
            {"role": "user", "text": "Somewhere quiet near good schools — we have two kids"},
        ],
        "expected": {"must_haves": ["quiet", "school"], "location": None},
    },
    {
        "name": "slots accumulate across turns",
        "conversation": [
            {"role": "user", "text": "I'm looking to buy in Denver"},
            {"role": "assistant", "text": "Great — what's your budget range?"},
            {"role": "user", "text": "Under 600k, and I need at least 2 bathrooms"},
        ],
        "expected": {"location": "Denver", "budget_max": 600000, "baths": 2},
    },
    {
        "name": "urgency captured as timeline, nothing else invented",
        "conversation": [
            {"role": "user", "text": "I need to move ASAP, within a month"},
        ],
        "expected": {"budget_max": None, "location": None},
        "expected_truthy": ["timeline"],
    },
    {
        "name": "pure greeting extracts nothing (don't guess)",
        "conversation": [
            {"role": "user", "text": "hi, can you help me find a home?"},
        ],
        "expected": {
            "budget_min": None,
            "budget_max": None,
            "location": None,
            "beds": None,
            "baths": None,
            "timeline": None,
        },
    },
    {
        "name": "dense one-shot fills every field",
        "conversation": [
            {
                "role": "user",
                "text": (
                    "4 bed 3 bath condo in Miami, max 900k, "
                    "needs a pool and a garage, moving next spring"
                ),
            },
        ],
        "expected": {
            "beds": 4,
            "baths": 3,
            "property_type": "condo",
            "location": "Miami",
            "budget_max": 900000,
            "must_haves": ["pool", "garage"],
        },
        "expected_truthy": ["timeline"],
    },
    {
        "name": "a correction overrides the earlier value",
        "conversation": [
            {"role": "user", "text": "Budget up to 400k"},
            {"role": "assistant", "text": "Got it — which area are you looking in?"},
            {"role": "user", "text": "Actually make that 450k. Looking in Portland."},
        ],
        "expected": {"budget_max": 450000, "location": "Portland"},
    },
]


ROUTING_CASES = [
    {
        "name": "vague opener -> clarify, no tools",
        "turns": ["I need a new place to live"],
        "expected_gate": "clarify",
        "must_not_call": ["search_listings"],
    },
    {
        "name": "complete criteria one-shot -> search",
        "turns": [
            "Looking for a 3 bed 2 bath in Austin, TX between 200k and 500k. "
            "Need a yard, hoping to move within 3 months."
        ],
        "expected_gate": "retrieve",
        "must_call": ["search_listings"],
    },
    {
        "name": "exactly at threshold (budget+location+beds) -> search",
        "turns": ["3 bedroom in Austin, TX under 500k please"],
        "expected_gate": "retrieve",
        "must_call": ["search_listings"],
    },
    {
        "name": "clarify then search across two turns",
        "turns": [
            "I'm looking to buy in Austin, TX",
            "Budget is 300k to 500k, need 3 beds and 2 baths",
        ],
        "expected_gate": "retrieve",
        "must_call": ["search_listings"],
    },
    {
        "name": "crime follow-up hits get_safety_stats, not a new search",
        "turns": [
            "Looking for a 3 bed 2 bath in Austin, TX between 200k and 500k, "
            "need a yard, moving within 3 months.",
            "What's the crime rate around the first one, at 101 Maple St?",
        ],
        "expected_gate": "retrieve",
        "must_call": ["get_safety_stats"],
        "must_not_call": ["search_listings"],
    },
    {
        "name": "conflicting budget blocks search even with everything else filled",
        "turns": [
            "3 bed 2 bath in Austin, TX, budget between 500k and 300k, "
            "need a yard, moving next month"
        ],
        "expected_gate": "clarify",
        "must_not_call": ["search_listings"],
    },
]


# Each groundedness case gives present_node a fixed `recommendations`
# payload and a question, then the judge checks the answer only states
# facts present in that payload.
_GROUNDED_RECS = [
    {
        "listing": {
            "id": "eval-listing-1",
            "address": "101 Maple St",
            "city": "Austin",
            "state": "TX",
            "zip_code": "78701",
            "price": 350000.0,
            "beds": 3,
            "baths": 2.0,
            "sqft": 1500,
            "status": "for_sale",
        },
        "recommendation_confidence": 0.4,
        "enrichment": {},
    },
    {
        "listing": {
            "id": "eval-listing-2",
            "address": "202 Oak Ave",
            "city": "Austin",
            "state": "TX",
            "zip_code": "78702",
            "price": 425000.0,
            "beds": 3,
            "baths": 2.5,
            "sqft": 1850,
            "status": "for_sale",
        },
        "recommendation_confidence": 0.4,
        "enrichment": {},
    },
]

GROUNDEDNESS_CASES = [
    {
        "name": "comparison question stays within the data",
        "question": "Which of these is cheapest, and how do they compare on space?",
        "recommendations": _GROUNDED_RECS,
        "slots": {"location": "Austin", "budget_max": 500000, "beds": 3},
    },
    {
        "name": "errored enrichment must not be presented as real stats",
        "question": "How safe is the neighborhood around 101 Maple St?",
        "recommendations": [
            {
                **_GROUNDED_RECS[0],
                "enrichment": {"safety": {"error": "FBI API unavailable"}},
            }
        ],
        "slots": {"location": "Austin"},
    },
    {
        "name": "no results -> no invented listings",
        "question": "What did you find for me?",
        "recommendations": [],
        "slots": {"location": "Austin", "budget_max": 200000, "beds": 5},
    },
]
