import type { PRDuration } from "./api";

export function formatHours(hours: number | null): string {
  if (hours === null) return "—";
  if (hours < 24) return `${hours.toFixed(1)}h`;
  return `${(hours / 24).toFixed(1)}d`;
}

export function median(values: number[]): number {
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 !== 0 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

function mondayOf(dateStr: string): string {
  const d = new Date(dateStr);
  const dayIndex = (d.getUTCDay() + 6) % 7; // Monday = 0
  const monday = new Date(d);
  monday.setUTCDate(d.getUTCDate() - dayIndex);
  return monday.toISOString().slice(0, 10);
}

export interface WeeklyTrendPoint {
  week: string;
  medianHours: number;
  count: number;
}

/** Buckets PR durations by the ISO week their end event fell in, so a
 * time-to-merge trend can be charted over weeks without a dedicated
 * backend aggregation. */
export function toWeeklyTrend(items: PRDuration[]): WeeklyTrendPoint[] {
  const buckets = new Map<string, number[]>();
  for (const item of items) {
    const week = mondayOf(item.end_at);
    const bucket = buckets.get(week) ?? [];
    bucket.push(item.hours);
    buckets.set(week, bucket);
  }
  return Array.from(buckets.entries())
    .map(([week, hoursList]) => ({ week, medianHours: median(hoursList), count: hoursList.length }))
    .sort((a, b) => a.week.localeCompare(b.week));
}

export function formatWeekLabel(week: string): string {
  const d = new Date(week);
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}
