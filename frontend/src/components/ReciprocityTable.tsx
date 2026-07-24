import type { ReciprocityPair } from "../api";

interface ReciprocityTableProps {
  data: ReciprocityPair[];
}

interface MiniBarProps {
  label: string;
  value: number;
  max: number;
}

function MiniBar({ label, value, max }: MiniBarProps) {
  const percent = max > 0 ? (value / max) * 100 : 0;
  return (
    <div className="reciprocity-bar-row">
      <span className="reciprocity-bar-label" title={label}>
        {label}
      </span>
      <div className="reciprocity-bar-track">
        <div className="reciprocity-bar-fill" style={{ width: `${percent}%` }} />
      </div>
      <span className="reciprocity-bar-value">{value}</span>
    </div>
  );
}

export function ReciprocityTable({ data }: ReciprocityTableProps) {
  if (data.length === 0) {
    return <div className="panel-empty">Not enough review activity between pairs yet to say anything meaningful.</div>;
  }

  // Shared scale across every row, not per-row - a per-row max would make a
  // single review look as "full" as fifty, which misrepresents magnitude.
  const max = Math.max(1, ...data.flatMap((pair) => [pair.a_reviews_b, pair.b_reviews_a]));

  return (
    <table>
      <thead>
        <tr>
          <th>Pair</th>
          <th>Reviews</th>
          <th>Pattern</th>
        </tr>
      </thead>
      <tbody>
        {data.map((pair) => (
          <tr key={`${pair.person_a}-${pair.person_b}`}>
            <td>
              {pair.person_a} / {pair.person_b}
            </td>
            <td>
              <MiniBar label={`${pair.person_a} → ${pair.person_b}`} value={pair.a_reviews_b} max={max} />
              <MiniBar label={`${pair.person_b} → ${pair.person_a}`} value={pair.b_reviews_a} max={max} />
            </td>
            <td>
              {pair.one_directional ? (
                <span className="stale-badge warning">one-way</span>
              ) : (
                <span style={{ color: "var(--text-muted)" }}>mutual</span>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
