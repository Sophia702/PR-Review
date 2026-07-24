import type { ReciprocityPair } from "../api";

interface ReciprocityTableProps {
  data: ReciprocityPair[];
}

export function ReciprocityTable({ data }: ReciprocityTableProps) {
  if (data.length === 0) {
    return <div className="panel-empty">Not enough review activity between pairs yet to say anything meaningful.</div>;
  }

  return (
    <table>
      <thead>
        <tr>
          <th>Pair</th>
          <th>A → B reviews</th>
          <th>B → A reviews</th>
          <th>Pattern</th>
        </tr>
      </thead>
      <tbody>
        {data.map((pair) => (
          <tr key={`${pair.person_a}-${pair.person_b}`}>
            <td>
              {pair.person_a} / {pair.person_b}
            </td>
            <td>{pair.a_reviews_b}</td>
            <td>{pair.b_reviews_a}</td>
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
