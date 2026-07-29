interface StatusLogProps {
  entries: string[];
}

export function StatusLog({ entries }: StatusLogProps) {
  if (entries.length === 0) return null;

  return (
    <ul className="flex flex-col gap-1 font-mono text-xs text-muted">
      {entries.map((entry, i) => (
        <li key={i} className="flex items-center gap-2">
          <span className="inline-block h-1 w-1 shrink-0 rounded-full bg-moss-bright" aria-hidden />
          {entry}
        </li>
      ))}
    </ul>
  );
}