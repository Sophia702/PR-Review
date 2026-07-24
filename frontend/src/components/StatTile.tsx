import type { Delta } from "../format";
import { Sparkline } from "./Sparkline";

interface StatTileProps {
  label: string;
  value: string;
  sublabel?: string;
  delta?: Delta | null;
  trend?: number[];
  hero?: boolean;
}

export function StatTile({ label, value, sublabel, delta, trend, hero }: StatTileProps) {
  return (
    <div className={hero ? "stat-tile stat-tile-hero" : "stat-tile"}>
      <div className="stat-tile-label">{label}</div>
      <div className="stat-tile-main">
        <div className="stat-tile-value">{value}</div>
        {delta && (
          <span className={delta.improved ? "stat-tile-delta good" : "stat-tile-delta bad"}>
            {delta.percentChange < 0 ? "▼" : "▲"} {Math.abs(delta.percentChange).toFixed(0)}%
          </span>
        )}
      </div>
      {sublabel && <div className="stat-tile-sublabel">{sublabel}</div>}
      {trend && trend.length >= 2 && (
        <div className="stat-tile-trend">
          <Sparkline values={trend} />
        </div>
      )}
    </div>
  );
}
