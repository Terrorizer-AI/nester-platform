"use client";

import { useEffect, useState } from "react";
import MetricCard from "@/components/MetricCard";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface Flow {
  name: string;
  version: string;
}

export default function Dashboard() {
  const [flows, setFlows] = useState<Flow[]>([]);
  const [health, setHealth] = useState<string>("checking...");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const [flowsRes, healthRes] = await Promise.all([
          fetch(`${API}/flows`),
          fetch(`${API}/healthcheck`),
        ]);
        const flowsData = await flowsRes.json();
        const healthData = await healthRes.json();
        setFlows(flowsData.flows || []);
        setHealth(healthData.status || "unknown");
      } catch {
        setHealth("offline");
      } finally {
        setLoading(false);
      }
    }
    load();
    const interval = setInterval(load, 10000);
    return () => clearInterval(interval);
  }, []);

  const FLOW_META: Record<string, { desc: string; agents: number; trigger: string; href?: string }> = {
    sales_outreach: {
      desc: "LinkedIn prospect research to personalized cold email",
      agents: 8,
      trigger: "On-demand",
    },
    sow_generator: {
      desc: "Upload proposals & templates, AI generates a Statement of Work",
      agents: 4,
      trigger: "On-demand",
      href: "/sow",
    },
  };

  // Only show flows that are ready (github_monitor hidden until backend is ready)
  const visibleFlows = flows.filter(f => f.name !== "github_monitor");

  // Append SOW as a virtual flow card (not a backend YAML flow)
  const SOW_VIRTUAL = { name: "sow_generator", version: "1.0" };
  const dashboardFlows = [...visibleFlows, ...(visibleFlows.some(f => f.name === "sow_generator") ? [] : [SOW_VIRTUAL])];

  return (
    <div className="max-w-7xl mx-auto px-6 py-10">
      <div className="mb-10">
        <h1 className="text-2xl font-bold tracking-tight mb-1">Dashboard</h1>
        <p className="text-muted text-sm">Nester Agent Platform</p>
      </div>

      <div className="grid grid-cols-4 gap-4 mb-10">
        <MetricCard
          label="Platform Status"
          value={loading ? "..." : health === "alive" ? "Online" : "Offline"}
          sub={health === "alive" ? "All systems operational" : "Check backend"}
        />
        <MetricCard label="Active Flows" value={dashboardFlows.length} sub="Deployed" />
        <MetricCard label="Total Agents" value={12} sub="8 outreach + 4 SOW" />
        <MetricCard label="Model" value="GPT-4o" sub="All agents" />
      </div>

      <h2 className="text-lg font-semibold mb-4">Flows</h2>
      <div className="grid grid-cols-2 gap-4">
        {dashboardFlows.map((flow) => {
          const meta = FLOW_META[flow.name];
          const href = meta?.href || `/flow/${flow.name}`;
          return (
            <a
              key={flow.name}
              href={href}
              className="group rounded-xl border border-card-border bg-card p-6 hover:border-accent/40 transition-all"
            >
              <div className="flex items-start justify-between mb-3">
                <div>
                  <h3 className="font-semibold text-base group-hover:text-accent transition-colors">
                    {flow.name.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())}
                  </h3>
                  <p className="text-sm text-muted mt-1">{meta?.desc}</p>
                </div>
                <span className="text-xs font-mono text-muted bg-card-border/50 px-2 py-1 rounded">
                  {meta?.trigger}
                </span>
              </div>
              <div className="flex gap-6 text-xs text-muted">
                <span>{meta?.agents} agents</span>
                <span>v{flow.version === "unknown" ? "1.0" : flow.version}</span>
              </div>
            </a>
          );
        })}
      </div>

      {!loading && flows.length === 0 && (
        <div className="text-center py-20 text-muted">
          <p>No flows found. Is the backend running?</p>
          <code className="text-xs mt-2 block">http://localhost:8000</code>
        </div>
      )}
    </div>
  );
}
