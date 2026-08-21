# evals/ — behavioral regression tests for the agent

Unit tests assert what code does; evals assert what the **model**
does. Any prompt edit, model upgrade, or graph change can silently
change behavior — this suite makes that visible before a user does.

## Run it

From the repo root, same virtualenv as the API (`.env` provides the
Gemini key):

```
python evals/run.py --suite confidence     # deterministic, no API key needed
python evals/run.py --suite all --runs 3   # the real thing
```

Exit code 0 only if every case passes → usable in CI to block a
regressing prompt change.

## The four suites, and why they're scored differently

| suite        | measures                                  | scorer                        |
|--------------|-------------------------------------------|-------------------------------|
| confidence   | `compute_confidence()` math + gate        | exact assertion (pure fn)     |
| intake       | conversation → extracted slots            | deterministic field compare   |
| routing      | gate decision + which tool got called     | deterministic trajectory check|
| groundedness | does the answer invent facts?             | LLM-as-judge, structured verdict |

The ordering is deliberate: prefer deterministic scorers wherever
possible, and only bring in an LLM judge for the one question
("did it make something up?") that has no exact-match answer. When you
change the judge prompt, spot-check a few of its verdicts by hand
before trusting it — judges are biased toward leniency and long
answers.

## Isolation

The routing suite runs the **real graph** (`build_graph`) but with the
tools swapped for `fake_tools.py` — same names and signatures, canned
data. So a routing failure can only mean one thing: the LLM chose
wrong. No Postgres, no MCP servers, no government APIs involved.

## --runs and flakiness

LLMs are non-deterministic even at temperature 0. `--runs 3` replays
each case 3×; a case passes on strict majority. `2/3 (FLAKY)` in the
output is a finding in itself — the prompt is borderline for that
case. Don't average it away; tighten the prompt until it's 3/3.

## The workflow this enables

1. See a bad conversation (or a failing case here).
2. Open its trace in LangSmith — eval runs are traced like any other
   traffic — and find the node where it went wrong.
3. Fix the prompt / graph.
4. `python evals/run.py --suite all --runs 3` — confirm the fix AND
   that nothing else regressed.
5. If the failure came from a real conversation, add it to `cases.py`
   so it can never come back silently.

Step 5 is how the dataset grows: distilled real failures beat large
synthetic datasets.

## Where to take this next (learning path)

- **LangSmith datasets & experiments**: upload `cases.py` as a LangSmith
  dataset and run via their `evaluate()` — you get score history over
  time, side-by-side diffs between prompt versions, and a UI for
  annotating failures.
- **Pairwise comparison**: when trying a new model (or local model for
  intake), run both and have a judge pick the better output per case.
- **Online evals**: sample real production traces and run the
  groundedness judge on them asynchronously — evals on live traffic,
  not just curated cases.
