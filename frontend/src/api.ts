const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export interface RepoSummary {
  owner: string;
  name: string;
}

export interface PRDuration {
  number: number;
  title: string;
  author: string | null;
  start_at: string;
  end_at: string;
  hours: number;
}

export interface DurationSummary {
  count: number;
  avg_hours: number | null;
  median_hours: number | null;
  items: PRDuration[];
}

export interface ReviewerLoad {
  reviewer: string;
  review_count: number;
}

export interface StalePR {
  number: number;
  title: string;
  author: string | null;
  updated_at: string;
  days_stale: number;
}

export interface ReciprocityPair {
  person_a: string;
  person_b: string;
  a_reviews_b: number;
  b_reviews_a: number;
  one_directional: boolean;
}

export interface MetricsFilters {
  since?: string;
  until?: string;
  author?: string;
}

class ApiError extends Error {}

async function getJSON<T>(path: string, params: Record<string, string | undefined> = {}): Promise<T> {
  const url = new URL(`${API_BASE_URL}${path}`);
  for (const [key, value] of Object.entries(params)) {
    if (value) url.searchParams.set(key, value);
  }
  const response = await fetch(url.toString());
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new ApiError(body.detail ?? `${response.status} ${response.statusText}`);
  }
  return response.json();
}

export function listRepos(): Promise<RepoSummary[]> {
  return getJSON("/repos");
}

export async function triggerSync(
  owner: string,
  repo: string,
  apiKey: string,
): Promise<{ repo: string; synced: number }> {
  const response = await fetch(`${API_BASE_URL}/sync/${owner}/${repo}`, {
    method: "POST",
    headers: { "X-API-Key": apiKey },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new ApiError(body.detail ?? `sync failed: ${response.status}`);
  }
  return response.json();
}

export function getTimeToFirstReview(
  owner: string,
  repo: string,
  filters: MetricsFilters,
): Promise<DurationSummary> {
  return getJSON(`/metrics/${owner}/${repo}/time-to-first-review`, { ...filters });
}

export function getTimeToMerge(owner: string, repo: string, filters: MetricsFilters): Promise<DurationSummary> {
  return getJSON(`/metrics/${owner}/${repo}/time-to-merge`, { ...filters });
}

export function getReviewLoad(
  owner: string,
  repo: string,
  filters: Omit<MetricsFilters, "author">,
): Promise<ReviewerLoad[]> {
  return getJSON(`/metrics/${owner}/${repo}/review-load`, { ...filters });
}

export function getStalePRs(owner: string, repo: string, staleDays: number): Promise<StalePR[]> {
  return getJSON(`/metrics/${owner}/${repo}/stale-prs`, { stale_days: String(staleDays) });
}

export function getReviewReciprocity(
  owner: string,
  repo: string,
  minInteractions = 2,
): Promise<ReciprocityPair[]> {
  return getJSON(`/metrics/${owner}/${repo}/review-reciprocity`, { min_interactions: String(minInteractions) });
}
