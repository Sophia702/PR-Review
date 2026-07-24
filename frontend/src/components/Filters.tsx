import { useState } from "react";
import type { RepoSummary } from "../api";

interface FiltersProps {
  repos: RepoSummary[];
  selectedRepo: string | null;
  onSelectRepo: (repoKey: string) => void;
  since: string;
  until: string;
  author: string;
  staleDays: number;
  onSinceChange: (value: string) => void;
  onUntilChange: (value: string) => void;
  onAuthorChange: (value: string) => void;
  onStaleDaysChange: (value: number) => void;
  onSync: (owner: string, name: string) => void;
  syncing: boolean;
}

export function Filters({
  repos,
  selectedRepo,
  onSelectRepo,
  since,
  until,
  author,
  staleDays,
  onSinceChange,
  onUntilChange,
  onAuthorChange,
  onStaleDaysChange,
  onSync,
  syncing,
}: FiltersProps) {
  const [newRepo, setNewRepo] = useState("");

  const handleSync = () => {
    if (newRepo.includes("/")) {
      const [owner, name] = newRepo.split("/").map((s) => s.trim());
      if (owner && name) {
        onSync(owner, name);
        setNewRepo("");
        return;
      }
    }
    if (selectedRepo) {
      const [owner, name] = selectedRepo.split("/");
      onSync(owner, name);
    }
  };

  return (
    <div className="filters">
      <div className="filter-field">
        <label htmlFor="repo-select">Repo</label>
        <select id="repo-select" value={selectedRepo ?? ""} onChange={(e) => onSelectRepo(e.target.value)}>
          {repos.length === 0 && <option value="">No repos synced yet</option>}
          {repos.map((r) => (
            <option key={`${r.owner}/${r.name}`} value={`${r.owner}/${r.name}`}>
              {r.owner}/{r.name}
            </option>
          ))}
        </select>
      </div>

      <div className="filter-field">
        <label htmlFor="since">Since</label>
        <input id="since" type="date" value={since} onChange={(e) => onSinceChange(e.target.value)} />
      </div>

      <div className="filter-field">
        <label htmlFor="until">Until</label>
        <input id="until" type="date" value={until} onChange={(e) => onUntilChange(e.target.value)} />
      </div>

      <div className="filter-field">
        <label htmlFor="author">Author</label>
        <input
          id="author"
          type="text"
          placeholder="github login"
          value={author}
          onChange={(e) => onAuthorChange(e.target.value)}
        />
      </div>

      <div className="filter-field">
        <label htmlFor="stale-days">Stale after (days)</label>
        <input
          id="stale-days"
          type="number"
          min={1}
          value={staleDays}
          onChange={(e) => onStaleDaysChange(Number(e.target.value) || 1)}
        />
      </div>

      <div className="filter-actions">
        <input
          type="text"
          placeholder="owner/repo to sync"
          value={newRepo}
          onChange={(e) => setNewRepo(e.target.value)}
          style={{ minWidth: 160 }}
        />
        <button className="secondary" onClick={handleSync} disabled={syncing || (!newRepo.includes("/") && !selectedRepo)}>
          {syncing ? "Syncing…" : newRepo.includes("/") ? "Sync" : "Re-sync"}
        </button>
      </div>
    </div>
  );
}
