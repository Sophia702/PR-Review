import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { ReviewerLoad } from "../api";

interface ReviewLoadChartProps {
  data: ReviewerLoad[];
}

export function ReviewLoadChart({ data }: ReviewLoadChartProps) {
  if (data.length === 0) {
    return <div className="panel-empty">No reviews in this window.</div>;
  }

  const height = Math.max(120, data.length * 36);

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} layout="vertical" margin={{ top: 4, right: 24, bottom: 4, left: 8 }}>
        <CartesianGrid horizontal={false} stroke="var(--gridline)" />
        <XAxis
          type="number"
          allowDecimals={false}
          stroke="var(--text-muted)"
          fontSize={12}
          tickLine={false}
          axisLine={{ stroke: "var(--baseline)" }}
        />
        <YAxis
          type="category"
          dataKey="reviewer"
          width={110}
          stroke="var(--text-muted)"
          fontSize={12}
          tickLine={false}
          axisLine={{ stroke: "var(--baseline)" }}
        />
        <Tooltip
          cursor={{ fill: "var(--gridline)" }}
          contentStyle={{
            background: "var(--surface-1)",
            border: "1px solid var(--border)",
            borderRadius: 6,
            fontSize: 12,
          }}
          formatter={(value: number) => [`${value} review${value === 1 ? "" : "s"}`, "Reviews given"]}
        />
        <Bar dataKey="review_count" fill="var(--series-1)" radius={[0, 4, 4, 0]} maxBarSize={24} />
      </BarChart>
    </ResponsiveContainer>
  );
}
