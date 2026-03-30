"use client";

import { type ReactNode } from "react";

/* ── Types ─────────────────────────────────────────────────────────────────── */

interface PersonaCardProps {
  persona: Record<string, unknown> | undefined;
  confidence?: number;
  communicationStyle?: string;
}

interface IdentitySnapshot {
  name: string;
  title: string;
  company: string;
  seniority: string;
  decisionAuthority: string;
  yearsInRole: string;
  totalExperience: string;
  trajectory: string;
}

interface Motivation {
  text: string;
  evidence: string;
  confidence: string;
}

interface PainPoint {
  description: string;
  evidence: string;
  confidence: string;
  solutionConnection: string;
}

interface TopicToAvoid {
  topic: string;
  reason: string;
  confidence: string;
}

interface ParsedPersona {
  identity: IdentitySnapshot | null;
  careerStory: string;
  keyTransitions: string;
  skillsExpertise: string;
  notableAchievements: string;
  company: {
    name: string; size: string; industry: string; stage: string;
    recentNews: string; roleInOrg: string; visibleChallenges: string;
  } | null;
  motivations: Motivation[];
  riskTolerance: string;
  values: string[];
  decisionStyle: string;
  painPoints: PainPoint[];
  writingStyle: string;
  emojiUsage: string;
  postLength: string;
  engagementTopics: string[];
  tone: string;
  bestChannel: string;
  openingAngle: string;
  topicsToAvoid: TopicToAvoid[];
  idealTiming: string;
  recommendedApproach: string;
  specificReference: string;
  connectionCount: string;
  followerCount: string;
  mutualConnections: string[];
  warmIntroSuggestion: string;
  influenceLevel: string;
  personaConfidence: number | null;
  dataGaps: string[];
  confidenceBreakdown: string[];
}

/* ── Main Component ─────────────────────────────────────────────────────────── */

export default function PersonaCard({ persona, confidence, communicationStyle }: PersonaCardProps) {
  if (!persona) {
    return (
      <div className="rounded-lg border border-card-border bg-card p-6 text-center text-sm text-muted">
        No persona data available. Run the pipeline first.
      </div>
    );
  }

  const parsed = parsePersona(persona);
  const displayConfidence = parsed.personaConfidence != null
    ? Math.round(parsed.personaConfidence * 100)
    : confidence != null ? Math.round(confidence * 100) : null;

  return (
    <div className="space-y-5">

      {/* ── Top bar ─────────────────────────────────────────────────────── */}
      <div className="flex items-center gap-3 flex-wrap">
        {displayConfidence != null && <ConfidenceMeter value={displayConfidence} label="Persona Confidence" />}
        {communicationStyle && (
          <span className="text-xs px-2.5 py-1 rounded-full bg-card border border-card-border text-muted">
            Style: <span className="text-foreground/80">{communicationStyle}</span>
          </span>
        )}
        {parsed.confidenceBreakdown.length > 0 && (
          <div className="flex gap-1.5 flex-wrap">
            {parsed.confidenceBreakdown.map((factor) => (
              <span key={factor} className="text-[10px] px-1.5 py-0.5 rounded bg-card-border/50 text-muted">
                {factor.replace(/_/g, " ")}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* ── Identity card ───────────────────────────────────────────────── */}
      {parsed.identity && <IdentityCard identity={parsed.identity} />}

      {/* ── Main 2-col grid ─────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">

        {/* Professional Narrative */}
        {(parsed.careerStory || parsed.keyTransitions || parsed.skillsExpertise || parsed.notableAchievements) && (
          <SectionCard title="Professional Narrative" icon="📋" accent>
            <div className="space-y-3">
              {parsed.careerStory && (
                <div>
                  <Label>Career Story</Label>
                  <p className="text-sm text-foreground/85 leading-relaxed">{parsed.careerStory}</p>
                </div>
              )}
              {parsed.keyTransitions && (
                <div>
                  <Label>Key Transitions</Label>
                  <p className="text-sm text-foreground/80 leading-relaxed">{parsed.keyTransitions}</p>
                </div>
              )}
              {parsed.skillsExpertise && (
                <div>
                  <Label>Skills & Expertise</Label>
                  <p className="text-sm text-foreground/80">{parsed.skillsExpertise}</p>
                </div>
              )}
              {parsed.notableAchievements && (
                <div>
                  <Label>Notable Achievements</Label>
                  <p className="text-sm text-foreground/80">{parsed.notableAchievements}</p>
                </div>
              )}
            </div>
          </SectionCard>
        )}

        {/* Company Context */}
        {parsed.company && (
          <SectionCard title="Company Context" icon="🏢">
            <div className="space-y-2">
              <KeyValueGrid items={[
                { label: "Company",    value: parsed.company.name },
                { label: "Size",       value: parsed.company.size },
                { label: "Industry",   value: parsed.company.industry },
                { label: "Stage",      value: parsed.company.stage },
                { label: "Role",       value: parsed.company.roleInOrg },
                { label: "Recent News",value: parsed.company.recentNews },
              ]} />
              {parsed.company.visibleChallenges && (
                <div className="mt-2">
                  <Label>Visible Challenges</Label>
                  <p className="text-sm text-foreground/80 leading-relaxed">{parsed.company.visibleChallenges}</p>
                </div>
              )}
            </div>
          </SectionCard>
        )}

        {/* Psychological Profile */}
        {(parsed.motivations.length > 0 || parsed.riskTolerance || parsed.values.length > 0 || parsed.decisionStyle) && (
          <SectionCard title="Psychological Profile" icon="🧠">
            <div className="space-y-4">
              {parsed.motivations.length > 0 && (
                <div>
                  <Label>Motivations</Label>
                  <div className="space-y-2">
                    {parsed.motivations.map((m, i) => (
                      <div key={i} className="rounded-lg bg-background border border-card-border px-3 py-2.5">
                        <p className="text-sm text-foreground/90">{m.text}</p>
                        {m.evidence && (
                          <p className="text-xs text-muted mt-1 italic">{m.evidence}</p>
                        )}
                        {m.confidence && <ConfidenceTag level={m.confidence} />}
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {parsed.riskTolerance && (
                <div>
                  <Label>Risk Tolerance</Label>
                  <p className="text-sm text-foreground/85">{parsed.riskTolerance}</p>
                </div>
              )}
              {parsed.values.length > 0 && (
                <div>
                  <Label>Values</Label>
                  <div className="flex flex-wrap gap-1.5">
                    {parsed.values.map((v) => (
                      <span key={v} className="text-[11px] px-2 py-0.5 rounded border bg-accent/10 text-accent border-accent/20">
                        {v}
                      </span>
                    ))}
                  </div>
                </div>
              )}
              {parsed.decisionStyle && (
                <div>
                  <Label>Decision Style</Label>
                  <p className="text-sm text-foreground/85">{parsed.decisionStyle}</p>
                </div>
              )}
            </div>
          </SectionCard>
        )}

        {/* Pain Points */}
        {parsed.painPoints.length > 0 && (
          <SectionCard title="Pain Points" icon="🎯">
            <div className="space-y-2.5">
              {parsed.painPoints.map((pp, i) => (
                <div key={i} className="rounded-lg bg-background border border-card-border px-3 py-2.5">
                  <div className="flex items-start gap-2">
                    <span className="text-xs font-bold text-accent shrink-0 mt-0.5">#{i + 1}</span>
                    <div className="min-w-0 space-y-1">
                      <p className="text-sm text-foreground/90 font-medium">{pp.description}</p>
                      {pp.evidence && (
                        <p className="text-xs text-muted italic">Evidence: {pp.evidence}</p>
                      )}
                      {pp.solutionConnection && (
                        <p className="text-xs text-accent-dim">Connection: {pp.solutionConnection}</p>
                      )}
                      {pp.confidence && <ConfidenceTag level={pp.confidence} />}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </SectionCard>
        )}

        {/* Communication DNA */}
        {(parsed.writingStyle || parsed.engagementTopics.length > 0 || parsed.bestChannel) && (
          <SectionCard title="Communication DNA" icon="💬">
            <div className="space-y-3">
              <KeyValueGrid items={[
                { label: "Writing Style", value: parsed.writingStyle },
                { label: "Tone",          value: parsed.tone },
                { label: "Post Length",   value: parsed.postLength },
                { label: "Emoji Usage",   value: parsed.emojiUsage },
                { label: "Best Channel",  value: parsed.bestChannel },
              ]} />
              {parsed.engagementTopics.length > 0 && (
                <div>
                  <Label>Engagement Topics</Label>
                  <div className="flex flex-wrap gap-1.5">
                    {parsed.engagementTopics.map((t) => (
                      <span key={t} className="text-[11px] px-2 py-0.5 rounded border bg-card-border/50 text-foreground/70 border-transparent">
                        {t}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </SectionCard>
        )}

        {/* Engagement Strategy */}
        {(parsed.openingAngle || parsed.topicsToAvoid.length > 0 || parsed.recommendedApproach) && (
          <SectionCard title="Engagement Strategy" icon="🚀" accent>
            <div className="space-y-3">
              {parsed.openingAngle && (
                <div className="rounded-lg bg-accent/5 border border-accent/20 px-3 py-2.5">
                  <Label>Opening Angle</Label>
                  <p className="text-sm text-foreground/90 leading-relaxed">{parsed.openingAngle}</p>
                </div>
              )}
              {parsed.specificReference && (
                <div>
                  <Label>Specific Reference</Label>
                  <p className="text-sm text-foreground/85 italic">"{parsed.specificReference}"</p>
                </div>
              )}
              <KeyValueGrid items={[
                { label: "Approach", value: parsed.recommendedApproach },
                { label: "Timing",   value: parsed.idealTiming },
              ]} />
              {parsed.topicsToAvoid.length > 0 && (
                <div>
                  <Label>Topics to Avoid</Label>
                  <div className="space-y-1.5">
                    {parsed.topicsToAvoid.map((t, i) => (
                      <div key={i} className="flex items-start gap-2">
                        <span className="text-[11px] px-2 py-0.5 rounded border bg-error/10 text-error border-error/20 shrink-0">
                          {t.topic}
                        </span>
                        {t.reason && (
                          <span className="text-xs text-muted leading-relaxed">{t.reason}</span>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </SectionCard>
        )}

        {/* Network & Influence */}
        {(parsed.connectionCount || parsed.mutualConnections.length > 0 || parsed.influenceLevel) && (
          <SectionCard title="Network & Influence" icon="🌐">
            <div className="space-y-3">
              <KeyValueGrid items={[
                { label: "Connections", value: parsed.connectionCount },
                { label: "Followers",   value: parsed.followerCount },
                { label: "Influence",   value: parsed.influenceLevel },
              ]} />
              {parsed.mutualConnections.length > 0 && (
                <div>
                  <Label>Mutual Connections</Label>
                  <div className="flex flex-wrap gap-1.5">
                    {parsed.mutualConnections.map((c) => (
                      <span key={c} className="text-[11px] px-2 py-0.5 rounded border bg-success/15 text-success border-success/20">
                        {c}
                      </span>
                    ))}
                  </div>
                </div>
              )}
              {parsed.warmIntroSuggestion && (
                <div>
                  <Label>Warm Intro Strategy</Label>
                  <p className="text-sm text-foreground/80 leading-relaxed">{parsed.warmIntroSuggestion}</p>
                </div>
              )}
            </div>
          </SectionCard>
        )}
      </div>

      {/* ── Data Gaps ───────────────────────────────────────────────────── */}
      {parsed.dataGaps.length > 0 && (
        <div className="rounded-xl border border-card-border bg-card px-4 py-3">
          <Label>Data Gaps</Label>
          <ul className="space-y-0.5 mt-1">
            {parsed.dataGaps.map((gap, i) => (
              <li key={i} className="text-xs text-muted">• {gap}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

/* ── Sub-components ───────────────────────────────────────────────────────── */

function ConfidenceMeter({ value, label }: { value: number; label?: string }) {
  const color = value >= 70 ? "text-success" : value >= 40 ? "text-warning" : "text-error";
  const bg    = value >= 70 ? "bg-success"   : value >= 40 ? "bg-warning"   : "bg-error";
  return (
    <div className="flex items-center gap-2">
      <div className="w-20 h-1.5 rounded-full bg-card-border overflow-hidden">
        <div className={`h-full rounded-full ${bg} transition-all`} style={{ width: `${value}%` }} />
      </div>
      <span className={`text-xs font-semibold ${color}`}>{value}%</span>
      {label && <span className="text-xs text-muted">{label}</span>}
    </div>
  );
}

function IdentityCard({ identity }: { identity: IdentitySnapshot }) {
  const initials = identity.name
    .split(" ").map((w) => w[0]).slice(0, 2).join("").toUpperCase();
  return (
    <div className="rounded-xl border border-accent/30 bg-accent/5 p-5">
      <div className="flex items-start gap-4">
        <div className="w-12 h-12 rounded-full bg-accent/20 flex items-center justify-center text-accent font-bold text-lg shrink-0">
          {initials}
        </div>
        <div className="min-w-0 flex-1">
          <h3 className="text-base font-semibold text-foreground">{identity.name}</h3>
          {identity.title && <p className="text-sm text-foreground/70 mt-0.5">{identity.title}</p>}
          <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2 text-xs text-muted">
            {identity.company && <span>{identity.company}</span>}
            {identity.seniority && (
              <span className="text-accent font-medium">{identity.seniority}</span>
            )}
            {identity.yearsInRole && <span>{identity.yearsInRole} in role</span>}
            {identity.totalExperience && <span>{identity.totalExperience} total</span>}
          </div>
          {identity.decisionAuthority && (
            <p className="text-xs text-foreground/60 mt-1.5">
              Authority: {identity.decisionAuthority}
            </p>
          )}
          {identity.trajectory && (
            <p className="text-xs text-foreground/55 mt-1 italic">{identity.trajectory}</p>
          )}
        </div>
      </div>
    </div>
  );
}

function SectionCard({
  title, icon, accent, children,
}: {
  title: string; icon?: string; accent?: boolean; children: ReactNode;
}) {
  return (
    <div className={`rounded-xl border p-4 ${accent ? "border-accent/20 bg-accent/[0.02]" : "border-card-border bg-card"}`}>
      <h3 className="text-xs font-semibold text-accent uppercase tracking-wider mb-3 flex items-center gap-1.5">
        {icon && <span>{icon}</span>}
        {title}
      </h3>
      {children}
    </div>
  );
}

function KeyValueGrid({ items }: { items: { label: string; value: string }[] }) {
  const filtered = items.filter((item) => item.value);
  if (filtered.length === 0) return null;
  return (
    <div className="space-y-1.5">
      {filtered.map((item) => (
        <div key={item.label} className="flex items-baseline gap-3">
          <span className="text-xs text-muted shrink-0 w-24">{item.label}</span>
          <span className="text-sm text-foreground/85">{item.value}</span>
        </div>
      ))}
    </div>
  );
}

function Label({ children }: { children: ReactNode }) {
  return <div className="text-[10px] text-muted uppercase tracking-wider font-semibold mb-1.5">{children}</div>;
}

function ConfidenceTag({ level }: { level: string }) {
  const lower = level.toLowerCase();
  const cls = lower.includes("high") ? "text-success" : lower.includes("medium") ? "text-warning" : "text-muted";
  return <span className={`text-[10px] ${cls} font-medium mt-1 inline-block`}>{level} confidence</span>;
}

/* ── Parser ───────────────────────────────────────────────────────────────── */

function parsePersona(persona: Record<string, unknown>): ParsedPersona {
  const result: ParsedPersona = {
    identity: null, careerStory: "", keyTransitions: "", skillsExpertise: "",
    notableAchievements: "", company: null, motivations: [], riskTolerance: "",
    values: [], decisionStyle: "", painPoints: [], writingStyle: "", emojiUsage: "",
    postLength: "", engagementTopics: [], tone: "", bestChannel: "", openingAngle: "",
    topicsToAvoid: [], idealTiming: "", recommendedApproach: "", specificReference: "",
    connectionCount: "", followerCount: "", mutualConnections: [], warmIntroSuggestion: "",
    influenceLevel: "", personaConfidence: null, dataGaps: [], confidenceBreakdown: [],
  };

  // confidence_breakdown lives at top level
  const breakdown = persona.confidence_breakdown;
  if (Array.isArray(breakdown)) {
    result.confidenceBreakdown = breakdown.map(String);
  }

  // Parse raw_response JSON (strip ```json fences)
  const raw = persona.raw_response;
  let d: Record<string, unknown> = persona;
  if (typeof raw === "string") {
    const parsed = tryParseJSON(raw);
    if (parsed) {
      d = parsed;
    }
  }

  // persona_confidence
  if (typeof d.persona_confidence === "number") {
    result.personaConfidence = d.persona_confidence;
  }

  // data_gaps
  if (Array.isArray(d.data_gaps)) {
    result.dataGaps = d.data_gaps.map(String);
  }

  // ── identity_snapshot ───────────────────────────────────────────────────
  const ids = asObj(d.identity_snapshot);
  if (ids) {
    result.identity = {
      name:              s(ids, "name"),
      title:             s(ids, "title"),
      company:           s(ids, "company"),
      seniority:         s(ids, "seniority"),
      decisionAuthority: s(ids, "decision_making_authority"),
      yearsInRole:       s(ids, "years_in_current_role"),
      totalExperience:   s(ids, "total_career_experience"),
      trajectory:        s(ids, "career_trajectory"),
    };
    if (!result.identity.name && !result.identity.title) result.identity = null;
  }

  // ── professional_narrative ──────────────────────────────────────────────
  const pn = asObj(d.professional_narrative);
  if (pn) {
    result.careerStory         = s(pn, "career_story");
    result.keyTransitions      = s(pn, "key_career_transitions");
    result.skillsExpertise     = s(pn, "skills_expertise");
    result.notableAchievements = s(pn, "notable_achievements");
  }

  // ── company_context ─────────────────────────────────────────────────────
  const cc = asObj(d.company_context);
  if (cc) {
    result.company = {
      name:              s(cc, "company_name") || s(cc, "name"),
      size:              s(cc, "size"),
      industry:          s(cc, "industry"),
      stage:             s(cc, "stage"),
      recentNews:        s(cc, "recent_news"),
      roleInOrg:         s(cc, "role_in_org"),
      visibleChallenges: s(cc, "visible_challenges"),
    };
  }

  // ── psychological_profile ───────────────────────────────────────────────
  const pp = asObj(d.psychological_profile);
  if (pp) {
    // motivations: array of {motivation, evidence, confidence}
    const motiRaw = pp.motivations;
    if (Array.isArray(motiRaw)) {
      result.motivations = motiRaw.map((m) => {
        const obj = asObj(m) ?? {};
        return {
          text:       s(obj, "motivation") || s(obj, "description") || s(obj, "text") || String(m ?? ""),
          evidence:   s(obj, "evidence"),
          confidence: s(obj, "confidence"),
        };
      }).filter((m) => m.text);
    }

    // risk_tolerance: may be {assessment, evidence}
    const rt = pp.risk_tolerance;
    if (typeof rt === "string") {
      result.riskTolerance = rt;
    } else {
      const rtObj = asObj(rt);
      result.riskTolerance = rtObj ? s(rtObj, "assessment") || s(rtObj, "description") : "";
    }

    // values: array of strings or objects
    const vals = pp.values;
    if (Array.isArray(vals)) {
      result.values = vals.map((v) => {
        if (typeof v === "string") return v;
        const obj = asObj(v);
        return obj ? s(obj, "value") || s(obj, "name") || s(obj, "text") || JSON.stringify(v) : String(v ?? "");
      }).filter(Boolean);
    }

    // decision_style: may be {style, evidence}
    const ds = pp.decision_style;
    if (typeof ds === "string") {
      result.decisionStyle = ds;
    } else {
      const dsObj = asObj(ds);
      result.decisionStyle = dsObj ? s(dsObj, "style") || s(dsObj, "description") : "";
    }
  }

  // ── pain_points ─────────────────────────────────────────────────────────
  const painRaw = d.pain_points;
  if (Array.isArray(painRaw)) {
    result.painPoints = painRaw.map((item) => {
      const obj = asObj(item) ?? {};
      return {
        description:        s(obj, "description") || s(obj, "pain_point") || String(item ?? ""),
        evidence:           s(obj, "evidence_source") || s(obj, "evidence"),
        confidence:         s(obj, "confidence"),
        solutionConnection: s(obj, "solution_connection"),
      };
    }).filter((p) => p.description);
  }

  // ── communication_dna ───────────────────────────────────────────────────
  const cd = asObj(d.communication_dna);
  if (cd) {
    // writing_style may be {style, examples}
    const ws = cd.writing_style;
    result.writingStyle = typeof ws === "string" ? ws : (asObj(ws) ? s(asObj(ws)!, "style") : "");
    result.emojiUsage   = s(cd, "emoji_usage");
    // post_length may be {preference, evidence}
    const pl = cd.post_length;
    result.postLength   = typeof pl === "string" ? pl : (asObj(pl) ? s(asObj(pl)!, "preference") : "");
    result.tone         = s(cd, "tone");
    result.bestChannel  = s(cd, "best_channel");
    const et = cd.engagement_topics;
    if (Array.isArray(et)) result.engagementTopics = et.map(String).filter(Boolean);
  }

  // ── engagement_strategy ─────────────────────────────────────────────────
  const es = asObj(d.engagement_strategy);
  if (es) {
    result.openingAngle      = s(es, "opening_angle");
    result.idealTiming       = s(es, "ideal_timing");
    result.specificReference = s(es, "specific_reference");

    // recommended_approach may be {approach, reasoning}
    const ra = es.recommended_approach;
    result.recommendedApproach = typeof ra === "string" ? ra : (asObj(ra) ? s(asObj(ra)!, "approach") : "");

    // topics_to_avoid: array of {topic, reason, evidence, confidence}
    const tta = es.topics_to_avoid;
    if (Array.isArray(tta)) {
      result.topicsToAvoid = tta.map((t) => {
        const obj = asObj(t) ?? {};
        return {
          topic:      s(obj, "topic") || s(obj, "description") || String(t ?? ""),
          reason:     s(obj, "reason"),
          confidence: s(obj, "confidence"),
        };
      }).filter((t) => t.topic);
    }
  }

  // ── network_influence ───────────────────────────────────────────────────
  const ni = asObj(d.network_influence);
  if (ni) {
    const connCount = ni.connection_count;
    result.connectionCount = connCount != null ? String(connCount) : "";
    const follCount = ni.follower_count;
    result.followerCount   = follCount != null ? String(follCount) : "";

    const mc = ni.mutual_connections;
    if (Array.isArray(mc)) result.mutualConnections = mc.map(String).filter(Boolean);

    // warm_intros_strategy may be {suggestion, evidence, confidence}
    const wis = ni.warm_intros_strategy;
    result.warmIntroSuggestion = typeof wis === "string" ? wis : (asObj(wis) ? s(asObj(wis)!, "suggestion") : "");

    // influence_level may be {assessment, evidence}
    const il = ni.influence_level;
    result.influenceLevel = typeof il === "string" ? il : (asObj(il) ? s(asObj(il)!, "assessment") : "");
  }

  return result;
}

/* ── Utilities ────────────────────────────────────────────────────────────── */

function tryParseJSON(text: string): Record<string, unknown> | null {
  // Strip markdown fences
  let cleaned = text.replace(/```json\s*/g, "").replace(/```/g, "").trim();

  // Try direct parse first
  try {
    const p = JSON.parse(cleaned);
    if (typeof p === "object" && p !== null && !Array.isArray(p)) return p as Record<string, unknown>;
  } catch { /* not pure JSON */ }

  // Try extracting the first JSON object from mixed text
  // (LLMs often prefix/suffix JSON with explanation text)
  const firstBrace = cleaned.indexOf("{");
  const lastBrace = cleaned.lastIndexOf("}");
  if (firstBrace !== -1 && lastBrace > firstBrace) {
    try {
      const extracted = cleaned.slice(firstBrace, lastBrace + 1);
      const p = JSON.parse(extracted);
      if (typeof p === "object" && p !== null && !Array.isArray(p)) return p as Record<string, unknown>;
    } catch { /* still not valid */ }
  }

  return null;
}
function asObj(v: unknown): Record<string, unknown> | null {
  return (v != null && typeof v === "object" && !Array.isArray(v)) ? v as Record<string, unknown> : null;
}
function s(obj: Record<string, unknown>, key: string): string {
  const v = obj[key]; return v != null ? String(v) : "";
}
