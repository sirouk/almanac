"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import Link from "next/link";

interface Deployment {
  deployment_id: string;
  hostname: string;
  status: string;
  service_health?: Record<string, string>[];
}

interface UserData {
  user?: { user_id: string; email: string; display_name: string };
  deployments?: Deployment[];
  entitlement?: { state: string };
}

interface BillingData {
  entitlement?: { state: string };
  subscriptions?: Record<string, string>[];
}

function StatusBadge({ status }: { status: string }) {
  const color =
    status === "healthy" || status === "active" || status === "paid"
      ? "text-neon-green"
      : status === "degraded" || status === "pending"
        ? "text-yellow-400"
        : "text-red-400";
  return <span className={`text-xs font-semibold uppercase ${color}`}>{status}</span>;
}

export default function DashboardPage() {
  const [data, setData] = useState<UserData | null>(null);
  const [billing, setBilling] = useState<BillingData | null>(null);
  const [error, setError] = useState("");
  const [activeTab, setActiveTab] = useState<"overview" | "billing" | "services">("overview");

  useEffect(() => {
    api.userDashboard().then((r) => {
      if (r.status === 200) setData(r.data as UserData);
      else setError("Not authenticated. Please log in.");
    }).catch(() => setError("Failed to load dashboard."));

    api.userBilling().then((r) => {
      if (r.status === 200) setBilling(r.data as BillingData);
    }).catch(() => {});
  }, []);

  return (
    <div className="flex min-h-screen flex-col">
      {/* Top bar */}
      <nav className="flex items-center justify-between border-b border-border px-6 py-4">
        <Link href="/" className="font-display text-lg font-bold tracking-wide">
          <span className="text-signal-orange">ARC</span>LINK
        </Link>
        <div className="flex items-center gap-4 text-sm">
          {data?.user && <span className="text-soft-white/60">{data.user.email}</span>}
          <Link href="/admin" className="text-soft-white/40 hover:text-soft-white">Admin</Link>
        </div>
      </nav>

      <div className="flex flex-1">
        {/* Sidebar */}
        <aside className="hidden w-56 shrink-0 border-r border-border p-4 md:block">
          <nav className="space-y-1">
            {(["overview", "billing", "services"] as const).map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`block w-full rounded px-3 py-2 text-left text-sm capitalize transition ${
                  activeTab === tab ? "bg-surface text-signal-orange" : "text-soft-white/60 hover:text-soft-white"
                }`}
              >
                {tab}
              </button>
            ))}
          </nav>
        </aside>

        {/* Main */}
        <main className="flex-1 overflow-x-hidden p-6">
          {error && (
            <div className="mb-6 rounded bg-red-900/40 px-4 py-3 text-sm text-red-300">{error}</div>
          )}

          {/* Mobile tab bar */}
          <div className="mb-6 flex gap-2 md:hidden">
            {(["overview", "billing", "services"] as const).map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`rounded px-3 py-1 text-xs capitalize ${
                  activeTab === tab ? "bg-signal-orange text-jet" : "bg-surface text-soft-white/60"
                }`}
              >
                {tab}
              </button>
            ))}
          </div>

          {activeTab === "overview" && data && (
            <div className="space-y-6">
              <h1 className="font-display text-2xl font-bold">Dashboard</h1>
              {data.entitlement && (
                <div className="rounded-lg border border-border bg-surface p-4">
                  <span className="text-sm text-soft-white/60">Entitlement: </span>
                  <StatusBadge status={data.entitlement.state} />
                </div>
              )}
              {data.deployments?.map((dep) => (
                <div key={dep.deployment_id} className="rounded-lg border border-border bg-surface p-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <h3 className="font-display font-semibold">{dep.hostname || dep.deployment_id}</h3>
                      <p className="text-xs text-soft-white/40">{dep.deployment_id}</p>
                    </div>
                    <StatusBadge status={dep.status || "unknown"} />
                  </div>
                  {dep.service_health && dep.service_health.length > 0 && (
                    <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3">
                      {dep.service_health.map((svc, i) => (
                        <div key={i} className="rounded bg-carbon px-2 py-1 text-xs">
                          <span className="text-soft-white/60">{svc.service_name}: </span>
                          <StatusBadge status={svc.status || "unknown"} />
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
              {(!data.deployments || data.deployments.length === 0) && (
                <div className="rounded-lg border border-border bg-surface p-6 text-center text-soft-white/40">
                  No deployments yet.{" "}
                  <Link href="/onboarding" className="text-signal-orange hover:underline">
                    Start one →
                  </Link>
                </div>
              )}
            </div>
          )}

          {activeTab === "billing" && (
            <div className="space-y-6">
              <h1 className="font-display text-2xl font-bold">Billing</h1>
              {billing?.entitlement && (
                <div className="rounded-lg border border-border bg-surface p-4">
                  <span className="text-sm text-soft-white/60">Plan Status: </span>
                  <StatusBadge status={billing.entitlement.state} />
                </div>
              )}
              {billing?.subscriptions && billing.subscriptions.length > 0 ? (
                billing.subscriptions.map((sub, i) => (
                  <div key={i} className="rounded-lg border border-border bg-surface p-4 text-sm">
                    <p>Subscription: <span className="text-soft-white">{sub.subscription_id || "—"}</span></p>
                    <p>Status: <StatusBadge status={sub.status || "unknown"} /></p>
                  </div>
                ))
              ) : (
                <p className="text-soft-white/40">No active subscriptions.</p>
              )}
            </div>
          )}

          {activeTab === "services" && data && (
            <div className="space-y-6">
              <h1 className="font-display text-2xl font-bold">Services</h1>
              <p className="text-sm text-soft-white/60">
                Deep links to your deployment services. Available once provisioning completes.
              </p>
              {data.deployments?.map((dep) => (
                <div key={dep.deployment_id} className="rounded-lg border border-border bg-surface p-4">
                  <h3 className="font-display font-semibold mb-3">{dep.hostname || dep.deployment_id}</h3>
                  <div className="grid gap-2 sm:grid-cols-2">
                    {["Hermes", "Files (Nextcloud)", "Code (code-server)", "Bot Setup", "Health"].map(
                      (svc) => (
                        <div
                          key={svc}
                          className="rounded border border-border bg-carbon px-3 py-2 text-sm text-soft-white/60"
                        >
                          {svc} — <span className="text-soft-white/30">link available after provisioning</span>
                        </div>
                      ),
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
