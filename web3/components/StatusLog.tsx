interface StatusLogProps {
  entries: string[];
}

/**
 * The live "what's happening right now" log — each line is a status
 * update written by a node in api/agent.py via _status(), streamed as
 * it happens rather than leaving a silent gap while the graph works
 * through several steps. Quiet and secondary by design (small, muted,
 * monospace, like a field log) — the point is transparency into what
 * the agent did, not competing with the actual reply for attention.
 */
export function StatusLog({ entries }: StatusLogProps) {
  if (entries.length === 0) return null;

  return (
    <ul className="flex flex-col gap-1 font-mono text-xs text-muted">
      {entries.map((entry, i) => (
        <li key={i} className="flex items-center gap-2">
          <span className="inline-block h-1 w-1 shrink-0 rounded-full bg-verdigris-bright" aria-hidden />
          {entry}
        </li>
      ))}
    </ul>
  );
}
