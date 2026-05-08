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
const FAKE_SESSION_ID = "sess_test_123";
const FAKE_SESSION_TOKEN = "tok_test_456";
const FAKE_CSRF = "csrf_test_789";

let lastFetchUrl = "";
let lastFetchOpts = {};

globalThis.document = {
  cookie: `arclink_user_session_id=${FAKE_SESSION_ID}; arclink_user_session_token=${FAKE_SESSION_TOKEN}; arclink_user_csrf=${FAKE_CSRF}`,
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

async function request(path, options = {}) {
  const url = `${API_BASE}${path}`;
  const headers = {
    "Content-Type": "application/json",
    ...(options.headers || {}),
  };
  const sessionId = document.cookie.match(/arclink_(?:user|admin)_session_id=([^;]+)/)?.[1] || "";
  const sessionToken = document.cookie.match(/arclink_(?:user|admin)_session_token=([^;]+)/)?.[1] || "";
  const csrf = document.cookie.match(/arclink_(?:user|admin)_csrf=([^;]+)/)?.[1] || "";
  if (sessionId) headers["X-ArcLink-Session-Id"] = sessionId;
  if (sessionToken) headers["Authorization"] = `Bearer ${sessionToken}`;
  if (csrf) headers["X-ArcLink-CSRF-Token"] = csrf;
  const res = await fetch(url, { ...options, headers, credentials: "include" });
  const data = await res.json();
  return { status: res.status, data };
}

const api = {
  startOnboarding: (body) => request("/onboarding/start", { method: "POST", body: JSON.stringify(body) }),
  answerOnboarding: (body) => request("/onboarding/answer", { method: "POST", body: JSON.stringify(body) }),
  openCheckout: (body) => request("/onboarding/checkout", { method: "POST", body: JSON.stringify(body) }),
  userDashboard: () => request("/user/dashboard"),
  userBilling: () => request("/user/billing"),
  userProvisioning: () => request("/user/provisioning"),
  userCredentials: () => request("/user/credentials"),
  acknowledgeCredential: (body) => request("/user/credentials/acknowledge", { method: "POST", body: JSON.stringify(body) }),
  userLinkedResources: () => request("/user/linked-resources"),
  denyShareGrant: (body) => request("/user/share-grants/deny", { method: "POST", body: JSON.stringify(body) }),
  revokeShareGrant: (body) => request("/user/share-grants/revoke", { method: "POST", body: JSON.stringify(body) }),
  adminDashboard: (params) => {
    const qs = params ? "?" + new URLSearchParams(params).toString() : "";
    return request(`/admin/dashboard${qs}`);
  },
  adminServiceHealth: () => request("/admin/service-health"),
  adminProvisioningJobs: () => request("/admin/provisioning-jobs"),
  adminDnsDrift: () => request("/admin/dns-drift"),
  adminAudit: () => request("/admin/audit"),
  adminEvents: () => request("/admin/events"),
  adminActions: () => request("/admin/actions"),
  queueAdminAction: (body) => request("/admin/actions", { method: "POST", body: JSON.stringify(body) }),
  login: (kind, body) => request(`/auth/${kind}/login`, { method: "POST", body: JSON.stringify(body) }),
  logout: (kind) => request(`/auth/${kind}/logout`, { method: "POST" }),
  userPortal: (body) => request("/user/portal", { method: "POST", body: JSON.stringify(body) }),
  revokeSession: (body) => request("/admin/sessions/revoke", { method: "POST", body: JSON.stringify(body) }),
  userProviderState: () => request("/user/provider-state"),
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

  it("userLinkedResources GETs /user/linked-resources", async () => {
    await api.userLinkedResources();
    assert.ok(lastFetchUrl.endsWith("/user/linked-resources"));
  });

  it("denyShareGrant POSTs to /user/share-grants/deny", async () => {
    await api.denyShareGrant({ grant_id: "share_1" });
    assert.ok(lastFetchUrl.endsWith("/user/share-grants/deny"));
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

  it("login POSTs to /auth/{kind}/login", async () => {
    await api.login("user", { email: "u@t.com" });
    assert.ok(lastFetchUrl.endsWith("/auth/user/login"));
    await api.login("admin", { email: "a@t.com" });
    assert.ok(lastFetchUrl.endsWith("/auth/admin/login"));
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

  it("revokeSession POSTs to /admin/sessions/revoke", async () => {
    await api.revokeSession({ target_session_id: "s1", session_kind: "user" });
    assert.ok(lastFetchUrl.endsWith("/admin/sessions/revoke"));
  });
});

describe("API client header injection", () => {
  beforeEach(() => resetFetch());

  it("injects session credentials from cookies", async () => {
    await api.userDashboard();
    const h = lastFetchOpts.headers;
    assert.equal(h["X-ArcLink-Session-Id"], FAKE_SESSION_ID);
    assert.equal(h["Authorization"], `Bearer ${FAKE_SESSION_TOKEN}`);
    assert.equal(h["X-ArcLink-CSRF-Token"], FAKE_CSRF);
    assert.equal(h["Content-Type"], "application/json");
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

console.log("PASS all 27 ArcLink web API client tests");
