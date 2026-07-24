import { useEffect, useState } from "react";
import {
  type DurationSummary,
  type ReciprocityPair,
  type RepoSummary,
  type ReviewerLoad,
  type StalePR,
  getCurrentUser,
  getReviewLoad,
  getReviewReciprocity,
  getStalePRs,
  getTimeToFirstReview,
  getTimeToMerge,
  githubLoginUrl,
  listRepos,
  logout,
  triggerSync,
} from "./api";
import { Filters } from "./components/Filters";
import { ReciprocityTable } from "./components/ReciprocityTable";
import { ReviewLoadChart } from "./components/ReviewLoadChart";
import { StalePRTable } from "./components/StalePRTable";
import { StatTile } from "./components/StatTile";
import { TimeToMergeTrend } from "./components/TimeToMergeTrend";
import { computeDurationDelta, formatHours, toWeeklyTrend } from "./format";

const EMPTY_SUMMARY: DurationSummary = { count: 0, avg_hours: null, median_hours: null, items: [] };

export default function App() {
  const [repos, setRepos] = useState<RepoSummary[]>([]);
  const [selectedRepo, setSelectedRepo] = useState<string | null>(null);

  const [since, setSince] = useState("");
  const [until, setUntil] = useState("");
  const [author, setAuthor] = useState("");
  const [staleDays, setStaleDays] = useState(14);

  const [ttfr, setTtfr] = useState<DurationSummary>(EMPTY_SUMMARY);
  const [ttm, setTtm] = useState<DurationSummary>(EMPTY_SUMMARY);
  const [load, setLoad] = useState<ReviewerLoad[]>([]);
  const [stale, setStale] = useState<StalePR[]>([]);
  const [reciprocity, setReciprocity] = useState<ReciprocityPair[]>([]);

  const [loading, setLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [githubLogin, setGithubLogin] = useState<string | null>(null);

  useEffect(() => {
    listRepos()
      .then((data) => {
        setRepos(data);
        if (data.length > 0 && !selectedRepo) {
          setSelectedRepo(`${data[0].owner}/${data[0].name}`);
        }
      })
      .catch((e) => setError(String(e)));
    getCurrentUser().then((user) => setGithubLogin(user.github_login));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!selectedRepo) return;
    const [owner, name] = selectedRepo.split("/");
    const filters = {
      since: since ? new Date(since).toISOString() : undefined,
      until: until ? new Date(until).toISOString() : undefined,
      author: author || undefined,
    };

    setLoading(true);
    setError(null);
    Promise.all([
      getTimeToFirstReview(owner, name, filters),
      getTimeToMerge(owner, name, filters),
      getReviewLoad(owner, name, { since: filters.since, until: filters.until }),
      getStalePRs(owner, name, staleDays),
      getReviewReciprocity(owner, name),
    ])
      .then(([ttfrData, ttmData, loadData, staleData, reciprocityData]) => {
        setTtfr(ttfrData);
        setTtm(ttmData);
        setLoad(loadData);
        setStale(staleData);
        setReciprocity(reciprocityData);
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [selectedRepo, since, until, author, staleDays]);

  const handleSync = async (owner: string, name: string, apiKey: string) => {
    setSyncing(true);
    setError(null);
    try {
      await triggerSync(owner, name, apiKey);
      const updated = await listRepos();
      setRepos(updated);
      setSelectedRepo(`${owner}/${name}`);
    } catch (e) {
      setError(String(e));
    } finally {
      setSyncing(false);
    }
  };

  const handleLogout = async () => {
    await logout();
    setGithubLogin(null);
  };

  return (
    <>
      <header className="app-header">
        <h1>PR Review Analytics</h1>
        <p>Time-to-first-review, time-to-merge, review load, and stale PRs for a synced repo.</p>
      </header>

      <Filters
        repos={repos}
        selectedRepo={selectedRepo}
        onSelectRepo={setSelectedRepo}
        since={since}
        until={until}
        author={author}
        staleDays={staleDays}
        onSinceChange={setSince}
        onUntilChange={setUntil}
        onAuthorChange={setAuthor}
        onStaleDaysChange={setStaleDays}
        onSync={handleSync}
        syncing={syncing}
        githubLogin={githubLogin}
        loginUrl={githubLoginUrl(window.location.href)}
        onLogout={handleLogout}
      />

      {error && <div className="error-banner">{error}</div>}

      {!selectedRepo && !error && (
        <div className="panel-empty">Sync a repo above (e.g. "encode/httpx") to see metrics.</div>
      )}

      {selectedRepo && (
        <>
          {(() => {
            const ttfrTrend = toWeeklyTrend(ttfr.items);
            const ttmTrend = toWeeklyTrend(ttm.items);
            return (
              <div className="stat-grid">
                <StatTile
                  hero
                  label="Time-to-first-review (median)"
                  value={formatHours(ttfr.median_hours)}
                  sublabel={`avg ${formatHours(ttfr.avg_hours)} · ${ttfr.count} reviewed PR${ttfr.count === 1 ? "" : "s"}`}
                  delta={computeDurationDelta(ttfr.items)}
                  trend={ttfrTrend.map((p) => p.medianHours)}
                />
                <StatTile
                  hero
                  label="Time-to-merge (median)"
                  value={formatHours(ttm.median_hours)}
                  sublabel={`avg ${formatHours(ttm.avg_hours)} · ${ttm.count} merged PR${ttm.count === 1 ? "" : "s"}`}
                  delta={computeDurationDelta(ttm.items)}
                  trend={ttmTrend.map((p) => p.medianHours)}
                />
              </div>
            );
          })()}

          <div className="panel">
            <h2>Review load</h2>
            <ReviewLoadChart data={load} />
          </div>

          <div className="panel">
            <h2>Time-to-merge trend (weekly median)</h2>
            <TimeToMergeTrend items={ttm.items} />
          </div>

          <div className="panel">
            <h2>Stale PRs (open, idle {staleDays}+ days)</h2>
            <StalePRTable data={stale} />
          </div>

          <div className="panel">
            <h2>Review reciprocity</h2>
            <ReciprocityTable data={reciprocity} />
          </div>

          {loading && <div className="panel-empty">Refreshing…</div>}
        </>
      )}
    </>
  );
}
