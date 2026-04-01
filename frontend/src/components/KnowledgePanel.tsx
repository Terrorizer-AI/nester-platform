"use client";

import { useState, useEffect, useCallback } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface KnowledgeDoc {
  file_id: string;
  file_name: string;
  mime_type: string;
  modified_time: string;
  chunk_count: number;
  indexed_at: string;
}

interface KnowledgeStatus {
  connected: boolean;
  has_access_token: boolean;
  selected_file_count: number;
  doc_count: number;
  chunk_count: number;
  last_sync: string | null;
  profile_generated: boolean;
  profile_generated_at: string | null;
  google_client_id: string;
}

// Load Google API script once
function loadGoogleApi(): Promise<void> {
  return new Promise((resolve) => {
    if ((window as any).gapi) { resolve(); return; }
    const script = document.createElement("script");
    script.src = "https://apis.google.com/js/api.js";
    script.onload = () => resolve();
    document.head.appendChild(script);
  });
}

function loadGoogleIdentity(): Promise<void> {
  return new Promise((resolve) => {
    if ((window as any).google?.accounts) { resolve(); return; }
    const script = document.createElement("script");
    script.src = "https://accounts.google.com/gsi/client";
    script.onload = () => resolve();
    document.head.appendChild(script);
  });
}

export default function KnowledgePanel() {
  const [status, setStatus] = useState<KnowledgeStatus | null>(null);
  const [docs, setDocs] = useState<KnowledgeDoc[]>([]);
  const [profile, setProfile] = useState<string>("");
  const [showProfile, setShowProfile] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [picking, setPicking] = useState(false);
  const [msg, setMsg] = useState("");
  const [tab, setTab] = useState<"docs" | "profile">("docs");
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const loadStatus = useCallback(async () => {
    try {
      const res = await fetch(`${API}/knowledge/status`);
      if (res.ok) setStatus(await res.json());
    } catch {}
  }, []);

  const loadDocs = useCallback(async () => {
    try {
      const res = await fetch(`${API}/knowledge/docs`);
      if (res.ok) setDocs((await res.json()).docs || []);
    } catch {}
  }, []);

  const loadProfile = useCallback(async () => {
    try {
      const res = await fetch(`${API}/knowledge/profile`);
      if (res.ok) setProfile((await res.json()).profile || "");
    } catch {}
  }, []);

  useEffect(() => { loadStatus(); loadDocs(); }, [loadStatus, loadDocs]);
  useEffect(() => { if (tab === "profile" && !profile) loadProfile(); }, [tab, profile, loadProfile]);

  // ── Google Picker ──────────────────────────────────────────────────────────

  const openPicker = async () => {
    if (!status?.google_client_id) {
      setMsg("GOOGLE_CLIENT_ID not set in .env — see setup guide.");
      return;
    }

    setPicking(true);
    setMsg("");

    try {
      await Promise.all([loadGoogleApi(), loadGoogleIdentity()]);
      const gapi = (window as any).gapi;
      const google = (window as any).google;

      // Step 1: Get OAuth token with Drive readonly scope
      const tokenClient = google.accounts.oauth2.initTokenClient({
        client_id: status.google_client_id,
        scope: "https://www.googleapis.com/auth/drive.readonly",
        callback: async (tokenResponse: any) => {
          if (tokenResponse.error) {
            setMsg(`Auth error: ${tokenResponse.error}`);
            setPicking(false);
            return;
          }

          const accessToken = tokenResponse.access_token;

          // Step 2: Load Picker API and open it
          gapi.load("picker", () => {
            const picker = new google.picker.PickerBuilder()
              .addView(new google.picker.DocsView()
                .setIncludeFolders(true)
                .setMimeTypes([
                  "application/vnd.google-apps.document",
                  "application/vnd.google-apps.presentation",
                  "application/vnd.google-apps.spreadsheet",
                  "application/pdf",
                  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                  "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                  "text/plain",
                  "text/markdown",
                ].join(","))
              )
              .addView(new google.picker.DocsView(google.picker.ViewId.FOLDERS)
                .setSelectFolderEnabled(false)
              )
              .setOAuthToken(accessToken)
              .setDeveloperKey("")  // not needed with OAuth token
              .enableFeature(google.picker.Feature.MULTISELECT_ENABLED)
              .setTitle("Select company documents")
              .setCallback(async (data: any) => {
                if (data.action === google.picker.Action.PICKED) {
                  const files = data.docs.map((d: any) => ({
                    id: d.id,
                    name: d.name,
                    mimeType: d.mimeType,
                  }));

                  setPicking(false);
                  setSyncing(true);
                  setMsg(`Selected ${files.length} file(s). Syncing...`);

                  try {
                    const res = await fetch(`${API}/knowledge/files`, {
                      method: "POST",
                      headers: { "Content-Type": "application/json" },
                      body: JSON.stringify({ files, access_token: accessToken }),
                    });
                    if (res.ok) {
                      setMsg(`Syncing ${files.length} file(s) in background. This takes ~30 seconds.`);
                      setTimeout(() => {
                        loadStatus();
                        loadDocs();
                        setProfile("");
                        setSyncing(false);
                        setMsg("Sync complete ✓");
                      }, 15000);
                    } else {
                      const err = await res.json();
                      setMsg(`Error: ${err.detail || "Sync failed"}`);
                      setSyncing(false);
                    }
                  } catch {
                    setMsg("Network error — is the backend running?");
                    setSyncing(false);
                  }
                } else if (data.action === google.picker.Action.CANCEL) {
                  setPicking(false);
                  setMsg("");
                }
              })
              .build();

            picker.setVisible(true);
          });
        },
      });

      tokenClient.requestAccessToken({ prompt: "" });
    } catch (e) {
      setMsg(`Error loading Google APIs: ${e}`);
      setPicking(false);
    }
  };

  const handleResync = async () => {
    setSyncing(true);
    setMsg("Re-syncing...");
    try {
      const res = await fetch(`${API}/knowledge/sync`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ force_resync: true, regenerate_profile: true }),
      });
      if (res.ok) {
        setMsg("Re-sync started. Refreshing in 15s...");
        setTimeout(() => { loadStatus(); loadDocs(); setProfile(""); setSyncing(false); setMsg(""); }, 15000);
      } else {
        const err = await res.json();
        setMsg(`Error: ${err.detail}`);
        setSyncing(false);
      }
    } catch {
      setMsg("Network error");
      setSyncing(false);
    }
  };

  const handleReset = async () => {
    if (!confirm("This wipes all indexed knowledge and re-syncs from scratch. Continue?")) return;
    setSyncing(true);
    setMsg("Resetting...");
    try {
      await fetch(`${API}/knowledge/reset`, { method: "DELETE" });
      setMsg("Reset complete. Re-syncing...");
      setTimeout(() => { loadStatus(); loadDocs(); setProfile(""); setSyncing(false); setMsg(""); }, 15000);
    } catch {
      setMsg("Reset failed");
      setSyncing(false);
    }
  };

  const handleDeleteFile = async (fileId: string, fileName: string) => {
    if (!confirm(`Remove "${fileName}" from the knowledge base?`)) return;
    setDeletingId(fileId);
    try {
      const res = await fetch(`${API}/knowledge/files/${fileId}`, { method: "DELETE" });
      if (res.ok) {
        setDocs(prev => prev.filter(d => d.file_id !== fileId));
        setMsg(`"${fileName}" removed.`);
        loadStatus();
        setTimeout(() => setMsg(""), 3000);
      } else {
        const err = await res.json();
        setMsg(`Error: ${err.detail || "Delete failed"}`);
      }
    } catch {
      setMsg("Network error — is the backend running?");
    } finally {
      setDeletingId(null);
    }
  };

  const fmtDate = (iso: string | null) =>
    iso ? new Date(iso).toLocaleString() : "Never";

  const mimeIcon = (mime: string) => {
    if (mime.includes("document")) return "📄";
    if (mime.includes("presentation") || mime.includes("slide")) return "📊";
    if (mime.includes("spreadsheet") || mime.includes("sheet")) return "📋";
    if (mime.includes("pdf")) return "📕";
    return "📝";
  };

  const hasDocs = (status?.doc_count ?? 0) > 0;

  return (
    <div className="space-y-5">

      {/* Status + actions */}
      <div className="rounded-xl border border-outline/20 bg-surface/50 p-5 space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-bold uppercase tracking-widest text-foreground/70">
            Google Drive
          </h3>
          <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
            status?.connected
              ? "bg-green-500/15 text-green-400 border border-green-500/30"
              : "bg-outline/20 text-foreground/40 border border-outline/20"
          }`}>
            {status?.connected ? "Connected" : "Not connected"}
          </span>
        </div>

        {/* Stats row */}
        <div className="grid grid-cols-3 gap-2 text-center">
          {[
            { label: "Docs", value: status?.doc_count ?? 0 },
            { label: "Chunks", value: status?.chunk_count ?? 0 },
            { label: "Last Sync", value: status?.last_sync ? new Date(status.last_sync).toLocaleDateString() : "—" },
          ].map((s) => (
            <div key={s.label} className="rounded-lg bg-surface/40 border border-outline/10 py-2 px-1">
              <div className="text-base font-bold text-foreground">{s.value}</div>
              <div className="text-[10px] uppercase tracking-wider text-foreground/40">{s.label}</div>
            </div>
          ))}
        </div>

        {msg && (
          <div className="p-2 rounded-lg bg-accent/10 border border-accent/20 text-xs text-accent-dim">
            {msg}
          </div>
        )}

        {!status?.google_client_id && (
          <div className="p-3 rounded-lg bg-yellow-500/10 border border-yellow-500/20 text-xs text-yellow-300">
            <span className="font-semibold">Setup required:</span> Add{" "}
            <code className="text-yellow-200">GOOGLE_CLIENT_ID</code> to your{" "}
            <code className="text-yellow-200">.env</code> file to enable the file picker.
          </div>
        )}

        {/* Action buttons */}
        <div className="flex gap-2">
          <button
            onClick={openPicker}
            disabled={picking || syncing || !status?.google_client_id}
            className="flex-1 py-2 text-xs font-semibold rounded-lg bg-accent/20 hover:bg-accent/30 border border-accent/30 text-accent-dim transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {picking ? "Opening picker..." : "+ Add Documents"}
          </button>
          {hasDocs && (
            <>
              <button
                onClick={handleResync}
                disabled={syncing}
                className="py-2 px-3 text-xs font-semibold rounded-lg border border-outline/20 text-foreground/50 hover:text-foreground/80 transition-colors disabled:opacity-40"
                title="Re-sync all selected files"
              >
                ⟳ Sync
              </button>
              <button
                onClick={handleReset}
                disabled={syncing}
                className="py-2 px-3 text-xs rounded-lg border border-red-500/20 text-red-400/60 hover:text-red-400 transition-colors disabled:opacity-40"
                title="Wipe and re-index"
              >
                ✕
              </button>
            </>
          )}
        </div>
      </div>

      {/* Docs + Profile tabs */}
      {hasDocs && (
        <div>
          <div className="flex gap-1 mb-3">
            {(["docs", "profile"] as const).map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition-colors ${
                  tab === t
                    ? "bg-accent/20 text-accent-dim border border-accent/30"
                    : "text-foreground/40 hover:text-foreground/70"
                }`}
              >
                {t === "docs" ? `Synced Files (${docs.length})` : "Company Profile"}
              </button>
            ))}
          </div>

          {tab === "docs" && (
            <div className="space-y-2">
              {docs.map((doc) => (
                <div
                  key={doc.file_id}
                  className="flex items-center justify-between p-3 rounded-lg border border-outline/15 bg-surface/30 text-xs group/doc"
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <span>{mimeIcon(doc.mime_type)}</span>
                    <div className="min-w-0">
                      <span className="block truncate font-medium text-foreground/80">{doc.file_name}</span>
                      <span className="text-[10px] text-foreground/30">{doc.chunk_count} chunks · {fmtDate(doc.indexed_at)}</span>
                    </div>
                  </div>
                  <button
                    onClick={() => handleDeleteFile(doc.file_id, doc.file_name)}
                    disabled={deletingId === doc.file_id}
                    className="ml-3 flex-shrink-0 opacity-0 group-hover/doc:opacity-100 transition-opacity px-2 py-1 rounded border border-red-500/20 text-red-400/60 hover:text-red-400 hover:border-red-500/40 text-[10px] font-bold disabled:opacity-30"
                    title="Remove from knowledge base"
                  >
                    {deletingId === doc.file_id ? "..." : "✕"}
                  </button>
                </div>
              ))}
            </div>
          )}

          {tab === "profile" && (
            <div className="rounded-xl border border-outline/20 bg-surface/30 p-4">
              {profile ? (
                <>
                  <div className="flex justify-between items-center mb-3">
                    <span className="text-xs text-foreground/40">
                      Generated {fmtDate(status?.profile_generated_at ?? null)}
                    </span>
                    <button
                      onClick={() => setShowProfile(!showProfile)}
                      className="text-xs text-accent-dim hover:underline"
                    >
                      {showProfile ? "Collapse" : "Expand"}
                    </button>
                  </div>
                  <div className={`text-xs text-foreground/70 whitespace-pre-wrap font-mono leading-relaxed overflow-hidden ${showProfile ? "" : "max-h-40"}`}>
                    {profile}
                  </div>
                  {!showProfile && (
                    <div className="h-6 bg-gradient-to-t from-surface/80 to-transparent -mt-6 relative pointer-events-none" />
                  )}
                </>
              ) : (
                <p className="text-xs text-foreground/40 text-center py-4">
                  {status?.profile_generated ? "Loading..." : "Profile not yet generated. Re-sync to generate."}
                </p>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
