"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { StatusBadge, ErrorAlert } from "@/components/ui";

type Tab = "overview" | "users" | "deployments" | "onboarding" | "health" | "provisioning" | "dns" | "payments" | "infrastructure" | "bots" | "security" | "releases" | "audit" | "events" | "actions" | "sessions" | "provider" | "reconciliation" | "operator";

interface AdminData {
  deployments?: Record<string, string>[];
  users?: Record<string, string>[];
  sections?: { section: string; label: string; status: string; counts: Record<string, number> }[];
  onboarding_funnel?: Record<string, unknown>;
  subscriptions?: Record<string, string>[];
  active_sessions?: { user: number; admin: number };
  recent_failures?: Record<string, string>[];
}

interface HealthEntry {
  deployment_id: string;
  service_name: string;
  status: string;
  last_check_at?: string;
}

export default function AdminPage() {
  const [tab, setTab] = useState<Tab>("overview");
  const [data, setData] = useState<AdminData | null>(null);
  const [health, setHealth] = useState<{ service_health?: HealthEntry[]; recent_failures?: HealthEntry[] } | null>(null);
  const [jobs, setJobs] = useState<{ provisioning_jobs?: Record<string, string>[] } | null>(null);
  const [drift, setDrift] = useState<{ dns_drift?: Record<string, string>[] } | null>(null);
  const [audit, setAudit] = useState<{ audit?: Record<string, string>[] } | null>(null);
  const [actions, setActions] = useState<{ actions?: Record<string, string>[] } | null>(null);
  const [events, setEvents] = useState<{ events?: Record<string, string>[] } | null>(null);
  const [providerState, setProviderState] = useState<Record<string, unknown> | null>(null);
  const [reconciliation, setReconciliation] = useState<{ drift?: Record<string, string>[]; summary?: Record<string, unknown> } | null>(null);
  const [operatorSnapshot, setOperatorSnapshot] = useState<Record<string, unknown> | null>(null);
  const [scaleOperations, setScaleOperations] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState("");
  const router = useRouter();

  async function handleLogout() {
    await api.logout("admin");
    router.push("/login");
  }

  useEffect(() => {
    api.adminDashboard().then((r) => {
      if (r.status === 200) setData(r.data as AdminData);
      else if (r.status === 401) router.push("/login");
      else setError("Failed to load admin data.");
    }).catch(() => setError("Failed to load admin data."));
  }, []);

  useEffect(() => {
    if (tab === "health") api.adminServiceHealth().then((r) => { if (r.status === 200) setHealth(r.data as typeof health); });
    if (tab === "provisioning") api.adminProvisioningJobs().then((r) => { if (r.status === 200) setJobs(r.data as typeof jobs); });
    if (tab === "dns") api.adminDnsDrift().then((r) => { if (r.status === 200) setDrift(r.data as typeof drift); });
    if (tab === "audit") api.adminAudit().then((r) => { if (r.status === 200) setAudit(r.data as typeof audit); });
    if (tab === "actions") api.adminActions().then((r) => { if (r.status === 200) setActions(r.data as typeof actions); });
    if (tab === "events") api.adminEvents().then((r) => { if (r.status === 200) setEvents(r.data as typeof events); });
    if (tab === "provider") api.adminProviderState().then((r) => { if (r.status === 200) setProviderState(r.data as typeof providerState); });
    if (tab === "reconciliation") api.adminReconciliation().then((r) => { if (r.status === 200) setReconciliation(r.data as typeof reconciliation); });
    if (tab === "operator") {
      api.adminOperatorSnapshot().then((r) => { if (r.status === 200) setOperatorSnapshot(r.data as typeof operatorSnapshot); });
      api.adminScaleOperations().then((r) => { if (r.status === 200) setScaleOperations(r.data as typeof scaleOperations); });
    }
  }, [tab]);

  const tabs: Tab[] = ["overview", "users", "deployments", "onboarding", "health", "provisioning", "dns", "payments", "infrastructure", "bots", "security", "releases", "audit", "events", "actions", "sessions", "provider", "reconciliation", "operator"];

  return (
    <div className="flex min-h-screen flex-col">
      <nav className="flex items-center justify-between border-b border-border px-6 py-4">
        <Link href="/" className="font-display text-lg font-bold tracking-wide">
          <span className="text-signal-orange">ARC</span>LINK
          <span className="ml-2 text-xs text-soft-white/40">Admin</span>
        </Link>
        <div className="flex items-center gap-4 text-sm">
          <Link href="/dashboard" className="text-soft-white/40 hover:text-soft-white">User Dashboard</Link>
          <button onClick={handleLogout} className="text-soft-white/40 hover:text-red-400">Sign Out</button>
        </div>
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
          {error && <ErrorAlert message={error} className="mb-6 py-3" />}

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

          {/* Users */}
          {tab === "users" && data && (
            <div className="space-y-6">
              <h1 className="font-display text-2xl font-bold">Users</h1>
              {data.users?.length ? (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-border text-left text-soft-white/40">
                        <th className="px-3 py-2">User ID</th>
                        <th className="px-3 py-2">Email</th>
                        <th className="px-3 py-2">Display Name</th>
                        <th className="px-3 py-2">Entitlement</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.users.map((u, i) => (
                        <tr key={i} className="border-b border-border/50">
                          <td className="px-3 py-2 font-mono text-xs">{u.user_id || "—"}</td>
                          <td className="px-3 py-2">{u.email || "—"}</td>
                          <td className="px-3 py-2 text-soft-white/60">{u.display_name || "—"}</td>
                          <td className="px-3 py-2"><StatusBadge status={u.entitlement_state || "unknown"} /></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="text-soft-white/40">No users found.</p>
              )}
            </div>
          )}

          {/* Payments */}
          {tab === "payments" && data && (
            <div className="space-y-6">
              <h1 className="font-display text-2xl font-bold">Payments</h1>
              {data.users?.length ? (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-border text-left text-soft-white/40">
                        <th className="px-3 py-2">User</th>
                        <th className="px-3 py-2">Stripe Customer</th>
                        <th className="px-3 py-2">Entitlement</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.users
                        .filter((u) => u.stripe_customer_id || u.entitlement_state === "paid")
                        .map((u, i) => (
                          <tr key={i} className="border-b border-border/50">
                            <td className="px-3 py-2">{u.email || u.user_id || "—"}</td>
                            <td className="px-3 py-2 font-mono text-xs">{u.stripe_customer_id || "—"}</td>
                            <td className="px-3 py-2"><StatusBadge status={u.entitlement_state || "unknown"} /></td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="text-soft-white/40">No payment data available.</p>
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

          {/* Events */}
          {tab === "events" && (
            <div className="space-y-6">
              <h1 className="font-display text-2xl font-bold">Events</h1>
              {events?.events?.length ? (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-border text-left text-soft-white/40">
                        <th className="px-3 py-2">When</th>
                        <th className="px-3 py-2">Type</th>
                        <th className="px-3 py-2">Deployment</th>
                        <th className="px-3 py-2">Details</th>
                      </tr>
                    </thead>
                    <tbody>
                      {events.events.map((ev, i) => (
                        <tr key={i} className="border-b border-border/50">
                          <td className="px-3 py-2 text-soft-white/40 text-xs">{ev.created_at || "—"}</td>
                          <td className="px-3 py-2">{ev.event_type || "—"}</td>
                          <td className="px-3 py-2 font-mono text-xs">{ev.deployment_id || "—"}</td>
                          <td className="px-3 py-2 text-soft-white/60">{ev.detail || ev.message || "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="text-soft-white/40">No events recorded.</p>
              )}
            </div>
          )}

          {/* Queued Actions */}
          {tab === "actions" && (
            <div className="space-y-6">
              <h1 className="font-display text-2xl font-bold">Queued Actions</h1>
              <QueueActionForm onQueued={() => api.adminActions().then((r) => { if (r.status === 200) setActions(r.data as typeof actions); })} />
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

          {/* Deployments */}
          {tab === "deployments" && data && (
            <div className="space-y-6">
              <h1 className="font-display text-2xl font-bold">Deployments</h1>
              {data.deployments?.length ? (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-border text-left text-soft-white/40">
                        <th className="px-3 py-2">Deployment ID</th>
                        <th className="px-3 py-2">User</th>
                        <th className="px-3 py-2">Hostname</th>
                        <th className="px-3 py-2">Status</th>
                        <th className="px-3 py-2">Updated</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.deployments.map((dep, i) => (
                        <tr key={i} className="border-b border-border/50">
                          <td className="px-3 py-2 font-mono text-xs">{dep.deployment_id || "—"}</td>
                          <td className="px-3 py-2 font-mono text-xs">{dep.user_id || "—"}</td>
                          <td className="px-3 py-2">{dep.prefix && dep.base_domain ? `${dep.prefix}.${dep.base_domain}` : "—"}</td>
                          <td className="px-3 py-2"><StatusBadge status={dep.status || "unknown"} /></td>
                          <td className="px-3 py-2 text-soft-white/40 text-xs">{dep.updated_at || "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="text-soft-white/40">No deployments.</p>
              )}
            </div>
          )}

          {/* Infrastructure */}
          {tab === "infrastructure" && data && (
            <div className="space-y-6">
              <h1 className="font-display text-2xl font-bold">Infrastructure</h1>
              <SectionCard data={data} section="infrastructure" />
              {data.recent_failures && data.recent_failures.length > 0 && (
                <div className="rounded-lg border border-red-900/50 bg-red-950/20 p-4">
                  <h3 className="font-display font-semibold text-red-400">Recent Failures</h3>
                  <ul className="mt-2 space-y-1 text-sm text-red-300">
                    {data.recent_failures.map((f, i) => (
                      <li key={i}>{f.service_name || f.job_kind || "unknown"} on {f.deployment_id} — {f.status}</li>
                    ))}
                  </ul>
                </div>
              )}
              <p className="text-sm text-soft-white/40">
                Node inventory, host metrics, backup status, and queue depth require live integration.
              </p>
            </div>
          )}

          {/* Bots */}
          {tab === "bots" && data && (
            <div className="space-y-6">
              <h1 className="font-display text-2xl font-bold">Bots</h1>
              <SectionCard data={data} section="bots" />
              <p className="text-sm text-soft-white/40">
                Webhook health, active onboarding sessions, and failure rates shown when live bot adapters are connected.
              </p>
            </div>
          )}

          {/* Security */}
          {tab === "security" && data && (
            <div className="space-y-6">
              <h1 className="font-display text-2xl font-bold">Security &amp; Abuse</h1>
              <SectionCard data={data} section="security_abuse" />
              <div className="grid gap-4 sm:grid-cols-2">
                <StatCard label="Active User Sessions" value={data.active_sessions?.user ?? 0} />
                <StatCard label="Active Admin Sessions" value={data.active_sessions?.admin ?? 0} />
              </div>
              <p className="text-sm text-soft-white/40">
                Failed auth attempts, suspicious resource use, and SSH/TUI events shown when live monitoring is active.
              </p>
            </div>
          )}

          {/* Releases */}
          {tab === "releases" && data && (
            <div className="space-y-6">
              <h1 className="font-display text-2xl font-bold">Releases &amp; Maintenance</h1>
              <SectionCard data={data} section="releases_maintenance" />
              <p className="text-sm text-soft-white/40">
                Image versions, canary rollout, maintenance mode, rollback, and announcements available when live executor is connected.
              </p>
            </div>
          )}

          {/* Provider State */}
          {tab === "provider" && (
            <div className="space-y-6">
              <h1 className="font-display text-2xl font-bold">Provider State</h1>
              {providerState ? (
                <div className="rounded-lg border border-border bg-surface p-4">
                  <pre className="overflow-x-auto text-xs text-soft-white/60">
                    {JSON.stringify(providerState, null, 2)}
                  </pre>
                </div>
              ) : (
                <p className="text-soft-white/40">No provider state data.</p>
              )}
            </div>
          )}

          {/* Reconciliation */}
          {tab === "reconciliation" && (
            <div className="space-y-6">
              <h1 className="font-display text-2xl font-bold">Reconciliation</h1>
              {reconciliation?.drift?.length ? (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-border text-left text-soft-white/40">
                        <th className="px-3 py-2">User</th>
                        <th className="px-3 py-2">Field</th>
                        <th className="px-3 py-2">Local</th>
                        <th className="px-3 py-2">Stripe</th>
                        <th className="px-3 py-2">Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {reconciliation.drift.map((d, i) => (
                        <tr key={i} className="border-b border-border/50">
                          <td className="px-3 py-2 font-mono text-xs">{d.user_id || d.customer_id || "—"}</td>
                          <td className="px-3 py-2">{d.field || "—"}</td>
                          <td className="px-3 py-2 text-soft-white/60">{d.local_value || "—"}</td>
                          <td className="px-3 py-2 text-soft-white/60">{d.stripe_value || "—"}</td>
                          <td className="px-3 py-2"><StatusBadge status={d.status || "drift"} /></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : reconciliation?.summary ? (
                <div className="rounded-lg border border-border bg-surface p-4">
                  <pre className="overflow-x-auto text-xs text-soft-white/60">
                    {JSON.stringify(reconciliation.summary, null, 2)}
                  </pre>
                </div>
              ) : (
                <p className="text-neon-green text-sm">No reconciliation drift detected.</p>
              )}
            </div>
          )}

          {/* Operator Snapshot */}
          {tab === "operator" && (
            <div className="space-y-6">
              <h1 className="font-display text-2xl font-bold">Operator Snapshot</h1>
              {operatorSnapshot ? (
                <>
                  <OperatorSection title="Host Readiness" ready={(operatorSnapshot.host_readiness as Record<string, unknown>)?.ready as boolean} checks={((operatorSnapshot.host_readiness as Record<string, unknown>)?.checks as Record<string, unknown>[]) || []} />
                  <OperatorSection title="Provider Diagnostics" ready={(operatorSnapshot.provider_diagnostics as Record<string, unknown>)?.all_ok as boolean} checks={((operatorSnapshot.provider_diagnostics as Record<string, unknown>)?.checks as Record<string, unknown>[]) || []} />
                  <ScaleOperationsSection snapshot={scaleOperations} />
                  <div className="rounded-lg border border-border bg-surface p-4">
                    <div className="flex items-center justify-between">
                      <h3 className="font-display font-semibold">Live Journey</h3>
                      <StatusBadge status={(operatorSnapshot.live_journey as Record<string, unknown>)?.all_credentials_present ? "ready" : "blocked"} />
                    </div>
                    <p className="mt-2 text-sm text-soft-white/60">
                      {((operatorSnapshot.live_journey as Record<string, unknown>)?.blocked_steps as number) || 0} of {((operatorSnapshot.live_journey as Record<string, unknown>)?.total_steps as number) || 0} steps blocked by missing credentials
                    </p>
                  </div>
                  <div className="rounded-lg border border-border bg-surface p-4">
                    <div className="flex items-center justify-between">
                      <h3 className="font-display font-semibold">Evidence</h3>
                      <StatusBadge status={(operatorSnapshot.evidence as Record<string, string>)?.live_proof || "unknown"} />
                    </div>
                    <p className="mt-2 text-sm text-soft-white/60">
                      Template: {(operatorSnapshot.evidence as Record<string, unknown>)?.template_ready ? "ready" : "missing"} · Credentialed: {(operatorSnapshot.evidence as Record<string, string>)?.credentialed_evidence || "unknown"}
                    </p>
                  </div>
                </>
              ) : (
                <p className="text-soft-white/40">Loading operator snapshot...</p>
              )}
            </div>
          )}

          {/* Sessions */}
          {tab === "sessions" && (
            <div className="space-y-6">
              <h1 className="font-display text-2xl font-bold">Session Management</h1>
              <p className="text-sm text-soft-white/60">
                Active sessions: {data?.active_sessions?.user ?? 0} user, {data?.active_sessions?.admin ?? 0} admin
              </p>
              <RevokeSessionForm />
            </div>
          )}
        </main>
      </div>
    </div>
  );
}

function RevokeSessionForm() {
  const [targetSessionId, setTargetSessionId] = useState("");
  const [sessionKind, setSessionKind] = useState<"user" | "admin">("user");
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState("");

  async function handleRevoke(e: React.FormEvent) {
    e.preventDefault();
    setResult("");
    setSubmitting(true);
    try {
      const res = await api.revokeSession({
        target_session_id: targetSessionId,
        session_kind: sessionKind,
        reason,
      });
      if (res.status === 200) {
        setResult("Session revoked.");
        setTargetSessionId("");
        setReason("");
      } else {
        setResult((res.data as Record<string, string>).error || "Revoke failed.");
      }
    } catch {
      setResult("Network error.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleRevoke} className="rounded-lg border border-border bg-surface p-4 space-y-3">
      <h3 className="text-sm font-semibold text-soft-white/80">Revoke Session</h3>
      <div className="grid gap-3 sm:grid-cols-2">
        <input
          required
          value={targetSessionId}
          onChange={(e) => setTargetSessionId(e.target.value)}
          aria-label="Target session ID"
          placeholder="Target session ID"
          className="rounded border border-border bg-carbon px-3 py-2 text-sm text-soft-white outline-none focus:border-signal-orange"
        />
        <select
          value={sessionKind}
          onChange={(e) => setSessionKind(e.target.value as "user" | "admin")}
          className="rounded border border-border bg-carbon px-3 py-2 text-sm text-soft-white outline-none focus:border-signal-orange"
        >
          <option value="user">user</option>
          <option value="admin">admin</option>
        </select>
        <input
          required
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          aria-label="Reason for revoking session"
          placeholder="Reason (required)"
          className="rounded border border-border bg-carbon px-3 py-2 text-sm text-soft-white outline-none focus:border-signal-orange sm:col-span-2"
        />
      </div>
      <div className="flex items-center gap-3">
        <button
          type="submit"
          disabled={submitting}
          className="rounded bg-red-600 px-4 py-2 text-sm font-semibold text-white transition hover:opacity-90 disabled:opacity-50"
        >
          {submitting ? "Revoking..." : "Revoke Session"}
        </button>
        {result && <span className="text-xs text-soft-white/60">{result}</span>}
      </div>
    </form>
  );
}

function SectionCard({ data, section }: { data: AdminData; section: string }) {
  const sec = data.sections?.find((s) => s.section === section);
  if (!sec) return <p className="text-soft-white/40">No data for {section}.</p>;
  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <div className="flex items-center justify-between">
        <h3 className="font-display font-semibold">{sec.label}</h3>
        <StatusBadge status={sec.status} />
      </div>
      <div className="mt-2 flex flex-wrap gap-4 text-sm text-soft-white/60">
        {Object.entries(sec.counts).map(([k, v]) => (
          <span key={k}>{k.replace(/_/g, " ")}: <span className="text-soft-white">{v}</span></span>
        ))}
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

function ScaleOperationsSection({ snapshot }: { snapshot: Record<string, unknown> | null }) {
  const capacity = (snapshot?.fleet_capacity as Record<string, unknown>) || {};
  const staleActions = (snapshot?.stale_actions as Record<string, unknown>[]) || [];
  const attempts = (snapshot?.recent_action_attempts as Record<string, unknown>[]) || [];
  const rollouts = (snapshot?.active_rollouts as Record<string, unknown>[]) || [];
  const placements = (snapshot?.placements as Record<string, unknown>[]) || [];
  const lastExecutor = (snapshot?.last_executor_result as Record<string, unknown>) || {};
  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <div className="flex items-center justify-between">
        <h3 className="font-display font-semibold">Scale Operations</h3>
        <StatusBadge status={staleActions.length ? "attention" : "ready"} />
      </div>
      {snapshot ? (
        <>
          <div className="mt-3 grid gap-3 sm:grid-cols-4">
            <MiniMetric label="Hosts" value={capacity.total_hosts as number || 0} />
            <MiniMetric label="Active" value={capacity.active_hosts as number || 0} />
            <MiniMetric label="Slots" value={capacity.total_slots as number || 0} />
            <MiniMetric label="Free" value={capacity.available_slots as number || 0} />
          </div>
          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            <OperatorList title="Placements" rows={placements} primary="deployment_id" secondary="host_id" statusKey="status" empty="No placements recorded." />
            <OperatorList title="Active Rollouts" rows={rollouts} primary="version_tag" secondary="deployment_id" statusKey="status" empty="No active rollouts." />
            <OperatorList title="Stale Actions" rows={staleActions} primary="action_type" secondary="target" statusKey="status" empty="No stale queued actions." />
            <OperatorList title="Recent Attempts" rows={attempts} primary="action_id" secondary="executor_adapter" statusKey="status" empty="No executor attempts." />
          </div>
          <p className="mt-4 text-xs text-soft-white/50">
            Last executor: {(lastExecutor.action_id as string) || "none"} {(lastExecutor.status as string) ? `(${lastExecutor.status as string})` : ""}
          </p>
        </>
      ) : (
        <p className="mt-2 text-sm text-soft-white/40">Loading scale operations...</p>
      )}
    </div>
  );
}

function MiniMetric({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded border border-border/70 bg-carbon px-3 py-2">
      <p className="text-xs text-soft-white/40">{label}</p>
      <p className="font-display text-lg font-semibold">{value}</p>
    </div>
  );
}

function OperatorList({
  title,
  rows,
  primary,
  secondary,
  statusKey,
  empty,
}: {
  title: string;
  rows: Record<string, unknown>[];
  primary: string;
  secondary: string;
  statusKey: string;
  empty: string;
}) {
  return (
    <div>
      <h4 className="mb-2 text-xs font-semibold uppercase text-soft-white/40">{title}</h4>
      {rows.length ? (
        <div className="space-y-2">
          {rows.slice(0, 4).map((row, i) => (
            <div key={i} className="flex items-center justify-between gap-3 rounded border border-border/60 bg-carbon px-3 py-2 text-xs">
              <div className="min-w-0">
                <p className="truncate font-mono text-soft-white/80">{(row[primary] as string) || "unknown"}</p>
                <p className="truncate text-soft-white/40">{(row[secondary] as string) || ""}</p>
              </div>
              <StatusBadge status={(row[statusKey] as string) || "unknown"} />
            </div>
          ))}
        </div>
      ) : (
        <p className="text-xs text-soft-white/40">{empty}</p>
      )}
    </div>
  );
}

function OperatorSection({ title, ready, checks }: { title: string; ready: boolean; checks: Record<string, unknown>[] }) {
  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <div className="flex items-center justify-between">
        <h3 className="font-display font-semibold">{title}</h3>
        <StatusBadge status={ready ? "ready" : "not_ready"} />
      </div>
      {checks.length > 0 && (
        <div className="mt-3 space-y-1">
          {checks.map((c, i) => (
            <div key={i} className="flex items-center gap-2 text-sm">
              <span className={c.ok ? "text-neon-green" : "text-red-400"}>{c.ok ? "✓" : "✗"}</span>
              <span className="text-soft-white/80">{(c.name || c.provider || "") as string}</span>
              <span className="text-soft-white/40 text-xs">{(c.detail || "") as string}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function QueueActionForm({ onQueued }: { onQueued: () => void }) {
  const [actionType, setActionType] = useState("");
  const [targetKind, setTargetKind] = useState("deployment");
  const [targetId, setTargetId] = useState("");
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState("");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setResult("");
    setSubmitting(true);
    try {
      const res = await api.queueAdminAction({
        action_type: actionType,
        target_kind: targetKind,
        target_id: targetId,
        reason,
        idempotency_key: `web-${Date.now()}`,
      });
      if (res.status === 202) {
        setResult("Action queued.");
        setActionType("");
        setTargetId("");
        setReason("");
        onQueued();
      } else {
        setResult((res.data as Record<string, string>).error || "Failed to queue action.");
      }
    } catch {
      setResult("Network error.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="rounded-lg border border-border bg-surface p-4 space-y-3">
      <h3 className="text-sm font-semibold text-soft-white/80">Queue New Action</h3>
      <div className="grid gap-3 sm:grid-cols-2">
        <input
          required
          value={actionType}
          onChange={(e) => setActionType(e.target.value)}
          aria-label="Action type"
          placeholder="Action type (e.g. restart)"
          className="rounded border border-border bg-carbon px-3 py-2 text-sm text-soft-white outline-none focus:border-signal-orange"
        />
        <select
          value={targetKind}
          onChange={(e) => setTargetKind(e.target.value)}
          className="rounded border border-border bg-carbon px-3 py-2 text-sm text-soft-white outline-none focus:border-signal-orange"
        >
          <option value="deployment">deployment</option>
          <option value="user">user</option>
          <option value="subscription">subscription</option>
          <option value="dns_record">dns_record</option>
          <option value="system">system</option>
        </select>
        <input
          required
          value={targetId}
          onChange={(e) => setTargetId(e.target.value)}
          aria-label="Target ID"
          placeholder="Target ID"
          className="rounded border border-border bg-carbon px-3 py-2 text-sm text-soft-white outline-none focus:border-signal-orange"
        />
        <input
          required
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          aria-label="Reason for action"
          placeholder="Reason (required)"
          className="rounded border border-border bg-carbon px-3 py-2 text-sm text-soft-white outline-none focus:border-signal-orange"
        />
      </div>
      <div className="flex items-center gap-3">
        <button
          type="submit"
          disabled={submitting}
          className="rounded bg-signal-orange px-4 py-2 text-sm font-semibold text-jet transition hover:opacity-90 disabled:opacity-50"
        >
          {submitting ? "Queuing..." : "Queue Action"}
        </button>
        {result && <span className="text-xs text-soft-white/60">{result}</span>}
      </div>
    </form>
  );
}
