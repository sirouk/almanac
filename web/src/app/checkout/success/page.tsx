"use client";

import Link from "next/link";
import { Suspense, useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { api, safeNavigationHref } from "@/lib/api";
import { StatusBadge, LoadingSpinner } from "@/components/ui";

const RESUME_KEY = "arclink_onboarding_resume";
const PROOF_STORAGE_KEY = "arclink_onboarding_proof";
const POLL_INTERVAL_MS = 3000;
const MAX_POLLS = 160; // ~8 minutes

const statusLabels: Record<string, string> = {
  active: "online",
  running: "online",
  provisioning_ready: "queued",
  provisioning: "provisioning",
  provisioning_failed: "needs repair",
  entitlement_required: "awaiting payment",
  reserved: "reserved",
};

type EntitlementStatus = "unknown" | "pending" | "paid" | "failed";
type ResourceUrls = {
  dashboard?: string;
  files?: string;
  code?: string;
  hermes?: string;
};
type DeploymentStatus = {
  deployment_id?: string;
  agent_label?: string;
  agent_title?: string;
  bundle_agent_index?: number;
  bundle_agent_count?: number;
  ready?: boolean;
  status?: string;
  access?: { urls?: ResourceUrls };
};
type CheckoutStatusData = {
  entitlement_state?: string;
  display_name?: string;
  channel?: string;
  deployment?: DeploymentStatus | null;
  deployments?: DeploymentStatus[];
  agent_count?: number;
  ready_count?: number;
};

function deploymentHref(deployment: DeploymentStatus) {
  const urls = deployment.access?.urls || {};
  return safeNavigationHref(urls.hermes) || safeNavigationHref(urls.dashboard);
}

export default function CheckoutSuccessPage() {
  return (
    <Suspense fallback={<CheckoutSuccessFallback />}>
      <CheckoutSuccessContent />
    </Suspense>
  );
}

function CheckoutSuccessFallback() {
  return (
    <main className="flex min-h-screen items-center justify-center px-6">
      <section className="w-full max-w-lg rounded-lg border border-border bg-surface p-8">
        <p className="mb-3 text-xs uppercase tracking-[0.22em] text-signal-orange">
          Verifying payment
        </p>
        <h1 className="font-display text-3xl font-bold">Waiting for confirmation</h1>
        <div className="mt-4 flex items-center gap-3">
          <LoadingSpinner label="" />
          <p className="text-sm text-soft-white/65">
            Loading checkout status...
          </p>
        </div>
      </section>
    </main>
  );
}

function CheckoutSuccessContent() {
  const params = useSearchParams();
  const sessionId = params.get("session") || "";
  const [claimToken, setClaimToken] = useState("");
  const [status, setStatus] = useState<EntitlementStatus>("pending");
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [channel, setChannel] = useState("");
  const [sessionClaimed, setSessionClaimed] = useState(false);
  const [deploymentReady, setDeploymentReady] = useState(false);
  const [deployments, setDeployments] = useState<DeploymentStatus[]>([]);
  const [agentCount, setAgentCount] = useState(1);
  const [readyCount, setReadyCount] = useState(0);
  const [pollCount, setPollCount] = useState(0);

  useEffect(() => {
    try {
      const raw = window.sessionStorage.getItem(PROOF_STORAGE_KEY);
      if (!raw) return;
      const parsed = JSON.parse(raw) as { sessionId?: string; claimToken?: string };
      if (!parsed.sessionId || parsed.sessionId === sessionId) {
        setClaimToken(parsed.claimToken || "");
      }
    } catch {
      // sessionStorage can be disabled; the success page should still render.
    }
  }, [sessionId]);

  const claimSession = useCallback(async () => {
    if (!sessionId || !claimToken || sessionClaimed) return;
    try {
      const res = await api.claimSession(sessionId, claimToken);
      if (res.status === 201) {
        setSessionClaimed(true);
        const data = res.data as { email?: string };
        if (data.email) setEmail(data.email);
        try {
          window.sessionStorage.removeItem(PROOF_STORAGE_KEY);
          window.localStorage.removeItem(RESUME_KEY);
        } catch {
          // ignore
        }
      }
    } catch {
      // Claim failed - user can still log in manually.
    }
  }, [sessionId, claimToken, sessionClaimed]);

  useEffect(() => {
    if (!sessionId) {
      setStatus("unknown");
      return;
    }
    if (deploymentReady || pollCount >= MAX_POLLS) return;

    const timer = setTimeout(async () => {
      try {
        const res = await api.checkoutStatus(sessionId, claimToken);
        if (res.status === 200) {
          const data = res.data as CheckoutStatusData;
          if (data.display_name) setDisplayName(data.display_name);
          if (data.channel) setChannel(data.channel);
          const nextDeployments = data.deployments?.length
            ? data.deployments
            : data.deployment
              ? [data.deployment]
              : [];
          const expectedCount =
            data.agent_count ||
            nextDeployments.find((deployment) => deployment.bundle_agent_count)?.bundle_agent_count ||
            nextDeployments.length ||
            1;
          const dashboardReadyCount = nextDeployments.filter(
            (deployment) => deployment.ready && deploymentHref(deployment),
          ).length;
          const nextReadyCount = nextDeployments.length ? dashboardReadyCount : data.ready_count ?? 0;
          setDeployments(nextDeployments);
          setAgentCount(expectedCount);
          setReadyCount(nextReadyCount);
          if (data.entitlement_state === "paid") {
            setStatus("paid");
            claimSession();
          }
          const allExpectedDashboardsReady =
            nextDeployments.length >= expectedCount &&
            nextDeployments.length > 0 &&
            nextDeployments.every((deployment) => deployment.ready && deploymentHref(deployment));
          if (allExpectedDashboardsReady) {
            setDeploymentReady(true);
          } else {
            setPollCount((c) => c + 1);
          }
        } else {
          setPollCount((c) => c + 1);
        }
      } catch {
        setPollCount((c) => c + 1);
      }
    }, pollCount === 0 ? 500 : POLL_INTERVAL_MS);

    return () => clearTimeout(timer);
  }, [sessionId, claimToken, deploymentReady, pollCount, claimSession]);

  useEffect(() => {
    if (status === "paid") claimSession();
  }, [status, claimSession]);

  const confirmed = status === "paid";
  const timedOut = pollCount >= MAX_POLLS && !deploymentReady;
  const waitingForResources = confirmed && !deploymentReady && !timedOut;
  const channelLabel = channel === "telegram" ? "Telegram" : channel === "discord" ? "Discord" : "";
  const agentWord = agentCount === 1 ? "Hermes Agent" : "Hermes Agents";
  const launchTitle = agentCount === 1 ? "Launching your Hermes Agent" : `Launching ${agentCount} Hermes Agents`;
  const readyTitle = agentCount === 1 ? "Your Hermes Agent is online" : `${agentCount} Hermes Agents online`;
  const statusSummary = deployments
    .map((deployment) => statusLabels[(deployment.status || "").toLowerCase()] || deployment.status)
    .filter(Boolean)
    .filter((value, index, list) => list.indexOf(value) === index)
    .join(", ");

  return (
    <main className="flex min-h-screen items-center justify-center px-6">
      <section className="w-full max-w-lg rounded-lg border border-border bg-surface p-8">
        <p className="mb-3 text-xs uppercase tracking-[0.22em] text-signal-orange">
          {confirmed ? "Payment confirmed" : "Verifying payment"}
        </p>
        <h1 className="font-display text-3xl font-bold">
          {confirmed ? (deploymentReady ? readyTitle : launchTitle) : "Waiting for confirmation"}
        </h1>

        {!confirmed && !timedOut && (
          <div className="mt-4 flex items-center gap-3">
            <LoadingSpinner label="" />
            <p className="text-sm text-soft-white/65">
              Watching for Stripe webhook confirmation...
            </p>
          </div>
        )}

        {confirmed && (
          <div className="mt-4">
            <p className="text-sm text-soft-white/65">
              {displayName ? `Captain ${displayName}, ` : ""}{deploymentReady ? `your ${agentWord} ${agentCount === 1 ? "is" : "are"} online.` : `payment cleared; Raven is moving your ${agentCount} ${agentWord} into the launch queue.`}
            </p>
            {channelLabel && (
              <p className="mt-2 text-sm text-soft-white/65">
                Return to your {channelLabel} chat with Raven. Raven will send ready links and the Hermes Agent Dashboard credential handoff there when provisioning is complete. This page will not show the password.
              </p>
            )}
            {waitingForResources && (
              <div className="mt-3 flex items-center gap-3">
                <LoadingSpinner label="" />
                <p className="text-sm text-soft-white/65">
                  Agent dashboards are coming online: {readyCount}/{agentCount} ready{statusSummary ? ` (${statusSummary})` : ""}.
                </p>
              </div>
            )}
            {deploymentReady && (
              <p className="mt-2 text-sm text-neon-green">
                {channelLabel ? "Use the dashboard username and password Raven gives you in chat. The same sign-in opens each Hermes Agent Dashboard in this Crew." : sessionClaimed ? "Use Account Dashboard for ready links and the Hermes Agent Dashboard credential handoff. The same sign-in opens each Hermes Agent Dashboard in this Crew." : "Sign in to Account Dashboard for ready links and the Hermes Agent Dashboard credential handoff."}
              </p>
            )}
            {sessionClaimed && (
              <p className="mt-2 text-sm text-neon-green">
                You are signed in{email ? ` as ${email}` : ""}.
              </p>
            )}
          </div>
        )}

        {timedOut && (
          <div className="mt-4">
            <p className="text-sm text-soft-white/65">
              {confirmed ? (channelLabel ? "Provisioning is taking longer than expected. Raven will keep reporting in chat." : "Provisioning is taking longer than expected. Your Account Dashboard will keep showing current status.") : "Payment confirmation is taking longer than expected. This is normal - Stripe webhooks can take a few minutes."}
            </p>
            <p className="mt-2 text-sm text-soft-white/65">
              You can safely close this page. If you began in Telegram or Discord, return to Raven there; otherwise check your dashboard for status updates.
            </p>
          </div>
        )}

        <div className="mt-4">
          <StatusBadge status={deploymentReady ? "ready" : confirmed ? "paid" : timedOut ? "pending" : "verifying"} />
        </div>

        <div className="mt-6 grid gap-3">
          {deployments.length > 0 ? deployments.map((deployment, index) => {
            const href = deploymentHref(deployment);
            const label = deployment.agent_label || `Hermes Agent ${deployment.bundle_agent_index || index + 1}`;
            const ready = Boolean(deployment.ready && href);
            return ready ? (
              <a
                key={deployment.deployment_id || label}
                href={href}
                target="_blank"
                rel="noopener noreferrer"
                className="rounded bg-signal-orange px-4 py-2 text-center font-semibold text-jet transition hover:opacity-90"
              >
                Open {label}
              </a>
            ) : (
              <button
                key={deployment.deployment_id || label}
                type="button"
                disabled
                className="flex items-center justify-center gap-2 rounded bg-signal-orange/40 px-4 py-2 font-semibold text-jet/70"
              >
                <LoadingSpinner label="" />
                {label} preparing
              </button>
            );
          }) : (
            <button
              type="button"
              disabled
              className="flex items-center justify-center gap-2 rounded bg-signal-orange/40 px-4 py-2 font-semibold text-jet/70"
            >
              <LoadingSpinner label="" />
              Hermes Agent dashboards preparing
            </button>
          )}
          {(sessionClaimed || (confirmed && !channelLabel)) && (
            <Link
              href="/dashboard"
              className="rounded border border-border px-4 py-2 text-center font-semibold text-soft-white transition hover:bg-carbon"
            >
              Account Dashboard
            </Link>
          )}
        </div>
      </section>
    </main>
  );
}
