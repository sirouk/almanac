const API_BASE = process.env.NEXT_PUBLIC_ARCLINK_API_URL || "/api/v1";

export interface ApiResult<T = Record<string, unknown>> {
  status: number;
  data: T;
}

async function request<T = Record<string, unknown>>(
  path: string,
  options: RequestInit = {},
): Promise<ApiResult<T>> {
  const url = `${API_BASE}${path}`;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string> || {}),
  };

  const sessionId = typeof window !== "undefined"
    ? document.cookie.match(/arclink_(?:user|admin)_session_id=([^;]+)/)?.[1] || ""
    : "";
  const sessionToken = typeof window !== "undefined"
    ? document.cookie.match(/arclink_(?:user|admin)_session_token=([^;]+)/)?.[1] || ""
    : "";
  const csrf = typeof window !== "undefined"
    ? document.cookie.match(/arclink_(?:user|admin)_csrf=([^;]+)/)?.[1] || ""
    : "";

  if (sessionId) headers["X-ArcLink-Session-Id"] = sessionId;
  if (sessionToken) headers["Authorization"] = `Bearer ${sessionToken}`;
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

  userDashboard: () => request("/user/dashboard"),

  userBilling: () => request("/user/billing"),

  userProvisioning: () => request("/user/provisioning"),

  adminDashboard: (params?: Record<string, string>) => {
    const qs = params ? "?" + new URLSearchParams(params).toString() : "";
    return request(`/admin/dashboard${qs}`);
  },

  adminServiceHealth: () => request("/admin/service-health"),

  adminProvisioningJobs: () => request("/admin/provisioning-jobs"),

  adminDnsDrift: () => request("/admin/dns-drift"),

  adminAudit: () => request("/admin/audit"),

  adminEvents: () => request("/admin/events"),

  adminActions: () => request("/admin/actions"),

  queueAdminAction: (body: Record<string, string>) =>
    request("/admin/actions", { method: "POST", body: JSON.stringify(body) }),
};
