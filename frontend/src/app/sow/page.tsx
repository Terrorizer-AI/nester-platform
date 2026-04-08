"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import SOWPreview from "@/components/SOWPreview";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ── Types ────────────────────────────────────────────────────────────────────

interface SOWSession {
  id: string;
  title: string;
  status: string;
  sow_markdown: string;
  created_at: string;
  updated_at: string;
}

interface SOWDocument {
  id: string;
  file_name: string;
  mime_type: string;
  doc_type: string;
  uploaded_at: string;
}

interface ChatMessage {
  id: number;
  role: "user" | "assistant";
  content: string;
  streaming?: boolean;
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function timeLabel(iso: string): string {
  const d = new Date(iso);
  const diff = Date.now() - d.getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return "Just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  if (days < 7) return `${days}d ago`;
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function mimeIcon(name: string) {
  if (name.endsWith(".pdf")) return "📕";
  if (name.endsWith(".pptx")) return "📊";
  if (name.endsWith(".docx")) return "📄";
  return "📝";
}

// ── Chat markdown renderer ──────────────────────────────────────────────────

function renderInline(text: string) {
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g);
  return parts.map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={i} className="font-semibold text-foreground">{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith("`") && part.endsWith("`")) {
      return <code key={i} className="px-1 py-0.5 rounded bg-surface-high text-accent-dim text-[11px] font-mono">{part.slice(1, -1)}</code>;
    }
    return <span key={i}>{part}</span>;
  });
}

function renderChatMarkdown(text: string) {
  // Strip SOW blocks from display
  const cleaned = text.replace(/~~~SOW[\s\S]*?~~~/g, "").trim();
  const blocks = cleaned.split(/\n\n+/);
  return blocks.map((block, bi) => {
    if (block.startsWith("### ")) {
      return <h4 key={bi} className="text-sm font-semibold text-foreground mt-2 mb-1">{renderInline(block.slice(4))}</h4>;
    }
    const lines = block.split("\n");
    const isList = lines.every(l => /^[-*]\s/.test(l.trim()) || l.trim() === "");
    if (isList && lines.some(l => l.trim())) {
      return (
        <ul key={bi} className="my-1 space-y-0.5 ml-1">
          {lines.filter(l => l.trim()).map((l, li) => (
            <li key={li} className="flex gap-2 text-[13px] leading-relaxed text-foreground/85">
              <span className="text-accent mt-0.5 shrink-0">&#8226;</span>
              <span>{renderInline(l.replace(/^[-*]\s/, ""))}</span>
            </li>
          ))}
        </ul>
      );
    }
    return (
      <p key={bi} className="text-[13px] leading-relaxed text-foreground/85 my-1">
        {lines.map((line, li, arr) => (
          <span key={li}>
            {renderInline(line)}
            {li < arr.length - 1 && <br />}
          </span>
        ))}
      </p>
    );
  });
}

// ── Doc list component ──────────────────────────────────────────────────────

function DocList({ docs, onDelete }: { docs: SOWDocument[]; onDelete: (id: string) => void }) {
  if (!docs.length) return null;
  return (
    <div className="space-y-1 mt-2">
      {docs.map(d => (
        <div key={d.id} className="group flex items-center gap-2 px-2 py-1.5 rounded-lg hover:bg-card/60 transition-colors">
          <span className="text-sm">{mimeIcon(d.file_name)}</span>
          <p className="text-[11px] text-foreground/60 truncate flex-1">{d.file_name}</p>
          <button
            onClick={() => onDelete(d.id)}
            className="opacity-0 group-hover:opacity-100 text-muted hover:text-error transition-all"
          >
            <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      ))}
    </div>
  );
}

// ── Main Page ────────────────────────────────────────────────────────────────

export default function SOWPage() {
  const [sessions, setSessions] = useState<SOWSession[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [proposals, setProposals] = useState<SOWDocument[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sowMarkdown, setSowMarkdown] = useState("");
  const [sessionTitle, setSessionTitle] = useState("");
  const [sessionStatus, setSessionStatus] = useState("draft");

  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [uploading, setUploading] = useState(false);

  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const proposalInputRef = useRef<HTMLInputElement>(null);

  // ── Data fetching ─────────────────────────────────────────────────────

  const fetchSessions = useCallback(async () => {
    try {
      const res = await fetch(`${API}/sow/sessions`);
      if (res.ok) {
        const data = await res.json();
        setSessions(Array.isArray(data) ? data : data.sessions || []);
      }
    } catch { /* backend down */ }
  }, []);

  useEffect(() => {
    fetchSessions();
  }, [fetchSessions]);

  // ── Load session detail ───────────────────────────────────────────────

  const loadSession = useCallback(async (id: string) => {
    setActiveId(id);
    try {
      const [sessRes, proposalRes] = await Promise.all([
        fetch(`${API}/sow/sessions/${id}`),
        fetch(`${API}/sow/sessions/${id}/proposals`),
      ]);
      if (sessRes.ok) {
        const data = await sessRes.json();
        const sess = data.session || data;
        const chatMsgs = data.messages || data.chat_history || [];
        setSessionTitle(sess.title || "");
        setSessionStatus(sess.status || "draft");
        setSowMarkdown(sess.sow_markdown || "");
        setMessages(
          chatMsgs.map((m: { id: number; role: string; content: string }) => ({
            id: m.id,
            role: m.role as "user" | "assistant",
            content: m.content,
          }))
        );
      }
      if (proposalRes.ok) {
        const pd = await proposalRes.json();
        setProposals(Array.isArray(pd) ? pd : pd.proposals || []);
      }
    } catch { /* network error */ }
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    inputRef.current?.focus();
  }, [activeId]);

  const active = sessions.find(s => s.id === activeId) || null;

  // ── Session actions ───────────────────────────────────────────────────

  const createSession = useCallback(async () => {
    try {
      const res = await fetch(`${API}/sow/sessions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      if (!res.ok) return;
      const data = await res.json();
      await fetchSessions();
      loadSession(data.id);
    } catch { /* error */ }
  }, [fetchSessions, loadSession]);

  const deleteSession = useCallback(async (id: string) => {
    try {
      await fetch(`${API}/sow/sessions/${id}`, { method: "DELETE" });
      await fetchSessions();
      if (activeId === id) {
        setActiveId(null);
        setMessages([]);
        setSowMarkdown("");
        setProposals([]);
      }
    } catch { /* error */ }
  }, [activeId, fetchSessions]);

  // ── Upload handlers ───────────────────────────────────────────────────

  const uploadProposals = useCallback(async (files: FileList | null) => {
    if (!files?.length || !activeId) return;
    setUploading(true);
    const form = new FormData();
    Array.from(files).forEach(f => form.append("files", f));
    try {
      const res = await fetch(`${API}/sow/sessions/${activeId}/proposals`, { method: "POST", body: form });
      if (res.ok) {
        const propRes = await fetch(`${API}/sow/sessions/${activeId}/proposals`);
        if (propRes.ok) {
          const pd = await propRes.json();
          setProposals(Array.isArray(pd) ? pd : pd.proposals || []);
        }
      }
    } catch { /* error */ }
    setUploading(false);
  }, [activeId]);

  // ── Delete handlers ───────────────────────────────────────────────────

  const deleteProposal = useCallback(async (docId: string) => {
    if (!activeId) return;
    try {
      await fetch(`${API}/sow/sessions/${activeId}/proposals/${docId}`, { method: "DELETE" });
      const res = await fetch(`${API}/sow/sessions/${activeId}/proposals`);
      if (res.ok) {
        const pd = await res.json();
        setProposals(Array.isArray(pd) ? pd : pd.proposals || []);
      }
    } catch { /* error */ }
  }, [activeId]);

  // ── Generate SOW (SSE) ────────────────────────────────────────────────

  const handleGenerate = useCallback(async () => {
    if (!activeId || generating) return;
    setGenerating(true);
    setSowMarkdown("");

    try {
      const res = await fetch(`${API}/sow/sessions/${activeId}/generate`, { method: "POST" });
      if (!res.ok || !res.body) {
        const err = await res.json().catch(() => ({ detail: "Generation failed" }));
        alert(err.detail || "Generation failed");
        setGenerating(false);
        return;
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let accumulated = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const chunk = decoder.decode(value, { stream: true });
        for (const line of chunk.split("\n")) {
          if (!line.startsWith("data: ")) continue;
          const raw = line.slice(6).trim();
          if (raw === "[DONE]") break;
          try {
            const parsed = JSON.parse(raw);
            if (parsed.token) {
              accumulated += parsed.token;
              setSowMarkdown(accumulated);
            }
          } catch { /* malformed SSE */ }
        }
      }

      await loadSession(activeId);
    } catch {
      alert("Generation failed — is the backend running?");
    } finally {
      setGenerating(false);
    }
  }, [activeId, generating, loadSession]);

  // ── Chat (SSE) ────────────────────────────────────────────────────────

  const sendChat = useCallback(async (text: string) => {
    if (!text.trim() || loading || !activeId) return;

    const userMsg: ChatMessage = { id: Date.now(), role: "user", content: text };
    const assistantMsg: ChatMessage = { id: Date.now() + 1, role: "assistant", content: "", streaming: true };

    setMessages(prev => [...prev, userMsg, assistantMsg]);
    setInput("");
    setLoading(true);

    try {
      const res = await fetch(`${API}/sow/sessions/${activeId}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text }),
      });

      if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let accumulated = "";
      let sowUpdated = false;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const chunk = decoder.decode(value, { stream: true });
        for (const line of chunk.split("\n")) {
          if (!line.startsWith("data: ")) continue;
          const raw = line.slice(6).trim();
          if (raw === "[DONE]") break;
          try {
            const parsed = JSON.parse(raw);
            if (parsed.token) {
              accumulated += parsed.token;
              const acc = accumulated;
              setMessages(prev => {
                const msgs = [...prev];
                msgs[msgs.length - 1] = { ...msgs[msgs.length - 1], content: acc, streaming: true };
                return msgs;
              });
            }
            if (parsed.sow_updated) sowUpdated = true;
          } catch { /* malformed SSE */ }
        }
      }

      const final = accumulated;
      setMessages(prev => {
        const msgs = [...prev];
        msgs[msgs.length - 1] = { ...msgs[msgs.length - 1], content: final, streaming: false };
        return msgs;
      });

      if (sowUpdated) {
        const sessRes = await fetch(`${API}/sow/sessions/${activeId}`);
        if (sessRes.ok) {
          const data = await sessRes.json();
          const sess = data.session || data;
          setSowMarkdown(sess.sow_markdown || "");
          setSessionStatus(sess.status || "draft");
        }
      }
    } catch {
      setMessages(prev => {
        const msgs = [...prev];
        msgs[msgs.length - 1] = { ...msgs[msgs.length - 1], content: "Something went wrong. Please try again.", streaming: false };
        return msgs;
      });
    } finally {
      setLoading(false);
    }
  }, [loading, activeId]);

  const handleSubmit = (e: React.FormEvent) => { e.preventDefault(); sendChat(input); };
  const handleKeyDown = (e: React.KeyboardEvent) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendChat(input); } };

  const hasSOW = sowMarkdown.trim().length > 0;

  // ── Render ────────────────────────────────────────────────────────────
  return (
    <div className="flex h-[calc(100vh-3.5rem)] overflow-hidden">
      {/* ── Sidebar ───────────────────────────────────────────────────── */}
      <div className={`shrink-0 border-r border-card-border bg-surface-low flex flex-col transition-all duration-300 ${sidebarOpen ? "w-72" : "w-0 overflow-hidden"}`}>
        {/* New session */}
        <div className="p-3 border-b border-card-border">
          <button
            onClick={createSession}
            className="w-full flex items-center gap-2 px-3 py-2.5 rounded-xl border border-card-border text-sm text-foreground/80 hover:bg-card hover:border-accent/30 transition-colors"
          >
            <svg className="w-4 h-4 text-muted" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
            </svg>
            New SOW
          </button>
        </div>

        <div className="flex-1 overflow-y-auto py-2 space-y-4">
          {/* Sessions */}
          <div>
            <div className="px-3 mb-1.5">
              <p className="text-[10px] uppercase tracking-widest text-muted font-bold">Sessions</p>
            </div>
            {sessions.length === 0 && <p className="text-xs text-muted text-center py-4 px-4">No sessions yet</p>}
            {sessions.map(sess => (
              <div
                key={sess.id}
                className={`group flex items-center gap-2 mx-2 mb-0.5 rounded-lg cursor-pointer transition-colors ${
                  sess.id === activeId ? "bg-card border border-accent/20 text-foreground" : "hover:bg-card/60 text-foreground/60 border border-transparent"
                }`}
              >
                <button onClick={() => loadSession(sess.id)} className="flex-1 text-left px-3 py-2 min-w-0">
                  <p className="text-xs font-medium truncate">{sess.title}</p>
                  <div className="flex items-center gap-1.5 mt-0.5">
                    <span className={`w-1.5 h-1.5 rounded-full ${sess.status === "final" ? "bg-success" : "bg-warning"}`} />
                    <p className="text-[10px] text-muted">{timeLabel(sess.updated_at)}</p>
                  </div>
                </button>
                <button
                  onClick={e => { e.stopPropagation(); deleteSession(sess.id); }}
                  className="pr-2 opacity-0 group-hover:opacity-100 text-muted hover:text-error transition-all"
                >
                  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                  </svg>
                </button>
              </div>
            ))}
          </div>

          {/* ── Client Proposals ──────────────────────────────────── */}
          {active && (
            <div className="px-3">
              <div className="rounded-lg border border-outline/15 bg-card/30 p-3">
                <div className="flex items-center gap-2 mb-1.5">
                  <span className="w-5 h-5 rounded-md bg-green-500/15 flex items-center justify-center text-[10px]">1</span>
                  <p className="text-[10px] uppercase tracking-widest text-muted font-bold">Client Proposals</p>
                </div>
                <p className="text-[10px] text-muted/60 mb-2">Project info filled from these documents</p>
                <DocList docs={proposals} onDelete={deleteProposal} />
                <button
                  onClick={() => proposalInputRef.current?.click()}
                  disabled={uploading}
                  className="w-full mt-1.5 text-[10px] px-2 py-1.5 rounded-lg border border-dashed border-outline/30 text-muted hover:text-foreground hover:border-accent/30 transition-colors disabled:opacity-50"
                >
                  + Upload Proposals (.pdf, .docx, .pptx)
                </button>
                <input ref={proposalInputRef} type="file" multiple accept=".pdf,.docx,.pptx" className="hidden" onChange={e => uploadProposals(e.target.files)} />
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-3 border-t border-card-border">
          <div className="flex items-center gap-2 px-2">
            <svg className="w-4 h-4 text-accent" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            <span className="text-[10px] text-muted">SOW Generator</span>
          </div>
        </div>
      </div>

      {/* ── Main Area ─────────────────────────────────────────────────── */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Top bar */}
        <div className="shrink-0 h-12 border-b border-card-border flex items-center px-4 gap-3">
          <button
            onClick={() => setSidebarOpen(!sidebarOpen)}
            className="p-1.5 rounded-lg text-muted hover:text-foreground hover:bg-card transition-colors"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </button>
          {active ? (
            <>
              <h2 className="text-sm font-medium text-foreground/80 truncate">{sessionTitle || active.title}</h2>
              <span className={`text-[10px] px-2 py-0.5 rounded-full font-bold ${sessionStatus === "final" ? "bg-success/15 text-success" : "bg-warning/15 text-warning"}`}>
                {sessionStatus}
              </span>
            </>
          ) : (
            <h2 className="text-sm font-medium text-foreground/80">SOW Generator</h2>
          )}
        </div>

        {/* Content area */}
        {!active ? (
          /* ── Welcome ──────────────────────────────────────────── */
          <div className="flex-1 flex flex-col items-center justify-center px-6">
            <div className="max-w-lg w-full text-center">
              <div className="w-16 h-16 rounded-2xl bg-accent/15 border border-accent/20 flex items-center justify-center mx-auto mb-5">
                <svg className="w-8 h-8 text-accent" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
              </div>
              <h1 className="text-2xl font-bold tracking-tight mb-2">SOW Generator</h1>
              <p className="text-sm text-muted max-w-md mx-auto mb-4">
                Create professional Statements of Work powered by AI.
              </p>
              <div className="text-left max-w-sm mx-auto mb-8 space-y-2">
                <div className="flex items-start gap-3">
                  <span className="w-5 h-5 rounded-md bg-green-500/15 flex items-center justify-center text-[10px] shrink-0 mt-0.5">1</span>
                  <p className="text-xs text-muted"><strong className="text-foreground/80">Upload Proposals</strong> &mdash; Client proposals, RFPs, project briefs</p>
                </div>
                <div className="flex items-start gap-3">
                  <span className="w-5 h-5 rounded-md bg-blue-500/15 flex items-center justify-center text-[10px] shrink-0 mt-0.5">2</span>
                  <p className="text-xs text-muted"><strong className="text-foreground/80">Generate SOW</strong> &mdash; AI creates a branded Nester Labs SOW</p>
                </div>
                <div className="flex items-start gap-3">
                  <span className="w-5 h-5 rounded-md bg-purple-500/15 flex items-center justify-center text-[10px] shrink-0 mt-0.5">3</span>
                  <p className="text-xs text-muted"><strong className="text-foreground/80">Refine via Chat</strong> &mdash; Edit sections, add details, download DOCX</p>
                </div>
              </div>
              <button
                onClick={createSession}
                className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-accent text-white text-sm font-bold hover:bg-accent/90 transition-colors"
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
                </svg>
                Create New SOW
              </button>
            </div>
          </div>
        ) : !hasSOW && !generating ? (
          /* ── Session setup ────────────────────────────────────── */
          <div className="flex-1 overflow-y-auto">
            <div className="max-w-xl mx-auto px-6 py-10 space-y-6">
              <div>
                <label className="text-[10px] uppercase tracking-widest text-muted font-bold mb-1.5 block">Session Title</label>
                <input
                  type="text"
                  value={sessionTitle}
                  onChange={e => setSessionTitle(e.target.value)}
                  onBlur={async () => {
                    if (!activeId) return;
                    await fetch(`${API}/sow/sessions/${activeId}`, {
                      method: "PATCH",
                      headers: { "Content-Type": "application/json" },
                      body: JSON.stringify({ title: sessionTitle }),
                    });
                    fetchSessions();
                  }}
                  className="w-full px-3 py-2 rounded-lg border border-card-border bg-card text-sm text-foreground focus:outline-none focus:border-accent/40 transition-colors"
                  placeholder="e.g. Acme Corp Website Redesign"
                />
              </div>

              {/* Status summary */}
              <div className="rounded-xl border border-outline/15 bg-card p-5 space-y-3">
                <h3 className="text-sm font-bold text-foreground">Ready to Generate?</h3>
                <div className="space-y-2">
                  <div className="flex items-center gap-3">
                    <span className="w-2 h-2 rounded-full bg-success" />
                    <p className="text-xs text-foreground/70">Design: Nester Labs brand (automatic)</p>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className={`w-2 h-2 rounded-full ${proposals.length > 0 ? "bg-success" : "bg-warning"}`} />
                    <p className="text-xs text-foreground/70">Client Proposals: {proposals.length > 0 ? `${proposals.length} uploaded` : "None yet — upload in sidebar"}</p>
                  </div>
                </div>
              </div>

              <button
                onClick={handleGenerate}
                disabled={proposals.length === 0 || uploading}
                className="w-full py-3 rounded-xl bg-accent text-white font-bold text-sm hover:bg-accent/90 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
              >
                {uploading ? "Uploading..." : "Generate SOW"}
              </button>
              <p className="text-[10px] text-muted text-center">Upload at least one client proposal to generate</p>
            </div>
          </div>
        ) : (
          /* ── Chat + Preview split ─────────────────────────────── */
          <div className="flex-1 flex min-h-0">
            {/* Chat panel */}
            <div className="flex-1 flex flex-col min-w-0 border-r border-card-border">
              <div className="flex-1 overflow-y-auto">
                {generating && !messages.length ? (
                  <div className="flex flex-col items-center justify-center h-full">
                    <svg className="w-8 h-8 text-accent animate-spin mb-3" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                    </svg>
                    <p className="text-sm text-muted">Generating SOW...</p>
                  </div>
                ) : messages.length === 0 ? (
                  <div className="flex flex-col items-center justify-center h-full px-6">
                    <p className="text-sm font-medium text-foreground/70 mb-2">SOW Generated</p>
                    <p className="text-xs text-muted text-center max-w-xs">
                      Your draft is in the preview panel. Use this chat to refine it.
                    </p>
                    <div className="flex flex-wrap gap-2 mt-4 justify-center">
                      {["Change payment terms to net-45", "Add more detail to deliverables", "Update the timeline"].map(s => (
                        <button key={s} onClick={() => sendChat(s)} className="text-[11px] px-3 py-1.5 rounded-lg border border-card-border bg-card hover:border-accent/30 text-foreground/70 hover:text-foreground transition-colors">
                          {s}
                        </button>
                      ))}
                    </div>
                  </div>
                ) : (
                  <div className="max-w-xl mx-auto px-4 py-4 space-y-4">
                    {messages.map(msg => (
                      <div key={msg.id} className="animate-fade-in">
                        {msg.role === "user" ? (
                          <div className="flex gap-3 justify-end">
                            <div className="max-w-[85%] rounded-2xl rounded-tr-md px-4 py-3 bg-accent text-white">
                              <p className="text-[13px] leading-relaxed whitespace-pre-wrap">{msg.content}</p>
                            </div>
                          </div>
                        ) : (
                          <div className="flex gap-3">
                            <div className="w-6 h-6 rounded-full bg-secondary/15 border border-secondary/20 flex items-center justify-center shrink-0 mt-1">
                              <svg className="w-3 h-3 text-secondary" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                              </svg>
                            </div>
                            <div className="max-w-[85%] rounded-2xl rounded-tl-md px-4 py-3 bg-card border border-card-border">
                              {msg.content ? <div>{renderChatMarkdown(msg.content)}</div> : null}
                              {msg.streaming && <span className="inline-block w-2 h-4 bg-secondary/60 ml-0.5 animate-pulse rounded-sm align-middle" />}
                            </div>
                          </div>
                        )}
                      </div>
                    ))}
                    <div ref={bottomRef} />
                  </div>
                )}
              </div>

              {/* Chat input */}
              <div className="shrink-0 border-t border-card-border px-4 py-3">
                <form onSubmit={handleSubmit} className="relative">
                  <div className="flex items-end gap-2 rounded-xl border border-card-border bg-card px-3 py-2.5 focus-within:border-accent/40 transition-colors">
                    <textarea
                      ref={inputRef}
                      value={input}
                      onChange={e => setInput(e.target.value)}
                      onKeyDown={handleKeyDown}
                      placeholder="Ask to refine the SOW..."
                      disabled={loading || generating}
                      rows={1}
                      className="flex-1 bg-transparent text-sm text-foreground placeholder:text-muted resize-none focus:outline-none disabled:opacity-50 max-h-24"
                      style={{ minHeight: "22px" }}
                      onInput={e => {
                        const t = e.currentTarget;
                        t.style.height = "22px";
                        t.style.height = `${Math.min(t.scrollHeight, 96)}px`;
                      }}
                    />
                    <button
                      type="submit"
                      disabled={loading || generating || !input.trim()}
                      className="shrink-0 w-7 h-7 rounded-lg bg-accent flex items-center justify-center disabled:opacity-30 hover:bg-accent/90 transition-colors"
                    >
                      {loading ? (
                        <svg className="w-3.5 h-3.5 text-white animate-spin" fill="none" viewBox="0 0 24 24">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                        </svg>
                      ) : (
                        <svg className="w-3.5 h-3.5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M5 12h14M12 5l7 7-7 7" />
                        </svg>
                      )}
                    </button>
                  </div>
                </form>
              </div>
            </div>

            {/* Document preview panel */}
            <div className="w-[48%] min-w-[360px] flex flex-col bg-background">
              <SOWPreview
                sessionId={activeId!}
                markdown={sowMarkdown}
                onMarkdownChange={md => setSowMarkdown(md)}
                generating={generating}
              />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
