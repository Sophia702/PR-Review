import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { PRDuration } from "../api";
import { formatWeekLabel, toWeeklyTrend } from "../format";

interface TimeToMergeTrendProps {
  items: PRDuration[];
}

export function TimeToMergeTrend({ items }: TimeToMergeTrendProps) {
  const trend = toWeeklyTrend(items).map((point) => ({ ...point, medianDays: point.medianHours / 24 }));

  if (trend.length === 0) {
    return <div className="panel-empty">No merged PRs in this window.</div>;
  }

  return (
    <ResponsiveContainer width="100%" height={220}>
      <LineChart data={trend} margin={{ top: 8, right: 16, bottom: 4, left: 0 }}>
        <CartesianGrid stroke="var(--gridline)" vertical={false} />
        <XAxis
          dataKey="week"
          tickFormatter={formatWeekLabel}
          stroke="var(--text-muted)"
          fontSize={12}
          tickLine={false}
          axisLine={{ stroke: "var(--baseline)" }}
        />
        <YAxis
          stroke="var(--text-muted)"
          fontSize={12}
          tickLine={false}
          axisLine={{ stroke: "var(--baseline)" }}
          label={{ value: "days", angle: -90, position: "insideLeft", fill: "var(--text-muted)", fontSize: 12 }}
        />
        <Tooltip
          cursor={{ stroke: "var(--baseline)" }}
          contentStyle={{
            background: "var(--surface-1)",
            border: "1px solid var(--border)",
            borderRadius: 6,
            fontSize: 12,
          }}
          labelFormatter={(label: string) => `Week of ${formatWeekLabel(label)}`}
          formatter={(value: number, _name, props) => [
            `${value.toFixed(1)}d (n=${props.payload.count})`,
            "Median time-to-merge",
          ]}
        />
        <Line
          type="monotone"
          dataKey="medianDays"
          stroke="var(--series-1)"
          strokeWidth={2}
          dot={{ r: 4, fill: "var(--series-1)", stroke: "var(--surface-1)", strokeWidth: 2 }}
          activeDot={{ r: 5 }}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
