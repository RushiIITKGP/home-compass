#!/usr/bin/env python3
"""
Eval harness for the Home Compass agent (see evals/README.md for the
concepts; see cases.py for the dataset and how to grow it).

Usage — from the repo root, same virtualenv as the API:

    python evals/run.py --suite confidence   # deterministic, no API key
    python evals/run.py --suite intake
    python evals/run.py --suite routing
    python evals/run.py --suite groundedness
    python evals/run.py --suite all --runs 3

--runs N replays every LLM-dependent case N times. LLMs are
non-deterministic even at temperature 0, so a single run can't tell a
real regression from noise: a case that passes 3/3 is solid, 2/3 is
flaky (which is itself a finding — tighten the prompt), 0/3 is broken.
A case PASSES overall if a strict majority of its runs pass.

Exit code is 0 only if every case passes — so this can run in CI and
block a prompt change that regresses behavior.

If LangSmith tracing is enabled (see .env), every eval run is traced
like any other traffic — open a failing case's trace to see exactly
what the model was asked and answered. That loop (fail -> trace ->
fix -> re-run) is the whole workflow this exists for.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Same guard as api/main.py: tracing enabled without an API key means
# every LLM call spews background upload failures into the eval output.
import os  # noqa: E402

if os.environ.get("LANGCHAIN_TRACING_V2", "").lower() == "true" and not (
    os.environ.get("LANGCHAIN_API_KEY") or os.environ.get("LANGSMITH_API_KEY")
):
    os.environ["LANGCHAIN_TRACING_V2"] = "false"
    print("[observability] no LANGCHAIN_API_KEY — tracing disabled for this eval run")

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(REPO_ROOT))  # repo root
sys.path.append(str(REPO_ROOT / "api"))  # agent.py
sys.path.append(str(Path(__file__).resolve().parent))  # cases.py, fake_tools.py

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from agent import (  # noqa: E402
    CONFIDENCE_THRESHOLD,
    INTAKE_SYSTEM_PROMPT,
    ExtractedSlots,
    build_graph,
    compute_confidence,
    extract_text_content,
    make_present_node,
)
from cases import CONFIDENCE_CASES, GROUNDEDNESS_CASES, INTAKE_CASES, ROUTING_CASES  # noqa: E402
from fake_tools import FAKE_TOOLS  # noqa: E402

# ------------------------------------------------------------- results --


@dataclass
class RunResult:
    suite: str
    case: str
    run: int
    passed: bool
    detail: str = ""


def _conversation_messages(conversation: list[dict]) -> list:
    out = []
    for turn in conversation:
        cls = HumanMessage if turn["role"] == "user" else AIMessage
        out.append(cls(content=turn["text"]))
    return out


# --------------------------------------------------- suite: confidence --
# Pure-function assertions — no LLM, no network. If any of these fail,
# either compute_confidence changed or the cases are stale; both need a
# human decision, which is exactly what a failing eval should force.


def run_confidence_suite() -> list[RunResult]:
    results = []
    for case in CONFIDENCE_CASES:
        score, missing = compute_confidence(case["slots"])
        problems = []
        if abs(score - case["expected_score"]) > 1e-9:
            problems.append(f"score {score} != expected {case['expected_score']}")
        if missing != case["expected_missing"]:
            problems.append(f"missing_slot {missing!r} != expected {case['expected_missing']!r}")
        results.append(
            RunResult("confidence", case["name"], 1, not problems, "; ".join(problems))
        )
    return results


# ------------------------------------------------------- suite: intake --
# Measures ONLY the structured extraction: conversation in, slots out.
# Scoring is deterministic field comparison — no judge needed.


def _field_matches(field: str, expected, actual) -> bool:
    if expected is None:
        return actual is None
    if field == "must_haves":
        if not isinstance(actual, list):
            return False
        joined = " | ".join(str(item).lower() for item in actual)
        return all(str(keyword).lower() in joined for keyword in expected)
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        return abs(float(expected) - float(actual)) < 1e-6
    if isinstance(expected, str) and isinstance(actual, str):
        e, a = expected.lower(), actual.lower()
        return e in a or a in e
    return expected == actual


def run_intake_suite(llm, runs: int) -> list[RunResult]:
    extractor = llm.with_structured_output(ExtractedSlots)
    results = []
    for case in INTAKE_CASES:
        for run in range(1, runs + 1):
            prompt = [SystemMessage(content=INTAKE_SYSTEM_PROMPT)]
            prompt += _conversation_messages(case["conversation"])
            try:
                extracted = extractor.invoke(prompt).model_dump()
            except Exception as exc:  # a hard error is a failed run, not a crash
                results.append(RunResult("intake", case["name"], run, False, f"exception: {exc}"))
                continue

            problems = []
            for field, expected in case["expected"].items():
                actual = extracted.get(field)
                if not _field_matches(field, expected, actual):
                    problems.append(f"{field}: expected {expected!r}, got {actual!r}")
            for field in case.get("expected_truthy", []):
                if not extracted.get(field):
                    problems.append(f"{field}: expected to be set, got {extracted.get(field)!r}")

            results.append(RunResult("intake", case["name"], run, not problems, "; ".join(problems)))
    return results


# ------------------------------------------------------ suite: routing --
# Measures the trajectory: gate decision (clarify vs retrieve) and which
# tools the LLM called on the FINAL turn — against fake_tools, so no
# database or MCP servers are involved. Multi-turn cases replay the whole
# conversation through a fresh graph + in-memory checkpointer.


def run_routing_suite(llm, runs: int) -> list[RunResult]:
    from langgraph.checkpoint.memory import MemorySaver

    results = []
    for case in ROUTING_CASES:
        for run in range(1, runs + 1):
            graph = build_graph(llm, FAKE_TOOLS, checkpointer=MemorySaver())
            config = {"configurable": {"thread_id": str(uuid.uuid4())}}
            try:
                state = {}
                messages_before_final = 0
                for i, turn in enumerate(case["turns"]):
                    if i == len(case["turns"]) - 1:
                        messages_before_final = len(state.get("messages", []))
                    state = graph.invoke({"messages": [HumanMessage(content=turn)]}, config=config)
            except Exception as exc:
                results.append(RunResult("routing", case["name"], run, False, f"exception: {exc}"))
                continue

            problems = []

            gate = "retrieve" if state["confidence_score"] >= CONFIDENCE_THRESHOLD else "clarify"
            if gate != case["expected_gate"]:
                problems.append(
                    f"gate {gate!r} != expected {case['expected_gate']!r} "
                    f"(confidence {state['confidence_score']:.2f})"
                )

            final_turn_messages = state["messages"][messages_before_final:]
            called = {
                tc["name"]
                for m in final_turn_messages
                if isinstance(m, AIMessage)
                for tc in (m.tool_calls or [])
            }
            for tool_name in case.get("must_call", []):
                if tool_name not in called:
                    problems.append(f"expected {tool_name} to be called; called={sorted(called) or 'none'}")
            for tool_name in case.get("must_not_call", []):
                if tool_name in called:
                    problems.append(f"{tool_name} must NOT be called; called={sorted(called)}")

            results.append(RunResult("routing", case["name"], run, not problems, "; ".join(problems)))
    return results


# ------------------------------------------- suite: groundedness (judge) --
# The one suite that needs LLM-as-judge, because "did the answer invent
# facts?" has no exact-match answer. The judge gets the SAME data the
# agent had plus the agent's answer, and returns a structured verdict —
# never free text, so scoring stays mechanical. Judges have biases
# (leniency, verbosity preference): before trusting a changed judge
# prompt, read a few of its verdicts yourself and check you agree.


class JudgeVerdict(BaseModel):
    grounded: bool = Field(
        description="True only if every specific factual claim in the answer "
        "(prices, counts, statistics, addresses, features) appears in the DATA."
    )
    ungrounded_claims: list[str] = Field(
        default_factory=list,
        description="Each specific claim in the answer that does not appear in the DATA.",
    )


JUDGE_SYSTEM_PROMPT = (
    "You are grading a real-estate assistant's answer for groundedness.\n"
    "DATA (everything the assistant was allowed to use):\n{data}\n\n"
    "Rules:\n"
    "- A claim is ungrounded if it states a specific fact (price, statistic, "
    "count, address, amenity, safety figure) not present in DATA.\n"
    "- Saying data is unavailable, hedging, giving general advice, or asking "
    "a follow-up question is GROUNDED.\n"
    "- If DATA contains an 'error' field for some category, presenting any "
    "concrete figure for that category is ungrounded.\n"
    "- Arithmetic over values in DATA (e.g. price differences) is grounded."
)


def run_groundedness_suite(llm, runs: int) -> list[RunResult]:
    present_node = make_present_node(llm)
    judge = llm.with_structured_output(JudgeVerdict)

    results = []
    for case in GROUNDEDNESS_CASES:
        for run in range(1, runs + 1):
            state = {
                "messages": [HumanMessage(content=case["question"])],
                "recommendations": case["recommendations"],
                "slots": case.get("slots", {}),
                "enrichment": {},
                "confidence_score": 1.0,
                "missing_slot": None,
            }
            try:
                answer = extract_text_content(present_node(state)["messages"][-1].content)
                verdict = judge.invoke(
                    [
                        SystemMessage(
                            content=JUDGE_SYSTEM_PROMPT.format(
                                data=json.dumps(case["recommendations"], indent=2)
                            )
                        ),
                        HumanMessage(content=f"ANSWER to grade:\n{answer}"),
                    ]
                )
            except Exception as exc:
                results.append(RunResult("groundedness", case["name"], run, False, f"exception: {exc}"))
                continue

            detail = "" if verdict.grounded else f"ungrounded: {verdict.ungrounded_claims}"
            results.append(RunResult("groundedness", case["name"], run, verdict.grounded, detail))
    return results


# ------------------------------------------------------------ reporting --


def report(results: list[RunResult]) -> bool:
    """Prints per-case results and returns overall pass/fail. A case
    passes if a strict majority of its runs passed."""
    by_case: dict[tuple[str, str], list[RunResult]] = defaultdict(list)
    for r in results:
        by_case[(r.suite, r.case)].append(r)

    all_passed = True
    current_suite = None
    suite_tallies: dict[str, list[int]] = defaultdict(lambda: [0, 0])

    for (suite, case), runs_list in by_case.items():
        if suite != current_suite:
            current_suite = suite
            print(f"\n=== {suite} ===")
        n_pass = sum(1 for r in runs_list if r.passed)
        n = len(runs_list)
        case_passed = n_pass * 2 > n
        suite_tallies[suite][0] += int(case_passed)
        suite_tallies[suite][1] += 1
        all_passed = all_passed and case_passed

        flaky = " (FLAKY)" if 0 < n_pass < n else ""
        mark = "PASS" if case_passed else "FAIL"
        print(f"  [{mark}] {case} — {n_pass}/{n} runs{flaky}")
        for r in runs_list:
            if not r.passed and r.detail:
                print(f"         run {r.run}: {r.detail}")

    print("\n--- summary ---")
    for suite, (passed, total) in suite_tallies.items():
        print(f"  {suite}: {passed}/{total} cases")
    print(f"  overall: {'PASS' if all_passed else 'FAIL'}")
    return all_passed


def build_llm():
    # Same factory as api/setup.py (api/llm.py, CHAT_MODEL in .env) so
    # evals always test the provider the app actually runs — but at
    # temperature 0, the most deterministic behavior the model can give.
    # Bake-off trick: run the suite twice with different CHAT_MODEL
    # values and compare the two score tables.
    from llm import build_chat_model

    return build_chat_model(temperature=0.0)


SUITES = ("confidence", "intake", "routing", "groundedness")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", choices=(*SUITES, "all"), default="all")
    parser.add_argument("--runs", type=int, default=1, help="repetitions per LLM case (default 1)")
    args = parser.parse_args()

    selected = SUITES if args.suite == "all" else (args.suite,)
    results: list[RunResult] = []

    if "confidence" in selected:
        results += run_confidence_suite()

    llm_suites = [s for s in selected if s != "confidence"]
    if llm_suites:
        llm = build_llm()
        if "intake" in llm_suites:
            results += run_intake_suite(llm, args.runs)
        if "routing" in llm_suites:
            results += run_routing_suite(llm, args.runs)
        if "groundedness" in llm_suites:
            results += run_groundedness_suite(llm, args.runs)

    return 0 if report(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
