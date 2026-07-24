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

export interface Delta {
  percentChange: number;
  improved: boolean;
}

const MIN_ITEMS_PER_HALF = 2;

/** Splits the full (chronologically ordered) item set into an earlier and a
 * more recent half and compares their medians. Deliberately not a
 * week-over-week comparison: with sparse data (a PR or two per week) that
 * would swing wildly on sample noise alone and read as a dramatic change
 * that isn't real. Requires at least MIN_ITEMS_PER_HALF PRs in each half -
 * returns null rather than show a delta backed by too little data.
 * Lower is better for duration metrics (time-to-first-review, time-to-merge),
 * so a negative change is the "improved" direction. */
export function computeDurationDelta(items: PRDuration[]): Delta | null {
  if (items.length < MIN_ITEMS_PER_HALF * 2) return null;

  const sorted = [...items].sort((a, b) => a.end_at.localeCompare(b.end_at));
  const mid = Math.floor(sorted.length / 2);
  const previous = median(sorted.slice(0, mid).map((item) => item.hours));
  const current = median(sorted.slice(mid).map((item) => item.hours));
  if (previous === 0) return null;

  const percentChange = ((current - previous) / previous) * 100;
  return { percentChange, improved: percentChange < 0 };
}
