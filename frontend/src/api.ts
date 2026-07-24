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

export interface CurrentUser {
  github_login: string | null;
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
  const headers: Record<string, string> = {};
  if (apiKey) headers["X-API-Key"] = apiKey;

  // credentials: "include" sends the session cookie cross-origin (frontend
  // and backend are different Fly subdomains) - a logged-in session works
  // here even with no API key entered.
  const response = await fetch(`${API_BASE_URL}/sync/${owner}/${repo}`, {
    method: "POST",
    headers,
    credentials: "include",
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new ApiError(body.detail ?? `sync failed: ${response.status}`);
  }
  return response.json();
}

export async function getCurrentUser(): Promise<CurrentUser> {
  const response = await fetch(`${API_BASE_URL}/auth/me`, { credentials: "include" });
  if (!response.ok) return { github_login: null };
  return response.json();
}

export function githubLoginUrl(returnTo: string): string {
  const url = new URL(`${API_BASE_URL}/auth/github/login`);
  url.searchParams.set("return_to", returnTo);
  return url.toString();
}

export async function logout(): Promise<void> {
  await fetch(`${API_BASE_URL}/auth/logout`, { method: "POST", credentials: "include" });
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
