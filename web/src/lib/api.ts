const API_BASE = process.env.NEXT_PUBLIC_ARCLINK_API_URL || "/api/v1";

export interface ApiResult<T = Record<string, unknown>> {
  status: number;
  data: T;
}

/**
 * Read a specific cookie value by name from document.cookie.
 * Only non-HttpOnly cookies are visible to JS (i.e. CSRF tokens).
 */
function readCookie(name: string): string {
  if (typeof document === "undefined") return "";
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : "";
}

async function request<T = Record<string, unknown>>(
  path: string,
  options: RequestInit = {},
  kind: "user" | "admin" = "user",
): Promise<ApiResult<T>> {
  const url = `${API_BASE}${path}`;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string> || {}),
  };

  // CSRF token is the only non-HttpOnly cookie; session credentials are
  // transported via HttpOnly cookies (credentials: "include" handles them).
  const csrf = readCookie(`arclink_${kind}_csrf`);
  if (csrf) headers["X-ArcLink-CSRF-Token"] = csrf;

  const res = await fetch(url, {
    ...options,
    headers,
    credentials: "include",
  });
  const data = await res.json() as T;
  return { status: res.status, data };
}

export const api = {
  startOnboarding: (body: Record<string, string>) =>
    request("/onboarding/start", { method: "POST", body: JSON.stringify(body) }),

  answerOnboarding: (body: Record<string, string>) =>
    request("/onboarding/answer", { method: "POST", body: JSON.stringify(body) }),

  openCheckout: (body: Record<string, string>) =>
    request("/onboarding/checkout", { method: "POST", body: JSON.stringify(body) }),

  checkoutStatus: (sessionId: string) =>
    request(`/onboarding/status?session_id=${encodeURIComponent(sessionId)}`),

  claimSession: (sessionId: string, claimToken: string) =>
    request("/onboarding/claim-session", { method: "POST", body: JSON.stringify({ session_id: sessionId, claim_token: claimToken }) }),

  cancelOnboarding: (sessionId: string, cancelToken: string) =>
    request("/onboarding/cancel", { method: "POST", body: JSON.stringify({ session_id: sessionId, cancel_token: cancelToken }) }),

  userDashboard: () => request("/user/dashboard", {}, "user"),

  userComms: () => request("/user/comms", {}, "user"),

  userBilling: () => request("/user/billing", {}, "user"),

  userProvisioning: () => request("/user/provisioning", {}, "user"),

  userCredentials: () => request("/user/credentials", {}, "user"),

  acknowledgeCredential: (body: Record<string, string>) =>
    request("/user/credentials/acknowledge", { method: "POST", body: JSON.stringify(body) }, "user"),

  updateAgentIdentity: (body: Record<string, string>) =>
    request("/user/agent-identity", { method: "POST", body: JSON.stringify(body) }, "user"),

  userCrewRecipe: () => request("/user/crew-recipe", {}, "user"),

  previewCrewRecipe: (body: Record<string, string>) =>
    request("/user/crew-recipe/preview", { method: "POST", body: JSON.stringify(body) }, "user"),

  applyCrewRecipe: (body: Record<string, string>) =>
    request("/user/crew-recipe/apply", { method: "POST", body: JSON.stringify(body) }, "user"),

  userLinkedResources: () => request("/user/linked-resources", {}, "user"),

  createShareGrant: (body: Record<string, string>) =>
    request("/user/share-grants", { method: "POST", body: JSON.stringify(body) }, "user"),

  approveShareGrant: (body: Record<string, string>) =>
    request("/user/share-grants/approve", { method: "POST", body: JSON.stringify(body) }, "user"),

  denyShareGrant: (body: Record<string, string>) =>
    request("/user/share-grants/deny", { method: "POST", body: JSON.stringify(body) }, "user"),

  acceptShareGrant: (body: Record<string, string>) =>
    request("/user/share-grants/accept", { method: "POST", body: JSON.stringify(body) }, "user"),

  revokeShareGrant: (body: Record<string, string>) =>
    request("/user/share-grants/revoke", { method: "POST", body: JSON.stringify(body) }, "user"),

  adminDashboard: (params?: Record<string, string>) => {
    const qs = params ? "?" + new URLSearchParams(params).toString() : "";
    return request(`/admin/dashboard${qs}`, {}, "admin");
  },

  adminComms: () => request("/admin/comms", {}, "admin"),

  adminServiceHealth: () => request("/admin/service-health", {}, "admin"),

  adminProvisioningJobs: () => request("/admin/provisioning-jobs", {}, "admin"),

  adminDnsDrift: () => request("/admin/dns-drift", {}, "admin"),

  adminAudit: () => request("/admin/audit", {}, "admin"),

  adminEvents: () => request("/admin/events", {}, "admin"),

  adminActions: () => request("/admin/actions", {}, "admin"),

  queueAdminAction: (body: Record<string, string>) =>
    request("/admin/actions", { method: "POST", body: JSON.stringify(body) }, "admin"),

  adminApplyCrewRecipe: (body: Record<string, string>) =>
    request("/admin/crew-recipe/apply", { method: "POST", body: JSON.stringify(body) }, "admin"),

  login: (body: Record<string, string>) =>
    request<{ session?: Record<string, unknown>; session_kind?: "user" | "admin"; role?: string; error?: string }>(
      "/auth/login",
      { method: "POST", body: JSON.stringify(body) },
    ),

  logout: (kind: "user" | "admin") =>
    request(`/auth/${kind}/logout`, { method: "POST" }, kind),

  userPortal: (body: Record<string, string>) =>
    request("/user/portal", { method: "POST", body: JSON.stringify(body) }, "user"),

  revokeSession: (body: Record<string, string>) =>
    request("/admin/sessions/revoke", { method: "POST", body: JSON.stringify(body) }, "admin"),

  userProviderState: () => request("/user/provider-state", {}, "user"),

  adminProviderState: () => request("/admin/provider-state", {}, "admin"),

  adminReconciliation: () => request("/admin/reconciliation", {}, "admin"),

  adminOperatorSnapshot: () => request("/admin/operator-snapshot", {}, "admin"),

  adminScaleOperations: () => request("/admin/scale-operations", {}, "admin"),

  health: () => request("/health"),

  adapterMode: () => request("/adapter-mode"),
};
