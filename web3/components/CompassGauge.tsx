"use client";

interface CompassGaugeProps {
  score: number; // 0..1
  size?: number;
}

/**
 * The confidence indicator, drawn as a compass needle rather than a
 * progress bar — the product is named Home Compass, and "how sure are
 * we of our bearings" is a more honest metaphor for this number than a
 * loading-bar aesthetic would be. Needle points south (no bearing) at
 * 0% and swings to true north (confident) at 100%.
 */
export function CompassGauge({ score, size = 56 }: CompassGaugeProps) {
  const clamped = Math.max(0, Math.min(1, score));
  const rotation = 180 * (1 - clamped);
  const pct = Math.round(clamped * 100);

  return (
    <div className="flex items-center gap-3" role="img" aria-label={`Confidence: ${pct} percent`}>
      <svg width={size} height={size} viewBox="0 0 100 100" className="shrink-0">
        <circle cx="50" cy="50" r="46" fill="var(--color-ink-2)" stroke="var(--color-rule-bright)" strokeWidth="1.5" />

        {/* Major tick marks — N / E / S / W */}
        {[0, 90, 180, 270].map((deg) => (
          <line
            key={deg}
            x1="50"
            y1="8"
            x2="50"
            y2="15"
            stroke="var(--color-parchment-dim)"
            strokeWidth="2"
            transform={`rotate(${deg} 50 50)`}
          />
        ))}
        {/* Minor tick marks */}
        {[45, 135, 225, 315].map((deg) => (
          <line
            key={deg}
            x1="50"
            y1="10"
            x2="50"
            y2="15"
            stroke="var(--color-muted)"
            strokeWidth="1"
            transform={`rotate(${deg} 50 50)`}
          />
        ))}

        {/* Needle */}
        <g style={{ transform: `rotate(${rotation}deg)`, transformOrigin: "50px 50px", transition: "transform 700ms cubic-bezier(0.16, 1, 0.3, 1)" }}>
          <polygon points="50,14 44,50 50,56 56,50" fill="var(--color-brass-bright)" />
          <polygon points="50,86 44,50 50,44 56,50" fill="var(--color-muted)" />
        </g>

        <circle cx="50" cy="50" r="4" fill="var(--color-parchment)" />
      </svg>
      <span className="font-mono text-lg text-parchment tabular-nums">{pct}%</span>
    </div>
  );
}
