"use client";

import { type FormEvent, useEffect, useState } from "react";
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

interface NotionSetup {
  status?: string;
  model?: string;
  callback_url?: string;
  public_status?: string;
  requested_at?: string;
  ready_at?: string;
  webhook?: {
    configured?: boolean;
    verified?: boolean;
    installed_at?: string;
    verified_at?: string;
    armed?: boolean;
    armed_until?: string;
  };
  index?: { status?: string };
  verification?: {
    dashboard?: string;
    email_share?: string;
    live_workspace?: string;
  };
}

interface BillingLifecycle {
  payment_state?: string;
  provider_access?: string;
  warning_cadence?: string;
  grace_period?: string;
  data_retention?: string;
  purge_policy?: string;
  reason?: string;
}

interface Deployment {
  deployment_id: string;
  agent_name?: string;
  agent_label?: string;
  agent_title?: string;
  hostname?: string;
  prefix?: string;
  base_domain?: string;
  status: string;
  service_health?: ServiceHealth[];
  model?: { provider: string; model_id: string; credential_state: string; billing_lifecycle?: BillingLifecycle };
  freshness?: { qmd: { status: string; checked_at: string }; memory: { status: string; checked_at: string } };
  notion_setup?: NotionSetup;
  bot_contact?: BotContact;
  access?: AccessUrls;
  sections?: DeploymentSection[];
  recent_events?: DeploymentEvent[];
}

interface DeploymentSection {
  section: string;
  label?: string;
  status?: string;
}

interface DeploymentEvent {
  event_id?: string;
  event_type?: string;
  created_at?: string;
}

interface UserData {
  user?: { user_id: string; email: string; display_name: string };
  deployments?: Deployment[];
  entitlement?: { state: string; updated_at?: string };
  wrapped?: WrappedData;
}

interface WrappedReport {
  report_id: string;
  period: string;
  period_start: string;
  period_end: string;
  status: string;
  novelty_score: number;
  created_at: string;
  delivered_at?: string;
  stats?: { key?: string; label?: string; value?: string | number; detail?: string }[];
  plain_text?: string;
  markdown?: string;
}

interface WrappedData {
  wrapped_frequency?: "daily" | "weekly" | "monthly";
  reports?: WrappedReport[];
}

interface ProvisioningDeployment {
  deployment_id: string;
  hostname: string;
  status: string;
  service_health?: ServiceHealth[];
  provisioning_jobs?: Record<string, string>[];
}

interface BillingData {
  entitlement?: { state: string; renewal_lifecycle?: BillingLifecycle };
  subscriptions?: Record<string, string>[];
  renewal_lifecycle?: BillingLifecycle;
}

interface CredentialHandoff {
  handoff_id: string;
  deployment_id: string;
  credential_kind: string;
  display_name: string;
  status: string;
  secret_ref?: string;
  reveal_mode?: string;
  delivery_hint?: string;
  copy_guidance?: string;
}

interface CredentialsData {
  instructions?: { copy?: string; acknowledge?: string; reissue?: string };
  credentials?: CredentialHandoff[];
  removed_count?: number;
}

interface LinkedResource {
  grant_id: string;
  owner_user_id: string;
  resource_kind: string;
  owner_deployment_id?: string;
  recipient_deployment_id?: string;
  resource_root: string;
  resource_path: string;
  linked_root?: string;
  linked_path?: string;
  projection?: {
    status?: string;
    linked_path?: string;
    entry_path?: string;
    read_only?: boolean;
    materialized_at?: string;
    removed_at?: string;
    reason?: string;
  };
  display_name?: string;
  access_mode: string;
  status: string;
  accepted_at?: string;
  reshare_allowed?: boolean;
}

interface LinkedResourcesData {
  linked_resources?: LinkedResource[];
}

interface CommsMessage {
  message_id: string;
  sender_deployment_id: string;
  recipient_deployment_id: string;
  body?: string;
  status: string;
  created_at?: string;
  delivered_at?: string;
}

interface CommsData {
  comms?: CommsMessage[];
}

interface ThresholdContinuation {
  status?: string;
  dashboard_guidance?: string;
  raven_notifications?: string;
  provider_fallback?: string;
  overage_refill?: string;
  warning_cadence?: string;
  reason?: string;
}

interface ProviderDeploymentModel {
  deployment_id: string;
  model_id?: string;
  credential_state?: string;
  allow_inference?: boolean;
  provider_detail?: {
    reason?: string;
    budget?: {
      status?: string;
      monthly_cents?: number;
      used_cents?: number;
      remaining_cents?: number;
      usage_percent?: number;
    };
    credential_lifecycle?: {
      current_mode?: string;
      posture?: string;
      live_key_creation?: string;
    };
    billing_lifecycle?: BillingLifecycle;
    threshold_continuation?: ThresholdContinuation;
  };
}

interface ProviderSettings {
  self_service_provider_add?: string;
  dashboard_mutation?: string;
  current_change_path?: string;
  secret_input_policy?: string;
  live_provider_mutation?: string;
  operator_decision_needed?: string;
  guidance?: string;
}

interface ProviderStateData {
  provider?: string;
  default_model?: string;
  provider_boundary?: {
    credential_isolation?: string;
    operator_shared_key_policy?: string;
    budget_enforcement?: string;
    live_key_creation?: string;
    threshold_continuation?: ThresholdContinuation;
  };
  provider_settings?: ProviderSettings;
  deployment_models?: ProviderDeploymentModel[];
}

interface CrewRecipe {
  recipe_id?: string;
  preset?: string;
  capacity?: string;
  role?: string;
  mission?: string;
  treatment?: string;
  applied_at?: string;
  status?: string;
  soul_overlay?: { crew_recipe_text?: string };
}

interface CrewRecipeState {
  current?: CrewRecipe | null;
  prior?: CrewRecipe | null;
  whats_changed?: { status?: string; summary?: string };
}

interface CrewRecipePreview {
  mode?: string;
  fallback?: boolean;
  fallback_reason?: string;
  recipe_text?: string;
}

interface CrewRecipeForm {
  [key: string]: string;
  role: string;
  mission: string;
  treatment: string;
  preset: string;
  capacity: string;
}

const DEFAULT_CREW_FORM: CrewRecipeForm = {
  role: "",
  mission: "",
  treatment: "Like a peer - casual, give pushback",
  preset: "Frontier",
  capacity: "development",
};
const CREW_TREATMENT_OPTIONS = [
  "Like a Captain - formal, ready to take orders",
  "Like a peer - casual, give pushback",
  "Like a coach - supportive, ask great questions",
];
const CREW_PRESET_OPTIONS = ["Frontier", "Concourse", "Salvage", "Vanguard"];
const CREW_CAPACITY_OPTIONS = [
  { label: "Sales", value: "sales" },
  { label: "Marketing", value: "marketing" },
  { label: "Development", value: "development" },
  { label: "Life Coaching", value: "life coaching" },
  { label: "Companionship", value: "companionship" },
];

type Tab = "overview" | "crew" | "billing" | "provisioning" | "services" | "vault" | "wrapped" | "comms" | "bots" | "model" | "memory" | "security" | "support";
const ALL_TABS: Tab[] = ["overview", "crew", "billing", "provisioning", "services", "vault", "wrapped", "comms", "bots", "model", "memory", "security", "support"];

function isGoodStatus(status = "") {
  return ["healthy", "active", "paid", "contacted", "recorded", "complete", "completed", "success", "ready", "running"].includes(status.toLowerCase());
}

function isAttentionStatus(status = "") {
  const normalized = status.toLowerCase();
  return ["attention", "blocked", "degraded", "failed", "unhealthy", "error", "drift", "past_due", "billing_suspended", "budget_warning", "budget_exhausted"].some((marker) =>
    normalized.includes(marker),
  );
}

function healthSummary(deployments: Deployment[] = []) {
  const services = deployments.flatMap((deployment) => deployment.service_health || []);
  const healthy = services.filter((service) => isGoodStatus(service.status)).length;
  const attention = services.filter((service) => service.status && !isGoodStatus(service.status)).length;
  return { total: services.length, healthy, attention };
}

function deploymentRank(dep: Deployment) {
  const status = (dep.status || "").toLowerCase();
  if (["active", "running", "ready", "healthy"].includes(status)) return 0;
  if (["provisioning", "provisioning_ready", "starting", "pending"].includes(status)) return 1;
  if (["entitlement_required", "blocked", "failed", "unhealthy"].includes(status)) return 3;
  return 2;
}

function orderedDeployments(deployments: Deployment[] = []) {
  return [...deployments].sort((a, b) => {
    const rankDelta = deploymentRank(a) - deploymentRank(b);
    if (rankDelta !== 0) return rankDelta;
    return deploymentTitle(a).localeCompare(deploymentTitle(b));
  });
}

function deploymentTitle(dep: Deployment) {
  return dep.agent_label || dep.hostname || (dep.prefix && dep.base_domain ? `${dep.prefix}.${dep.base_domain}` : dep.deployment_id);
}

function deploymentHost(dep: Deployment) {
  return dep.hostname || (dep.prefix && dep.base_domain ? `${dep.prefix}.${dep.base_domain}` : "");
}

function urlJoin(base: string, path = "") {
  const cleanBase = (base || "").trim();
  if (!cleanBase) return "";
  if (!path) return cleanBase;
  return `${cleanBase.replace(/\/+$/, "")}/${path.replace(/^\/+/, "")}`;
}

function hermesBaseUrl(dep: Deployment) {
  const urls = dep.access?.urls || {};
  if (urls.hermes) return urls.hermes;
  if (urls.dashboard) return urls.dashboard;
  return "";
}

function hermesPluginLinks(dep: Deployment) {
  const urls = dep.access?.urls || {};
  const base = hermesBaseUrl(dep);
  const dashboard = base || urls.dashboard || "";
  return [
    { name: "Hermes Dashboard", href: dashboard },
    { name: "Drive", href: urls.files || (base ? urlJoin(base, "drive") : "") },
    { name: "Code", href: urls.code || (base ? urlJoin(base, "code") : "") },
    { name: "Terminal", href: urls.terminal || (base ? urlJoin(base, "terminal") : "") },
  ];
}

function sectionStatus(dep: Deployment | undefined, section: string, fallback = "unknown") {
  if (!dep) return fallback;
  return dep.sections?.find((item) => item.section === section)?.status || fallback;
}

function providerModelForDeployment(dep: Deployment | undefined, state: ProviderStateData | null) {
  if (!dep) return undefined;
  return state?.deployment_models?.find((model) => model.deployment_id === dep.deployment_id);
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
  const [credentials, setCredentials] = useState<CredentialsData | null>(null);
  const [linkedResources, setLinkedResources] = useState<LinkedResourcesData | null>(null);
  const [comms, setComms] = useState<CommsData | null>(null);
  const [providerState, setProviderState] = useState<ProviderStateData | null>(null);
  const [crewRecipe, setCrewRecipe] = useState<CrewRecipeState | null>(null);
  const [crewPreview, setCrewPreview] = useState<CrewRecipePreview | null>(null);
  const [crewForm, setCrewForm] = useState<CrewRecipeForm>(DEFAULT_CREW_FORM);
  const [credentialsError, setCredentialsError] = useState("");
  const [linkedResourcesError, setLinkedResourcesError] = useState("");
  const [providerStateError, setProviderStateError] = useState("");
  const [wrappedError, setWrappedError] = useState("");
  const [wrappedUpdating, setWrappedUpdating] = useState(false);
  const [crewError, setCrewError] = useState("");
  const [crewLoading, setCrewLoading] = useState(false);
  const [credentialAckLoading, setCredentialAckLoading] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [activeTab, setActiveTab] = useState<Tab>("overview");
  const router = useRouter();

  async function handleLogout() {
    await api.logout("user");
    router.push("/login");
  }

  async function handleAcknowledgeCredential(handoffId: string) {
    setCredentialAckLoading(handoffId);
    setError("");
    try {
      const result = await api.acknowledgeCredential({ handoff_id: handoffId });
      if (result.status !== 200) {
        setError("Could not acknowledge credential handoff.");
        return;
      }
      const refreshed = await api.userCredentials();
      if (refreshed.status === 200) {
        setCredentials(refreshed.data as CredentialsData);
      } else {
        setCredentials((current) => {
          const existing: CredentialsData = current || {};
          return {
            ...existing,
            credentials: (existing.credentials || []).filter((credential) => credential.handoff_id !== handoffId),
            removed_count: (existing.removed_count || 0) + 1,
          };
        });
      }
    } catch {
      setError("Could not acknowledge credential handoff.");
    } finally {
      setCredentialAckLoading("");
    }
  }

  async function handleAgentIdentitySubmit(event: FormEvent<HTMLFormElement>, deploymentId: string) {
    event.preventDefault();
    setError("");
    const form = new FormData(event.currentTarget);
    const agentName = String(form.get("agent_name") || "").trim();
    const agentTitle = String(form.get("agent_title") || "").trim();
    const result = await api.updateAgentIdentity({
      deployment_id: deploymentId,
      agent_name: agentName,
      agent_title: agentTitle,
    });
    if (result.status !== 200) {
      setError("Could not update Agent identity.");
      return;
    }
    const deployment = (result.data as { deployment?: Deployment }).deployment;
    if (!deployment) return;
    setData((current) => {
      if (!current?.deployments) return current;
      return {
        ...current,
        deployments: current.deployments.map((item) => (
          item.deployment_id === deployment.deployment_id
            ? { ...item, agent_label: deployment.agent_name || item.agent_label, agent_title: deployment.agent_title }
            : item
        )),
      };
    });
  }

  async function refreshCrewRecipe() {
    const result = await api.userCrewRecipe();
    if (result.status === 200) {
      setCrewRecipe(result.data as CrewRecipeState);
    }
  }

  function updateCrewForm(field: keyof CrewRecipeForm, value: string) {
    setCrewForm((current) => ({ ...current, [field]: value }));
  }

  async function handleCrewPreview(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault();
    setCrewError("");
    setCrewLoading(true);
    try {
      const result = await api.previewCrewRecipe(crewForm);
      if (result.status !== 200) {
        setCrewError("Could not preview Crew Recipe.");
        return;
      }
      setCrewPreview((result.data as { preview?: CrewRecipePreview }).preview || null);
    } catch {
      setCrewError("Could not preview Crew Recipe.");
    } finally {
      setCrewLoading(false);
    }
  }

  async function handleCrewApply() {
    setCrewError("");
    setCrewLoading(true);
    try {
      const result = await api.applyCrewRecipe(crewForm);
      if (result.status !== 200) {
        setCrewError("Could not apply Crew Training.");
        return;
      }
      const preview = (result.data as { preview?: CrewRecipePreview }).preview;
      if (preview) setCrewPreview(preview);
      await refreshCrewRecipe();
    } catch {
      setCrewError("Could not apply Crew Training.");
    } finally {
      setCrewLoading(false);
    }
  }

  async function handleWrappedFrequency(frequency: string) {
    setWrappedError("");
    setWrappedUpdating(true);
    try {
      const result = await api.updateWrappedFrequency({ frequency });
      if (result.status !== 200) {
        setWrappedError("Could not update ArcLink Wrapped cadence.");
        return;
      }
      setData((current) => current ? {
        ...current,
        wrapped: {
          ...(current.wrapped || {}),
          wrapped_frequency: (result.data as { wrapped_frequency?: "daily" | "weekly" | "monthly" }).wrapped_frequency || "daily",
        },
      } : current);
    } catch {
      setWrappedError("Could not update ArcLink Wrapped cadence.");
    } finally {
      setWrappedUpdating(false);
    }
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
      api.userCredentials().then((r) => {
        if (!mounted) return;
        if (r.status === 200) {
          setCredentials(r.data as CredentialsData);
          setCredentialsError("");
        } else {
          setCredentialsError("Credential handoff could not be loaded. Refresh the dashboard or ask support to reissue the handoff.");
        }
      }).catch(() => {
        if (mounted) setCredentialsError("Credential handoff could not be loaded. Refresh the dashboard or ask support to reissue the handoff.");
      }),
      api.userLinkedResources().then((r) => {
        if (!mounted) return;
        if (r.status === 200) {
          setLinkedResources(r.data as LinkedResourcesData);
          setLinkedResourcesError("");
        } else {
          setLinkedResourcesError("Linked resources could not be loaded. Drive and Code will still keep accepted shares read-only when the API is available.");
        }
      }).catch(() => {
        if (mounted) setLinkedResourcesError("Linked resources could not be loaded. Drive and Code will still keep accepted shares read-only when the API is available.");
      }),
      api.userComms().then((r) => {
        if (mounted && r.status === 200) setComms(r.data as CommsData);
      }),
      api.userProviderState().then((r) => {
        if (!mounted) return;
        if (r.status === 200) {
          setProviderState(r.data as ProviderStateData);
          setProviderStateError("");
        } else {
          setProviderStateError("Provider state could not be loaded. Provider changes remain operator-managed until the API is available.");
        }
      }).catch(() => {
        if (mounted) setProviderStateError("Provider state could not be loaded. Provider changes remain operator-managed until the API is available.");
      }),
      api.userCrewRecipe().then((r) => {
        if (mounted && r.status === 200) setCrewRecipe(r.data as CrewRecipeState);
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

  const deployments = orderedDeployments(data?.deployments ?? []);
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
              {activeDeployment && (
                <form onSubmit={(event) => handleAgentIdentitySubmit(event, activeDeployment.deployment_id)} className="grid gap-3 border border-border bg-surface/80 p-4 md:grid-cols-[1fr_1fr_auto] md:items-end">
                  <div>
                    <label htmlFor="agent-identity-name" className="text-xs uppercase tracking-[0.18em] text-soft-white/40">Agent Name</label>
                    <input
                      id="agent-identity-name"
                      name="agent_name"
                      type="text"
                      required
                      maxLength={40}
                      defaultValue={deploymentTitle(activeDeployment)}
                      className="mt-1 w-full rounded border border-border bg-carbon px-3 py-2 text-sm text-soft-white outline-none transition focus:border-signal-orange"
                    />
                  </div>
                  <div>
                    <label htmlFor="agent-identity-title" className="text-xs uppercase tracking-[0.18em] text-soft-white/40">Agent Title</label>
                    <input
                      id="agent-identity-title"
                      name="agent_title"
                      type="text"
                      required
                      maxLength={80}
                      defaultValue={activeDeployment.agent_title || ""}
                      className="mt-1 w-full rounded border border-border bg-carbon px-3 py-2 text-sm text-soft-white outline-none transition focus:border-signal-orange"
                    />
                  </div>
                  <button type="submit" className="rounded border border-signal-orange/60 px-4 py-2 text-sm font-semibold text-signal-orange transition hover:bg-signal-orange hover:text-jet">
                    Update Identity
                  </button>
                </form>
              )}
              <DashboardRecoveryRail
                deployment={activeDeployment}
                entitlementState={entitlementState}
                credentials={credentials}
                providerState={providerState}
                onTab={setActiveTab}
              />
              <WorkspaceReadinessGrid
                deployment={activeDeployment}
                entitlementState={entitlementState}
                health={health}
                linkedResources={linkedResources}
                providerState={providerState}
                onTab={setActiveTab}
              />
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

          {activeTab === "crew" && (
            <div className="space-y-6">
              <SectionHeader title="Crew Training" eyebrow="Crew Recipe" detail="Capture the Captain posture, generate a Crew Recipe, and apply it as an additive SOUL overlay for every Pod in your Crew." />
              {crewError && <ErrorAlert message={crewError} />}
              <div className="grid gap-4 lg:grid-cols-[1.2fr_0.8fr]">
                <form onSubmit={handleCrewPreview} className="space-y-4 border border-border bg-surface/80 p-4">
                  <div className="grid gap-3 md:grid-cols-2">
                    <label className="block text-sm">
                      <span className="text-xs uppercase tracking-[0.18em] text-soft-white/40">Your Role</span>
                      <input
                        value={crewForm.role}
                        onChange={(event) => updateCrewForm("role", event.target.value)}
                        required
                        maxLength={240}
                        className="mt-1 w-full rounded border border-border bg-carbon px-3 py-2 text-sm text-soft-white outline-none transition focus:border-signal-orange"
                        placeholder="founder building a startup"
                      />
                    </label>
                    <label className="block text-sm">
                      <span className="text-xs uppercase tracking-[0.18em] text-soft-white/40">Treatment</span>
                      <select
                        value={crewForm.treatment}
                        onChange={(event) => updateCrewForm("treatment", event.target.value)}
                        className="mt-1 w-full rounded border border-border bg-carbon px-3 py-2 text-sm text-soft-white outline-none transition focus:border-signal-orange"
                      >
                        {CREW_TREATMENT_OPTIONS.map((option) => (
                          <option key={option}>{option}</option>
                        ))}
                      </select>
                    </label>
                  </div>
                  <label className="block text-sm">
                    <span className="text-xs uppercase tracking-[0.18em] text-soft-white/40">Mission</span>
                    <textarea
                      value={crewForm.mission}
                      onChange={(event) => updateCrewForm("mission", event.target.value)}
                      required
                      maxLength={500}
                      rows={3}
                      className="mt-1 w-full rounded border border-border bg-carbon px-3 py-2 text-sm text-soft-white outline-none transition focus:border-signal-orange"
                      placeholder="what should your Crew help you ship in the next 12 weeks"
                    />
                  </label>
                  <div className="grid gap-3 md:grid-cols-2">
                    <label className="block text-sm">
                      <span className="text-xs uppercase tracking-[0.18em] text-soft-white/40">Crew Preset</span>
                      <select
                        value={crewForm.preset}
                        onChange={(event) => updateCrewForm("preset", event.target.value)}
                        className="mt-1 w-full rounded border border-border bg-carbon px-3 py-2 text-sm text-soft-white outline-none transition focus:border-signal-orange"
                      >
                        {CREW_PRESET_OPTIONS.map((option) => (
                          <option key={option}>{option}</option>
                        ))}
                      </select>
                    </label>
                    <label className="block text-sm">
                      <span className="text-xs uppercase tracking-[0.18em] text-soft-white/40">Crew Capacity</span>
                      <select
                        value={crewForm.capacity}
                        onChange={(event) => updateCrewForm("capacity", event.target.value)}
                        className="mt-1 w-full rounded border border-border bg-carbon px-3 py-2 text-sm text-soft-white outline-none transition focus:border-signal-orange"
                      >
                        {CREW_CAPACITY_OPTIONS.map((option) => (
                          <option key={option.value} value={option.value}>
                            {option.label}
                          </option>
                        ))}
                      </select>
                    </label>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <button type="submit" disabled={crewLoading} className="rounded border border-signal-orange/60 px-4 py-2 text-sm font-semibold text-signal-orange transition hover:bg-signal-orange hover:text-jet disabled:opacity-50">
                      {crewPreview ? "Regenerate" : "Preview Recipe"}
                    </button>
                    <button type="button" disabled={crewLoading || !crewPreview} onClick={handleCrewApply} className="rounded border border-neon-green/50 px-4 py-2 text-sm font-semibold text-neon-green transition hover:bg-neon-green hover:text-jet disabled:opacity-50">
                      Confirm Training
                    </button>
                  </div>
                </form>
                <div className="space-y-4">
                  <div className="border border-border bg-surface/80 p-4">
                    <p className="text-xs uppercase tracking-[0.18em] text-soft-white/40">Current Recipe</p>
                    {crewRecipe?.current ? (
                      <div className="mt-3 text-sm text-soft-white/65">
                        <p className="font-semibold text-soft-white">{crewRecipe.current.preset} / {crewRecipe.current.capacity}</p>
                        <p className="mt-2">{crewRecipe.current.soul_overlay?.crew_recipe_text || crewRecipe.current.mission}</p>
                        <p className="mt-2 text-xs text-soft-white/35">{crewRecipe.current.applied_at ? `Applied ${formatDate(crewRecipe.current.applied_at)}` : "Applied time unavailable"}</p>
                      </div>
                    ) : (
                      <p className="mt-3 text-sm text-soft-white/45">No Crew Recipe is active yet.</p>
                    )}
                  </div>
                  <div className="border border-border bg-surface/80 p-4">
                    <p className="text-xs uppercase tracking-[0.18em] text-soft-white/40">What Changed</p>
                    <p className="mt-3 text-sm text-soft-white/60">{crewRecipe?.whats_changed?.summary || "No prior Crew Recipe to compare."}</p>
                  </div>
                </div>
              </div>
              {crewPreview && (
                <div className="border border-signal-orange/30 bg-signal-orange/10 p-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="text-xs uppercase tracking-[0.18em] text-signal-orange">Review</p>
                    <StatusBadge status={crewPreview.mode || "preview"} />
                  </div>
                  <p className="mt-3 text-sm leading-6 text-soft-white/70">{crewPreview.recipe_text}</p>
                  {crewPreview.fallback && (
                    <p className="mt-3 text-xs leading-5 text-yellow-200">{crewPreview.fallback_reason || "Live recipe generation requires Chutes credentials. Using preset-only overlay."}</p>
                  )}
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
              {(billing?.renewal_lifecycle || billing?.entitlement?.renewal_lifecycle) && (
                <div className="rounded-lg border border-border bg-surface p-4 text-sm">
                  <div className="flex flex-wrap items-center gap-3">
                    <span className="text-soft-white/60">Provider Access:</span>
                    <StatusBadge status={(billing?.renewal_lifecycle || billing?.entitlement?.renewal_lifecycle)?.provider_access || "unknown"} />
                    <span className="text-soft-white/60">Renewal Policy:</span>
                    <StatusBadge status={(billing?.renewal_lifecycle || billing?.entitlement?.renewal_lifecycle)?.purge_policy || "unknown"} />
                  </div>
                  <p className="mt-3 text-xs leading-5 text-soft-white/45">
                    {(billing?.renewal_lifecycle || billing?.entitlement?.renewal_lifecycle)?.reason || "Renewal lifecycle state is not available."}
                  </p>
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
                Authenticated Hermes dashboard surfaces. Drive, Code, and Terminal are native plugins inside the same protected agent dashboard.
              </p>
              {data.deployments?.map((dep) => {
                const services = hermesPluginLinks(dep);
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
                const provisioned = dep.status === "active" || dep.status === "running";
                const vaultHealth = dep.service_health?.find((s) => s.service_name === "hermes-dashboard" || s.service_name === "qmd-mcp");
                const vaultUrl = hermesPluginLinks(dep).find((link) => link.name === "Drive")?.href || "";
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
              <LinkedResourcesPanel resources={linkedResources} loadError={linkedResourcesError} />
            </div>
          )}

          {activeTab === "comms" && (
            <div className="space-y-6">
              <SectionHeader title="Comms" eyebrow="Crew messages" detail="Pod-to-Pod messages for your Captain account. Attachments appear only as accepted share references." />
              <CommsPanel messages={comms?.comms || []} />
            </div>
          )}

          {activeTab === "wrapped" && data && (
            <div className="space-y-6">
              <SectionHeader title="ArcLink Wrapped" eyebrow="Period reports" detail="Captain-facing daily, weekly, or monthly highlights generated from scoped ArcLink activity." />
              {wrappedError && <ErrorAlert message={wrappedError} />}
              <WrappedPanel
                wrapped={data.wrapped}
                updating={wrappedUpdating}
                onFrequencyChange={handleWrappedFrequency}
              />
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
              <ProviderSettingsPanel state={providerState} loadError={providerStateError} />
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
                    <NotionSetupPanel setup={dep.notion_setup} />
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
                <p className="mt-2">Secret values are never exposed in dashboard responses; pending handoffs show masked references only.</p>
              </div>
              <CredentialHandoffPanel
                credentials={credentials}
                loadError={credentialsError}
                acknowledging={credentialAckLoading}
                onAcknowledge={handleAcknowledgeCredential}
              />
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

type RecoveryAction = {
  title: string;
  detail: string;
  status: string;
  tab: Tab;
};

function recoveryActionsForDashboard({
  deployment,
  entitlementState,
  credentials,
  providerState,
}: {
  deployment?: Deployment;
  entitlementState: string;
  credentials: CredentialsData | null;
  providerState: ProviderStateData | null;
}) {
  const actions: RecoveryAction[] = [];
  const pendingCredentials = credentials?.credentials?.length || 0;
  const providerModel = providerModelForDeployment(deployment, providerState);
  const providerStatus = providerModel?.credential_state || deployment?.model?.credential_state || "";
  const thresholdContinuation =
    providerModel?.provider_detail?.threshold_continuation || providerState?.provider_boundary?.threshold_continuation;
  const serviceAttention = (deployment?.service_health || []).filter((service) => isAttentionStatus(service.status));

  if (!deployment) {
    actions.push({
      title: "Launch first agent",
      detail: "No private workspace has been provisioned for this account yet.",
      status: "pending",
      tab: "provisioning",
    });
    return actions;
  }

  if (!isGoodStatus(entitlementState)) {
    actions.push({
      title: "Billing needs review",
      detail: "Provider access and deployment changes stay fail-closed until entitlement is current.",
      status: entitlementState || "unknown",
      tab: "billing",
    });
  }

  if (!isGoodStatus(deployment.status)) {
    actions.push({
      title: "Provisioning is not complete",
      detail: "Open provisioning for job state, service output, and operator handoff status.",
      status: deployment.status || "unknown",
      tab: "provisioning",
    });
  }

  if (serviceAttention.length > 0) {
    actions.push({
      title: "Service attention",
      detail: `${serviceAttention.length} reported service signal(s) need operator review.`,
      status: "attention",
      tab: "services",
    });
  }

  if (pendingCredentials > 0) {
    actions.push({
      title: "Credential handoff pending",
      detail: "Store each secure completion-bundle credential before acknowledging removal.",
      status: "pending",
      tab: "security",
    });
  }

  if (!deployment.bot_contact?.first_contacted || !deployment.bot_contact?.handoff_recorded) {
    actions.push({
      title: "Bot handoff pending",
      detail: "Raven and the private agent channel are not both recorded as contacted.",
      status: "pending",
      tab: "bots",
    });
  }

  if (deployment.notion_setup?.verification?.live_workspace === "proof_gated") {
    actions.push({
      title: "SSOT live proof gated",
      detail: "Local broker status is visible; live workspace/page permission proof needs an authorized run.",
      status: "proof_gated",
      tab: "memory",
    });
  }

  if (isAttentionStatus(providerStatus)) {
    actions.push({
      title: "Provider threshold state visible",
      detail: thresholdContinuation?.reason || "ArcLink shows warning or exhausted state only; refill and fallback paths remain policy-gated.",
      status: providerStatus,
      tab: "model",
    });
  }

  return actions.slice(0, 5);
}

function DashboardRecoveryRail({
  deployment,
  entitlementState,
  credentials,
  providerState,
  onTab,
}: {
  deployment?: Deployment;
  entitlementState: string;
  credentials: CredentialsData | null;
  providerState: ProviderStateData | null;
  onTab: (tab: Tab) => void;
}) {
  const actions = recoveryActionsForDashboard({ deployment, entitlementState, credentials, providerState });
  return (
    <div className="border border-border bg-surface/85 p-4">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-xs uppercase tracking-[0.18em] text-signal-orange">Recovery Actions</p>
          <h3 className="mt-1 font-display text-xl font-semibold">Next safest steps</h3>
        </div>
        <StatusBadge status={actions.length ? "attention" : "clear"} />
      </div>
      <div className="mt-4 grid gap-3 lg:grid-cols-2">
        {actions.length ? actions.map((action) => (
          <button
            key={`${action.title}-${action.tab}`}
            onClick={() => onTab(action.tab)}
            className="border border-border/70 bg-carbon/70 px-3 py-3 text-left transition hover:border-signal-orange/60"
          >
            <div className="flex items-start justify-between gap-3">
              <p className="font-medium text-soft-white">{action.title}</p>
              <StatusBadge status={action.status} />
            </div>
            <p className="mt-2 text-xs leading-5 text-soft-white/45">{action.detail}</p>
          </button>
        )) : (
          <div className="lg:col-span-2 border border-border/70 bg-carbon/70 px-3 py-3">
            <p className="font-medium text-soft-white">No required recovery actions</p>
            <p className="mt-2 text-xs leading-5 text-soft-white/45">Reported service, billing, handoff, and credential signals are clear.</p>
          </div>
        )}
      </div>
    </div>
  );
}

function WorkspaceReadinessGrid({
  deployment,
  entitlementState,
  health,
  linkedResources,
  providerState,
  onTab,
}: {
  deployment?: Deployment;
  entitlementState: string;
  health: { total: number; healthy: number; attention: number };
  linkedResources: LinkedResourcesData | null;
  providerState: ProviderStateData | null;
  onTab: (tab: Tab) => void;
}) {
  const providerModel = providerModelForDeployment(deployment, providerState);
  const linkedCount = linkedResources?.linked_resources?.length || 0;
  const readiness = [
    {
      label: "Billing",
      value: entitlementState || "unknown",
      detail: "Plan and provider access state.",
      tab: "billing" as Tab,
    },
    {
      label: "Services",
      value: health.attention ? "attention" : health.total ? "ready" : "pending",
      detail: `${health.healthy}/${health.total || 0} reported healthy.`,
      tab: "services" as Tab,
    },
    {
      label: "Channel",
      value: deployment?.bot_contact?.first_contacted && deployment?.bot_contact?.handoff_recorded ? "recorded" : "pending",
      detail: deployment?.bot_contact?.channel || "No handoff channel recorded.",
      tab: "bots" as Tab,
    },
    {
      label: "Knowledge",
      value: sectionStatus(deployment, "qmd_memory", "unknown"),
      detail: `qmd ${deployment?.freshness?.qmd?.status || "unknown"} · memory ${deployment?.freshness?.memory?.status || "unknown"}`,
      tab: "memory" as Tab,
    },
    {
      label: "Linked",
      value: linkedCount ? "available" : "clear",
      detail: linkedCount ? `${linkedCount} read-only resource(s).` : "No accepted linked resources.",
      tab: "vault" as Tab,
    },
    {
      label: "Provider",
      value: providerModel?.credential_state || deployment?.model?.credential_state || "unknown",
      detail: providerModel?.provider_detail?.reason || "Provider state is read-only in the dashboard.",
      tab: "model" as Tab,
    },
  ];
  return (
    <div className="border border-border bg-surface/85 p-4">
      <SectionHeader title="Workspace Readiness" eyebrow="Grouped status" detail="Each signal links to the tab that owns its evidence and recovery state." />
      <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {readiness.map((item) => (
          <button
            key={item.label}
            onClick={() => onTab(item.tab)}
            className="border border-border/70 bg-carbon/70 px-3 py-3 text-left transition hover:border-signal-orange/60"
          >
            <div className="flex items-start justify-between gap-3">
              <p className="text-xs uppercase tracking-wide text-soft-white/35">{item.label}</p>
              <StatusBadge status={item.value} />
            </div>
            <p className="mt-2 line-clamp-2 text-xs leading-5 text-soft-white/45">{item.detail}</p>
          </button>
        ))}
      </div>
    </div>
  );
}

function DeploymentOverview({ dep }: { dep: Deployment }) {
  const services = dep.service_health || [];
  const links = hermesPluginLinks(dep).filter((link) => link.href);
  const host = deploymentHost(dep);
  return (
    <div className="border border-border bg-surface/85 p-4">
      <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
        <div className="min-w-0">
          <p className="text-xs uppercase tracking-[0.18em] text-signal-orange">Private agent</p>
          <h3 className="mt-1 truncate font-display text-xl font-semibold">{deploymentTitle(dep)}</h3>
          {host && <p className="mt-1 truncate text-xs text-soft-white/45">{host}</p>}
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
            {links.length ? links.map((link) => (
              <a key={link.name} href={link.href} target="_blank" rel="noopener noreferrer" className="flex items-center justify-between border border-border bg-jet/45 px-3 py-2 text-sm text-soft-white/75 transition hover:border-signal-orange/60 hover:text-signal-orange">
                <span>{link.name}</span>
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

function DeploymentCard({ dep, children }: { dep: { deployment_id: string; hostname?: string; agent_label?: string }; children: React.ReactNode }) {
  return (
    <div className="border border-border bg-surface/85 p-4">
      <h3 className="mb-1 font-display font-semibold">{dep.agent_label || dep.hostname || dep.deployment_id}</h3>
      {dep.agent_label && dep.hostname && <p className="mb-3 text-xs text-soft-white/40">{dep.hostname}</p>}
      {children}
    </div>
  );
}

function NotionSetupPanel({ setup }: { setup?: NotionSetup }) {
  const status = setup?.status || "unavailable";
  const callbackUrl = setup?.callback_url || "";
  const webhookStatus = setup?.webhook?.verified ? "verified" : setup?.webhook?.configured ? "configured" : setup?.webhook?.armed ? "webhook_install_armed" : "not_configured";
  return (
    <div className="mt-3 rounded bg-carbon px-3 py-3 text-sm">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-xs text-soft-white/60">Notion SSOT</p>
          <p className="mt-1 text-soft-white/55">
            Brokered shared-root setup with dashboard/operator verification.
          </p>
        </div>
        <StatusBadge status={status} />
      </div>
      <div className="mt-3 grid gap-2 sm:grid-cols-3">
        <div className="rounded border border-border/70 bg-jet/40 px-2 py-2">
          <p className="text-[10px] uppercase tracking-wide text-soft-white/35">Webhook</p>
          <div className="mt-1"><StatusBadge status={webhookStatus} /></div>
          {setup?.webhook?.verified_at && (
            <p className="mt-1 truncate text-[10px] text-soft-white/30">{formatDate(setup.webhook.verified_at)}</p>
          )}
        </div>
        <div className="rounded border border-border/70 bg-jet/40 px-2 py-2">
          <p className="text-[10px] uppercase tracking-wide text-soft-white/35">Index</p>
          <div className="mt-1"><StatusBadge status={setup?.index?.status || "not_seen"} /></div>
        </div>
        <div className="rounded border border-border/70 bg-jet/40 px-2 py-2">
          <p className="text-[10px] uppercase tracking-wide text-soft-white/35">Live Proof</p>
          <div className="mt-1"><StatusBadge status={setup?.verification?.live_workspace || "proof_gated"} /></div>
        </div>
      </div>
      {callbackUrl ? (
        <p className="mt-3 break-all font-mono text-xs text-soft-white/40">{callbackUrl}</p>
      ) : (
        <p className="mt-3 text-xs text-soft-white/40">Callback URL appears after provisioning publishes the deployment route.</p>
      )}
      <p className="mt-2 text-xs text-soft-white/35">
        Email sharing alone is not proof of API access; live workspace/page permission proof stays gated until an operator runs it.
      </p>
    </div>
  );
}

function formatCents(value?: number) {
  if (typeof value !== "number" || Number.isNaN(value)) return "-";
  return `$${(value / 100).toFixed(2)}`;
}

function humanizeValue(value?: string) {
  return (value || "").replaceAll("_", " ");
}

function ProviderSettingsPanel({ state, loadError = "" }: { state: ProviderStateData | null; loadError?: string }) {
  const settings = state?.provider_settings || {};
  const boundary = state?.provider_boundary || {};
  const models = state?.deployment_models || [];
  const selfServiceStatus = settings.self_service_provider_add || "policy_question";
  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h3 className="font-display font-semibold">Provider Settings</h3>
          <p className="mt-1 text-sm text-soft-white/60">
            {settings.guidance || "The dashboard shows provider state only. Provider changes are not a live self-service mutation path."}
          </p>
        </div>
        <StatusBadge status={loadError ? "unavailable" : selfServiceStatus} />
      </div>
      {loadError ? (
        <div className="mt-3 border border-yellow-500/30 bg-yellow-500/10 px-3 py-2 text-sm text-yellow-100">
          {loadError}
        </div>
      ) : (
        <>
          <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <div className="rounded border border-border/70 bg-carbon px-3 py-2">
              <p className="text-[10px] uppercase tracking-wide text-soft-white/35">Current Provider</p>
              <p className="mt-1 text-sm text-soft-white">{state?.provider || "-"}</p>
            </div>
            <div className="rounded border border-border/70 bg-carbon px-3 py-2">
              <p className="text-[10px] uppercase tracking-wide text-soft-white/35">Default Model</p>
              <p className="mt-1 break-all text-sm text-soft-white">{state?.default_model || "-"}</p>
            </div>
            <div className="rounded border border-border/70 bg-carbon px-3 py-2">
              <p className="text-[10px] uppercase tracking-wide text-soft-white/35">Credential Isolation</p>
              <p className="mt-1 text-sm text-soft-white">{boundary.credential_isolation || "secret:// scoped references required"}</p>
            </div>
            <div className="rounded border border-border/70 bg-carbon px-3 py-2">
              <p className="text-[10px] uppercase tracking-wide text-soft-white/35">Live Key Mutation</p>
              <div className="mt-1"><StatusBadge status={settings.live_provider_mutation || boundary.live_key_creation || "proof_gated"} /></div>
            </div>
          </div>
          <div className="mt-4 rounded border border-border/70 bg-jet/40 px-3 py-3 text-sm">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <p className="font-medium text-soft-white">Self-Service Provider Add</p>
                <p className="mt-1 text-soft-white/55">
                  {settings.operator_decision_needed || "Policy is required before ArcLink accepts provider changes directly from user settings."}
                </p>
              </div>
              <StatusBadge status={selfServiceStatus} />
            </div>
            <p className="mt-2 text-xs text-soft-white/35">
              Secret input policy: {humanizeValue(settings.secret_input_policy) || "dashboard never collects raw provider tokens"}.
            </p>
          </div>
          {models.length ? (
            <div className="mt-4 grid gap-3">
              {models.map((model) => {
                const detail = model.provider_detail || {};
                const budget = detail.budget || {};
                const continuation = detail.threshold_continuation;
                return (
                  <div key={model.deployment_id} className="border border-border/70 bg-carbon px-3 py-3 text-sm">
                    <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                      <div className="min-w-0">
                        <p className="font-medium text-soft-white">{model.deployment_id}</p>
                        <p className="mt-1 break-all text-xs text-soft-white/45">Model: {model.model_id || state?.default_model || "-"}</p>
                        {detail.reason && (
                          <p className="mt-2 text-xs text-soft-white/40">{detail.reason}</p>
                        )}
                      </div>
                      <div className="grid min-w-[220px] gap-2 text-xs text-soft-white/45 sm:grid-cols-2">
                        <div>
                          <p className="text-soft-white/35">Credential</p>
                          <StatusBadge status={model.credential_state || "unknown"} />
                        </div>
                        <div>
                          <p className="text-soft-white/35">Budget</p>
                          <StatusBadge status={budget.status || "unknown"} />
                        </div>
                        <p>Used: {formatCents(budget.used_cents)}</p>
                        <p>Remaining: {formatCents(budget.remaining_cents)}</p>
                      </div>
                    </div>
                    {continuation?.status && continuation.status !== "not_applicable" && (
                      <div className="mt-3 border-t border-border/60 pt-3 text-xs text-soft-white/45">
                        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                          <p className="font-medium text-soft-white">Threshold Guidance Policy</p>
                          <StatusBadge status={continuation.status} />
                        </div>
                        {continuation.reason && (
                          <p className="mt-2 text-soft-white/45">{continuation.reason}</p>
                        )}
                        <p className="mt-2">
                          Raven notifications: {humanizeValue(continuation.raven_notifications || "policy_question")}; fallback:{" "}
                          {humanizeValue(continuation.provider_fallback || "policy_question")}; refill:{" "}
                          {humanizeValue(continuation.overage_refill || "policy_question")}.
                        </p>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          ) : (
            <p className="mt-4 text-sm text-soft-white/40">Provider deployment state appears after provisioning.</p>
          )}
        </>
      )}
    </div>
  );
}

function NoDeployments({ message }: { message?: string }) {
  return <p className="text-soft-white/40">{message || "No deployments."}</p>;
}

function LinkedResourcesPanel({ resources, loadError = "" }: { resources: LinkedResourcesData | null; loadError?: string }) {
  const linked = resources?.linked_resources || [];
  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <h3 className="mb-3 font-display font-semibold">Linked Resources</h3>
      <p className="mb-3 text-sm text-soft-white/60">
        Accepted shares appear as a read-only Linked root in Drive and Code. They cannot be reshared from this account.
      </p>
      {linked.length ? (
        <div className="grid gap-3">
          {linked.map((resource) => (
            <div key={resource.grant_id} className="border border-border/70 bg-carbon px-3 py-2 text-sm">
              <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                <div className="min-w-0">
                  <p className="font-medium text-soft-white">{resource.display_name || resource.resource_path}</p>
                  <p className="break-all font-mono text-xs text-soft-white/40">{resource.resource_root}:{resource.resource_path}</p>
                  <p className="break-all font-mono text-xs text-soft-white/40">
                    Linked: {resource.linked_root || "linked"}:{resource.projection?.linked_path || resource.linked_path || "pending"}
                  </p>
                  {(resource.owner_deployment_id || resource.recipient_deployment_id) && (
                    <p className="break-all font-mono text-xs text-soft-white/35">
                      Agent path: {resource.owner_deployment_id || "owner"} -&gt; {resource.recipient_deployment_id || "recipient"}
                    </p>
                  )}
                  <p className="mt-1 text-xs text-soft-white/35">Owner: {resource.owner_user_id}</p>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <StatusBadge status={resource.access_mode || "read"} />
                  <StatusBadge status={resource.projection?.status || resource.status || "pending"} />
                  <StatusBadge status={resource.reshare_allowed ? "reshare" : "no reshare"} />
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : loadError ? (
        <div className="border border-yellow-500/30 bg-yellow-500/10 px-3 py-2 text-sm text-yellow-100">
          {loadError}
        </div>
      ) : (
        <p className="text-sm text-soft-white/40">No linked resources accepted yet.</p>
      )}
    </div>
  );
}

function CredentialHandoffPanel({
  credentials,
  loadError = "",
  acknowledging,
  onAcknowledge,
}: {
  credentials: CredentialsData | null;
  loadError?: string;
  acknowledging: string;
  onAcknowledge: (handoffId: string) => void;
}) {
  const pending = credentials?.credentials || [];
  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h3 className="font-display font-semibold">Credential Handoff</h3>
          <p className="mt-1 text-sm text-soft-white/60">
            {credentials?.instructions?.copy || "Copy credentials from the secure completion bundle into your password manager."}
          </p>
        </div>
        <StatusBadge status={loadError ? "unavailable" : pending.length ? "pending" : "clear"} />
      </div>
      {pending.length ? (
        <div className="grid gap-3">
          {pending.map((credential) => (
            <div key={credential.handoff_id} className="border border-border/70 bg-carbon px-3 py-3 text-sm">
              <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                <div className="min-w-0">
                  <p className="font-medium text-soft-white">{credential.display_name || credential.credential_kind}</p>
                  <p className="mt-1 text-xs text-soft-white/45">
                    {credential.delivery_hint || "Store it before acknowledging removal from the dashboard."}
                  </p>
                  {credential.secret_ref && (
                    <p className="mt-2 break-all font-mono text-xs text-soft-white/45">{credential.secret_ref}</p>
                  )}
                  {credential.copy_guidance && (
                    <p className="mt-2 text-xs text-soft-white/35">{credential.copy_guidance}</p>
                  )}
                </div>
                <button
                  onClick={() => onAcknowledge(credential.handoff_id)}
                  disabled={acknowledging === credential.handoff_id}
                  className="shrink-0 rounded border border-signal-orange/50 bg-signal-orange/10 px-3 py-2 text-sm text-signal-orange transition hover:bg-signal-orange/20 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {acknowledging === credential.handoff_id ? "Removing..." : "I Stored This"}
                </button>
              </div>
            </div>
          ))}
        </div>
      ) : loadError ? (
        <div className="border border-yellow-500/30 bg-yellow-500/10 px-3 py-2 text-sm text-yellow-100">
          {loadError}
        </div>
      ) : (
        <p className="text-sm text-soft-white/40">
          No pending credential handoffs. {credentials?.removed_count ? `${credentials.removed_count} handoff(s) already removed from future responses.` : ""}
        </p>
      )}
      <p className="mt-3 text-xs text-soft-white/30">
        {credentials?.instructions?.acknowledge || "After acknowledgement, ArcLink removes the handoff from future dashboard responses."}
      </p>
    </div>
  );
}

function CommsPanel({ messages }: { messages: CommsMessage[] }) {
  return (
    <div className="border border-border bg-surface/85 p-4">
      <h3 className="font-display font-semibold">Recent Comms</h3>
      <div className="mt-3 space-y-2">
        {messages.length ? messages.map((message) => (
          <div key={message.message_id} className="border border-border/70 bg-carbon/70 p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="font-mono text-xs text-soft-white/50">{message.sender_deployment_id} to {message.recipient_deployment_id}</p>
              <StatusBadge status={message.status || "queued"} />
            </div>
            <p className="mt-2 text-sm leading-6 text-soft-white/80">{message.body || "Redacted message"}</p>
            <p className="mt-2 text-xs text-soft-white/35">{formatDate(message.created_at || "")}</p>
          </div>
        )) : (
          <p className="text-sm text-soft-white/40">No Pod Comms yet.</p>
        )}
      </div>
    </div>
  );
}

function WrappedPanel({
  wrapped,
  updating,
  onFrequencyChange,
}: {
  wrapped?: WrappedData;
  updating: boolean;
  onFrequencyChange: (frequency: string) => void;
}) {
  const reports = wrapped?.reports || [];
  const frequency = wrapped?.wrapped_frequency || "daily";
  return (
    <div className="grid gap-4 lg:grid-cols-[18rem_1fr]">
      <div className="border border-border bg-surface/85 p-4">
        <h3 className="font-display font-semibold">Cadence</h3>
        <p className="mt-2 text-sm text-soft-white/55">Daily is the fastest supported ArcLink Wrapped cadence.</p>
        <label className="mt-4 block text-sm">
          <span className="text-xs uppercase tracking-[0.18em] text-soft-white/40">Frequency</span>
          <select
            value={frequency}
            disabled={updating}
            onChange={(event) => onFrequencyChange(event.target.value)}
            className="mt-2 w-full rounded border border-border bg-carbon px-3 py-2 text-sm text-soft-white outline-none transition focus:border-signal-orange"
          >
            <option value="daily">Daily</option>
            <option value="weekly">Weekly</option>
            <option value="monthly">Monthly</option>
          </select>
        </label>
      </div>
      <div className="space-y-3">
        {reports.length ? reports.map((report) => (
          <article key={report.report_id} className="border border-border bg-surface/85 p-4">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <p className="text-xs uppercase tracking-[0.18em] text-signal-orange">{report.period}</p>
                <h3 className="mt-1 font-display text-xl font-semibold">Novelty score {report.novelty_score}</h3>
                <p className="mt-1 text-xs text-soft-white/40">{formatDate(report.period_start)} to {formatDate(report.period_end)}</p>
              </div>
              <StatusBadge status={report.status} />
            </div>
            <pre className="mt-4 max-h-72 overflow-auto whitespace-pre-wrap rounded border border-border/70 bg-carbon p-3 text-sm leading-6 text-soft-white/75">
              {report.markdown || report.plain_text || "ArcLink Wrapped report is still rendering."}
            </pre>
            <div className="mt-3 grid gap-2 sm:grid-cols-2">
              {(report.stats || []).slice(0, 6).map((stat) => (
                <div key={stat.key || stat.label} className="rounded bg-carbon px-3 py-2 text-sm">
                  <p className="text-soft-white/55">{stat.label}</p>
                  <p className="font-semibold text-soft-white">{stat.value}</p>
                </div>
              ))}
            </div>
          </article>
        )) : (
          <div className="border border-border bg-surface/85 p-6 text-sm text-soft-white/45">
            No ArcLink Wrapped reports yet.
          </div>
        )}
      </div>
    </div>
  );
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
