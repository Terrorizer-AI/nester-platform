"use client";

import { useState, useCallback, useEffect, useRef } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface SOWPreviewProps {
  sessionId: string;
  markdown: string;
  onMarkdownChange: (md: string) => void;
  generating?: boolean;
}

export default function SOWPreview({ sessionId, markdown, onMarkdownChange, generating }: SOWPreviewProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(markdown);
  const [saving, setSaving] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const [previewKey, setPreviewKey] = useState(0);
  const [savedOnce, setSavedOnce] = useState(false);

  // Only reload iframe when markdown is saved to DB (not during streaming)
  // The markdown is saved when generating transitions from true → false
  useEffect(() => {
    if (!generating && markdown && !editing) {
      setSavedOnce(true);
      setPreviewKey(k => k + 1);
    }
  }, [generating, editing]); // eslint-disable-line react-hooks/exhaustive-deps

  // Also reload when markdown changes via chat (sow_updated event) — not during generation
  const prevMarkdown = useRef(markdown);
  useEffect(() => {
    if (!generating && !editing && markdown && markdown !== prevMarkdown.current && savedOnce) {
      setPreviewKey(k => k + 1);
    }
    prevMarkdown.current = markdown;
  }, [markdown, generating, editing, savedOnce]);

  const handleEdit = () => {
    setDraft(markdown);
    setEditing(true);
  };

  const handleCancel = () => {
    setEditing(false);
    setDraft(markdown);
  };

  const handleSave = useCallback(async () => {
    setSaving(true);
    try {
      const res = await fetch(`${API}/sow/sessions/${sessionId}/sow`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ markdown: draft }),
      });
      if (!res.ok) throw new Error("Save failed");
      onMarkdownChange(draft);
      setEditing(false);
    } catch {
      alert("Failed to save changes");
    } finally {
      setSaving(false);
    }
  }, [sessionId, draft, onMarkdownChange]);

  const handleDownload = useCallback(async () => {
    setDownloading(true);
    try {
      const res = await fetch(`${API}/sow/sessions/${sessionId}/download`);
      if (!res.ok) throw new Error("Download failed");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `SOW-${sessionId.slice(0, 8)}.docx`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch {
      alert("Failed to download DOCX");
    } finally {
      setDownloading(false);
    }
  }, [sessionId]);

  if (!markdown && !editing) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-muted/50 px-6">
        <svg className="w-12 h-12 mb-3 text-muted/20" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
        </svg>
        <p className="text-sm font-medium">No SOW generated yet</p>
        <p className="text-xs mt-1">Upload proposals and click Generate to create a draft</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Toolbar */}
      <div className="shrink-0 flex items-center gap-2 px-4 py-2.5 border-b border-card-border bg-surface-low/50">
        <svg className="w-4 h-4 text-accent" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
        </svg>
        <span className="text-xs font-bold text-foreground/80 flex-1">Document Preview</span>

        {editing ? (
          <>
            <button
              onClick={handleCancel}
              className="text-[10px] px-2.5 py-1 rounded-lg border border-outline/30 text-muted hover:text-foreground transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={handleSave}
              disabled={saving}
              className="text-[10px] px-2.5 py-1 rounded-lg bg-accent text-white font-bold hover:bg-accent/90 transition-colors disabled:opacity-50"
            >
              {saving ? "Saving..." : "Save"}
            </button>
          </>
        ) : (
          <>
            <button
              onClick={handleEdit}
              className="text-[10px] px-2.5 py-1 rounded-lg border border-outline/30 text-muted hover:text-foreground hover:border-accent/30 transition-colors"
            >
              Edit Markdown
            </button>
            <button
              onClick={handleDownload}
              disabled={downloading}
              className="text-[10px] px-2.5 py-1 rounded-lg bg-accent text-white font-bold hover:bg-accent/90 transition-colors disabled:opacity-50"
            >
              {downloading ? "..." : "Download DOCX"}
            </button>
          </>
        )}
      </div>

      {/* Content */}
      {editing ? (
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          className="flex-1 w-full p-4 bg-background text-xs font-mono text-foreground/85 resize-none focus:outline-none leading-relaxed"
          spellCheck={false}
        />
      ) : generating || !savedOnce ? (
        <div className="flex-1 flex flex-col items-center justify-center text-muted/50">
          <svg className="w-8 h-8 animate-spin mb-3 text-accent/40" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          <p className="text-xs">Generating document preview...</p>
        </div>
      ) : (
        <iframe
          ref={iframeRef}
          key={previewKey}
          src={`${API}/sow/sessions/${sessionId}/preview`}
          className="flex-1 w-full border-0"
          title="SOW Document Preview"
        />
      )}
    </div>
  );
}
