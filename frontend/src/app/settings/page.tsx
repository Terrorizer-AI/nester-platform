"use client";

import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import ConfirmModal from "@/components/ConfirmModal";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface ApiKeyMeta {
  key: string;
  label: string;
  description: string;
  placeholder: string;
  link: string;
  group: string;
  required: string;
  source: "ui" | "env" | "none";
  masked: string;
  is_set: boolean;
}

// ── Agent/flow tab config ──────────────────────────────────────────────────────
const AGENT_META: Record<string, {
  icon: string;
  color: string;
  tagline: string;
  description: string;
}> = {
  "Sales Outreach": {
    icon: "🚀",
    color: "text-violet-400",
    tagline: "AI-powered outreach pipeline",
    description: "Researches prospects, builds personalized personas, and writes multi-touch email sequences. Requires OpenAI for LLM, Tavily for web search, and Firecrawl for website scraping.",
  },
  "GitHub Monitor": {
    icon: "🔭",
    color: "text-blue-400",
    tagline: "Repo health & security watchdog",
    description: "Monitors repositories for PRs, issues, dependency vulnerabilities, and security alerts. Posts weekly digests and real-time alerts to Slack channels.",
  },
  "Google Drive": {
    icon: "📁",
    color: "text-yellow-400",
    tagline: "Company knowledge base",
    description: "Connects to Google Drive so agents can read internal docs, pitch decks, and SOPs. Powers the company knowledge sidebar in every flow.",
  },
  "Observability": {
    icon: "📊",
    color: "text-pink-400",
    tagline: "LLM tracing & cost tracking",
    description: "Sends every LLM call to Langfuse for step-by-step tracing, latency tracking, and token cost dashboards. Optional — works without these keys.",
  },
};

// ── KeyRow ─────────────────────────────────────────────────────────────────────
function KeyRow({ meta, onSaved, onDeleted }: {
  meta: ApiKeyMeta;
  onSaved: () => void;
  onDeleted: () => void;
}) {
  const [value, setValue] = useState("");
  const [show, setShow] = useState(false);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [msg, setMsg] = useState("");
  const [editing, setEditing] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);

  const handleSave = async () => {
    if (!value.trim()) return;
    setSaving(true);
    setMsg("");
    try {
      const res = await fetch(`${API}/settings/keys`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ keys: [{ key: meta.key, value: value.trim() }] }),
      });
      if (res.ok) {
        setMsg("Saved");
        setValue("");
        setEditing(false);
        setShow(false);
        setTimeout(() => setMsg(""), 2000);
        onSaved();
      } else {
        const err = await res.json();
        setMsg(err.detail || "Failed");
      }
    } catch {
      setMsg("Network error");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    setDeleting(true);
    try {
      await fetch(`${API}/settings/keys/${meta.key}`, { method: "DELETE" });
      onDeleted();
    } catch {
      setMsg("Delete failed");
    } finally {
      setDeleting(false);
    }
  };

  const isRequired = meta.required === "true";

  const sourceBadge =
    meta.source === "ui"
      ? <span className="text-[0.55rem] px-1.5 py-0.5 rounded-full bg-secondary/15 text-secondary border border-secondary/20 font-bold">SET VIA UI</span>
      : meta.source === "env"
      ? <span className="text-[0.55rem] px-1.5 py-0.5 rounded-full bg-muted/10 text-muted border border-outline/20 font-bold">FROM .ENV</span>
      : <span className="text-[0.55rem] px-1.5 py-0.5 rounded-full bg-error/10 text-error border border-error/20 font-bold">NOT SET</span>;

  const requiredBadge = isRequired
    ? <span className="text-[0.55rem] px-1.5 py-0.5 rounded-full bg-accent/10 text-accent border border-accent/20 font-bold">REQUIRED</span>
    : <span className="text-[0.55rem] px-1.5 py-0.5 rounded-full bg-muted/5 text-muted/40 border border-outline/10 font-bold">OPTIONAL</span>;

  return (
    <div className={`rounded-xl border bg-card p-4 space-y-3 transition-colors hover:border-outline/30 ${
      !meta.is_set && isRequired ? "border-error/20" : "border-outline/20"
    }`}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-0.5 flex-wrap">
            <span className="text-sm font-bold text-foreground">{meta.label}</span>
            {requiredBadge}
            {sourceBadge}
          </div>
          <p className="text-xs text-muted/60 mb-1">{meta.description}</p>
          <code className="text-[0.6rem] text-muted/40 font-mono">{meta.key}</code>
        </div>
        <a
          href={meta.link}
          target="_blank"
          rel="noopener noreferrer"
          className="text-[0.6rem] text-accent/60 hover:text-accent transition-colors shrink-0 mt-1 whitespace-nowrap"
        >
          Get key ↗
        </a>
      </div>

      {meta.is_set && !editing && (
        <div className="flex items-center gap-2">
          <code className="flex-1 text-xs font-mono text-foreground/50 bg-surface-high/50 px-3 py-1.5 rounded-lg truncate">
            {meta.masked}
          </code>
          <button
            onClick={() => setEditing(true)}
            className="text-xs px-3 py-1.5 rounded-lg border border-outline/20 text-muted hover:text-foreground transition-colors"
          >
            Update
          </button>
          {meta.source === "ui" && (
            <button
              onClick={() => setConfirmOpen(true)}
              disabled={deleting}
              className="text-xs px-2 py-1.5 rounded-lg border border-error/20 text-error/50 hover:text-error transition-colors disabled:opacity-40"
            >
              {deleting ? "..." : "✕"}
            </button>
          )}
        </div>
      )}

      {(!meta.is_set || editing) && (
        <div className="flex gap-2">
          <div className="relative flex-1">
            <input
              type={show ? "text" : "password"}
              value={value}
              onChange={e => setValue(e.target.value)}
              placeholder={meta.placeholder}
              onKeyDown={e => e.key === "Enter" && handleSave()}
              className="w-full bg-surface-high/50 border border-outline/20 rounded-lg px-3 py-2 text-xs font-mono text-foreground placeholder:text-muted/30 focus:outline-none focus:border-accent/40 pr-10"
            />
            <button
              type="button"
              onClick={() => setShow(s => !s)}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted/40 hover:text-muted transition-colors text-[0.6rem]"
            >
              {show ? "hide" : "show"}
            </button>
          </div>
          <button
            onClick={handleSave}
            disabled={saving || !value.trim()}
            className="px-4 py-2 rounded-lg bg-accent/20 border border-accent/30 text-accent text-xs font-bold hover:bg-accent/30 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {saving ? "..." : "Save"}
          </button>
          {editing && (
            <button
              onClick={() => { setEditing(false); setValue(""); }}
              className="px-3 py-2 rounded-lg border border-outline/20 text-muted text-xs hover:text-foreground transition-colors"
            >
              Cancel
            </button>
          )}
        </div>
      )}

      {msg && (
        <p className={`text-xs ${msg === "Saved" ? "text-secondary" : "text-error"}`}>{msg}</p>
      )}

      <ConfirmModal
        open={confirmOpen}
        title={`Remove ${meta.label}?`}
        message="This will delete the key from Settings. The pipeline will fall back to the .env value if one exists."
        confirmLabel="Remove Key"
        variant="danger"
        onConfirm={() => { setConfirmOpen(false); handleDelete(); }}
        onCancel={() => setConfirmOpen(false)}
      />
    </div>
  );
}

// ── Page ───────────────────────────────────────────────────────────────────────
export default function SettingsPage() {
  const [keys, setKeys] = useState<ApiKeyMeta[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [activeAgent, setActiveAgent] = useState<string>("All");
  const searchRef = useRef<HTMLInputElement>(null);

  const loadKeys = useCallback(async () => {
    try {
      const res = await fetch(`${API}/settings/keys`);
      if (res.ok) {
        const data = await res.json();
        setKeys(data.keys || []);
      }
    } catch {}
    finally { setLoading(false); }
  }, []);

  useEffect(() => { loadKeys(); }, [loadKeys]);

  // Force-clear any browser-autofilled value from the search field
  useEffect(() => {
    setSearch("");
    if (searchRef.current) searchRef.current.value = "";
  }, []);

  // Derive unique agents from loaded keys (preserves backend order)
  const agents = useMemo(() => {
    const seen = new Set<string>();
    keys.forEach(k => seen.add(k.group));
    return ["All", ...Array.from(seen)];
  }, [keys]);

  // Stats
  const setCount = keys.filter(k => k.is_set).length;
  const requiredUnset = keys.filter(k => !k.is_set && k.required === "true").length;

  // Filtered keys
  const filtered = useMemo(() => {
    return keys.filter(k => {
      const matchAgent = activeAgent === "All" || k.group === activeAgent;
      const q = search.toLowerCase();
      const matchSearch = !q
        || k.label.toLowerCase().includes(q)
        || k.description.toLowerCase().includes(q)
        || k.key.toLowerCase().includes(q);
      return matchAgent && matchSearch;
    });
  }, [keys, activeAgent, search]);

  // Group the filtered results
  const grouped = useMemo(() => {
    const map = new Map<string, ApiKeyMeta[]>();
    filtered.forEach(k => {
      if (!map.has(k.group)) map.set(k.group, []);
      map.get(k.group)!.push(k);
    });
    return map;
  }, [filtered]);

  return (
    <div className="max-w-2xl mx-auto px-6 py-10 space-y-8">

      {/* Header */}
      <div>
        <h1 className="text-xl font-bold text-foreground mb-1">API Keys</h1>
        <p className="text-sm text-foreground/40">
          Configure API keys for each agent. Keys set here override{" "}
          <code className="text-accent/70">.env</code> instantly — no restart needed.
        </p>
      </div>

      {/* Stats bar */}
      {!loading && (
        <div className="flex items-center gap-3 flex-wrap">
          <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-secondary/10 border border-secondary/20">
            <div className="w-1.5 h-1.5 rounded-full bg-secondary" />
            <span className="text-xs font-semibold text-secondary">{setCount} configured</span>
          </div>
          {requiredUnset > 0 && (
            <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-error/10 border border-error/20">
              <div className="w-1.5 h-1.5 rounded-full bg-error" />
              <span className="text-xs font-semibold text-error">{requiredUnset} required key{requiredUnset > 1 ? "s" : ""} missing</span>
            </div>
          )}
          <span className="text-xs text-muted/40 ml-auto">
            Stored in <code className="text-accent/60">~/.nester/ops.db</code>
          </span>
        </div>
      )}

      {/* Search */}
      <div className="relative">
        <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted/40" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-4.35-4.35M17 11A6 6 0 1 1 5 11a6 6 0 0 1 12 0z" />
        </svg>
        <input
          ref={searchRef}
          type="search"
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Search keys by name, description, or env var..."
          autoComplete="off"
          autoCorrect="off"
          autoCapitalize="none"
          spellCheck={false}
          name="settings-search-nofill"
          className="w-full bg-card border border-outline/20 rounded-xl pl-9 pr-4 py-2.5 text-sm text-foreground placeholder:text-muted/30 focus:outline-none focus:border-accent/40 transition-colors"
        />
        {search && (
          <button
            onClick={() => setSearch("")}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-muted/40 hover:text-muted transition-colors text-xs"
          >
            ✕
          </button>
        )}
      </div>

      {/* Agent tabs */}
      <div className="flex gap-1.5 flex-wrap">
        {agents.map(agent => {
          const am = AGENT_META[agent];
          const isActive = activeAgent === agent;
          const agentKeys = agent === "All" ? keys : keys.filter(k => k.group === agent);
          const setInAgent = agentKeys.filter(k => k.is_set).length;
          const requiredInAgent = agentKeys.filter(k => k.required === "true").length;
          const requiredSetInAgent = agentKeys.filter(k => k.required === "true" && k.is_set).length;
          const allRequiredSet = requiredInAgent === 0 || requiredSetInAgent === requiredInAgent;

          return (
            <button
              key={agent}
              onClick={() => setActiveAgent(agent)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold border transition-colors ${
                isActive
                  ? "bg-accent/20 border-accent/30 text-accent"
                  : "border-outline/20 text-muted/60 hover:text-foreground hover:border-outline/40"
              }`}
            >
              {am ? <span>{am.icon}</span> : null}
              <span>{agent}</span>
              <span className={`text-[0.5rem] font-bold px-1 py-0.5 rounded-full ${
                allRequiredSet && setInAgent > 0
                  ? "bg-secondary/15 text-secondary"
                  : !allRequiredSet
                  ? "bg-error/15 text-error"
                  : "bg-muted/10 text-muted/50"
              }`}>
                {setInAgent}/{agentKeys.length}
              </span>
            </button>
          );
        })}
      </div>

      {/* Key list */}
      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3, 4].map(i => (
            <div key={i} className="h-20 rounded-xl skeleton" />
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-12 text-muted/40 text-sm">
          No keys match &ldquo;{search}&rdquo;
        </div>
      ) : (
        <div className="space-y-10">
          {Array.from(grouped.entries()).map(([agent, agentKeys]) => {
            const am = AGENT_META[agent];
            const setInGroup = agentKeys.filter(k => k.is_set).length;
            const requiredCount = agentKeys.filter(k => k.required === "true").length;
            const requiredSet = agentKeys.filter(k => k.required === "true" && k.is_set).length;

            return (
              <section key={agent} className="space-y-4">
                {/* Agent section header */}
                <div className="rounded-xl border border-outline/15 bg-surface/30 p-4">
                  <div className="flex items-start justify-between gap-3 mb-2">
                    <div className="flex items-center gap-2">
                      {am && <span className="text-xl">{am.icon}</span>}
                      <div>
                        <h2 className={`text-sm font-bold ${am?.color ?? "text-foreground/80"}`}>
                          {agent}
                        </h2>
                        {am && (
                          <p className="text-[0.65rem] text-muted/50 font-medium">{am.tagline}</p>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      {requiredCount > 0 && (
                        <span className={`text-[0.55rem] font-bold px-2 py-0.5 rounded-full border ${
                          requiredSet === requiredCount
                            ? "bg-secondary/10 text-secondary border-secondary/20"
                            : "bg-error/10 text-error border-error/20"
                        }`}>
                          {requiredSet}/{requiredCount} required
                        </span>
                      )}
                      <span className="text-[0.55rem] text-muted/40">
                        {setInGroup}/{agentKeys.length} set
                      </span>
                    </div>
                  </div>
                  {am && (
                    <p className="text-xs text-foreground/40 leading-relaxed">{am.description}</p>
                  )}
                </div>

                {/* Keys */}
                <div className="space-y-3">
                  {agentKeys.map(meta => (
                    <KeyRow
                      key={meta.key}
                      meta={meta}
                      onSaved={loadKeys}
                      onDeleted={loadKeys}
                    />
                  ))}
                </div>
              </section>
            );
          })}
        </div>
      )}
    </div>
  );
}
