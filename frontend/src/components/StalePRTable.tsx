import type { StalePR } from "../api";

interface StalePRTableProps {
  data: StalePR[];
}

function severity(daysStale: number): "warning" | "critical" {
  return daysStale >= 30 ? "critical" : "warning";
}

export function StalePRTable({ data }: StalePRTableProps) {
  if (data.length === 0) {
    return <div className="panel-empty">No stale PRs in this window.</div>;
  }

  return (
    <table>
      <thead>
        <tr>
          <th>PR</th>
          <th>Title</th>
          <th>Author</th>
          <th>Idle for</th>
        </tr>
      </thead>
      <tbody>
        {data.map((pr) => (
          <tr key={pr.number}>
            <td>#{pr.number}</td>
            <td>{pr.title}</td>
            <td>{pr.author ?? "—"}</td>
            <td>
              <span className={`stale-badge ${severity(pr.days_stale)}`}>{pr.days_stale}d</span>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
