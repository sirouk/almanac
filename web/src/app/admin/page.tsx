"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import Link from "next/link";

type Tab = "overview" | "onboarding" | "health" | "provisioning" | "dns" | "audit" | "actions";

interface AdminData {
  deployments?: Record<string, string>[];
  users?: Record<string, string>[];
  onboarding_funnel?: Record<string, unknown>;
  active_sessions?: { user: number; admin: number };
  recent_failures?: Record<string, string>[];
}

interface HealthEntry {
  deployment_id: string;
  service_name: string;
  status: string;
  last_check_at?: string;
}

function StatusBadge({ status }: { status: string }) {
  const color =
    status === "healthy" || status === "active" || status === "paid"
      ? "text-neon-green"
      : status === "degraded" || status === "pending" || status === "queued"
        ? "text-yellow-400"
        : "text-red-400";
  return <span className={`text-xs font-semibold uppercase ${color}`}>{status}</span>;
}

export default function AdminPage() {
  const [tab, setTab] = useState<Tab>("overview");
  const [data, setData] = useState<AdminData | null>(null);
  const [health, setHealth] = useState<{ service_health?: HealthEntry[]; recent_failures?: HealthEntry[] } | null>(null);
  const [jobs, setJobs] = useState<{ provisioning_jobs?: Record<string, string>[] } | null>(null);
  const [drift, setDrift] = useState<{ dns_drift?: Record<string, string>[] } | null>(null);
  const [audit, setAudit] = useState<{ audit?: Record<string, string>[] } | null>(null);
  const [actions, setActions] = useState<{ actions?: Record<string, string>[] } | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.adminDashboard().then((r) => {
      if (r.status === 200) setData(r.data as AdminData);
      else setError("Admin authentication required.");
    }).catch(() => setError("Failed to load admin data."));
  }, []);

  useEffect(() => {
    if (tab === "health") api.adminServiceHealth().then((r) => { if (r.status === 200) setHealth(r.data as typeof health); });
    if (tab === "provisioning") api.adminProvisioningJobs().then((r) => { if (r.status === 200) setJobs(r.data as typeof jobs); });
    if (tab === "dns") api.adminDnsDrift().then((r) => { if (r.status === 200) setDrift(r.data as typeof drift); });
    if (tab === "audit") api.adminAudit().then((r) => { if (r.status === 200) setAudit(r.data as typeof audit); });
    if (tab === "actions") api.adminActions().then((r) => { if (r.status === 200) setActions(r.data as typeof actions); });
  }, [tab]);

  const tabs: Tab[] = ["overview", "onboarding", "health", "provisioning", "dns", "audit", "actions"];

  return (
    <div className="flex min-h-screen flex-col">
      <nav className="flex items-center justify-between border-b border-border px-6 py-4">
        <Link href="/" className="font-display text-lg font-bold tracking-wide">
          <span className="text-signal-orange">ARC</span>LINK
          <span className="ml-2 text-xs text-soft-white/40">Admin</span>
        </Link>
        <Link href="/dashboard" className="text-sm text-soft-white/40 hover:text-soft-white">
          User Dashboard
        </Link>
      </nav>

      <div className="flex flex-1">
        {/* Sidebar */}
        <aside className="hidden w-56 shrink-0 border-r border-border p-4 md:block">
          <nav className="space-y-1">
            {tabs.map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={`block w-full rounded px-3 py-2 text-left text-sm capitalize transition ${
                  tab === t ? "bg-surface text-signal-orange" : "text-soft-white/60 hover:text-soft-white"
                }`}
              >
                {t}
              </button>
            ))}
          </nav>
        </aside>

        <main className="flex-1 overflow-x-hidden p-6">
          {error && <div className="mb-6 rounded bg-red-900/40 px-4 py-3 text-sm text-red-300">{error}</div>}

          {/* Mobile tabs */}
          <div className="mb-6 flex flex-wrap gap-2 md:hidden">
            {tabs.map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={`rounded px-3 py-1 text-xs capitalize ${
                  tab === t ? "bg-signal-orange text-jet" : "bg-surface text-soft-white/60"
                }`}
              >
                {t}
              </button>
            ))}
          </div>

          {/* Overview */}
          {tab === "overview" && data && (
            <div className="space-y-6">
              <h1 className="font-display text-2xl font-bold">Admin Overview</h1>
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                <StatCard label="Users" value={data.users?.length ?? 0} />
                <StatCard label="Deployments" value={data.deployments?.length ?? 0} />
                <StatCard label="User Sessions" value={data.active_sessions?.user ?? 0} />
                <StatCard label="Admin Sessions" value={data.active_sessions?.admin ?? 0} />
              </div>
              {data.recent_failures && data.recent_failures.length > 0 && (
                <div className="rounded-lg border border-red-900/50 bg-red-950/20 p-4">
                  <h3 className="font-display font-semibold text-red-400">Recent Failures</h3>
                  <ul className="mt-2 space-y-1 text-sm text-red-300">
                    {data.recent_failures.map((f, i) => (
                      <li key={i}>{f.service_name} on {f.deployment_id} — {f.status}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}

          {/* Onboarding funnel */}
          {tab === "onboarding" && data && (
            <div className="space-y-6">
              <h1 className="font-display text-2xl font-bold">Onboarding Funnel</h1>
              {data.onboarding_funnel ? (
                <div className="rounded-lg border border-border bg-surface p-4">
                  <pre className="overflow-x-auto text-xs text-soft-white/60">
                    {JSON.stringify(data.onboarding_funnel, null, 2)}
                  </pre>
                </div>
              ) : (
                <p className="text-soft-white/40">No funnel data available.</p>
              )}
            </div>
          )}

          {/* Service Health */}
          {tab === "health" && (
            <div className="space-y-6">
              <h1 className="font-display text-2xl font-bold">Service Health</h1>
              {health?.service_health?.length ? (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-border text-left text-soft-white/40">
                        <th className="px-3 py-2">Deployment</th>
                        <th className="px-3 py-2">Service</th>
                        <th className="px-3 py-2">Status</th>
                        <th className="px-3 py-2">Last Check</th>
                      </tr>
                    </thead>
                    <tbody>
                      {health.service_health.map((h, i) => (
                        <tr key={i} className="border-b border-border/50">
                          <td className="px-3 py-2 font-mono text-xs">{h.deployment_id}</td>
                          <td className="px-3 py-2">{h.service_name}</td>
                          <td className="px-3 py-2"><StatusBadge status={h.status} /></td>
                          <td className="px-3 py-2 text-soft-white/40">{h.last_check_at || "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="text-soft-white/40">No health data.</p>
              )}
            </div>
          )}

          {/* Provisioning */}
          {tab === "provisioning" && (
            <div className="space-y-6">
              <h1 className="font-display text-2xl font-bold">Provisioning Jobs</h1>
              {jobs?.provisioning_jobs?.length ? (
                jobs.provisioning_jobs.map((j, i) => (
                  <div key={i} className="rounded-lg border border-border bg-surface p-4 text-sm">
                    <p>Job: <span className="font-mono text-xs">{j.job_id || j.deployment_id}</span></p>
                    <p>Status: <StatusBadge status={j.status || "unknown"} /></p>
                  </div>
                ))
              ) : (
                <p className="text-soft-white/40">No provisioning jobs.</p>
              )}
            </div>
          )}

          {/* DNS Drift */}
          {tab === "dns" && (
            <div className="space-y-6">
              <h1 className="font-display text-2xl font-bold">DNS Drift</h1>
              {drift?.dns_drift?.length ? (
                drift.dns_drift.map((d, i) => (
                  <div key={i} className="rounded-lg border border-border bg-surface p-4 text-sm">
                    <p>{d.deployment_id}: {d.expected || "—"} → {d.actual || "—"}</p>
                    <StatusBadge status={d.status || "drift"} />
                  </div>
                ))
              ) : (
                <p className="text-neon-green text-sm">No DNS drift detected.</p>
              )}
            </div>
          )}

          {/* Audit */}
          {tab === "audit" && (
            <div className="space-y-6">
              <h1 className="font-display text-2xl font-bold">Audit Log</h1>
              {audit?.audit?.length ? (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-border text-left text-soft-white/40">
                        <th className="px-3 py-2">When</th>
                        <th className="px-3 py-2">Actor</th>
                        <th className="px-3 py-2">Action</th>
                        <th className="px-3 py-2">Target</th>
                        <th className="px-3 py-2">Reason</th>
                      </tr>
                    </thead>
                    <tbody>
                      {audit.audit.map((a, i) => (
                        <tr key={i} className="border-b border-border/50">
                          <td className="px-3 py-2 text-soft-white/40 text-xs">{a.created_at || "—"}</td>
                          <td className="px-3 py-2 font-mono text-xs">{a.actor_id || "—"}</td>
                          <td className="px-3 py-2">{a.action_type || "—"}</td>
                          <td className="px-3 py-2 font-mono text-xs">{a.target_id || "—"}</td>
                          <td className="px-3 py-2 text-soft-white/60">{a.reason || "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="text-soft-white/40">No audit entries.</p>
              )}
            </div>
          )}

          {/* Queued Actions */}
          {tab === "actions" && (
            <div className="space-y-6">
              <h1 className="font-display text-2xl font-bold">Queued Actions</h1>
              {actions?.actions?.length ? (
                actions.actions.map((a, i) => (
                  <div key={i} className="rounded-lg border border-border bg-surface p-4 text-sm">
                    <div className="flex items-center justify-between">
                      <span className="font-mono text-xs">{a.action_id || "—"}</span>
                      <StatusBadge status={a.status || "queued"} />
                    </div>
                    <p className="mt-1">
                      <span className="text-soft-white/60">Type:</span> {a.action_type}{" "}
                      <span className="text-soft-white/60">Target:</span> {a.target_id}
                    </p>
                    <p className="mt-1 text-soft-white/40">Reason: {a.reason || "—"}</p>
                  </div>
                ))
              ) : (
                <p className="text-soft-white/40">No queued actions.</p>
              )}
            </div>
          )}
        </main>
      </div>
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <p className="text-sm text-soft-white/60">{label}</p>
      <p className="mt-1 font-display text-2xl font-bold">{value}</p>
    </div>
  );
}
