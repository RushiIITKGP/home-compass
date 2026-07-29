"use client";

interface CompassGaugeProps {
  score: number; // 0..1
  size?: number;
  variant?: "compact" | "full";
  label?: string;
}

export function CompassGauge({ score, size = 96, variant = "compact", label = "Needs understood" }: CompassGaugeProps) {
  const clamped = Math.max(0, Math.min(1, score));
  const pct = Math.round(clamped * 100);
  const ready = clamped >= 0.8;

  const angleDeg = 180 - 180 * clamped;
  const angleRad = (angleDeg * Math.PI) / 180;
  const cx = 100;
  const cy = 100;
  const r = 78;
  const needleR = 66;
  const tipX = cx + needleR * Math.cos(angleRad);
  const tipY = cy - needleR * Math.sin(angleRad);

  const arc = (
    <svg
      width={size}
      height={size * 0.62}
      viewBox="0 0 200 124"
      className="shrink-0"
      role="img"
      aria-label={`Confidence: ${pct} percent`}
    >
      <path
        d={`M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`}
        fill="none"
        stroke="var(--color-rule-bright)"
        strokeWidth="9"
        strokeLinecap="round"
      />
      <path
        d={`M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`}
        fill="none"
        stroke="var(--color-moss)"
        strokeWidth="9"
        strokeLinecap="round"
        strokeDasharray={`${Math.PI * r}`}
        strokeDashoffset={`${Math.PI * r * (1 - clamped)}`}
        style={{ transition: "stroke-dashoffset 700ms cubic-bezier(0.16, 1, 0.3, 1)" }}
      />
      <line
        x1={cx}
        y1={cy}
        x2={tipX}
        y2={tipY}
        stroke="var(--color-brass-deep)"
        strokeWidth="3.5"
        strokeLinecap="round"
        style={{ transition: "all 700ms cubic-bezier(0.16, 1, 0.3, 1)" }}
      />
      <circle cx={cx} cy={cy} r="5" fill="var(--color-ink)" />
    </svg>
  );

  if (variant === "compact") {
    return (
      <div className="flex items-center gap-2">
        {arc}
        <span className="font-mono text-sm text-ink tabular-nums">{pct}%</span>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-5">
      {arc}
      <div>
        <p className="font-display text-4xl leading-none text-ink tabular-nums">{clamped.toFixed(2)}</p>
        <p className="mt-1 font-mono text-[11px] uppercase tracking-wide text-muted">{label}</p>
        <span
          className={`mt-2 inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 font-mono text-[11px] uppercase tracking-wide ${
            ready ? "border-moss/40 text-moss" : "border-rule-bright text-muted"
          }`}
        >
          <span className={`h-1.5 w-1.5 rounded-full ${ready ? "bg-moss" : "bg-muted"}`} aria-hidden />
          {ready ? "Ready to search" : "Gathering needs"}
        </span>
      </div>
    </div>
  );
}