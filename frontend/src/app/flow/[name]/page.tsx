"use client";

import { useState, useCallback, useEffect } from "react";
import { useParams } from "next/navigation";
import EmailPreview from "@/components/EmailPreview";
import PersonaCard from "@/components/PersonaCard";
import AnalysisPanel from "@/components/AnalysisPanel";
import CompanyDashboard from "@/components/CompanyDashboard";
import ResearchChatDrawer from "@/components/ResearchChatDrawer";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const PROFILE_KEY = "nester_sender_profile";

// ── Types ─────────────────────────────────────────────────────────────────────

interface AgentStep {
  id: string;
  label: string;
  status: "idle" | "running" | "completed" | "failed";
  parallel?: boolean;
  durationMs?: number;
}

interface SenderProfile {
  sender_name: string;
  sender_company: string;
  sender_role: string;
  services: string;
  value_proposition: string;
  target_pain_points: string;
  ideal_outcome: string;
  case_studies: string;
  email_tone: string;
  cta_preference: string;
}

interface SalesForm extends SenderProfile {
  linkedin_url: string;
  company_website: string;
  company_linkedin_url: string;
}

interface ProspectRow {
  id: string;
  linkedin_url: string;
  company_website: string;
  company_linkedin_url: string;
  status: "idle" | "running" | "completed" | "failed";
  result: Record<string, unknown> | null;
  agents: AgentStep[];
  duration_ms: number | null;
}

const CONCURRENCY = 5;
const STAGGER_MS  = 15_000; // 15s between starts to avoid LinkedIn burst detection

// ── Pipeline config ───────────────────────────────────────────────────────────

const PIPELINE_STAGES: AgentStep[] = [
  { id: "linkedin_researcher",        label: "LinkedIn",        status: "idle" },
  { id: "company_researcher",         label: "Company",         status: "idle", parallel: true },
  { id: "company_linkedin_researcher",label: "Co. LinkedIn",    status: "idle", parallel: true },
  { id: "activity_analyzer",          label: "User LinkedIn",   status: "idle", parallel: true },
  { id: "persona_builder",            label: "Persona",         status: "idle" },
  { id: "service_matcher",            label: "Service Match",   status: "idle" },
  { id: "email_composer",             label: "Email Compose",   status: "idle" },
  { id: "output_formatter",           label: "Formatter",       status: "idle" },
];

const BLANK_PROFILE: SenderProfile = {
  sender_name: "", sender_company: "", sender_role: "", services: "",
  value_proposition: "", target_pain_points: "", ideal_outcome: "",
  case_studies: "", email_tone: "professional", cta_preference: "soft",
};

function makeProspect(overrides: Partial<ProspectRow> = {}): ProspectRow {
  return {
    id: Math.random().toString(36).slice(2),
    linkedin_url: "",
    company_website: "",
    company_linkedin_url: "",
    status: "idle",
    result: null,
    agents: PIPELINE_STAGES.map(a => ({ ...a })),
    duration_ms: null,
    ...overrides,
  };
}

// ── Profile persistence ───────────────────────────────────────────────────────

function loadSavedProfile(): SenderProfile | null {
  try {
    const raw = localStorage.getItem(PROFILE_KEY);
    return raw ? (JSON.parse(raw) as SenderProfile) : null;
  } catch { return null; }
}

function saveProfile(p: SenderProfile): void {
  try { localStorage.setItem(PROFILE_KEY, JSON.stringify(p)); } catch { /* noop */ }
}

function extractProfile(f: SalesForm): SenderProfile {
  const { linkedin_url, company_website, company_linkedin_url, ...profile } = f;
  void linkedin_url; void company_website; void company_linkedin_url;
  return profile;
}

// ── Pipeline Timeline ─────────────────────────────────────────────────────────

function AgentNode({ step, index }: { step: AgentStep; index: number }) {
  const isDone = step.status === "completed";
  const isRunning = step.status === "running";
  const isFailed = step.status === "failed";

  return (
    <div className="flex flex-col items-center gap-1.5 group/node relative px-3">
      {/* Node orb */}
      <div className={`relative flex items-center justify-center rounded-full border transition-all duration-500 ${
        isDone
          ? "w-8 h-8 bg-secondary border-secondary/30 shadow-[0_0_12px_rgba(78,222,163,0.5)]"
          : isRunning
          ? "w-9 h-9 bg-accent border-accent/50 shadow-[0_0_18px_rgba(128,131,255,0.6)] animate-pulse"
          : isFailed
          ? "w-8 h-8 bg-error/20 border-error/40"
          : "w-8 h-8 bg-surface-high border-outline/20"
      }`}>
        {isDone ? (
          <svg className="w-3.5 h-3.5 text-background" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
          </svg>
        ) : isRunning ? (
          <svg className="w-3.5 h-3.5 text-white animate-spin" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
          </svg>
        ) : isFailed ? (
          <span className="text-error text-[10px] font-black">✕</span>
        ) : (
          <span className={`text-[10px] font-black ${isDone ? "text-background" : "text-muted/50"}`}>{index + 1}</span>
        )}
      </div>

      {/* Label */}
      <div className="text-center min-w-0">
        <span className={`block text-[0.5rem] uppercase tracking-wider font-bold whitespace-nowrap ${
          isDone ? "text-secondary" : isRunning ? "text-accent" : "text-muted/40"
        }`}>
          {step.label}
        </span>
        <span className={`block text-[0.42rem] font-mono mt-0.5 ${
          isDone ? "text-secondary/50" : isRunning ? "text-accent/60 animate-pulse" : "text-muted/25"
        }`}>
          {isDone && step.durationMs ? `${(step.durationMs/1000).toFixed(1)}s` : isRunning ? "RUNNING" : "STANDBY"}
        </span>
      </div>

      {/* Hover tooltip */}
      <div className="absolute bottom-full mb-2 left-1/2 -translate-x-1/2 bg-card border border-outline/30 rounded-lg px-3 py-2 text-[10px] whitespace-nowrap opacity-0 group-hover/node:opacity-100 transition-opacity pointer-events-none z-50 shadow-xl">
        <span className="font-bold text-foreground block">{step.label}</span>
        <span className={`font-mono text-[9px] ${isDone ? "text-secondary" : isRunning ? "text-accent" : "text-muted"}`}>
          {isDone ? `✓ done` : isRunning ? "● running" : "○ pending"}
        </span>
      </div>
    </div>
  );
}

function Wire({ active }: { active: boolean }) {
  return (
    <div className={`h-px w-5 flex-shrink-0 transition-all duration-500 self-start mt-4 ${
      active ? "bg-secondary/70" : ""
    }`}
      style={active ? {} : {
        backgroundImage: "repeating-linear-gradient(90deg,#464554 0,#464554 3px,transparent 3px,transparent 7px)"
      }}
    />
  );
}

// ── Architecture node card ────────────────────────────────────────────────────

function ArchNode({
  step, index, role, desc, outputs,
}: {
  step: AgentStep; index: number; role: string; desc: string; outputs: string[];
}) {
  const isDone    = step.status === "completed";
  const isRunning = step.status === "running";
  const isFailed  = step.status === "failed";

  const borderColor = isDone
    ? "border-secondary/40 shadow-[0_0_14px_rgba(78,222,163,0.18)]"
    : isRunning
    ? "border-accent/50 shadow-[0_0_18px_rgba(128,131,255,0.3)] animate-pulse"
    : isFailed
    ? "border-error/30"
    : "border-outline/20";

  const dotColor = isDone ? "bg-secondary" : isRunning ? "bg-accent animate-pulse" : "bg-outline/30";

  return (
    <div className={`relative rounded-xl border bg-card/70 backdrop-blur-sm px-4 py-3 w-44 transition-all duration-500 ${borderColor}`}>
      {/* Index badge */}
      <div className="absolute -top-2.5 -left-2.5 w-5 h-5 rounded-full bg-surface-high border border-outline/30 flex items-center justify-center">
        <span className="text-[0.45rem] font-black text-muted">{index}</span>
      </div>
      {/* Status dot */}
      <div className={`absolute -top-1.5 -right-1.5 w-3 h-3 rounded-full border-2 border-background ${dotColor}`} />

      <div className="mb-1.5 flex items-center gap-1.5">
        <span className={`text-[0.6rem] font-black uppercase tracking-wider truncate ${
          isDone ? "text-secondary" : isRunning ? "text-accent" : "text-muted/60"
        }`}>{step.label}</span>
      </div>

      <div className={`text-[0.5rem] font-bold uppercase tracking-widest mb-1 ${
        isDone ? "text-secondary/50" : "text-muted/30"
      }`}>{role}</div>

      <p className="text-[0.5rem] text-muted/50 leading-relaxed mb-2">{desc}</p>

      {/* Outputs */}
      <div className="flex flex-wrap gap-1">
        {outputs.map(o => (
          <span key={o} className={`text-[0.42rem] font-bold px-1.5 py-0.5 rounded-full uppercase tracking-wide ${
            isDone ? "bg-secondary/10 text-secondary/70" : "bg-surface-high text-muted/40"
          }`}>{o}</span>
        ))}
      </div>

      {/* Timing */}
      {isDone && step.durationMs && (
        <div className="mt-2 pt-2 border-t border-outline/10 text-[0.45rem] font-mono text-secondary/50">
          ✓ {(step.durationMs / 1000).toFixed(1)}s
        </div>
      )}
      {isRunning && (
        <div className="mt-2 pt-2 border-t border-outline/10 flex items-center gap-1">
          <span className="w-1 h-1 rounded-full bg-accent animate-bounce" style={{ animationDelay: "0ms" }} />
          <span className="w-1 h-1 rounded-full bg-accent animate-bounce" style={{ animationDelay: "150ms" }} />
          <span className="w-1 h-1 rounded-full bg-accent animate-bounce" style={{ animationDelay: "300ms" }} />
        </div>
      )}
    </div>
  );
}

// ── Vertical arrow connector ──────────────────────────────────────────────────

function VArrow({ active, label }: { active: boolean; label?: string }) {
  return (
    <div className="flex flex-col items-center gap-0 py-1">
      {label && (
        <span className={`text-[0.4rem] uppercase tracking-widest font-bold mb-0.5 ${active ? "text-secondary/60" : "text-muted/20"}`}>
          {label}
        </span>
      )}
      <div className={`w-px h-6 transition-colors duration-500 ${active ? "bg-secondary/50" : "bg-outline/15"}`} />
      <svg width="8" height="6" viewBox="0 0 8 6" className={`transition-colors duration-500 ${active ? "text-secondary/50" : "text-outline/15"}`}>
        <path d="M4 6 L0 0 L8 0 Z" fill="currentColor" />
      </svg>
    </div>
  );
}

// ── Horizontal arrow ─────────────────────────────────────────────────────────

function HArrow({ active }: { active: boolean }) {
  return (
    <svg width="32" height="8" viewBox="0 0 32 8" className={`flex-shrink-0 transition-colors duration-500 ${active ? "text-secondary/60" : "text-outline/20"}`}>
      <path d="M0 4 L26 4 M22 0 L26 4 L22 8" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  );
}

// ── Stage badge label ─────────────────────────────────────────────────────────

function StageBadge({ label, accent }: { label: string; accent?: boolean }) {
  return (
    <div className="my-1">
      <span className={`text-[0.45rem] font-bold uppercase tracking-widest px-2 py-0.5 rounded-full border border-outline/10 flex items-center gap-1.5 ${
        accent ? "bg-surface-high text-muted/40" : "bg-surface-high text-muted/30"
      }`}>
        {accent && <span className="w-1.5 h-1.5 rounded-full bg-accent/40" />}
        {label}
      </span>
    </div>
  );
}

// ── Mini node (compact card for single-row diagram) ──────────────────────────

function MiniNode({ step, index, label, sub }: { step: AgentStep; index: number; label: string; sub: string }) {
  const isDone    = step.status === "completed";
  const isRunning = step.status === "running";

  return (
    <div className={`relative rounded-lg border px-2.5 py-2 shrink-0 transition-all duration-500 ${
      isDone    ? "border-secondary/40 bg-secondary/5 shadow-[0_0_10px_rgba(78,222,163,0.12)]"
      : isRunning ? "border-accent/50 bg-accent/5 shadow-[0_0_12px_rgba(128,131,255,0.2)] animate-pulse"
      : "border-outline/20 bg-card/50"
    }`} style={{ minWidth: "68px" }}>
      {/* index */}
      <div className="absolute -top-2 -left-2 w-4 h-4 rounded-full bg-surface-high border border-outline/30 flex items-center justify-center">
        <span className="text-[0.38rem] font-black text-muted">{index}</span>
      </div>
      {/* status dot */}
      <div className={`absolute -top-1 -right-1 w-2 h-2 rounded-full border border-background ${
        isDone ? "bg-secondary" : isRunning ? "bg-accent animate-pulse" : "bg-outline/30"
      }`} />
      <div className={`text-[0.5rem] font-black uppercase tracking-wide truncate ${
        isDone ? "text-secondary" : isRunning ? "text-accent" : "text-muted/50"
      }`}>{label}</div>
      <div className="text-[0.38rem] text-muted/40 truncate">{sub}</div>
      {isDone && step.durationMs ? (
        <div className="text-[0.38rem] font-mono text-secondary/50 mt-0.5">✓ {(step.durationMs/1000).toFixed(1)}s</div>
      ) : isRunning ? (
        <div className="flex gap-0.5 mt-0.5">
          {[0,150,300].map(d => <span key={d} className="w-0.5 h-0.5 rounded-full bg-accent animate-bounce" style={{ animationDelay: `${d}ms` }} />)}
        </div>
      ) : null}
    </div>
  );
}

// ── Parallel fork / join SVGs ─────────────────────────────────────────────────

function ParallelFork({ active }: { active: boolean }) {
  const c = active ? "#4edea3" : "rgba(70,69,84,0.25)";
  // From 1 point on left → split to 3 rows (top/mid/bot) on right
  return (
    <svg width="20" height="90" viewBox="0 0 20 90" className="transition-all duration-500 shrink-0">
      <line x1="0" y1="45" x2="10" y2="45" stroke={c} strokeWidth="1.5"/>
      <line x1="10" y1="15" x2="10" y2="75" stroke={c} strokeWidth="1.5"/>
      <line x1="10" y1="15" x2="20" y2="15" stroke={c} strokeWidth="1.5"/>
      <line x1="10" y1="45" x2="20" y2="45" stroke={c} strokeWidth="1.5"/>
      <line x1="10" y1="75" x2="20" y2="75" stroke={c} strokeWidth="1.5"/>
    </svg>
  );
}

function ParallelJoin({ active }: { active: boolean }) {
  const c = active ? "#4edea3" : "rgba(70,69,84,0.25)";
  return (
    <svg width="20" height="90" viewBox="0 0 20 90" className="transition-all duration-500 shrink-0">
      <line x1="0" y1="15" x2="10" y2="15" stroke={c} strokeWidth="1.5"/>
      <line x1="0" y1="45" x2="10" y2="45" stroke={c} strokeWidth="1.5"/>
      <line x1="0" y1="75" x2="10" y2="75" stroke={c} strokeWidth="1.5"/>
      <line x1="10" y1="15" x2="10" y2="75" stroke={c} strokeWidth="1.5"/>
      <line x1="10" y1="45" x2="20" y2="45" stroke={c} strokeWidth="1.5"/>
    </svg>
  );
}

// ── Fan-out / fan-in for parallel block ───────────────────────────────────────

function FanOut({ active }: { active: boolean }) {
  const c = active ? "#4edea3" : "rgba(70,69,84,0.3)";
  return (
    <svg width="200" height="28" viewBox="0 0 200 28" className="transition-all duration-500">
      {/* Vertical stem down */}
      <line x1="100" y1="0" x2="100" y2="12" stroke={c} strokeWidth="1.5" />
      {/* Horizontal bar */}
      <line x1="24" y1="12" x2="176" y2="12" stroke={c} strokeWidth="1.5" />
      {/* Three drops */}
      <line x1="24"  y1="12" x2="24"  y2="28" stroke={c} strokeWidth="1.5" />
      <line x1="100" y1="12" x2="100" y2="28" stroke={c} strokeWidth="1.5" />
      <line x1="176" y1="12" x2="176" y2="28" stroke={c} strokeWidth="1.5" />
    </svg>
  );
}

function FanIn({ active }: { active: boolean }) {
  const c = active ? "#4edea3" : "rgba(70,69,84,0.3)";
  return (
    <svg width="200" height="28" viewBox="0 0 200 28" className="transition-all duration-500">
      {/* Three rises */}
      <line x1="24"  y1="0" x2="24"  y2="16" stroke={c} strokeWidth="1.5" />
      <line x1="100" y1="0" x2="100" y2="16" stroke={c} strokeWidth="1.5" />
      <line x1="176" y1="0" x2="176" y2="16" stroke={c} strokeWidth="1.5" />
      {/* Horizontal bar */}
      <line x1="24" y1="16" x2="176" y2="16" stroke={c} strokeWidth="1.5" />
      {/* Stem up */}
      <line x1="100" y1="16" x2="100" y2="28" stroke={c} strokeWidth="1.5" />
    </svg>
  );
}

function PipelineTimeline({ steps, fullscreen = false }: { steps: AgentStep[]; fullscreen?: boolean }) {
  const linkedin   = steps[0];
  const company    = steps[1];
  const coLinkedin = steps[2];
  const activity   = steps[3];
  const persona    = steps[4];
  const service    = steps[5];
  const email      = steps[6];
  const formatter  = steps[7];

  const completedCount = steps.filter(s => s.status === "completed").length;
  const progress = steps.length ? (completedCount / steps.length) * 100 : 0;
  const isRunning = steps.some(s => s.status === "running");
  const isComplete = steps.every(s => s.status === "completed") && steps.length > 0;
  const totalMs = steps.reduce((sum, s) => sum + (s.durationMs || 0), 0);

  const linkedinDone    = linkedin?.status === "completed";
  const parallelAllDone = [company, coLinkedin, activity].every(s => s?.status === "completed");
  const personaDone     = persona?.status === "completed";
  const serviceDone     = service?.status === "completed";
  const emailDone       = email?.status === "completed";

  if (fullscreen) {
    return (
      <div className="w-full h-full flex flex-col items-center justify-center px-6 py-4 gap-4">

        {/* ── Header ── */}
        <div className="flex items-center gap-3 shrink-0">
          <div>
            <h2 className="text-xs font-black uppercase tracking-widest text-foreground">Sales Outreach Pipeline</h2>
            <p className="text-[0.48rem] text-muted/50 uppercase tracking-widest">8-Agent Architecture · AI-Driven Personalization</p>
          </div>
          {isRunning && (
            <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-accent/10 border border-accent/20">
              <span className="w-1.5 h-1.5 rounded-full bg-accent animate-pulse" />
              <span className="text-[0.45rem] font-bold uppercase tracking-widest text-accent">Live · {completedCount}/{steps.length}</span>
            </span>
          )}
          {isComplete && (
            <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-secondary/10 border border-secondary/20">
              <span className="w-1.5 h-1.5 rounded-full bg-secondary" />
              <span className="text-[0.45rem] font-bold uppercase tracking-widest text-secondary">Complete · {(totalMs/1000).toFixed(1)}s</span>
            </span>
          )}
          {!isRunning && !isComplete && (
            <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-surface-high border border-outline/20">
              <span className="w-1.5 h-1.5 rounded-full bg-muted/30" />
              <span className="text-[0.45rem] font-bold uppercase tracking-widest text-muted/40">Ready</span>
            </span>
          )}
        </div>

        {/* ── Single-row architecture diagram ── */}
        <div className="flex items-center justify-center gap-0 shrink-0 w-full">

          {/* Input bubble */}
          <div className="rounded-lg border border-dashed border-outline/20 bg-surface-low/30 px-2 py-1.5 text-center shrink-0">
            <div className="text-[0.38rem] font-bold uppercase tracking-widest text-muted/40 mb-0.5">Input</div>
            <div className="text-[0.38rem] text-muted/40 leading-relaxed">
              <div>LinkedIn</div><div>Company</div><div>Seller</div>
            </div>
          </div>

          <HArrow active={true} />

          {/* Stage 1 */}
          {linkedin && <MiniNode step={linkedin} index={1} label="LinkedIn" sub="Profile + Posts" />}

          {/* Parallel fork */}
          <div className="flex flex-col items-center shrink-0 mx-1">
            <ParallelFork active={linkedinDone} />
          </div>

          {/* Stage 2 — stacked parallel */}
          <div className="flex flex-col gap-1.5 shrink-0">
            <div className="text-[0.38rem] font-bold uppercase tracking-widest text-accent/40 text-center mb-0.5">∥ parallel</div>
            {company    && <MiniNode step={company}    index={2} label="Company"    sub="Website scrape" />}
            {coLinkedin && <MiniNode step={coLinkedin} index={3} label="Co.LinkedIn" sub="Team + posts" />}
            {activity   && <MiniNode step={activity}   index={4} label="User LI"    sub="Posts + DNA" />}
          </div>

          {/* Parallel join */}
          <div className="flex flex-col items-center shrink-0 mx-1">
            <ParallelJoin active={parallelAllDone} />
          </div>

          {/* Stage 3a */}
          {persona && <MiniNode step={persona} index={5} label="Persona" sub="Psych profile" />}
          <HArrow active={personaDone} />

          {/* Stage 3b */}
          {service && <MiniNode step={service} index={6} label="Matcher" sub="Service fit" />}
          <HArrow active={serviceDone} />

          {/* Stage 3c */}
          {email && <MiniNode step={email} index={7} label="Email" sub="3 variants" />}
          <HArrow active={emailDone} />

          {/* Stage 4 */}
          {formatter && <MiniNode step={formatter} index={8} label="Formatter" sub="JSON output" />}

          <HArrow active={isComplete} />

          {/* Output bubble */}
          <div className={`rounded-lg border px-2 py-1.5 text-center shrink-0 transition-all duration-500 ${
            isComplete ? "border-secondary/30 bg-secondary/5" : "border-dashed border-outline/20 bg-surface-low/30"
          }`}>
            <div className={`text-[0.38rem] font-bold uppercase tracking-widest mb-0.5 ${isComplete ? "text-secondary/60" : "text-muted/40"}`}>Output</div>
            <div className="text-[0.38rem] text-muted/40 leading-relaxed">
              <div>Emails</div><div>Persona</div><div>Intel</div>
            </div>
          </div>

        </div>

        {/* Progress bar */}
        <div className="w-full max-w-xl shrink-0 flex flex-col gap-1">
          <div className="flex justify-between text-[0.45rem] font-mono text-muted/40">
            <span>{completedCount}/{steps.length} agents</span>
            <span>{Math.round(progress)}%</span>
          </div>
          <div className="h-1 bg-outline/10 rounded-full overflow-hidden">
            <div className="h-full bg-gradient-to-r from-accent to-secondary rounded-full transition-all duration-700" style={{ width: `${progress}%` }} />
          </div>
        </div>

      </div>
    );
  }

  // ── Compact header bar (shown after pipeline completes) ────────────────────

  const linkedinDone2    = linkedin?.status === "completed";
  const parallelAllDone2 = [company, coLinkedin, activity].every(s => s?.status === "completed");

  return (
    <div className="glass border-b border-outline/10 px-6 py-4 shrink-0">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="text-[0.55rem] font-black uppercase tracking-widest text-muted">Pipeline</span>
          {isRunning && (
            <span className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-accent/10 border border-accent/20">
              <span className="w-1.5 h-1.5 rounded-full bg-accent animate-pulse" />
              <span className="text-[0.45rem] font-bold uppercase tracking-widest text-accent">Live</span>
            </span>
          )}
          {isComplete && (
            <span className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-secondary/10 border border-secondary/20">
              <span className="w-1.5 h-1.5 rounded-full bg-secondary" />
              <span className="text-[0.45rem] font-bold uppercase tracking-widest text-secondary">Complete · {(totalMs/1000).toFixed(1)}s</span>
            </span>
          )}
        </div>
        <div className="flex items-center gap-4">
          {isComplete && totalMs > 0 && (
            <div className="text-right">
              <span className="block text-[0.42rem] uppercase tracking-widest text-muted">Time</span>
              <span className="text-xs font-black text-accent font-mono">{(totalMs/1000).toFixed(1)}s</span>
            </div>
          )}
          <div className="text-right">
            <span className="block text-[0.42rem] uppercase tracking-widest text-muted">Progress</span>
            <span className="text-xs font-black text-secondary font-mono">{Math.round(progress)}%</span>
          </div>
        </div>
      </div>

      {/* Timeline — single horizontal row */}
      <div className="flex items-start justify-center overflow-x-auto">
        <div className="flex flex-col items-center" style={{ paddingTop: "13px" }}>
          {linkedin && <AgentNode step={linkedin} index={0} />}
        </div>
        <Wire active={linkedinDone2} />

        <div className="flex flex-col items-center">
          <span className="text-[0.38rem] uppercase tracking-widest text-accent/30 font-bold mb-1 h-3 flex items-center">∥ parallel</span>
          <div className="flex items-start border border-accent/15 rounded-xl bg-surface-low/30 px-1 py-1">
            {[company, coLinkedin, activity].map((step, i) => step && (
              <div key={step.id} className="flex items-start">
                <AgentNode step={step} index={i + 1} />
                {i < 2 && <div className="w-px h-4 bg-outline/20 mt-4 flex-shrink-0" />}
              </div>
            ))}
          </div>
        </div>

        <Wire active={parallelAllDone2} />

        {[
          { step: persona,   idx: 4, active: persona?.status === "completed" },
          { step: service,   idx: 5, active: service?.status === "completed" },
          { step: email,     idx: 6, active: email?.status === "completed" },
          { step: formatter, idx: 7, active: false },
        ].map(({ step, idx, active }, pos) => step && (
          <div key={step.id} className="flex items-start">
            <div style={{ paddingTop: "13px" }}>
              <AgentNode step={step} index={idx} />
            </div>
            {pos < 3 && <Wire active={active} />}
          </div>
        ))}
      </div>

      {/* Progress bar */}
      <div className="mt-3 h-px bg-outline/10 rounded-full overflow-hidden">
        <div
          className="h-full bg-gradient-to-r from-accent to-secondary rounded-full transition-all duration-700"
          style={{ width: `${progress}%` }}
        />
      </div>
    </div>
  );
}

// ── Service Match Dial ────────────────────────────────────────────────────────

function MatchDial({ score }: { score: number }) {
  const r = 36;
  const circ = 2 * Math.PI * r;
  const offset = circ - (score / 100) * circ;
  const color = score >= 70 ? "#4edea3" : score >= 50 ? "#8083ff" : "#ffb95f";

  return (
    <div className="relative w-24 h-24 flex items-center justify-center">
      <svg className="w-full h-full -rotate-90" viewBox="0 0 80 80">
        <circle cx="40" cy="40" r={r} fill="transparent" stroke="#2a292f" strokeWidth="6" />
        <circle
          cx="40" cy="40" r={r} fill="transparent"
          stroke={color} strokeWidth="6"
          strokeDasharray={circ} strokeDashoffset={offset}
          strokeLinecap="round"
          className="transition-all duration-1000"
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-xl font-black tracking-tighter">{score}</span>
        <span className="text-[0.5rem] uppercase tracking-widest text-muted font-bold">match</span>
      </div>
    </div>
  );
}

// ── Left Panel ────────────────────────────────────────────────────────────────

function ServiceTag({ label, selected, onClick }: { label: string; selected: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={`px-3 py-1.5 rounded-full text-[0.625rem] font-bold uppercase tracking-tight transition-all active:scale-95 ${
        selected
          ? "bg-accent text-white shadow-[0_0_8px_rgba(128,131,255,0.3)]"
          : "bg-surface-high text-muted hover:text-foreground"
      }`}
    >
      {label}
    </button>
  );
}

// ── Skeleton ──────────────────────────────────────────────────────────────────

function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`skeleton rounded-lg ${className}`} />;
}

// ── Output Canvas (right side) ────────────────────────────────────────────────

type Tab = "email" | "persona" | "intelligence" | "company" | "raw";

function OutputCanvas({
  output,
  running,
  onVerify,
}: {
  output: Record<string, unknown> | null;
  running: boolean;
  onVerify: () => void;
}) {
  const [tab, setTab] = useState<Tab>("email");

  const tabs: { key: Tab; label: string }[] = [
    { key: "email",        label: "Generated Variants" },
    { key: "persona",      label: "Persona" },
    { key: "intelligence", label: "Intelligence" },
    { key: "company",      label: "Company Research" },
    { key: "raw",          label: "Raw" },
  ];

  if (!output && !running) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center gap-6 text-center px-12">
        <div className="w-16 h-16 rounded-2xl bg-surface-high border border-outline/20 flex items-center justify-center">
          <svg className="w-8 h-8 text-muted/40" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z" />
          </svg>
        </div>
        <div>
          <p className="text-sm font-semibold text-foreground/60 mb-1">Canvas is empty</p>
          <p className="text-xs text-muted">Fill in the prospect parameters and run the pipeline</p>
        </div>
        {/* Ghost sections */}
        <div className="w-full max-w-lg space-y-3 mt-4">
          {["Generated Email", "Persona Analysis", "Research Intelligence"].map(s => (
            <div key={s} className="rounded-xl border border-dashed border-outline/20 p-5">
              <div className="text-[0.6rem] uppercase tracking-widest text-muted/30 font-bold">{s}</div>
              <div className="mt-3 space-y-2">
                <div className="h-2 w-3/4 bg-surface-high/50 rounded" />
                <div className="h-2 w-1/2 bg-surface-high/50 rounded" />
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (running && !output) {
    return (
      <div className="flex-1 px-10 py-8 space-y-6 overflow-y-auto">
        {["Research Verification", "Intelligence Cards", "Generated Variants"].map(s => (
          <section key={s} className="animate-fade-in">
            <div className="flex items-center gap-3 mb-4">
              <span className="text-[0.6875rem] font-bold uppercase tracking-widest text-muted">{s}</span>
              <div className="h-px flex-1 bg-outline/10" />
              <span className="w-1.5 h-1.5 rounded-full bg-accent animate-pulse" />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <Skeleton className="h-28" />
              <Skeleton className="h-28" />
            </div>
          </section>
        ))}
      </div>
    );
  }

  if (!output) return null;

  const serviceMatch = output.service_match as Record<string, unknown> | undefined;
  const matchScore = typeof serviceMatch?.match_confidence === "number"
    ? Math.round(serviceMatch.match_confidence * 100)
    : 75;

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* Tab bar */}
      <div className="flex items-center gap-1 px-10 pt-6 border-b border-outline/10">
        {tabs.map(t => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-4 py-2.5 text-[0.6875rem] font-bold uppercase tracking-widest border-b-2 transition-all ${
              tab === t.key
                ? "border-accent text-accent-dim"
                : "border-transparent text-muted hover:text-foreground"
            }`}
          >
            {t.label}
          </button>
        ))}
        <div className="ml-auto flex items-center gap-2 pb-1">
          <button
            onClick={onVerify}
            className="flex items-center gap-1.5 text-[0.625rem] px-3 py-1.5 rounded-full border border-accent/30 text-accent hover:bg-accent/10 font-bold uppercase tracking-widest transition-colors"
          >
            <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            Verify Sources
          </button>
        </div>
      </div>

      {/* Tab content */}
      <div className="flex-1 min-h-0 overflow-y-auto px-10 py-8 space-y-10 animate-slide-up">

        {/* ── EMAIL TAB ── */}
        {tab === "email" && (
          <>
            {/* Service Alignment + Engagement row */}
            <div className="grid grid-cols-12 gap-5">
              <div className="col-span-4 bg-card rounded-2xl border border-outline/10 p-6 flex flex-col items-center justify-center text-center">
                <MatchDial score={matchScore} />
                <h4 className="font-bold text-xs uppercase tracking-widest mt-3 mb-1">Service Alignment</h4>
                <p className="text-[0.6875rem] text-muted leading-relaxed">
                  {typeof output.primary_hook === "string"
                    ? output.primary_hook.slice(0, 80) + "..."
                    : "Analyzing service fit..."}
                </p>
              </div>
              <div className="col-span-8 bg-surface-low rounded-2xl border border-outline/10 p-6">
                <div className="flex justify-between items-center mb-5">
                  <h4 className="font-bold text-xs uppercase tracking-widest">Engagement Probability</h4>
                  <span className="text-[0.625rem] text-accent font-bold uppercase tracking-wide">AI Model</span>
                </div>
                {[
                  { label: "Direct Email", pct: 82, color: "bg-secondary" },
                  { label: "LinkedIn InMail", pct: 64, color: "bg-accent" },
                  { label: "Phone Follow-up", pct: 12, color: "bg-outline" },
                ].map(row => (
                  <div key={row.label} className="space-y-1.5 mb-4 last:mb-0">
                    <div className="flex justify-between text-[0.625rem] font-bold uppercase tracking-widest">
                      <span className="text-muted">{row.label}</span>
                      <span className={row.pct > 50 ? "text-secondary" : row.pct > 30 ? "text-accent-dim" : "text-muted"}>
                        {row.pct}%
                      </span>
                    </div>
                    <div className="h-1 w-full bg-surface-high rounded-full overflow-hidden">
                      <div className={`h-full ${row.color} rounded-full transition-all duration-1000`} style={{ width: `${row.pct}%` }} />
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Email drafts */}
            <EmailPreview
              subject={String(output.email_subject || "")}
              body={String(output.email_body || "")}
              approved={Boolean(output.email_approved)}
              personalizationNotes={output.personalization_notes as string | undefined}
              styleMatch={output.style_match as string | undefined}
              qualityScore={output.email_quality_score as number | undefined}
              drafts={Array.isArray(output.email_drafts) ? output.email_drafts as import("@/components/EmailPreview").EmailDraft[] : undefined}
              onVerify={onVerify}
            />
          </>
        )}

        {/* ── PERSONA TAB ── */}
        {tab === "persona" && (
          <PersonaCard
            persona={output.persona as Record<string, unknown> | undefined}
            confidence={output.persona_confidence as number | undefined}
            communicationStyle={output.communication_style as string | undefined}
          />
        )}

        {/* ── INTELLIGENCE TAB ── */}
        {tab === "intelligence" && (
          <AnalysisPanel
            linkedinData={output.linkedin_data as Record<string, unknown> | undefined}
            companyData={output.company_data as Record<string, unknown> | undefined}
            companyLinkedinData={output.company_linkedin_data as Record<string, unknown> | undefined}
            activityData={output.activity_data as Record<string, unknown> | undefined}
            serviceMatch={output.service_match as Record<string, unknown> | undefined}
            primaryHook={output.primary_hook as string | undefined}
            dataQuality={output.linkedin_data_quality as string | undefined}
            linkedinParsed={output.linkedin_parsed as Record<string, unknown> | undefined}
            companyParsed={output.company_parsed as Record<string, unknown> | undefined}
            companyLinkedinParsed={output.company_linkedin_parsed as Record<string, unknown> | undefined}
            activityParsed={output.activity_parsed as Record<string, unknown> | undefined}
          />
        )}

        {/* ── COMPANY TAB ── */}
        {tab === "company" && (
          <CompanyDashboard
            companyParsed={output.company_parsed as Record<string, unknown> | undefined}
            companyLinkedinParsed={output.company_linkedin_parsed as Record<string, unknown> | undefined}
            companyData={output.company_data as Record<string, unknown> | undefined}
          />
        )}

        {/* ── RAW TAB ── */}
        {tab === "raw" && (
          <div className="rounded-xl border border-outline/10 bg-card p-5 overflow-auto max-h-[70vh]">
            <pre className="text-[0.6875rem] font-mono text-muted/80 whitespace-pre-wrap leading-relaxed">
              {JSON.stringify(output, null, 2)}
            </pre>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function FlowPage() {
  const params = useParams();
  const name = params.name as string;
  const isSales = name === "sales_outreach";

  // ── Sender profile (shared across all prospects) ─────────────────────────
  const [senderForm, setSenderForm] = useState<SenderProfile>({ ...BLANK_PROFILE });
  const [savedProfile, setSavedProfile] = useState<SenderProfile | null>(null);
  const [profileMode, setProfileMode] = useState<"saved" | "editing" | "new">("new");
  const [profileLoaded, setProfileLoaded] = useState(false);

  // Tag-style service input
  const [serviceInput, setServiceInput] = useState("");
  const [serviceTags, setServiceTags] = useState<string[]>([]);

  // ── Prospect queue ────────────────────────────────────────────────────────
  const [prospects, setProspects] = useState<ProspectRow[]>([makeProspect()]);
  const [selectedId, setSelectedId] = useState<string>(() => "");
  const [runAllActive, setRunAllActive] = useState(false);

  const [verifyOpen, setVerifyOpen] = useState(false);
  const [pipelineCollapsed, setPipelineCollapsed] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  // Knowledge panel state
  const [knowledgeDocCount, setKnowledgeDocCount] = useState(0);
  const [knowledgeDocs, setKnowledgeDocs] = useState<{ file_id: string; file_name: string; mime_type: string; chunk_count: number }[]>([]);
  const [knowledgeSyncing, setKnowledgeSyncing] = useState(false);
  const [knowledgeDeletingId, setKnowledgeDeletingId] = useState<string | null>(null);
  const [knowledgeMsg, setKnowledgeMsg] = useState("");
  const [knowledgeOpen, setKnowledgeOpen] = useState(false);

  // Load saved profile on mount
  useEffect(() => {
    const p = loadSavedProfile();
    if (p) {
      setSavedProfile(p);
      setSenderForm(p);
      setProfileMode("saved");
      if (p.services) setServiceTags(p.services.split(",").map(s => s.trim()).filter(s => s && s !== "[object Object]"));
    }
    setProfileLoaded(true);
  }, []);

  // Select first prospect by default once mounted
  useEffect(() => {
    setSelectedId(prev => prev || prospects[0]?.id || "");
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const refreshKnowledge = useCallback(() => {
    fetch(`${API}/knowledge/status`)
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d) setKnowledgeDocCount(d.doc_count || 0); })
      .catch(() => {});
    fetch(`${API}/knowledge/docs`)
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d) setKnowledgeDocs(d.docs || []); })
      .catch(() => {});
  }, []);

  // Load knowledge status + docs on mount
  useEffect(() => { refreshKnowledge(); }, [refreshKnowledge]);

  const updateSender = (field: keyof SenderProfile, value: string) =>
    setSenderForm(prev => ({ ...prev, [field]: value }));

  const addServiceTag = (tag: string) => {
    const trimmed = tag.trim();
    if (!trimmed || serviceTags.includes(trimmed)) return;
    const next = [...serviceTags, trimmed];
    setServiceTags(next);
    setSenderForm(prev => ({ ...prev, services: next.join(", ") }));
    setServiceInput("");
  };

  const removeServiceTag = (tag: string) => {
    const next = serviceTags.filter(t => t !== tag);
    setServiceTags(next);
    setSenderForm(prev => ({ ...prev, services: next.join(", ") }));
  };

  const handleSaveProfile = () => {
    saveProfile(senderForm);
    setSavedProfile(senderForm);
    setProfileMode("saved");
  };

  const handleClearProfile = () => {
    try { localStorage.removeItem(PROFILE_KEY); } catch { /* noop */ }
    setSavedProfile(null);
    setSenderForm({ ...BLANK_PROFILE });
    setServiceTags([]);
    setProfileMode("new");
  };

  // ── Prospect queue helpers ────────────────────────────────────────────────
  const addProspect = () => {
    const p = makeProspect();
    setProspects(prev => [...prev, p]);
    setSelectedId(p.id);
  };

  const removeProspect = (id: string) => {
    setProspects(prev => {
      const next = prev.filter(p => p.id !== id);
      return next.length ? next : [makeProspect()];
    });
    setSelectedId(prev => {
      if (prev !== id) return prev;
      const remaining = prospects.filter(p => p.id !== id);
      return remaining[0]?.id || "";
    });
  };

  const updateProspect = (id: string, field: keyof Pick<ProspectRow, "linkedin_url" | "company_website" | "company_linkedin_url">, value: string) => {
    setProspects(prev => prev.map(p => p.id === id ? { ...p, [field]: value } : p));
  };

  const selectedProspect = prospects.find(p => p.id === selectedId) || prospects[0] || null;

  const openKnowledgePicker = useCallback(async () => {
    setKnowledgeSyncing(true);
    setKnowledgeMsg("Loading Google APIs...");
    try {
      // Load Google Identity and Picker scripts
      await Promise.all([
        new Promise<void>(resolve => {
          if ((window as any).google?.accounts) { resolve(); return; }
          const s = document.createElement("script");
          s.src = "https://accounts.google.com/gsi/client";
          s.onload = () => resolve();
          document.head.appendChild(s);
        }),
        new Promise<void>(resolve => {
          if ((window as any).gapi) { resolve(); return; }
          const s = document.createElement("script");
          s.src = "https://apis.google.com/js/api.js";
          s.onload = () => resolve();
          document.head.appendChild(s);
        }),
      ]);

      // Get status for client_id
      const statusRes = await fetch(`${API}/knowledge/status`);
      const statusData = statusRes.ok ? await statusRes.json() : {};
      const clientId = statusData.google_client_id || "";
      if (!clientId) { setKnowledgeMsg("GOOGLE_CLIENT_ID not configured"); setKnowledgeSyncing(false); return; }

      setKnowledgeMsg("Authorizing with Google...");

      const tokenClient = (window as any).google.accounts.oauth2.initTokenClient({
        client_id: clientId,
        scope: "https://www.googleapis.com/auth/drive.readonly",
        callback: (tokenResponse: any) => {
          if (tokenResponse.error) { setKnowledgeMsg("Auth failed: " + tokenResponse.error); setKnowledgeSyncing(false); return; }
          const accessToken = tokenResponse.access_token;
          setKnowledgeMsg("Opening file picker...");

          (window as any).gapi.load("picker", () => {
            const picker = new (window as any).google.picker.PickerBuilder()
              .addView(new (window as any).google.picker.DocsView()
                .setIncludeFolders(false)
                .setSelectFolderEnabled(false))
              .setOAuthToken(accessToken)
              .enableFeature((window as any).google.picker.Feature.MULTISELECT_ENABLED)
              .setCallback(async (data: any) => {
                if (data.action !== (window as any).google.picker.Action.PICKED) {
                  if (data.action === (window as any).google.picker.Action.CANCEL) {
                    setKnowledgeMsg(""); setKnowledgeSyncing(false);
                  }
                  return;
                }
                const files = data.docs.map((d: any) => ({ id: d.id, name: d.name, mimeType: d.mimeType }));
                setKnowledgeMsg(`Syncing ${files.length} file(s)...`);
                try {
                  const res = await fetch(`${API}/knowledge/files`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ files, access_token: accessToken }),
                  });
                  if (res.ok) {
                    setKnowledgeMsg(`✓ Syncing ${files.length} file(s) in background`);
                    setTimeout(() => {
                      refreshKnowledge();
                      setKnowledgeMsg("");
                    }, 8000);
                  } else {
                    setKnowledgeMsg("Sync failed — check backend logs");
                  }
                } catch { setKnowledgeMsg("Network error"); }
                setKnowledgeSyncing(false);
              })
              .build();
            picker.setVisible(true);
          });
        },
      });
      tokenClient.requestAccessToken();
    } catch (err: any) {
      setKnowledgeMsg("Error: " + (err?.message || "unknown"));
      setKnowledgeSyncing(false);
    }
  }, [refreshKnowledge]);

  // ── Run a single prospect ─────────────────────────────────────────────────
  const runProspect = useCallback(async (prospectId: string) => {
    const prospect = prospects.find(p => p.id === prospectId);
    if (!prospect || prospect.status === "running") return;

    // Save profile on first run
    saveProfile(senderForm);
    setSavedProfile(senderForm);

    // Reset this prospect's state
    setProspects(prev => prev.map(p => p.id === prospectId
      ? { ...p, status: "running", result: null, duration_ms: null, agents: PIPELINE_STAGES.map(a => ({ ...a })) }
      : p
    ));
    setSelectedId(prospectId);
    setPipelineCollapsed(false);

    // Animate pipeline stages for this prospect
    const stageCount = PIPELINE_STAGES.length;
    const timers: ReturnType<typeof setTimeout>[] = [];
    for (let i = 0; i < stageCount; i++) {
      timers.push(setTimeout(() => {
        setProspects(prev => prev.map(p => p.id !== prospectId ? p : {
          ...p,
          agents: p.agents.map((a, idx) => {
            if (idx === i) return { ...a, status: "running" as const };
            if (idx < i) return { ...a, status: "completed" as const, durationMs: 5000 + Math.random() * 5000 };
            return a;
          }),
        }));
      }, i * 8000));
    }

    try {
      const input = isSales ? {
        linkedin_url: prospect.linkedin_url,
        company_website: prospect.company_website,
        company_linkedin_url: prospect.company_linkedin_url,
        service_catalog: serviceTags.map(s => ({ name: s })),
        sender_name: senderForm.sender_name,
        sender_company: senderForm.sender_company,
        sender_role: senderForm.sender_role,
        value_proposition: senderForm.value_proposition,
        target_pain_points: senderForm.target_pain_points,
        ideal_outcome: senderForm.ideal_outcome,
        email_tone: senderForm.email_tone,
        case_studies: senderForm.case_studies,
        cta_preference: senderForm.cta_preference,
      } : {};

      const res = await fetch(`${API}/flow/${name}/invoke`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(input),
      });
      const data = await res.json();
      timers.forEach(clearTimeout);
      setProspects(prev => prev.map(p => p.id !== prospectId ? p : {
        ...p,
        status: "completed",
        result: data.output || {},
        duration_ms: data.duration_ms || null,
        agents: p.agents.map(a => ({ ...a, status: "completed" as const, durationMs: (data.duration_ms || 60000) / p.agents.length })),
      }));
      setTimeout(() => setPipelineCollapsed(true), 1800);
    } catch {
      timers.forEach(clearTimeout);
      setProspects(prev => prev.map(p => p.id !== prospectId ? p : {
        ...p,
        status: "failed",
        agents: p.agents.map(a => a.status === "running" ? { ...a, status: "failed" as const } : a),
      }));
    }
  }, [prospects, senderForm, serviceTags, isSales, name]);

  // ── Run all idle/failed prospects with concurrency limit ──────────────────
  const runAll = useCallback(async () => {
    const targets = prospects.filter(p => p.status === "idle" || p.status === "failed");
    if (!targets.length || runAllActive) return;
    setRunAllActive(true);

    let idx = 0;
    let active = 0;

    await new Promise<void>(resolve => {
      const tryNext = () => {
        while (active < CONCURRENCY && idx < targets.length) {
          const prospect = targets[idx++];
          active++;
          // Stagger starts
          const delay = (idx - 1) * STAGGER_MS;
          setTimeout(() => {
            runProspect(prospect.id).finally(() => {
              active--;
              if (idx < targets.length) tryNext();
              else if (active === 0) resolve();
            });
          }, delay);
        }
        if (idx >= targets.length && active === 0) resolve();
      };
      tryNext();
    });

    setRunAllActive(false);
  }, [prospects, runAllActive, runProspect]);

  // Only name + company are required — value prop/services come from docs if synced
  const hasKnowledgeDocs = knowledgeDocCount > 0;
  const profileIsComplete = Boolean(senderForm.sender_name && senderForm.sender_company);

  return (
    <div className="flex h-[calc(100vh-56px)] overflow-hidden">

      {/* ── Left Panel — click to open/close ────────────────────────────────── */}
      <aside className={`relative z-30 flex-shrink-0 transition-[width] duration-300 ease-in-out bg-surface-low border-r border-outline/10 flex flex-col overflow-hidden ${sidebarOpen ? "w-[420px]" : "w-12"}`}>

        {/* Collapsed strip — click to open */}
        {!sidebarOpen && (
          <button
            onClick={() => setSidebarOpen(true)}
            className="absolute inset-0 w-12 flex flex-col items-center justify-center gap-4 hover:bg-surface-high/20 transition-colors"
          >
            <div className="w-1 h-16 rounded-full bg-accent/20" />
            <svg className="w-4 h-4 text-muted/40" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
            </svg>
            <div className="w-1 h-16 rounded-full bg-accent/20" />
          </button>
        )}

        {/* Expanded content */}
        <div className={`w-[420px] flex flex-col flex-1 overflow-y-auto overflow-x-hidden transition-opacity duration-200 ${sidebarOpen ? "opacity-100" : "opacity-0 pointer-events-none"}`}>

        {/* Close button */}
        <div className="flex items-center justify-between px-8 pt-6 pb-2 shrink-0">
          <span className="text-[0.6rem] font-black uppercase tracking-widest text-muted/40">Configuration</span>
          <button
            onClick={() => setSidebarOpen(false)}
            className="w-7 h-7 flex items-center justify-center rounded-lg border border-outline/20 text-muted/50 hover:text-foreground hover:border-outline/50 transition-colors"
            title="Collapse sidebar"
          >
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
            </svg>
          </button>
        </div>

        <div className="px-8 pt-4 pb-6">

          {/* Saved profile identity card */}
          {profileLoaded && savedProfile && profileMode === "saved" && (
            <div
              onClick={() => setProfileMode("editing")}
              className="bg-surface-high/40 border border-outline/20 rounded-xl p-5 flex items-center gap-4 hover:bg-surface-high/60 cursor-pointer group mb-6 transition-all"
            >
              <div className="w-11 h-11 rounded-lg bg-accent/20 border border-accent/20 flex items-center justify-center text-lg font-black text-accent-dim shrink-0">
                {savedProfile.sender_name.charAt(0).toUpperCase()}
              </div>
              <div className="flex-1 min-w-0">
                <p className="font-bold text-sm truncate">{savedProfile.sender_name}</p>
                <p className="text-[0.6875rem] text-accent/70 font-bold uppercase tracking-widest truncate">
                  {savedProfile.sender_role} @ {savedProfile.sender_company}
                </p>
              </div>
              <div className="flex gap-2 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
                <button
                  onClick={e => { e.stopPropagation(); setProfileMode("editing"); }}
                  className="text-[0.6rem] px-2 py-1 rounded border border-outline/30 text-muted hover:text-foreground transition-colors uppercase tracking-wide font-bold"
                >
                  Edit
                </button>
                <button
                  onClick={e => { e.stopPropagation(); handleClearProfile(); }}
                  className="text-[0.6rem] px-2 py-1 rounded border border-error/30 text-error/70 hover:text-error transition-colors uppercase tracking-wide font-bold"
                >
                  Clear
                </button>
              </div>
            </div>
          )}

          {/* Prospect Queue */}
          <section className="mb-6">
            <div className="flex items-center justify-between mb-4">
              <label className="block text-[0.6rem] uppercase tracking-widest text-muted font-bold">
                Prospects <span className="text-accent/70">({prospects.length})</span>
              </label>
              <button
                onClick={addProspect}
                className="text-[0.6rem] px-2 py-1 rounded border border-accent/30 text-accent hover:bg-accent/10 transition-colors font-bold uppercase tracking-wide"
              >
                + Add
              </button>
            </div>

            <div className="space-y-2">
              {prospects.map((prospect, idx) => {
                const isSelected = prospect.id === selectedId;
                const statusColor =
                  prospect.status === "completed" ? "text-secondary border-secondary/30 bg-secondary/5"
                  : prospect.status === "running"  ? "text-accent border-accent/30 bg-accent/5"
                  : prospect.status === "failed"   ? "text-error border-error/30 bg-error/5"
                  : "text-muted/40 border-outline/15 bg-card/30";

                return (
                  <div
                    key={prospect.id}
                    onClick={() => setSelectedId(prospect.id)}
                    className={`rounded-xl border p-3 cursor-pointer transition-all group/prospect ${
                      isSelected ? "border-accent/40 bg-accent/5" : "border-outline/15 bg-card/30 hover:border-outline/30"
                    }`}
                  >
                    {/* Row header */}
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-1.5">
                        <span className="text-[0.5rem] font-black text-muted/40 uppercase">#{idx + 1}</span>
                        <span className={`text-[0.45rem] font-bold uppercase tracking-wide px-1.5 py-0.5 rounded-full border ${statusColor}`}>
                          {prospect.status === "running" ? (
                            <span className="flex items-center gap-1">
                              <span className="w-1 h-1 rounded-full bg-accent animate-pulse inline-block" />
                              running
                            </span>
                          ) : prospect.status}
                        </span>
                        {prospect.duration_ms && (
                          <span className="text-[0.45rem] font-mono text-secondary/60">{(prospect.duration_ms / 1000).toFixed(1)}s</span>
                        )}
                      </div>
                      <div className="flex items-center gap-1 opacity-0 group-hover/prospect:opacity-100 transition-opacity">
                        {(prospect.status === "idle" || prospect.status === "failed") && (
                          <button
                            onClick={e => { e.stopPropagation(); runProspect(prospect.id); }}
                            className="text-[0.5rem] px-1.5 py-0.5 rounded bg-accent/20 text-accent hover:bg-accent/30 transition-colors font-bold"
                            title="Run this prospect"
                          >
                            ▶
                          </button>
                        )}
                        {prospects.length > 1 && (
                          <button
                            onClick={e => { e.stopPropagation(); removeProspect(prospect.id); }}
                            className="text-[0.5rem] px-1.5 py-0.5 rounded bg-error/10 text-error/70 hover:bg-error/20 transition-colors font-bold"
                            title="Remove"
                          >
                            ✕
                          </button>
                        )}
                      </div>
                    </div>

                    {/* Fields — only show when selected */}
                    {isSelected && (
                      <div className="space-y-2 mt-2" onClick={e => e.stopPropagation()}>
                        <CockpitInput
                          placeholder="https://linkedin.com/in/..."
                          label="LinkedIn"
                          value={prospect.linkedin_url}
                          onChange={v => updateProspect(prospect.id, "linkedin_url", v)}
                        />
                        <CockpitInput
                          placeholder="https://company.com"
                          label="Website"
                          value={prospect.company_website}
                          onChange={v => updateProspect(prospect.id, "company_website", v)}
                        />
                        <CockpitInput
                          placeholder="linkedin.com/company/..."
                          label="Co. LinkedIn"
                          value={prospect.company_linkedin_url}
                          onChange={v => updateProspect(prospect.id, "company_linkedin_url", v)}
                        />
                      </div>
                    )}

                    {/* Collapsed summary */}
                    {!isSelected && prospect.linkedin_url && (
                      <p className="text-[0.5rem] text-muted/50 truncate mt-1">{prospect.linkedin_url}</p>
                    )}
                    {!isSelected && !prospect.linkedin_url && (
                      <p className="text-[0.5rem] text-muted/30 italic">No URL set</p>
                    )}
                  </div>
                );
              })}
            </div>
          </section>

          {/* Your Profile */}
          {(profileMode === "editing" || profileMode === "new") && (
            <>
              <section className="mb-6">
                <div className="flex items-center justify-between mb-4">
                  <label className="block text-[0.6rem] uppercase tracking-widest text-muted font-bold">
                    Your Profile Context
                  </label>
                  {profileMode === "editing" && (
                    <button
                      onClick={() => setProfileMode("saved")}
                      className="text-[0.6rem] text-muted hover:text-foreground transition-colors uppercase tracking-wide"
                    >
                      ← Back
                    </button>
                  )}
                </div>
                <div className="bg-surface-high/20 rounded-xl p-4 space-y-3">
                  <CockpitInput placeholder="Your Name" label="Name" value={senderForm.sender_name} onChange={v => updateSender("sender_name", v)} />
                  <CockpitInput placeholder="Your Company" label="Company" value={senderForm.sender_company} onChange={v => updateSender("sender_company", v)} />
                  <CockpitInput placeholder="Founder / Sales / CTO" label="Role" value={senderForm.sender_role} onChange={v => updateSender("sender_role", v)} />
                </div>
              </section>

              {/* Service Catalog — hidden when docs cover it */}
              {!hasKnowledgeDocs && (
                <section className="mb-6">
                  <label className="block text-[0.6rem] uppercase tracking-widest text-muted font-bold mb-4">
                    Service Catalog
                  </label>
                  <div className="flex flex-wrap gap-2 mb-3">
                    {serviceTags.map(tag => (
                      <ServiceTag
                        key={tag}
                        label={tag}
                        selected
                        onClick={() => removeServiceTag(tag)}
                      />
                    ))}
                  </div>
                  <div className="flex gap-2">
                    <input
                      value={serviceInput}
                      onChange={e => setServiceInput(e.target.value)}
                      onKeyDown={e => {
                        if (e.key === "Enter" || e.key === ",") {
                          e.preventDefault();
                          addServiceTag(serviceInput);
                        }
                      }}
                      placeholder="Add service, press Enter"
                      className="flex-1 bg-surface-high/30 border-none rounded-lg px-3 py-2 text-xs text-foreground placeholder:text-muted/50 focus:outline-none focus:ring-1 focus:ring-accent/30"
                    />
                    <button
                      onClick={() => addServiceTag(serviceInput)}
                      className="px-3 py-2 rounded-lg bg-accent/20 text-accent text-xs font-bold hover:bg-accent/30 transition-colors"
                    >
                      +
                    </button>
                  </div>
                </section>
              )}

              <section className="mb-6">
                <div className="flex items-center justify-between mb-4">
                  <label className="block text-[0.6rem] uppercase tracking-widest text-muted font-bold">
                    Targeting Brief
                  </label>
                  {hasKnowledgeDocs && (
                    <span className="text-[0.5rem] px-2 py-0.5 rounded-full bg-secondary/15 text-secondary font-bold uppercase tracking-wide">
                      ✓ from docs
                    </span>
                  )}
                </div>

                {/* If docs synced — just show tone/CTA, brief note */}
                {hasKnowledgeDocs ? (
                  <div className="space-y-3">
                    <div className="rounded-lg bg-secondary/5 border border-secondary/15 px-3 py-2.5">
                      <p className="text-[0.55rem] text-secondary/70 leading-relaxed">
                        Services, value proposition, case studies and pain points are pulled automatically from your synced company docs.
                      </p>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                      <CockpitSelect
                        label="Tone"
                        value={senderForm.email_tone}
                        onChange={v => updateSender("email_tone", v)}
                        options={[
                          { value: "professional", label: "Professional" },
                          { value: "casual", label: "Casual" },
                          { value: "technical", label: "Technical" },
                          { value: "founder", label: "Founder" },
                        ]}
                      />
                      <CockpitSelect
                        label="CTA"
                        value={senderForm.cta_preference}
                        onChange={v => updateSender("cta_preference", v)}
                        options={[
                          { value: "soft", label: "Soft" },
                          { value: "direct", label: "Direct" },
                          { value: "question", label: "Question" },
                        ]}
                      />
                    </div>
                  </div>
                ) : (
                  <div className="space-y-3">
                    <CockpitTextarea
                      placeholder="Value proposition — what do you offer and why does it matter?"
                      label="Value Prop"
                      value={senderForm.value_proposition}
                      onChange={v => updateSender("value_proposition", v)}
                      rows={3}
                    />
                    <CockpitTextarea
                      placeholder="Pain points you solve"
                      label="Pain Points"
                      value={senderForm.target_pain_points}
                      onChange={v => updateSender("target_pain_points", v)}
                      rows={2}
                    />
                    <CockpitTextarea
                      placeholder="Case studies or social proof"
                      label="Proof"
                      value={senderForm.case_studies}
                      onChange={v => updateSender("case_studies", v)}
                      rows={2}
                    />
                    <div className="grid grid-cols-2 gap-3">
                      <CockpitSelect
                        label="Tone"
                        value={senderForm.email_tone}
                        onChange={v => updateSender("email_tone", v)}
                        options={[
                          { value: "professional", label: "Professional" },
                          { value: "casual", label: "Casual" },
                          { value: "technical", label: "Technical" },
                          { value: "founder", label: "Founder" },
                        ]}
                      />
                      <CockpitSelect
                        label="CTA"
                        value={senderForm.cta_preference}
                        onChange={v => updateSender("cta_preference", v)}
                        options={[
                          { value: "soft", label: "Soft" },
                          { value: "direct", label: "Direct" },
                          { value: "question", label: "Question" },
                        ]}
                      />
                    </div>
                  </div>
                )}
              </section>

              {profileIsComplete && (
                <button
                  onClick={handleSaveProfile}
                  className="w-full py-2 rounded-lg text-[0.625rem] font-bold uppercase tracking-widest border border-accent/30 text-accent hover:bg-accent/10 transition-colors mb-4"
                >
                  {savedProfile ? "Update Profile" : "Save Profile"}
                </button>
              )}
            </>
          )}
        </div>

        {/* ── Company Knowledge ────────────────────────────────────────────── */}
        <div className="px-8 pb-4">
          <div className="border border-outline/15 rounded-xl overflow-hidden bg-card/40">
            {/* Header row — always visible, toggles collapse */}
            <button
              onClick={() => setKnowledgeOpen(o => !o)}
              className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-surface-high/30 transition-colors"
            >
              <div className="flex items-center gap-2">
                <svg className="w-3.5 h-3.5 text-accent/70 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
                <span className="text-[0.6rem] font-bold uppercase tracking-widest text-muted">Company Knowledge</span>
              </div>
              <div className="flex items-center gap-2">
                {knowledgeDocCount > 0 && (
                  <span className="text-[0.5rem] font-bold px-1.5 py-0.5 rounded-full bg-secondary/15 text-secondary">{knowledgeDocCount} docs</span>
                )}
                <svg className={`w-3 h-3 text-muted/40 transition-transform duration-200 ${knowledgeOpen ? "rotate-180" : ""}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
                </svg>
              </div>
            </button>

            {/* Collapsible body */}
            {knowledgeOpen && (
              <div className="border-t border-outline/10">

                {/* File list */}
                {knowledgeDocs.length > 0 && (
                  <div className="px-4 pt-3 space-y-1.5">
                    {knowledgeDocs.map(doc => {
                      const icon = doc.mime_type.includes("pdf") ? "📕"
                        : doc.mime_type.includes("presentation") || doc.mime_type.includes("slide") ? "📊"
                        : doc.mime_type.includes("spreadsheet") || doc.mime_type.includes("sheet") ? "📋"
                        : "📄";
                      return (
                        <div key={doc.file_id} className="flex items-center gap-2 group/kfile rounded-lg px-2 py-1.5 hover:bg-surface-high/30 transition-colors">
                          <span className="text-[0.65rem] flex-shrink-0">{icon}</span>
                          <div className="flex-1 min-w-0">
                            <p className="text-[0.55rem] font-medium text-foreground/80 truncate">{doc.file_name}</p>
                            <p className="text-[0.45rem] text-muted/40">{doc.chunk_count} chunks</p>
                          </div>
                          <button
                            onClick={async () => {
                              if (!confirm(`Remove "${doc.file_name}"?`)) return;
                              setKnowledgeDeletingId(doc.file_id);
                              try {
                                const res = await fetch(`${API}/knowledge/files/${doc.file_id}`, { method: "DELETE" });
                                if (res.ok) {
                                  setKnowledgeDocs(prev => prev.filter(d => d.file_id !== doc.file_id));
                                  setKnowledgeDocCount(prev => Math.max(0, prev - 1));
                                }
                              } catch {}
                              setKnowledgeDeletingId(null);
                            }}
                            disabled={knowledgeDeletingId === doc.file_id}
                            className="flex-shrink-0 opacity-0 group-hover/kfile:opacity-100 transition-opacity w-5 h-5 flex items-center justify-center rounded text-error/50 hover:text-error hover:bg-error/10 text-[0.6rem] font-bold disabled:opacity-30"
                            title="Remove file"
                          >
                            {knowledgeDeletingId === doc.file_id ? "…" : "✕"}
                          </button>
                        </div>
                      );
                    })}
                  </div>
                )}

                {/* Empty state */}
                {knowledgeDocs.length === 0 && !knowledgeSyncing && (
                  <p className="text-[0.55rem] text-muted/40 italic text-center py-3 px-4">
                    No docs synced yet
                  </p>
                )}

                {/* Add / status */}
                <div className="px-4 pb-4 pt-3">
                  <button
                    onClick={openKnowledgePicker}
                    disabled={knowledgeSyncing}
                    className="w-full py-2 rounded-lg text-[0.625rem] font-bold uppercase tracking-widest bg-accent/15 text-accent hover:bg-accent/25 transition-colors disabled:opacity-50 disabled:cursor-wait"
                  >
                    {knowledgeSyncing ? "Working..." : knowledgeDocs.length > 0 ? "+ Add More Files" : "Select Drive Files"}
                  </button>
                  {knowledgeMsg && (
                    <p className={`text-[0.55rem] mt-2 text-center ${knowledgeMsg.startsWith("✓") ? "text-secondary" : "text-muted/60"}`}>
                      {knowledgeMsg}
                    </p>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Sticky Run Buttons */}
        <div className="mt-auto px-8 pb-8 pt-4 border-t border-outline/10 space-y-2">
          {/* Progress summary */}
          {prospects.some(p => p.status !== "idle") && (
            <div className="flex items-center justify-between text-[0.6rem] text-muted mb-1">
              <span className="uppercase tracking-widest">
                {prospects.filter(p => p.status === "completed").length}/{prospects.length} done
              </span>
              <span className="text-secondary font-bold">
                {prospects.filter(p => p.status === "running").length > 0
                  ? `${prospects.filter(p => p.status === "running").length} running`
                  : prospects.filter(p => p.status === "failed").length > 0
                  ? `${prospects.filter(p => p.status === "failed").length} failed`
                  : ""}
              </span>
            </div>
          )}

          {/* Run All */}
          <button
            onClick={runAll}
            disabled={runAllActive || prospects.every(p => p.status === "running" || p.status === "completed")}
            className={`w-full py-3.5 rounded-xl text-xs font-black uppercase tracking-widest transition-all active:scale-[0.98] ${
              runAllActive
                ? "bg-accent/20 text-accent cursor-wait"
                : "bg-accent text-white hover:bg-accent/90 shadow-[0_0_20px_rgba(128,131,255,0.25)]"
            }`}
          >
            {runAllActive ? (
              <span className="flex items-center justify-center gap-2">
                <svg className="w-3.5 h-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                Running {prospects.filter(p => p.status === "running").length} / {CONCURRENCY} concurrent...
              </span>
            ) : (
              prospects.length === 1 ? "Run Pipeline →" : `Run All ${prospects.length} →`
            )}
          </button>

          {/* Reset idle button — shown after some are done */}
          {prospects.some(p => p.status === "completed" || p.status === "failed") && (
            <button
              onClick={() => setProspects(prev => prev.map(p => ({ ...p, status: "idle" as const, result: null, duration_ms: null, agents: PIPELINE_STAGES.map(a => ({ ...a })) })))}
              className="w-full py-2 rounded-xl text-[0.6rem] font-bold uppercase tracking-widest border border-outline/20 text-muted hover:text-foreground hover:border-outline/40 transition-colors"
            >
              Reset All
            </button>
          )}
        </div>
        </div>{/* end expanded content */}
      </aside>

      {/* ── Right Output Canvas — full remaining space ─────────────────────── */}
      <div className="flex-1 flex flex-col overflow-hidden relative">

        {/* ── Prospect result tabs (shown when any prospect has a result) ── */}
        {prospects.some(p => p.result || p.status === "running") && (
          <div className="shrink-0 flex items-center gap-1 px-4 pt-3 pb-0 overflow-x-auto border-b border-outline/10 bg-surface-low/50">
            {prospects
              .filter(p => p.result || p.status === "running" || p.status === "failed")
              .map((p, idx) => {
                const name = (p.result as any)?.linkedin_parsed?.name
                  || (p.result as any)?.persona?.name
                  || p.linkedin_url.split("/in/")[1]?.replace(/\/$/, "")
                  || `Prospect ${idx + 1}`;
                const isSelected = p.id === selectedId;
                const dotColor = p.status === "completed" ? "bg-secondary" : p.status === "running" ? "bg-accent animate-pulse" : "bg-error";
                return (
                  <button
                    key={p.id}
                    onClick={() => setSelectedId(p.id)}
                    className={`shrink-0 flex items-center gap-1.5 px-3 py-2 rounded-t-lg text-[0.6rem] font-bold uppercase tracking-wide transition-colors border-b-2 ${
                      isSelected
                        ? "text-foreground border-accent bg-surface-high/50"
                        : "text-muted/50 border-transparent hover:text-muted hover:bg-surface-high/20"
                    }`}
                  >
                    <span className={`w-1.5 h-1.5 rounded-full ${dotColor}`} />
                    {name.length > 16 ? name.slice(0, 16) + "…" : name}
                  </button>
                );
              })}
          </div>
        )}

        {/* ── Phase: idle — full-screen pipeline placeholder ── */}
        {selectedProspect?.status === "idle" && (
          <div className="flex-1 flex flex-col items-center justify-center gap-8 px-12">
            <PipelineTimeline steps={selectedProspect.agents} fullscreen />
            <div className="w-full max-w-lg space-y-3 mt-2 opacity-40">
              {["Generated Email", "Persona Analysis", "Research Intelligence"].map(s => (
                <div key={s} className="rounded-xl border border-dashed border-outline/20 p-5">
                  <div className="text-[0.6rem] uppercase tracking-widest text-muted/30 font-bold">{s}</div>
                  <div className="mt-3 space-y-2">
                    <div className="h-2 w-3/4 bg-surface-high/50 rounded" />
                    <div className="h-2 w-1/2 bg-surface-high/50 rounded" />
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ── Phase: running — full-screen pipeline ── */}
        {selectedProspect?.status === "running" && !selectedProspect.result && (
          <div className="flex-1 flex flex-col items-center justify-center px-12">
            <PipelineTimeline steps={selectedProspect.agents} fullscreen />
          </div>
        )}

        {/* ── Phase: failed ── */}
        {selectedProspect?.status === "failed" && !selectedProspect.result && (
          <div className="flex-1 flex flex-col items-center justify-center gap-4 px-12">
            <PipelineTimeline steps={selectedProspect.agents} fullscreen />
            <div className="text-[0.7rem] text-error/70 font-bold uppercase tracking-widest">Pipeline failed — check backend logs</div>
            <button
              onClick={() => runProspect(selectedProspect.id)}
              className="px-4 py-2 rounded-lg bg-accent/20 text-accent text-xs font-bold hover:bg-accent/30 transition-colors"
            >
              Retry
            </button>
          </div>
        )}

        {/* ── Phase: done — pipeline slides out, canvas takes over ── */}
        {selectedProspect?.result && (
          <div className="flex-1 flex flex-col overflow-hidden min-h-0">
            <div
              className="shrink-0 overflow-hidden transition-all duration-700 ease-in-out"
              style={{
                maxHeight: pipelineCollapsed ? "0px" : "120px",
                opacity: pipelineCollapsed ? 0 : 1,
                transform: pipelineCollapsed ? "translateY(-100%)" : "translateY(0)",
              }}
            >
              <PipelineTimeline steps={selectedProspect.agents} />
            </div>
            <div className="flex-1 flex flex-col overflow-hidden min-h-0">
              <OutputCanvas output={selectedProspect.result} running={false} onVerify={() => setVerifyOpen(true)} />
            </div>
          </div>
        )}
      </div>

      {/* Research Verification Drawer */}
      {selectedProspect?.result && (
        <ResearchChatDrawer
          open={verifyOpen}
          onClose={() => setVerifyOpen(false)}
          researchContext={selectedProspect.result}
        />
      )}
    </div>
  );
}

// ── Cockpit Form Primitives ───────────────────────────────────────────────────

function CockpitInput({
  label, placeholder, value, onChange,
}: {
  label: string; placeholder: string; value: string; onChange: (v: string) => void;
}) {
  return (
    <div className="relative">
      <input
        value={value}
        onChange={e => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full bg-card/60 border-none rounded-xl px-4 py-3 pr-16 text-xs text-foreground placeholder:text-muted/40 focus:outline-none focus:ring-1 focus:ring-accent/30 transition-all"
      />
      <span className="absolute right-3 top-3 text-[0.55rem] text-accent/40 font-bold uppercase tracking-widest">
        {label}
      </span>
    </div>
  );
}

function CockpitTextarea({
  label, placeholder, value, onChange, rows = 3,
}: {
  label: string; placeholder: string; value: string; onChange: (v: string) => void; rows?: number;
}) {
  return (
    <div className="relative">
      <textarea
        value={value}
        onChange={e => onChange(e.target.value)}
        placeholder={placeholder}
        rows={rows}
        className="w-full bg-card/60 border-none rounded-xl px-4 py-3 text-xs text-foreground placeholder:text-muted/40 focus:outline-none focus:ring-1 focus:ring-accent/30 resize-none transition-all"
      />
      <span className="absolute right-3 top-3 text-[0.55rem] text-accent/40 font-bold uppercase tracking-widest">
        {label}
      </span>
    </div>
  );
}

function CockpitSelect({
  label, value, onChange, options,
}: {
  label: string; value: string; onChange: (v: string) => void;
  options: { value: string; label: string }[];
}) {
  return (
    <div>
      <label className="block text-[0.55rem] uppercase tracking-widest text-muted font-bold mb-1.5">{label}</label>
      <select
        value={value}
        onChange={e => onChange(e.target.value)}
        className="w-full bg-card/60 border-none rounded-lg px-3 py-2 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-accent/30"
      >
        {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </div>
  );
}
