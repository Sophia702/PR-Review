interface SparklineProps {
  values: number[];
  width?: number;
  height?: number;
}

/** A minimal trend line for a stat tile: 2px line in the de-emphasis ink,
 * current-period end-point as an 8px accent-colored marker with a surface
 * ring so it stays legible where the line crosses under it. */
export function Sparkline({ values, width = 100, height = 28 }: SparklineProps) {
  if (values.length < 2) return null;

  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const padding = 4;
  const usableHeight = height - padding * 2;
  const stepX = width / (values.length - 1);

  const points = values.map((v, i) => {
    const x = i * stepX;
    const y = padding + usableHeight - ((v - min) / range) * usableHeight;
    return [x, y] as const;
  });

  const path = points.map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const [lastX, lastY] = points[points.length - 1];

  return (
    <svg width={width} height={height} className="sparkline" role="img" aria-hidden="true">
      <path
        d={path}
        fill="none"
        stroke="var(--text-muted)"
        strokeWidth={2}
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      <circle cx={lastX} cy={lastY} r={4} fill="var(--series-1)" stroke="var(--surface-1)" strokeWidth={2} />
    </svg>
  );
}
