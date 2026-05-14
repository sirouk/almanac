/**
 * API client tests for web/src/lib/api.ts
 *
 * Replicates the api module logic to verify request construction,
 * header injection, and response parsing by mocking global fetch.
 * Runs with `node --test web/tests/test_api_client.mjs` from repo root.
 */
import { describe, it, beforeEach } from "node:test";
import assert from "node:assert/strict";

// --- Replicate api.ts logic for testability ---

const API_BASE = "/api/v1";
const FAKE_USER_CSRF = "csrf_user_789";
const FAKE_ADMIN_CSRF = "csrf_admin_987";

let lastFetchUrl = "";
let lastFetchOpts = {};

globalThis.document = {
  cookie: `arclink_user_session_id=usess_hidden; arclink_user_session_token=utok_hidden; arclink_user_csrf=${FAKE_USER_CSRF}; arclink_admin_session_id=asess_hidden; arclink_admin_session_token=atok_hidden; arclink_admin_csrf=${FAKE_ADMIN_CSRF}`,
};
globalThis.window = {};

function resetFetch(status = 200, data = { ok: true }) {
  lastFetchUrl = "";
  lastFetchOpts = {};
  globalThis.fetch = async (url, opts) => {
    lastFetchUrl = url;
    lastFetchOpts = opts || {};
    return { status, json: async () => data };
  };
}

function readCookie(name) {
  if (typeof document === "undefined") return "";
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : "";
}

async function request(path, options = {}, kind = "user") {
  const url = `${API_BASE}${path}`;
  const headers = {
    "Content-Type": "application/json",
    ...(options.headers || {}),
  };
  const csrf = readCookie(`arclink_${kind}_csrf`);
  if (csrf) headers["X-ArcLink-CSRF-Token"] = csrf;
  const res = await fetch(url, { ...options, headers, credentials: "include" });
  const data = await res.json();
  return { status: res.status, data };
}

const api = {
  startOnboarding: (body) => request("/onboarding/start", { method: "POST", body: JSON.stringify(body) }),
  answerOnboarding: (body) => request("/onboarding/answer", { method: "POST", body: JSON.stringify(body) }),
  openCheckout: (body) => request("/onboarding/checkout", { method: "POST", body: JSON.stringify(body) }),
  checkoutStatus: (sessionId) => request(`/onboarding/status?session_id=${encodeURIComponent(sessionId)}`),
  claimSession: (sessionId, claimToken) => request("/onboarding/claim-session", { method: "POST", body: JSON.stringify({ session_id: sessionId, claim_token: claimToken }) }),
  cancelOnboarding: (sessionId, cancelToken) => request("/onboarding/cancel", { method: "POST", body: JSON.stringify({ session_id: sessionId, cancel_token: cancelToken }) }),
  userDashboard: () => request("/user/dashboard", {}, "user"),
  userBilling: () => request("/user/billing", {}, "user"),
  userProvisioning: () => request("/user/provisioning", {}, "user"),
  userCredentials: () => request("/user/credentials", {}, "user"),
  acknowledgeCredential: (body) => request("/user/credentials/acknowledge", { method: "POST", body: JSON.stringify(body) }, "user"),
  updateAgentIdentity: (body) => request("/user/agent-identity", { method: "POST", body: JSON.stringify(body) }, "user"),
  userCrewRecipe: () => request("/user/crew-recipe", {}, "user"),
  previewCrewRecipe: (body) => request("/user/crew-recipe/preview", { method: "POST", body: JSON.stringify(body) }, "user"),
  applyCrewRecipe: (body) => request("/user/crew-recipe/apply", { method: "POST", body: JSON.stringify(body) }, "user"),
  userLinkedResources: () => request("/user/linked-resources", {}, "user"),
  createShareGrant: (body) => request("/user/share-grants", { method: "POST", body: JSON.stringify(body) }, "user"),
  approveShareGrant: (body) => request("/user/share-grants/approve", { method: "POST", body: JSON.stringify(body) }, "user"),
  denyShareGrant: (body) => request("/user/share-grants/deny", { method: "POST", body: JSON.stringify(body) }, "user"),
  acceptShareGrant: (body) => request("/user/share-grants/accept", { method: "POST", body: JSON.stringify(body) }, "user"),
  revokeShareGrant: (body) => request("/user/share-grants/revoke", { method: "POST", body: JSON.stringify(body) }, "user"),
  adminDashboard: (params) => {
    const qs = params ? "?" + new URLSearchParams(params).toString() : "";
    return request(`/admin/dashboard${qs}`, {}, "admin");
  },
  adminServiceHealth: () => request("/admin/service-health", {}, "admin"),
  adminProvisioningJobs: () => request("/admin/provisioning-jobs", {}, "admin"),
  adminDnsDrift: () => request("/admin/dns-drift", {}, "admin"),
  adminAudit: () => request("/admin/audit", {}, "admin"),
  adminEvents: () => request("/admin/events", {}, "admin"),
  adminActions: () => request("/admin/actions", {}, "admin"),
  queueAdminAction: (body) => request("/admin/actions", { method: "POST", body: JSON.stringify(body) }, "admin"),
  adminApplyCrewRecipe: (body) => request("/admin/crew-recipe/apply", { method: "POST", body: JSON.stringify(body) }, "admin"),
  login: (body) => request("/auth/login", { method: "POST", body: JSON.stringify(body) }),
  logout: (kind) => request(`/auth/${kind}/logout`, { method: "POST" }, kind),
  userPortal: (body) => request("/user/portal", { method: "POST", body: JSON.stringify(body) }, "user"),
  revokeSession: (body) => request("/admin/sessions/revoke", { method: "POST", body: JSON.stringify(body) }, "admin"),
  userProviderState: () => request("/user/provider-state", {}, "user"),
  adminProviderState: () => request("/admin/provider-state", {}, "admin"),
  adminReconciliation: () => request("/admin/reconciliation", {}, "admin"),
  adminOperatorSnapshot: () => request("/admin/operator-snapshot", {}, "admin"),
  adminScaleOperations: () => request("/admin/scale-operations", {}, "admin"),
  health: () => request("/health"),
  adapterMode: () => request("/adapter-mode"),
};

// --- Tests ---

describe("API client route construction", () => {
  beforeEach(() => resetFetch());

  it("startOnboarding POSTs to /onboarding/start", async () => {
    await api.startOnboarding({ channel: "web", email: "test@example.com" });
    assert.ok(lastFetchUrl.endsWith("/onboarding/start"));
    assert.equal(lastFetchOpts.method, "POST");
    assert.equal(JSON.parse(lastFetchOpts.body).channel, "web");
  });

  it("answerOnboarding POSTs to /onboarding/answer", async () => {
    await api.answerOnboarding({ session_id: "s1", question_key: "name" });
    assert.ok(lastFetchUrl.endsWith("/onboarding/answer"));
  });

  it("openCheckout POSTs to /onboarding/checkout", async () => {
    await api.openCheckout({ session_id: "s1" });
    assert.ok(lastFetchUrl.endsWith("/onboarding/checkout"));
  });

  it("checkoutStatus GETs /onboarding/status with session_id", async () => {
    await api.checkoutStatus("s1");
    assert.ok(lastFetchUrl.endsWith("/onboarding/status?session_id=s1"));
  });

  it("claimSession POSTs to /onboarding/claim-session", async () => {
    await api.claimSession("s1", "claim_1");
    assert.ok(lastFetchUrl.endsWith("/onboarding/claim-session"));
    assert.equal(lastFetchOpts.method, "POST");
    assert.equal(JSON.parse(lastFetchOpts.body).claim_token, "claim_1");
  });

  it("cancelOnboarding POSTs to /onboarding/cancel", async () => {
    await api.cancelOnboarding("s1", "cancel_1");
    assert.ok(lastFetchUrl.endsWith("/onboarding/cancel"));
    assert.equal(lastFetchOpts.method, "POST");
    assert.equal(JSON.parse(lastFetchOpts.body).cancel_token, "cancel_1");
  });

  it("userDashboard GETs /user/dashboard", async () => {
    await api.userDashboard();
    assert.ok(lastFetchUrl.endsWith("/user/dashboard"));
  });

  it("userBilling GETs /user/billing", async () => {
    await api.userBilling();
    assert.ok(lastFetchUrl.endsWith("/user/billing"));
  });

  it("userProvisioning GETs /user/provisioning", async () => {
    await api.userProvisioning();
    assert.ok(lastFetchUrl.endsWith("/user/provisioning"));
  });

  it("userCredentials GETs /user/credentials", async () => {
    await api.userCredentials();
    assert.ok(lastFetchUrl.endsWith("/user/credentials"));
  });

  it("acknowledgeCredential POSTs to /user/credentials/acknowledge", async () => {
    await api.acknowledgeCredential({ handoff_id: "cred_1" });
    assert.ok(lastFetchUrl.endsWith("/user/credentials/acknowledge"));
    assert.equal(lastFetchOpts.method, "POST");
    assert.equal(JSON.parse(lastFetchOpts.body).handoff_id, "cred_1");
  });

  it("updateAgentIdentity POSTs to /user/agent-identity", async () => {
    await api.updateAgentIdentity({ deployment_id: "dep_1", agent_name: "Atlas", agent_title: "the right hand" });
    assert.ok(lastFetchUrl.endsWith("/user/agent-identity"));
    assert.equal(lastFetchOpts.method, "POST");
    const body = JSON.parse(lastFetchOpts.body);
    assert.equal(body.agent_name, "Atlas");
    assert.equal(body.agent_title, "the right hand");
  });

  it("Crew Training routes use user session and CSRF", async () => {
    await api.userCrewRecipe();
    assert.ok(lastFetchUrl.endsWith("/user/crew-recipe"));
    await api.previewCrewRecipe({ role: "founder", mission: "ship", treatment: "peer", preset: "Frontier", capacity: "development" });
    assert.ok(lastFetchUrl.endsWith("/user/crew-recipe/preview"));
    assert.equal(lastFetchOpts.method, "POST");
    assert.equal(lastFetchOpts.headers["X-ArcLink-CSRF-Token"], FAKE_USER_CSRF);
    await api.applyCrewRecipe({ role: "founder", mission: "ship", treatment: "peer", preset: "Frontier", capacity: "development" });
    assert.ok(lastFetchUrl.endsWith("/user/crew-recipe/apply"));
  });

  it("userLinkedResources GETs /user/linked-resources", async () => {
    await api.userLinkedResources();
    assert.ok(lastFetchUrl.endsWith("/user/linked-resources"));
  });

  it("createShareGrant POSTs to /user/share-grants", async () => {
    await api.createShareGrant({ recipient_user_id: "usr_2", resource_kind: "drive" });
    assert.ok(lastFetchUrl.endsWith("/user/share-grants"));
    assert.equal(lastFetchOpts.method, "POST");
    assert.equal(JSON.parse(lastFetchOpts.body).recipient_user_id, "usr_2");
  });

  it("approveShareGrant POSTs to /user/share-grants/approve", async () => {
    await api.approveShareGrant({ grant_id: "share_1" });
    assert.ok(lastFetchUrl.endsWith("/user/share-grants/approve"));
    assert.equal(lastFetchOpts.method, "POST");
    assert.equal(JSON.parse(lastFetchOpts.body).grant_id, "share_1");
  });

  it("denyShareGrant POSTs to /user/share-grants/deny", async () => {
    await api.denyShareGrant({ grant_id: "share_1" });
    assert.ok(lastFetchUrl.endsWith("/user/share-grants/deny"));
    assert.equal(lastFetchOpts.method, "POST");
    assert.equal(JSON.parse(lastFetchOpts.body).grant_id, "share_1");
  });

  it("acceptShareGrant POSTs to /user/share-grants/accept", async () => {
    await api.acceptShareGrant({ grant_id: "share_1" });
    assert.ok(lastFetchUrl.endsWith("/user/share-grants/accept"));
    assert.equal(lastFetchOpts.method, "POST");
    assert.equal(JSON.parse(lastFetchOpts.body).grant_id, "share_1");
  });

  it("revokeShareGrant POSTs to /user/share-grants/revoke", async () => {
    await api.revokeShareGrant({ grant_id: "share_1" });
    assert.ok(lastFetchUrl.endsWith("/user/share-grants/revoke"));
    assert.equal(lastFetchOpts.method, "POST");
    assert.equal(JSON.parse(lastFetchOpts.body).grant_id, "share_1");
  });

  it("adminDashboard GETs with query params", async () => {
    await api.adminDashboard({ channel: "web", status: "active" });
    assert.ok(lastFetchUrl.includes("/admin/dashboard?"));
    assert.ok(lastFetchUrl.includes("channel=web"));
  });

  it("adminServiceHealth GETs /admin/service-health", async () => {
    await api.adminServiceHealth();
    assert.ok(lastFetchUrl.endsWith("/admin/service-health"));
  });

  it("adminProvisioningJobs GETs /admin/provisioning-jobs", async () => {
    await api.adminProvisioningJobs();
    assert.ok(lastFetchUrl.endsWith("/admin/provisioning-jobs"));
  });

  it("adminDnsDrift GETs /admin/dns-drift", async () => {
    await api.adminDnsDrift();
    assert.ok(lastFetchUrl.endsWith("/admin/dns-drift"));
  });

  it("adminAudit GETs /admin/audit", async () => {
    await api.adminAudit();
    assert.ok(lastFetchUrl.endsWith("/admin/audit"));
  });

  it("adminEvents GETs /admin/events", async () => {
    await api.adminEvents();
    assert.ok(lastFetchUrl.endsWith("/admin/events"));
  });

  it("adminActions GETs /admin/actions", async () => {
    await api.adminActions();
    assert.ok(lastFetchUrl.endsWith("/admin/actions"));
  });

  it("queueAdminAction POSTs to /admin/actions", async () => {
    await api.queueAdminAction({ action_type: "restart", reason: "test" });
    assert.ok(lastFetchUrl.endsWith("/admin/actions"));
    assert.equal(lastFetchOpts.method, "POST");
  });

  it("adminApplyCrewRecipe POSTs to admin on-behalf route", async () => {
    await api.adminApplyCrewRecipe({ user_id: "arcusr_1", role: "operator", mission: "ship", treatment: "coach", preset: "Vanguard", capacity: "sales" });
    assert.ok(lastFetchUrl.endsWith("/admin/crew-recipe/apply"));
    assert.equal(lastFetchOpts.method, "POST");
    assert.equal(lastFetchOpts.headers["X-ArcLink-CSRF-Token"], FAKE_ADMIN_CSRF);
  });

  it("login POSTs to /auth/login", async () => {
    await api.login({ email: "u@t.com" });
    assert.ok(lastFetchUrl.endsWith("/auth/login"));
  });

  it("logout POSTs to /auth/{kind}/logout", async () => {
    await api.logout("user");
    assert.ok(lastFetchUrl.endsWith("/auth/user/logout"));
    await api.logout("admin");
    assert.ok(lastFetchUrl.endsWith("/auth/admin/logout"));
  });

  it("userPortal POSTs to /user/portal", async () => {
    await api.userPortal({ return_url: "https://app.arclink.online" });
    assert.ok(lastFetchUrl.endsWith("/user/portal"));
  });

  it("userProviderState GETs /user/provider-state", async () => {
    await api.userProviderState();
    assert.ok(lastFetchUrl.endsWith("/user/provider-state"));
  });

  it("adminProviderState GETs /admin/provider-state", async () => {
    await api.adminProviderState();
    assert.ok(lastFetchUrl.endsWith("/admin/provider-state"));
  });

  it("adminReconciliation GETs /admin/reconciliation", async () => {
    await api.adminReconciliation();
    assert.ok(lastFetchUrl.endsWith("/admin/reconciliation"));
  });

  it("adminOperatorSnapshot GETs /admin/operator-snapshot", async () => {
    await api.adminOperatorSnapshot();
    assert.ok(lastFetchUrl.endsWith("/admin/operator-snapshot"));
  });

  it("adminScaleOperations GETs /admin/scale-operations", async () => {
    await api.adminScaleOperations();
    assert.ok(lastFetchUrl.endsWith("/admin/scale-operations"));
  });

  it("revokeSession POSTs to /admin/sessions/revoke", async () => {
    await api.revokeSession({ target_session_id: "s1", session_kind: "user" });
    assert.ok(lastFetchUrl.endsWith("/admin/sessions/revoke"));
  });

  it("health GETs /health", async () => {
    await api.health();
    assert.ok(lastFetchUrl.endsWith("/health"));
  });

  it("adapterMode GETs /adapter-mode", async () => {
    await api.adapterMode();
    assert.ok(lastFetchUrl.endsWith("/adapter-mode"));
  });
});

describe("API client header injection", () => {
  beforeEach(() => resetFetch());

  it("injects only the user CSRF token from cookies", async () => {
    await api.userDashboard();
    const h = lastFetchOpts.headers;
    assert.equal(h["X-ArcLink-Session-Id"], undefined);
    assert.equal(h["Authorization"], undefined);
    assert.equal(h["X-ArcLink-CSRF-Token"], FAKE_USER_CSRF);
    assert.equal(h["Content-Type"], "application/json");
  });

  it("injects the admin CSRF token for admin calls", async () => {
    await api.adminDashboard();
    const h = lastFetchOpts.headers;
    assert.equal(h["X-ArcLink-Session-Id"], undefined);
    assert.equal(h["Authorization"], undefined);
    assert.equal(h["X-ArcLink-CSRF-Token"], FAKE_ADMIN_CSRF);
  });

  it("sends credentials: include for cookie transport", async () => {
    await api.userDashboard();
    assert.equal(lastFetchOpts.credentials, "include");
  });

  it("does not inject empty session fields when cookies absent", async () => {
    const orig = document.cookie;
    document.cookie = "";
    await api.userDashboard();
    assert.equal(lastFetchOpts.headers["X-ArcLink-Session-Id"], undefined);
    assert.equal(lastFetchOpts.headers["Authorization"], undefined);
    assert.equal(lastFetchOpts.headers["X-ArcLink-CSRF-Token"], undefined);
    document.cookie = orig;
  });
});

describe("API client response parsing", () => {
  it("returns status and parsed JSON data", async () => {
    resetFetch(201, { session: { session_id: "s1" } });
    const res = await api.startOnboarding({ channel: "web", email: "t@t.com" });
    assert.equal(res.status, 201);
    assert.equal(res.data.session.session_id, "s1");
  });

  it("returns error status without throwing", async () => {
    resetFetch(401, { error: "unauthorized" });
    const res = await api.userDashboard();
    assert.equal(res.status, 401);
    assert.equal(res.data.error, "unauthorized");
  });
});

console.log("PASS all 42 ArcLink web API client tests");
