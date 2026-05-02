"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { StatusBadge, ErrorAlert, LoadingSpinner } from "@/components/ui";

interface ServiceHealth {
  service_name: string;
  status: string;
  checked_at?: string;
}

interface BotContact {
  channel?: string;
  status?: string;
  first_contacted?: boolean;
  handoff_recorded?: boolean;
}

interface AccessUrls {
  urls?: Record<string, string>;
}

interface Deployment {
  deployment_id: string;
  hostname?: string;
  prefix?: string;
  base_domain?: string;
  status: string;
  service_health?: ServiceHealth[];
  model?: { provider: string; model_id: string; credential_state: string };
  freshness?: { qmd: { status: string; checked_at: string }; memory: { status: string; checked_at: string } };
  bot_contact?: BotContact;
  access?: AccessUrls;
}

interface UserData {
  user?: { user_id: string; email: string; display_name: string };
  deployments?: Deployment[];
  entitlement?: { state: string };
}

interface ProvisioningDeployment {
  deployment_id: string;
  hostname: string;
  status: string;
  service_health?: ServiceHealth[];
  provisioning_jobs?: Record<string, string>[];
}

interface BillingData {
  entitlement?: { state: string };
  subscriptions?: Record<string, string>[];
}

type Tab = "overview" | "billing" | "provisioning" | "services" | "vault" | "bots" | "model" | "memory" | "security" | "support";
const ALL_TABS: Tab[] = ["overview", "billing", "provisioning", "services", "vault", "bots", "model", "memory", "security", "support"];

export default function DashboardPage() {
  const [data, setData] = useState<UserData | null>(null);
  const [billing, setBilling] = useState<BillingData | null>(null);
  const [provisioning, setProvisioning] = useState<{ deployments?: ProvisioningDeployment[] } | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [activeTab, setActiveTab] = useState<Tab>("overview");
  const router = useRouter();

  async function handleLogout() {
    await api.logout("user");
    router.push("/login");
  }

  useEffect(() => {
    let mounted = true;
    Promise.all([
      api.userDashboard().then((r) => {
        if (!mounted) return;
        if (r.status === 200) setData(r.data as UserData);
        else if (r.status === 401) router.push("/login");
        else setError("Failed to load dashboard.");
      }),
      api.userBilling().then((r) => {
        if (mounted && r.status === 200) setBilling(r.data as BillingData);
      }),
      api.userProvisioning().then((r) => {
        if (mounted && r.status === 200) setProvisioning(r.data as { deployments?: ProvisioningDeployment[] });
      }),
    ]).catch(() => {
      if (mounted) setError("Failed to load dashboard.");
    }).finally(() => {
      if (mounted) setLoading(false);
    });
    return () => { mounted = false; };
  }, []);

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <LoadingSpinner label="Loading dashboard..." />
      </div>
    );
  }

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
          <button onClick={handleLogout} className="text-soft-white/40 hover:text-red-400">Sign Out</button>
        </div>
      </nav>

      <div className="flex flex-1">
        {/* Sidebar */}
        <aside className="hidden w-56 shrink-0 border-r border-border p-4 md:block">
          <nav className="space-y-1">
            {ALL_TABS.map((tab) => (
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
            <ErrorAlert message={error} className="mb-6 py-3" />
          )}

          {/* Mobile tab bar — scrollable to fit all tabs */}
          <div className="mb-6 flex gap-2 overflow-x-auto md:hidden">
            {ALL_TABS.map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`shrink-0 rounded px-3 py-1 text-xs capitalize ${
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
              <PortalLinkButton />
            </div>
          )}

          {activeTab === "provisioning" && (
            <div className="space-y-6">
              <h1 className="font-display text-2xl font-bold">Provisioning</h1>
              {provisioning?.deployments?.length ? (
                provisioning.deployments.map((dep) => (
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
                    {dep.provisioning_jobs && dep.provisioning_jobs.length > 0 && (
                      <div className="mt-3 space-y-1">
                        <p className="text-xs text-soft-white/40">Provisioning Jobs:</p>
                        {dep.provisioning_jobs.map((job, i) => (
                          <div key={i} className="rounded bg-carbon px-2 py-1 text-xs">
                            <span className="font-mono">{job.job_id || "—"}</span>{" "}
                            <StatusBadge status={job.status || "unknown"} />
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                ))
              ) : (
                <p className="text-soft-white/40">No provisioning data available.</p>
              )}
            </div>
          )}

          {activeTab === "services" && data && (
            <div className="space-y-6">
              <h1 className="font-display text-2xl font-bold">Services</h1>
              <p className="text-sm text-soft-white/60">
                Deep links to your deployment services. Available once provisioning completes.
              </p>
              {data.deployments?.map((dep) => {
                const host = dep.hostname || "";
                const provisioned = dep.status === "active" || dep.status === "running";
                const services = [
                  { name: "Hermes", path: "/hermes" },
                  { name: "Files (Nextcloud)", path: ":8443" },
                  { name: "Code (code-server)", path: ":8080" },
                  { name: "Bot Setup", path: "/bot" },
                  { name: "Health", path: "/health" },
                ];
                return (
                  <DeploymentCard key={dep.deployment_id} dep={dep}>
                    <div className="grid gap-2 sm:grid-cols-2">
                      {services.map((svc) =>
                        provisioned && host ? (
                          <a
                            key={svc.name}
                            href={`https://${host}${svc.path}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="rounded border border-border bg-carbon px-3 py-2 text-sm text-signal-orange hover:opacity-80 transition"
                          >
                            {svc.name} →
                          </a>
                        ) : (
                          <div
                            key={svc.name}
                            className="rounded border border-border bg-carbon px-3 py-2 text-sm text-soft-white/60"
                          >
                            {svc.name} — <span className="text-soft-white/30">link available after provisioning</span>
                          </div>
                        ),
                      )}
                    </div>
                  </DeploymentCard>
                );
              })}
              {(!data.deployments || data.deployments.length === 0) && (
                <NoDeployments message="No deployments. Service links available after provisioning." />
              )}
            </div>
          )}

          {activeTab === "vault" && data && (
            <div className="space-y-6">
              <h1 className="font-display text-2xl font-bold">Vault &amp; Files</h1>
              <p className="text-sm text-soft-white/60">
                Per-deployment Nextcloud file vault for documents, configs, and persistent storage.
              </p>
              {data.deployments?.map((dep) => {
                const host = dep.hostname || "";
                const provisioned = dep.status === "active" || dep.status === "running";
                const vaultHealth = dep.service_health?.find((s) => s.service_name === "nextcloud");
                const vaultUrl = dep.access?.urls?.files || (provisioned && host ? `https://${host}:8443` : "");
                return (
                  <DeploymentCard key={dep.deployment_id} dep={dep}>
                    <div className="grid gap-3 sm:grid-cols-2">
                      <div className="rounded bg-carbon px-3 py-2">
                        <p className="text-xs text-soft-white/60">Vault Status</p>
                        <StatusBadge status={vaultHealth?.status || (provisioned ? "pending" : "not provisioned")} />
                        {vaultHealth?.checked_at && (
                          <p className="mt-1 text-xs text-soft-white/30">Last check: {vaultHealth.checked_at}</p>
                        )}
                      </div>
                      <div className="rounded bg-carbon px-3 py-2">
                        <p className="text-xs text-soft-white/60">Access</p>
                        {vaultUrl ? (
                          <a href={vaultUrl} target="_blank" rel="noopener noreferrer" className="text-sm text-signal-orange hover:underline">
                            Open Files →
                          </a>
                        ) : (
                          <p className="text-sm text-soft-white/30">Available after provisioning</p>
                        )}
                      </div>
                    </div>
                  </DeploymentCard>
                );
              })}
              {(!data.deployments || data.deployments.length === 0) && (
                <NoDeployments message="No deployments. Vault access available after provisioning." />
              )}
            </div>
          )}

          {activeTab === "bots" && data && (
            <div className="space-y-6">
              <h1 className="font-display text-2xl font-bold">Bot Status</h1>
              <p className="text-sm text-soft-white/60">
                Telegram and Discord bot onboarding and connection state per deployment.
              </p>
              {data.deployments?.map((dep) => {
                const bot = dep.bot_contact;
                const botHealth = dep.service_health?.filter((s) =>
                  s.service_name === "telegram-bot" || s.service_name === "discord-bot"
                );
                return (
                  <DeploymentCard key={dep.deployment_id} dep={dep}>
                    <div className="grid gap-3 sm:grid-cols-2">
                      <div className="rounded bg-carbon px-3 py-2">
                        <p className="text-xs text-soft-white/60">Onboarding Channel</p>
                        <p className="text-sm text-soft-white">{bot?.channel || "—"}</p>
                      </div>
                      <div className="rounded bg-carbon px-3 py-2">
                        <p className="text-xs text-soft-white/60">Contact Status</p>
                        <StatusBadge status={bot?.first_contacted ? "contacted" : "pending"} />
                      </div>
                      <div className="rounded bg-carbon px-3 py-2">
                        <p className="text-xs text-soft-white/60">Handoff</p>
                        <StatusBadge status={bot?.handoff_recorded ? "recorded" : "pending"} />
                      </div>
                      {botHealth && botHealth.length > 0 && botHealth.map((bh, i) => (
                        <div key={i} className="rounded bg-carbon px-3 py-2">
                          <p className="text-xs text-soft-white/60">{bh.service_name}</p>
                          <StatusBadge status={bh.status || "unknown"} />
                          {bh.checked_at && (
                            <p className="mt-1 text-xs text-soft-white/30">Last: {bh.checked_at}</p>
                          )}
                        </div>
                      ))}
                    </div>
                  </DeploymentCard>
                );
              })}
              {(!data.deployments || data.deployments.length === 0) && (
                <NoDeployments message="No deployments. Bot status available after onboarding." />
              )}
            </div>
          )}

          {activeTab === "model" && data && (
            <div className="space-y-6">
              <h1 className="font-display text-2xl font-bold">Model &amp; Skills</h1>
              {data.deployments?.map((dep) => {
                const model = dep.model;
                return (
                  <DeploymentCard key={dep.deployment_id} dep={dep}>
                    {model ? (
                      <div className="space-y-2 text-sm">
                        <p><span className="text-soft-white/60">Provider:</span> {model.provider || "—"}</p>
                        <p><span className="text-soft-white/60">Model:</span> {model.model_id || "default"}</p>
                        <p><span className="text-soft-white/60">Credential:</span> <StatusBadge status={model.credential_state || "pending"} /></p>
                      </div>
                    ) : (
                      <p className="text-soft-white/40">Model configuration available after provisioning.</p>
                    )}
                    <p className="mt-3 text-xs text-soft-white/30">Skills, BYOK, and provider catalog managed through deployment config.</p>
                  </DeploymentCard>
                );
              })}
              {(!data.deployments || data.deployments.length === 0) && (
                <NoDeployments message="No deployments. Model settings available after provisioning." />
              )}
            </div>
          )}

          {activeTab === "memory" && data && (
            <div className="space-y-6">
              <h1 className="font-display text-2xl font-bold">Memory &amp; QMD</h1>
              {data.deployments?.map((dep) => {
                const freshness = dep.freshness;
                return (
                  <DeploymentCard key={dep.deployment_id} dep={dep}>
                    <div className="grid gap-3 sm:grid-cols-2">
                      <div className="rounded bg-carbon px-3 py-2">
                        <p className="text-xs text-soft-white/60">QMD (Retrieval)</p>
                        <StatusBadge status={freshness?.qmd?.status || "unknown"} />
                        {freshness?.qmd?.checked_at && (
                          <p className="mt-1 text-xs text-soft-white/30">Last: {freshness.qmd.checked_at}</p>
                        )}
                      </div>
                      <div className="rounded bg-carbon px-3 py-2">
                        <p className="text-xs text-soft-white/60">Memory Synthesis</p>
                        <StatusBadge status={freshness?.memory?.status || "unknown"} />
                        {freshness?.memory?.checked_at && (
                          <p className="mt-1 text-xs text-soft-white/30">Last: {freshness.memory.checked_at}</p>
                        )}
                      </div>
                    </div>
                  </DeploymentCard>
                );
              })}
              {(!data.deployments || data.deployments.length === 0) && (
                <NoDeployments message="No deployments. Memory data available after provisioning." />
              )}
            </div>
          )}

          {activeTab === "security" && (
            <div className="space-y-6">
              <h1 className="font-display text-2xl font-bold">Security</h1>
              <div className="rounded-lg border border-border bg-surface p-4 text-sm text-soft-white/60">
                <p>Session authentication uses hashed tokens with HttpOnly cookie transport.</p>
                <p className="mt-2">CSRF protection is enforced on all mutation endpoints.</p>
                <p className="mt-2">Secret references are never exposed in dashboard responses.</p>
              </div>
              <div className="rounded-lg border border-border bg-surface p-4">
                <h3 className="font-display font-semibold mb-3">Session Controls</h3>
                <p className="text-sm text-soft-white/60 mb-3">
                  You are currently signed in. Use the button below to end this session.
                </p>
                <button
                  onClick={handleLogout}
                  className="rounded border border-red-500/40 bg-red-900/20 px-4 py-2 text-sm text-red-300 transition hover:bg-red-900/40"
                >
                  Sign Out
                </button>
              </div>
              <p className="text-xs text-soft-white/30">
                Password change, MFA setup, and API key management available when live auth provider is connected.
              </p>
            </div>
          )}

          {activeTab === "support" && (
            <div className="space-y-6">
              <h1 className="font-display text-2xl font-bold">Support</h1>
              <div className="rounded-lg border border-border bg-surface p-4 text-sm text-soft-white/60">
                <p>For deployment issues, contact the ArcLink admin team.</p>
                <p className="mt-2">System status is visible in the Service Health and Provisioning tabs.</p>
                <p className="mt-2">Admin actions (restart, reprovision, DNS repair) are queued with reason tracking and audit logs.</p>
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}

function DeploymentCard({ dep, children }: { dep: { deployment_id: string; hostname?: string }; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <h3 className="font-display font-semibold mb-3">{dep.hostname || dep.deployment_id}</h3>
      {children}
    </div>
  );
}

function NoDeployments({ message }: { message?: string }) {
  return <p className="text-soft-white/40">{message || "No deployments."}</p>;
}

function PortalLinkButton() {
  const [loading, setLoading] = useState(false);
  const [portalUrl, setPortalUrl] = useState("");

  async function handlePortal() {
    setLoading(true);
    try {
      const res = await api.userPortal({ return_url: window.location.href });
      if (res.status === 200) {
        const url = (res.data as Record<string, string>).portal_url;
        if (url) setPortalUrl(url);
      }
    } catch { /* ignore */ }
    setLoading(false);
  }

  if (portalUrl) {
    return (
      <a
        href={portalUrl}
        className="inline-block rounded bg-signal-orange px-4 py-2 text-sm font-semibold text-jet transition hover:opacity-90"
      >
        Open Billing Portal →
      </a>
    );
  }

  return (
    <button
      onClick={handlePortal}
      disabled={loading}
      className="rounded border border-border bg-surface px-4 py-2 text-sm text-soft-white/60 transition hover:text-soft-white disabled:opacity-50"
    >
      {loading ? "Loading..." : "Manage Billing →"}
    </button>
  );
}
