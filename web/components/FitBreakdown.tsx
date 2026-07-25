import type { Recommendation } from "@/lib/types";

/**
 * Explains, under the listing cards, exactly how each card's fit % is
 * calculated. Mirrors FIT_WEIGHTS + compute_fit() in api/agent.py —
 * keep them in sync. Criteria the user hasn't stated show as excluded
 * (their weight redistributes across the rest).
 */

const CRITERIA = [
  { key: "budget", label: "Budget", weight: 35, how: "100% within your range; over budget scales down proportionally" },
  { key: "location", label: "Location", weight: 25, how: "city matches your stated area" },
  { key: "beds", label: "Bedrooms", weight: 20, how: "100% at or above your minimum; below scales down" },
  { key: "baths", label: "Bathrooms", weight: 20, how: "100% at or above your minimum; below scales down" },
] as const;

export function FitBreakdown({ recommendations }: { recommendations: Recommendation[] }) {
  if (recommendations.length === 0) return null;
  const sample = recommendations[0]?.fit_components;

  return (
    <details className="mt-1 w-full rounded-lg border border-rule bg-ink-2/60 px-4 py-2.5 text-sm">
      <summary className="cursor-pointer select-none font-mono text-xs uppercase tracking-wide text-muted hover:text-parchment">
        How the fit % on each card is calculated
      </summary>
      <div className="mt-3 flex flex-col gap-1.5">
        {CRITERIA.map((criterion) => {
          const applies = sample ? sample[criterion.key] != null : true;
          return (
            <div key={criterion.key} className="flex items-baseline justify-between gap-3">
              <span className={applies ? "text-parchment" : "text-muted"}>
                <span className="font-mono text-xs mr-2">{applies ? "✓" : "—"}</span>
                {criterion.label}
                <span className="ml-2 text-xs text-muted">{applies ? criterion.how : "not in your criteria — weight redistributed"}</span>
              </span>
              <span className="font-mono text-xs tabular-nums text-brass-bright shrink-0">
                {criterion.weight}%
              </span>
            </div>
          );
        })}
        <p className="mt-2 border-t border-rule pt-2 text-xs leading-relaxed text-muted">
          Fit measures how well each listing matches what you asked for — it is graded, not
          pass/fail (slightly over budget scores slightly lower, not zero). It does not yet include
          neighborhood data like crime or schools; ask about a listing to see that data with
          sources. Cards are ranked by fit.
        </p>
      </div>
    </details>
  );
}
