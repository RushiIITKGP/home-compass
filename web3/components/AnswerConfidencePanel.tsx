import type { AnswerConfidence } from "@/lib/types";

/**
 * Per-answer confidence box at the bottom of an agent message — how
 * good THIS answer is to THIS question, with the component breakdown
 * (mirrors ANSWER_WEIGHTS in api/agent.py). Components that didn't
 * apply this turn show as n/a with their weight redistributed, and a
 * score under the threshold is flagged for review.
 */

const LABELS: Record<string, string> = {
  intent_match: "Intent match",
  grounding: "Grounding",
  data_coverage: "Data coverage",
  criteria_match: "Criteria match",
  compliance: "Compliance",
};

export function AnswerConfidencePanel({ confidence }: { confidence: AnswerConfidence }) {
  const { score, threshold, flagged, components, redistributed } = confidence;

  const entries = Object.entries(LABELS).map(([key, label]) => ({
    label,
    value: components[key as keyof typeof components],
  }));

  return (
    <div
      className={`w-full rounded-lg border px-4 py-2.5 text-sm ${
        flagged ? "border-danger/40 bg-danger/5" : "border-rule bg-ink-2/60"
      }`}
    >
      <div className="flex items-baseline justify-between gap-3">
        <span className="font-mono text-xs uppercase tracking-wide text-muted">
          Answer confidence
        </span>
        <span
          className={`font-mono text-sm tabular-nums ${
            flagged ? "text-danger" : "text-verdigris-bright"
          }`}
        >
          {score.toFixed(3)}
          {flagged && <span className="ml-2 text-xs">flagged for review</span>}
        </span>
      </div>

      <p className="mt-1.5 font-mono text-[11px] leading-relaxed text-muted">
        {entries.map((entry, i) => (
          <span key={entry.label}>
            {i > 0 && " · "}
            {entry.label}:{" "}
            <span className={entry.value == null ? "" : "text-parchment"}>
              {entry.value == null ? "n/a" : entry.value.toFixed(3)}
            </span>
          </span>
        ))}
        {" · "}Threshold: {threshold.toFixed(2)}
      </p>

      {redistributed.length > 0 && (
        <p className="mt-1 text-[10px] text-muted">
          {redistributed.map((k) => LABELS[k] ?? k).join(", ")} not applicable this turn — weight
          redistributed.
        </p>
      )}
    </div>
  );
}
