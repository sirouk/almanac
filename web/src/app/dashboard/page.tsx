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
  entitlement?: { state: string; updated_at?: string };
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

function isGoodStatus(status = "") {
  return ["healthy", "active", "paid", "contacted", "recorded", "complete", "completed", "success", "ready", "running"].includes(status.toLowerCase());
}

function healthSummary(deployments: Deployment[] = []) {
  const services = deployments.flatMap((deployment) => deployment.service_health || []);
  const healthy = services.filter((service) => isGoodStatus(service.status)).length;
  const attention = services.filter((service) => service.status && !isGoodStatus(service.status)).length;
  return { total: services.length, healthy, attention };
}

function deploymentTitle(dep: Deployment) {
  return dep.hostname || (dep.prefix && dep.base_domain ? `${dep.prefix}.${dep.base_domain}` : dep.deployment_id);
}

function formatDate(value?: string) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

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
  }, [router]);

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <LoadingSpinner label="Loading dashboard..." />
      </div>
    );
  }

  const deployments = data?.deployments ?? [];
  const activeDeployment = deployments[0];
  const health = healthSummary(deployments);
  const entitlementState = data?.entitlement?.state || billing?.entitlement?.state || "unknown";

  return (
    <div className="flex min-h-screen flex-col bg-jet/70">
      <nav className="sticky top-0 z-20 flex items-center justify-between border-b border-border/80 bg-jet/90 px-4 py-3 backdrop-blur md:px-6">
        <Link href="/" className="flex items-center gap-3 font-display tracking-wide">
          <span className="flex h-9 w-9 items-center justify-center border border-signal-orange/40 bg-signal-orange/10 text-sm font-bold text-signal-orange">R</span>
          <span className="text-lg font-bold"><span className="text-signal-orange">ARC</span>LINK</span>
          <span className="hidden rounded-full border border-border bg-surface px-2 py-0.5 text-[10px] uppercase tracking-wide text-soft-white/45 sm:inline-flex">User console</span>
        </Link>
        <div className="flex items-center gap-3 text-sm">
          {data?.user && <span className="hidden text-soft-white/50 md:inline">{data.user.email}</span>}
          <Link href="/admin" className="rounded border border-border px-3 py-1.5 text-soft-white/55 transition hover:border-signal-orange/50 hover:text-soft-white">Admin</Link>
          <button onClick={handleLogout} className="rounded border border-border px-3 py-1.5 text-soft-white/55 transition hover:border-red-400/50 hover:text-red-300">Sign Out</button>
        </div>
      </nav>

      <div className="flex flex-1">
        <aside className="hidden w-64 shrink-0 border-r border-border/70 bg-carbon/35 p-4 md:block">
          <div className="mb-5 border border-border bg-surface/70 p-3">
            <p className="text-[10px] uppercase tracking-[0.2em] text-soft-white/35">Agent</p>
            <p className="mt-1 truncate font-display text-sm font-semibold">{activeDeployment ? deploymentTitle(activeDeployment) : "No active agent"}</p>
            <div className="mt-3"><StatusBadge status={activeDeployment?.status || "standby"} /></div>
          </div>
          <nav className="space-y-1">
            {ALL_TABS.map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`block w-full border px-3 py-2 text-left text-sm capitalize transition ${
                  activeTab === tab ? "border-signal-orange/50 bg-signal-orange/10 text-signal-orange" : "border-transparent text-soft-white/55 hover:border-border hover:bg-surface/70 hover:text-soft-white"
                }`}
              >
                {tab}
              </button>
            ))}
          </nav>
        </aside>

        <main className="flex-1 overflow-x-hidden p-4 md:p-6">
          {error && (
            <ErrorAlert message={error} className="mb-6 py-3" />
          )}

          <section className="mb-6 border border-border/80 bg-surface/85 p-4 shadow-2xl shadow-black/30 md:p-6">
            <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
              <div>
                <p className="text-xs uppercase tracking-[0.22em] text-signal-orange">Raven console</p>
                <h1 className="mt-2 font-display text-3xl font-bold tracking-tight md:text-4xl">
                  {data?.user?.display_name || "ArcLink Operator"}
                </h1>
                <p className="mt-2 max-w-2xl text-sm leading-6 text-soft-white/60">
                  Your private agent workspace, service links, model lane, memory rail, billing state, and launch health in one place.
                </p>
              </div>
              <div className="grid grid-cols-3 gap-2 text-right sm:min-w-[26rem]">
                <ConsoleMetric label="Agents" value={deployments.length} />
                <ConsoleMetric label="Services" value={health.total} />
                <ConsoleMetric label="Attention" value={health.attention} tone={health.attention ? "warn" : "good"} />
              </div>
            </div>
            <div className="mt-5 grid gap-3 md:grid-cols-3">
              <SignalPanel label="Account" value={entitlementState} />
              <SignalPanel label="Primary agent" value={activeDeployment ? deploymentTitle(activeDeployment) : "Not launched"} />
              <SignalPanel label="Service posture" value={`${health.healthy}/${health.total || 0} healthy`} good={health.attention === 0 && health.total > 0} />
            </div>
          </section>

          <div className="mb-6 flex gap-2 overflow-x-auto md:hidden">
            {ALL_TABS.map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`shrink-0 border px-3 py-1.5 text-xs capitalize ${
                  activeTab === tab ? "border-signal-orange bg-signal-orange text-jet" : "border-border bg-surface text-soft-white/60"
                }`}
              >
                {tab}
              </button>
            ))}
          </div>

          {activeTab === "overview" && data && (
            <div className="space-y-6">
              <SectionHeader title="Mission Overview" eyebrow="Current state" detail="Raven keeps the launch board human-readable while the raw service signals remain visible below." />
              <div className="grid gap-4 lg:grid-cols-3">
                <InfoPanel title="Entitlement" value={data.entitlement?.state || "unknown"} detail={data.entitlement?.updated_at ? `Updated ${formatDate(data.entitlement.updated_at)}` : "Billing signal from ArcLink control."} />
                <InfoPanel title="Primary Agent" value={activeDeployment ? deploymentTitle(activeDeployment) : "Not launched"} detail={activeDeployment?.deployment_id || "Start launch to create the first private workspace."} />
                <InfoPanel title="Service Health" value={`${health.healthy}/${health.total || 0}`} detail={health.attention ? `${health.attention} service signals need attention.` : "All reported services are clear."} />
              </div>
              {data.deployments?.map((dep) => (
                <DeploymentOverview key={dep.deployment_id} dep={dep} />
              ))}
              {(!data.deployments || data.deployments.length === 0) && (
                <div className="border border-border bg-surface/80 p-6 text-center text-soft-white/45">
                  No deployments yet.{" "}
                  <Link href="/onboarding" className="text-signal-orange hover:underline">
                    Start launch
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
                    <p>Subscription: <span className="text-soft-white">{sub.subscription_id || "-"}</span></p>
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
                            <span className="font-mono">{job.job_id || "-"}</span>{" "}
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
                const urls = dep.access?.urls || {};
                const services = [
                  { name: "Hermes", href: urls.hermes || (provisioned && host ? `https://${host}:8443/` : "") },
                  { name: "Drive", href: urls.files || (provisioned && host ? `https://${host}:8443/drive` : "") },
                  { name: "Code", href: urls.code || (provisioned && host ? `https://${host}:8443/code` : "") },
                  { name: "Health", href: urls.dashboard || (provisioned && host ? `https://${host}/u/${dep.prefix || dep.deployment_id}` : "") },
                ];
                return (
                  <DeploymentCard key={dep.deployment_id} dep={dep}>
                    <div className="grid gap-2 sm:grid-cols-2">
                      {services.map((svc) =>
                        svc.href ? (
                          <a
                            key={svc.name}
                            href={svc.href}
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
                            {svc.name} - <span className="text-soft-white/30">link available after provisioning</span>
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
              <h1 className="font-display text-2xl font-bold">Drive</h1>
              <p className="text-sm text-soft-white/60">
                Per-deployment workspace and vault access through the authenticated Hermes dashboard.
              </p>
              {data.deployments?.map((dep) => {
                const host = dep.hostname || "";
                const provisioned = dep.status === "active" || dep.status === "running";
                const vaultHealth = dep.service_health?.find((s) => s.service_name === "nextcloud");
                const vaultUrl = dep.access?.urls?.files || (provisioned && host ? `https://${host}:8443/drive` : "");
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
                            Open Drive →
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
                        <p className="text-sm text-soft-white">{bot?.channel || "-"}</p>
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
                        <p><span className="text-soft-white/60">Provider:</span> {model.provider || "-"}</p>
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

function SectionHeader({ title, eyebrow, detail }: { title: string; eyebrow?: string; detail?: string }) {
  return (
    <div>
      {eyebrow && <p className="text-xs uppercase tracking-[0.22em] text-signal-orange">{eyebrow}</p>}
      <h2 className="mt-1 font-display text-2xl font-bold">{title}</h2>
      {detail && <p className="mt-2 max-w-3xl text-sm leading-6 text-soft-white/55">{detail}</p>}
    </div>
  );
}

function ConsoleMetric({ label, value, tone = "neutral" }: { label: string; value: number | string; tone?: "neutral" | "good" | "warn" }) {
  const color = tone === "good" ? "text-neon-green" : tone === "warn" ? "text-yellow-300" : "text-soft-white";
  return (
    <div className="border border-border bg-carbon/70 px-3 py-2">
      <p className="text-[10px] uppercase tracking-wide text-soft-white/35">{label}</p>
      <p className={`font-display text-2xl font-bold ${color}`}>{value}</p>
    </div>
  );
}

function SignalPanel({ label, value, good }: { label: string; value: string; good?: boolean }) {
  return (
    <div className="border border-border bg-carbon/70 p-3">
      <p className="text-[10px] uppercase tracking-wide text-soft-white/35">{label}</p>
      <p className={`mt-1 truncate text-sm font-semibold ${good ? "text-neon-green" : "text-soft-white"}`}>{value}</p>
    </div>
  );
}

function InfoPanel({ title, value, detail }: { title: string; value: string; detail?: string }) {
  return (
    <div className="border border-border bg-surface/80 p-4">
      <p className="text-xs uppercase tracking-[0.18em] text-soft-white/35">{title}</p>
      <p className="mt-3 font-display text-2xl font-semibold">{value.replaceAll("_", " ")}</p>
      {detail && <p className="mt-2 text-xs leading-5 text-soft-white/45">{detail}</p>}
    </div>
  );
}

function DeploymentOverview({ dep }: { dep: Deployment }) {
  const services = dep.service_health || [];
  const urls = dep.access?.urls || {};
  return (
    <div className="border border-border bg-surface/85 p-4">
      <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
        <div className="min-w-0">
          <p className="text-xs uppercase tracking-[0.18em] text-signal-orange">Private agent</p>
          <h3 className="mt-1 truncate font-display text-xl font-semibold">{deploymentTitle(dep)}</h3>
          <p className="mt-1 break-all font-mono text-xs text-soft-white/35">{dep.deployment_id}</p>
        </div>
        <StatusBadge status={dep.status || "unknown"} />
      </div>
      <div className="mt-4 grid gap-3 lg:grid-cols-[1.2fr_0.8fr]">
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          {services.length ? services.map((svc, i) => (
            <div key={`${svc.service_name}-${i}`} className="border border-border/70 bg-carbon/80 p-2">
              <p className="truncate text-xs text-soft-white/50">{svc.service_name}</p>
              <div className="mt-2"><StatusBadge status={svc.status || "unknown"} /></div>
              {svc.checked_at && <p className="mt-1 truncate text-[10px] text-soft-white/30">{formatDate(svc.checked_at)}</p>}
            </div>
          )) : (
            <p className="col-span-full text-sm text-soft-white/40">No service health signals yet.</p>
          )}
        </div>
        <div className="border border-border/70 bg-carbon/80 p-3">
          <p className="text-xs uppercase tracking-wide text-soft-white/35">Access</p>
          <div className="mt-3 grid gap-2">
            {Object.entries(urls).length ? Object.entries(urls).map(([key, value]) => (
              <a key={key} href={value} target="_blank" rel="noopener noreferrer" className="flex items-center justify-between border border-border bg-jet/45 px-3 py-2 text-sm text-soft-white/75 transition hover:border-signal-orange/60 hover:text-signal-orange">
                <span className="capitalize">{key.replaceAll("_", " ")}</span>
                <span className="text-xs text-soft-white/35">open</span>
              </a>
            )) : (
              <p className="text-sm text-soft-white/40">Links appear once provisioning completes.</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function DeploymentCard({ dep, children }: { dep: { deployment_id: string; hostname?: string }; children: React.ReactNode }) {
  return (
    <div className="border border-border bg-surface/85 p-4">
      <h3 className="mb-3 font-display font-semibold">{dep.hostname || dep.deployment_id}</h3>
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
