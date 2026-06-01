/**
 * ArcLink Production 10 - Browser Product Checks
 *
 * Runs against the built Next.js app with deterministic mocked API responses.
 * Verifies brand system, layout integrity, accessible forms, empty/error/loading
 * states, and no false live-service claims across desktop and mobile viewports.
 *
 * Regenerate screenshots:
 *   cd web && npx playwright test --update-snapshots
 */
import { test, expect, type Page, type Route } from "@playwright/test";

// ---------------------------------------------------------------------------
// Deterministic mock API responses
// ---------------------------------------------------------------------------

const MOCK_USER_DASHBOARD = {
  user: { user_id: "u_test1", email: "test@arclink.dev", display_name: "Test User" },
  deployments: [
    {
      deployment_id: "dep_001",
      agent_label: "Raven Prime",
      hostname: "test.arclink.online",
      prefix: "test",
      base_domain: "arclink.online",
      status: "active",
      service_health: [
        { service_name: "hermes", status: "healthy", checked_at: "2026-05-01T12:00:00Z" },
        { service_name: "nextcloud", status: "healthy", checked_at: "2026-05-01T12:00:00Z" },
        { service_name: "code-server", status: "degraded", checked_at: "2026-05-01T12:00:00Z" },
      ],
      model: { provider: "chutes", model_id: "deepseek-r1", credential_state: "active" },
      freshness: {
        qmd: { status: "fresh", checked_at: "2026-05-01T12:00:00Z" },
        memory: { status: "stale", checked_at: "2026-04-30T08:00:00Z" },
      },
      notion_setup: {
        status: "local_metadata_verified",
        model: "brokered_shared_root",
        callback_url: "https://test.arclink.online/notion/webhook",
        public_status: "ready_for_dashboard_verification",
        webhook: {
          configured: true,
          verified: true,
          status: "webhook_verified",
          installed_at: "2026-05-01T12:00:00Z",
          verified_at: "2026-05-01T12:05:00Z",
        },
        index: { status: "available" },
        verification: {
          state: "local_metadata_verified",
          dashboard: "local_metadata_verified",
          setup_intent: "ready_for_dashboard_verification",
          local_metadata: "local_metadata_verified",
          email_share: "not_proof",
          user_owned_oauth: "policy_question",
          shared_root_live_read: "proof_gated",
          brokered_write_preflight: "proof_gated",
          live_workspace: "proof_gated",
        },
      },
      bot_contact: { channel: "telegram", first_contacted: true, handoff_recorded: true },
      access: {
        urls: {
          dashboard: "https://test.arclink.online/u/arc-test",
          files: "https://test.arclink.online/u/arc-test/drive",
          code: "https://test.arclink.online/u/arc-test/code",
          hermes: "https://test.arclink.online/u/arc-test/hermes",
        },
      },
    },
  ],
  entitlement: { state: "paid" },
};

const MOCK_USER_BILLING = {
  entitlement: { state: "paid" },
  subscriptions: [{ subscription_id: "sub_test1", status: "active" }],
  renewal_lifecycle: {
    payment_state: "paid",
    provider_access: "allowed",
    warning_cadence: "not_applicable",
    grace_period: "not_applicable",
    data_retention: "active",
    purge_policy: "not_applicable",
    reason: "Billing is current for this deployment.",
  },
};

const MOCK_USER_PROVISIONING = {
  deployments: [
    {
      deployment_id: "dep_001",
      hostname: "test.arclink.online",
      status: "active",
      service_health: [
        { service_name: "hermes", status: "healthy" },
      ],
    },
  ],
};

const MOCK_USER_CREDENTIALS = {
  instructions: {
    copy: "Copy each credential from the secure completion bundle into your password manager.",
    acknowledge: "After acknowledgement, ArcLink removes the handoff from future user API responses.",
  },
  credentials: [
    {
      handoff_id: "cred_test_dashboard",
      deployment_id: "dep_001",
      credential_kind: "dashboard_password",
      display_name: "Dashboard password",
      status: "available",
      secret_ref: "secret://masked/dashboard/dep_001/password",
      reveal_mode: "secure_completion_bundle",
      delivery_hint: "Copy the credential from the secure completion bundle into your password manager.",
      copy_guidance: "Store it in a password manager; do not paste it into shared channels.",
    },
  ],
  removed_count: 0,
};

const MOCK_USER_LINKED_RESOURCES = {
  linked_resources: [
    {
      grant_id: "share_001",
      owner_user_id: "u_owner",
      resource_kind: "drive",
      resource_root: "vault",
      resource_path: "/Projects/brief.md",
      linked_root: "linked",
      linked_path: "/share_001-project-brief",
      projection: {
        status: "materialized",
        linked_root: "linked",
        linked_path: "/share_001-project-brief",
        entry_path: "/share_001-project-brief/brief.md",
        read_only: false,
      },
      display_name: "Project Brief",
      access_mode: "read_write",
      status: "accepted",
      reshare_allowed: false,
    },
  ],
};

const MOCK_USER_SHARE_GRANTS = {
  share_grants: [],
};

const MOCK_USER_CREW_RECIPE = {
  current: {
    recipe_id: "crew_001",
    preset: "Frontier",
    capacity: "development",
    role: "founder",
    mission: "ship the launch",
    treatment: "peer",
    applied_at: "2026-05-01T12:00:00Z",
    status: "active",
    soul_overlay: { crew_recipe_text: "Frontier Development Crew Recipe for shipping the launch." },
  },
  prior: null,
  whats_changed: { status: "first_recipe", summary: "This is the first active Crew Recipe." },
};

const MOCK_USER_ACADEMY = {
  majors: [
    {
      program_id: "academy_founder_operator",
      label: "Founder Operator",
      summary: "Conversation-led training that prepares a Hermes Agent for a specialist role.",
      source_lanes: ["captain_instructions", "weekly_sources"],
      default_depth: "deep",
    },
  ],
  trainees: [],
  graduates: [],
};

const MOCK_USER_PROVIDER_STATE = {
  provider: "chutes",
  default_model: "deepseek-r1",
  provider_boundary: {
    credential_isolation: "per-user or per-deployment secret:// reference required",
    operator_shared_key_policy: "not accepted as user isolation",
    budget_enforcement: "fail_closed",
    live_key_creation: "proof_gated",
    threshold_continuation: {
      status: "policy_question",
      dashboard_guidance: "show_sanitized_threshold_state_only",
      raven_notifications: "disabled_until_warning_cadence_policy",
      provider_fallback: "policy_question",
      overage_refill: "policy_question",
      warning_cadence: "policy_question",
      reason: "ArcLink exposes sanitized Chutes warning/exhaustion state only. Provider fallback, overage refill, and Raven warning cadence require operator policy before continuation guidance is shown.",
    },
  },
  provider_settings: {
    self_service_provider_add: "policy_question",
    dashboard_mutation: "disabled",
    current_change_path: "operator_managed_deployment_config_or_secure_credential_handoff",
    secret_input_policy: "dashboard_never_collects_raw_provider_tokens",
    live_provider_mutation: "proof_gated",
    operator_decision_needed: "Decide whether users may self-service provider changes in ArcLink settings, or whether provider changes remain operator-managed deployment config.",
    guidance: "The dashboard shows provider state only. Provider changes use secure credential handoff or operator-managed config until product policy defines a self-service flow.",
  },
  deployment_models: [
    {
      deployment_id: "dep_001",
      model_id: "deepseek-r1",
      credential_state: "budget_warning",
      allow_inference: true,
      provider_detail: {
        reason: "Provider budget is near the configured warning threshold.",
        budget: { status: "warning", monthly_cents: 10000, used_cents: 8500, remaining_cents: 1500, usage_percent: 85 },
        threshold_continuation: {
          status: "policy_question",
          dashboard_guidance: "show_sanitized_threshold_state_only",
          raven_notifications: "disabled_until_warning_cadence_policy",
          provider_fallback: "policy_question",
          overage_refill: "policy_question",
          warning_cadence: "policy_question",
          reason: "ArcLink exposes sanitized Chutes warning/exhaustion state only. Provider fallback, overage refill, and Raven warning cadence require operator policy before continuation guidance is shown.",
        },
      },
    },
  ],
};

const MOCK_ADMIN_ACTION_MATRIX = [
  {
    action_type: "restart",
    label: "Restart",
    readiness: "queueable",
    queueable: true,
    worker_support: "wired",
    operation_kind: "docker_compose_lifecycle",
    required_adapter: "ARCLINK_EXECUTOR_ADAPTER=fake|local|ssh",
    live_proof_gate: "PG-PROVISION",
    local_contract: "queues an audited Docker Compose lifecycle restart intent",
    fail_closed_reason: "",
  },
  {
    action_type: "dns_repair",
    label: "DNS repair",
    readiness: "queueable",
    queueable: true,
    worker_support: "wired",
    operation_kind: "cloudflare_dns_apply",
    required_adapter: "ARCLINK_EXECUTOR_ADAPTER=fake|local|ssh plus configured DNS provider credentials for live mutation",
    live_proof_gate: "PG-INGRESS",
    local_contract: "queues an audited DNS repair intent",
    fail_closed_reason: "",
  },
  {
    action_type: "rollout",
    label: "Rollout",
    readiness: "queueable",
    queueable: true,
    worker_support: "wired",
    operation_kind: "arcpod_update_rollout",
    required_adapter: "action worker with control DB access; explicit fake/local record-only execution contract",
    live_proof_gate: "PG-UPGRADE/PG-HERMES",
    local_contract: "queues audited local ArcPod update rollout rows and can record one bounded fake/local batch",
    fail_closed_reason: "",
  },
];

const MOCK_ADMIN_DASHBOARD = {
  users: [
    { user_id: "u_test1", email: "test@arclink.dev", display_name: "Test User", entitlement_state: "paid", stripe_customer_id: "cus_test1" },
  ],
  deployments: [
    { deployment_id: "dep_001", user_id: "u_test1", prefix: "test", base_domain: "arclink.online", status: "active", updated_at: "2026-05-01T12:00:00Z" },
  ],
  sections: [
    { section: "infrastructure", label: "Infrastructure", status: "healthy", counts: { nodes: 1, containers: 4 } },
    { section: "bots", label: "Bots", status: "healthy", counts: { telegram: 1, discord: 0 } },
    { section: "security_abuse", label: "Security & Abuse", status: "healthy", counts: { failed_logins: 0 } },
    { section: "releases_maintenance", label: "Releases", status: "current", counts: { pending: 0 } },
  ],
  onboarding_funnel: { started: 3, answered: 2, checkout: 1, paid: 1 },
  subscriptions: [],
  active_sessions: { user: 1, admin: 1 },
  recent_failures: [],
  action_execution_readiness: {
    executable: ["restart", "reprovision", "dns_repair", "rotate_chutes_key", "refund", "cancel", "comp", "rollout"],
    pending_not_implemented: ["force_resynth", "rotate_bot_key", "suspend", "unsuspend"],
    disabled: ["force_resynth", "rotate_bot_key", "suspend", "unsuspend"],
    action_matrix: MOCK_ADMIN_ACTION_MATRIX,
    action_support: Object.fromEntries(MOCK_ADMIN_ACTION_MATRIX.map((entry) => [entry.action_type, entry])),
    executor_adapter: "fake",
    queue_policy: "admin UI queues only modeled worker actions; pending actions stay disabled until worker wiring lands",
  },
};

const MOCK_ONBOARDING_START = {
  session: { session_id: "sess_mock_1" },
  browser_claim_token: "claim_mock_1",
  browser_cancel_token: "cancel_mock_1",
};
const MOCK_ONBOARDING_ANSWER = { ok: true };
const MOCK_ONBOARDING_STATUS_PAID = {
  entitlement_state: "paid",
  display_name: "New User",
  channel: "web",
  deployment: { ready: false, status: "queued", access: { urls: {} } },
};
const MOCK_LOGIN_OK = { session: { session_id: "sess_login_1" } };
const MOCK_ADAPTER_MODE = { fake_mode: true };

// ---------------------------------------------------------------------------
// Route mocking helper
// ---------------------------------------------------------------------------

async function mockApi(
  page: Page,
  options: {
    credentialsStatus?: number;
    linkedResourcesStatus?: number;
    onboardingStarts?: Array<Record<string, unknown>>;
  } = {},
) {
  await page.route("**/api/v1/**", async (route: Route) => {
    const url = route.request().url();
    const method = route.request().method();

    if (url.includes("/user/dashboard")) {
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_USER_DASHBOARD) });
    }
    if (url.includes("/user/billing")) {
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_USER_BILLING) });
    }
    if (url.includes("/user/provisioning")) {
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_USER_PROVISIONING) });
    }
    if (url.includes("/user/comms")) {
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ comms: [] }) });
    }
    if (url.includes("/user/crew-recipe/preview") && method === "POST") {
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ preview: { mode: "fallback", fallback: true, fallback_reason: "Live recipe generation requires Chutes credentials. Using preset-only overlay.", recipe_text: "Frontier Development Crew Recipe for shipping the launch." } }) });
    }
    if (url.includes("/user/crew-recipe/apply") && method === "POST") {
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ recipe: MOCK_USER_CREW_RECIPE.current, preview: { mode: "fallback", fallback: true, recipe_text: "Frontier Development Crew Recipe for shipping the launch." }, identity_projection: {} }) });
    }
    if (url.includes("/user/crew-recipe")) {
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_USER_CREW_RECIPE) });
    }
    if (url.includes("/user/credentials/acknowledge") && method === "POST") {
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ credential: { ...MOCK_USER_CREDENTIALS.credentials[0], status: "removed" } }) });
    }
    if (url.includes("/user/credentials")) {
      if (options.credentialsStatus && options.credentialsStatus !== 200) {
        return route.fulfill({ status: options.credentialsStatus, contentType: "application/json", body: JSON.stringify({ error: "unavailable" }) });
      }
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_USER_CREDENTIALS) });
    }
    if (url.includes("/user/linked-resources")) {
      if (options.linkedResourcesStatus && options.linkedResourcesStatus !== 200) {
        return route.fulfill({ status: options.linkedResourcesStatus, contentType: "application/json", body: JSON.stringify({ error: "unavailable" }) });
      }
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_USER_LINKED_RESOURCES) });
    }
    if (url.includes("/user/share-grants")) {
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_USER_SHARE_GRANTS) });
    }
    if (url.includes("/user/academy")) {
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_USER_ACADEMY) });
    }
    if (url.includes("/user/provider-state")) {
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_USER_PROVIDER_STATE) });
    }
    if (url.includes("/adapter-mode")) {
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_ADAPTER_MODE) });
    }
    if (url.includes("/user/portal") && method === "POST") {
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ portal_url: "https://billing.stripe.com/test" }) });
    }
    if (url.includes("/admin/dashboard")) {
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_ADMIN_DASHBOARD) });
    }
    if (url.includes("/admin/service-health")) {
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ service_health: MOCK_USER_DASHBOARD.deployments[0].service_health.map(s => ({ ...s, deployment_id: "dep_001" })) }) });
    }
    if (url.includes("/admin/provisioning-jobs")) {
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ provisioning_jobs: [] }) });
    }
    if (url.includes("/admin/dns-drift")) {
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ dns_drift: [] }) });
    }
    if (url.includes("/admin/audit")) {
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ audit: [{ created_at: "2026-05-01", actor_id: "admin_1", action: "restart", target_id: "dep_001", reason: "test" }] }) });
    }
    if (url.includes("/admin/events")) {
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ events: [] }) });
    }
    if (url.includes("/admin/actions") && method === "GET") {
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ actions: [] }) });
    }
    if (url.includes("/admin/actions") && method === "POST") {
      return route.fulfill({ status: 202, contentType: "application/json", body: JSON.stringify({ ok: true, action_id: "act_mock" }) });
    }
    if (url.includes("/admin/crew-recipe/apply") && method === "POST") {
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ recipe: MOCK_USER_CREW_RECIPE.current, identity_projection: {} }) });
    }
    if (url.includes("/admin/provider-state")) {
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ stripe: "fake", cloudflare: "fake", chutes: "fake" }) });
    }
    if (url.includes("/admin/reconciliation")) {
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ reconciliation: [], drift_count: 0 }) });
    }
    if (url.includes("/admin/sessions/revoke") && method === "POST") {
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ok: true }) });
    }
    if (url.includes("/onboarding/start") && method === "POST") {
      try {
        options.onboardingStarts?.push(JSON.parse(route.request().postData() || "{}") as Record<string, unknown>);
      } catch {
        options.onboardingStarts?.push({});
      }
      return route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify(MOCK_ONBOARDING_START) });
    }
    if (url.includes("/onboarding/answer") && method === "POST") {
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_ONBOARDING_ANSWER) });
    }
    if (url.includes("/onboarding/checkout") && method === "POST") {
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ session: { checkout_url: "https://checkout.stripe.com/test" } }) });
    }
    if (url.includes("/onboarding/status") && method === "GET") {
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_ONBOARDING_STATUS_PAID) });
    }
    if (url.includes("/onboarding/claim-session") && method === "POST") {
      return route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify({ email: "new.user@example.test" }) });
    }
    if (url.includes("/onboarding/cancel") && method === "POST") {
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "payment_cancelled", changed: true }) });
    }
    if (url.includes("/auth/") && url.includes("/login") && method === "POST") {
      return route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify(MOCK_LOGIN_OK) });
    }
    if (url.includes("/auth/") && url.includes("/logout") && method === "POST") {
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ok: true }) });
    }

    return route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ error: "unmocked" }) });
  });
}

async function mockDashboardAuxApi(page: Page) {
  await page.route("**/api/v1/user/comms", async (route: Route) => {
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ comms: [] }) });
  });
  await page.route("**/api/v1/user/crew-recipe", async (route: Route) => {
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_USER_CREW_RECIPE) });
  });
  await page.route("**/api/v1/user/credentials/acknowledge", async (route: Route) => {
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ credential: { ...MOCK_USER_CREDENTIALS.credentials[0], status: "removed" } }) });
  });
  await page.route("**/api/v1/user/credentials", async (route: Route) => {
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_USER_CREDENTIALS) });
  });
  await page.route("**/api/v1/user/linked-resources", async (route: Route) => {
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_USER_LINKED_RESOURCES) });
  });
  await page.route("**/api/v1/user/share-grants", async (route: Route) => {
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_USER_SHARE_GRANTS) });
  });
  await page.route("**/api/v1/user/academy", async (route: Route) => {
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_USER_ACADEMY) });
  });
  await page.route("**/api/v1/user/provider-state", async (route: Route) => {
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_USER_PROVIDER_STATE) });
  });
}

// ---------------------------------------------------------------------------
// Brand system checks
// ---------------------------------------------------------------------------

test.describe("Brand system", () => {
  test("landing page uses ArcLink brand colors and typography", async ({ page }) => {
    await page.goto("/");
    const body = page.locator("body");
    await expect(body).toBeVisible();

    // Brand text present
    await expect(page.locator("text=ARCLINK").first()).toBeVisible();

    // Signal orange CTA exists
    const cta = page.locator('a[href="/onboarding"]').first();
    await expect(cta).toBeVisible();

    // No blank page
    const content = await page.textContent("body");
    expect(content!.length).toBeGreaterThan(50);
  });

  test("standalone build serves critical marketing assets", async ({ page }) => {
    const logo = await page.request.get("/marketing/Arclink_v3--orange_symbol_white_text.svg");
    expect(logo.status()).toBe(200);
    expect(logo.headers()["content-type"]).toContain("image/svg+xml");
    const ravenHero = await page.request.get("/marketing/raven-hero1.png");
    expect(ravenHero.status()).toBe(200);
    expect(ravenHero.headers()["content-type"]).toContain("image/png");
  });

  test("landing page loads brand imagery without broken images", async ({ page }) => {
    await page.goto("/");
    const logo = page.getByAltText("ArcLink").first();
    await expect(logo).toBeVisible();
    expect(await logo.evaluate((img) => (img as HTMLImageElement).complete && (img as HTMLImageElement).naturalWidth > 0)).toBeTruthy();
    const ravenHero = page.getByAltText("Raven — ArcLink AI Operator").first();
    await expect(ravenHero).toBeVisible();
    expect(await ravenHero.evaluate((img) => (img as HTMLImageElement).complete && (img as HTMLImageElement).naturalWidth > 0)).toBeTruthy();
  });

  test("landing page renders the imported marketing sections", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: /Raven runs your operations/i })).toBeVisible();
    await expect(page.getByRole("heading", { name: /Hire Raven, an agent/i })).toBeVisible();
    await expect(page.getByRole("heading", { name: /From idea to operating/i })).toBeVisible();
    await expect(page.getByRole("heading", { name: /One agent. Clear price./i })).toBeVisible();
    await expect(page.getByRole("heading", { name: /Questions answered./i })).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// Route-level smoke tests: no blank pages, primary actions visible
// ---------------------------------------------------------------------------

test.describe("Route smoke", () => {
  test("/ renders without errors", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator("nav")).toBeVisible();
    await expect(page.locator("main")).toBeVisible();
    await expect(page.locator("footer")).toBeVisible();
  });

  test("/login renders sign-in form", async ({ page }) => {
    await page.goto("/login");
    await expect(page.locator("text=Sign In").first()).toBeVisible();
    await expect(page.locator('input[type="email"]')).toBeVisible();
    await expect(page.locator('button[type="submit"]')).toBeVisible();
  });

  test("/onboarding renders start step", async ({ page }) => {
    await mockApi(page);
    await page.goto("/onboarding");
    await expect(page.getByRole("heading", { name: "Choose ArcLink Onboarding" })).toBeVisible();
    await expect(page.getByText("I can take you from a few answers to an Agent live on ArcLink")).toBeVisible();
    await expect(page.getByRole("button", { name: /Founders - \$149\/month/ })).toBeVisible();
    // Fake adapter notice present
    await expect(page.locator("text=Fake adapters")).toBeVisible();
  });

  test("/dashboard renders with mocked data", async ({ page }) => {
    await mockApi(page);
    await page.goto("/dashboard");
    await expect(page.locator("text=Raven console").first()).toBeVisible();
    await expect(page.locator("main").getByText("Raven Prime").first()).toBeVisible();
    await expect(page.locator("main").getByText("test.arclink.online").first()).toBeVisible();
    await expect(page.getByText("Recovery Actions")).toBeVisible();
    await expect(page.getByText("Workspace Readiness")).toBeVisible();
    await expect(page.getByText("Service attention")).toBeVisible();
    await expect(page.getByText("Provider threshold state visible")).toBeVisible();
    await page.locator('button:has-text("security"):visible').first().click();
    await expect(page.getByText("Credential Handoff")).toBeVisible();
    await expect(page.getByText("Dashboard password")).toBeVisible();
    await expect(page.getByText("secret://masked/dashboard/dep_001/password")).toBeVisible();
    await expect(page.locator("body")).not.toContainText("secret://arclink");
    await page.locator('button:has-text("billing"):visible').first().click();
    await expect(page.getByText("Provider Access")).toBeVisible();
    await expect(page.getByText("Billing is current for this deployment.")).toBeVisible();
    await page.locator('button:has-text("vault"):visible').first().click();
    await expect(page.getByRole("heading", { name: "Linked Resources" })).toBeVisible();
    await expect(page.getByText("Accepted Drive and Code folders appear as writable Linked resources.")).toBeVisible();
    await expect(page.getByText("Project Brief")).toBeVisible();
    await expect(page.getByText("Linked: linked:/share_001-project-brief")).toBeVisible();
    await expect(page.getByText("materialized")).toBeVisible();
    await expect(page.getByText("no reshare")).toBeVisible();
    await expect(page.locator("body")).not.toContainText("Generate share link");
    await expect(page.locator("body")).not.toContainText("Create share link");
    await page.locator('button:has-text("services"):visible').first().click();
    await expect(page.getByRole("link", { name: "Hermes Dashboard →" })).toHaveAttribute("href", "https://test.arclink.online/u/arc-test/hermes");
    await expect(page.getByRole("link", { name: "Drive →" })).toHaveAttribute("href", "https://test.arclink.online/u/arc-test/drive");
    await expect(page.getByRole("link", { name: "Code →" })).toHaveAttribute("href", "https://test.arclink.online/u/arc-test/code");
    await expect(page.getByRole("link", { name: "Terminal →" })).toHaveAttribute("href", "https://test.arclink.online/u/arc-test/hermes/terminal");
    await page.locator('button:has-text("model"):visible').first().click();
    await expect(page.getByText("Provider Settings")).toBeVisible();
    await expect(page.getByText("Self-Service Provider Add")).toBeVisible();
    await expect(page.getByText("Threshold Guidance Policy")).toBeVisible();
    await expect(page.getByText("Raven notifications: disabled until warning cadence policy; fallback: policy question; refill: policy question.")).toBeVisible();
    await expect(page.getByText("policy question").first()).toBeVisible();
    await expect(page.getByText("dashboard never collects raw provider tokens")).toBeVisible();
    await page.locator('button:has-text("memory"):visible').first().click();
    await expect(page.getByText("Notion SSOT")).toBeVisible();
    await expect(page.getByText("https://test.arclink.online/notion/webhook")).toBeVisible();
    await expect(page.locator("body")).not.toContainText("verification_token");
  });

  test("/admin renders with mocked data", async ({ page }) => {
    await mockApi(page);
    await page.goto("/admin");
    await expect(page.locator("text=ArcLink Global Operations").first()).toBeVisible();
    await expect(page.getByText("Operations Triage")).toBeVisible();
    await expect(page.getByText("Actionable control-plane signals")).toBeVisible();
    await expect(page.getByText("Disabled and proof-gated actions")).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// Accessible forms
// ---------------------------------------------------------------------------

test.describe("Accessibility", () => {
  test("login form has labeled inputs", async ({ page }) => {
    await page.goto("/login");
    const emailInput = page.locator('input[id="email"]');
    await expect(emailInput).toBeVisible();
    const label = page.locator('label[for="email"]');
    await expect(label).toBeVisible();
  });

  test("onboarding form has labeled inputs", async ({ page }) => {
    await mockApi(page);
    await page.goto("/onboarding");
    await page.getByRole("button", { name: /Founders - \$149\/month/ }).click();
    const nameInput = page.locator('input[id="name"]');
    await expect(nameInput).toBeVisible();
    const label = page.locator('label[for="name"]');
    await expect(label).toBeVisible();
    await expect(page.locator('label[for="agent-name"]')).toHaveText("Agent Name");
    await expect(page.locator('input[id="agent-name"]')).toHaveAttribute("required", "");
    await expect(page.locator('label[for="agent-title"]')).toHaveText("Agent Title");
    await expect(page.locator('input[id="agent-title"]')).toHaveAttribute("required", "");
  });

  test("login form focus state works", async ({ page }) => {
    await page.goto("/login");
    const emailInput = page.locator('input[id="email"]');
    await emailInput.focus();
    await expect(emailInput).toBeFocused();
  });

  test("keyboard navigation works on login", async ({ page }) => {
    await page.goto("/login");
    await page.keyboard.press("Tab");
    // Something should be focused
    const focused = page.locator(":focus");
    await expect(focused).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// Empty / error / loading states
// ---------------------------------------------------------------------------

test.describe("Empty and loading states", () => {
  test("dashboard shows loading spinner initially", async ({ page }) => {
    await mockDashboardAuxApi(page);
    // Delay API response to catch loading state
    await page.route("**/api/v1/user/dashboard", async (route) => {
      await new Promise((r) => setTimeout(r, 1500));
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_USER_DASHBOARD) });
    });
    await page.route("**/api/v1/user/billing", async (route) => {
      await new Promise((r) => setTimeout(r, 1500));
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_USER_BILLING) });
    });
    await page.route("**/api/v1/user/provisioning", async (route) => {
      await new Promise((r) => setTimeout(r, 1500));
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_USER_PROVISIONING) });
    });
    const loadingVisible = expect(page.getByText("Loading dashboard", { exact: false })).toBeVisible();
    await page.goto("/dashboard");
    await loadingVisible;
  });

  test("dashboard shows empty state with no deployments", async ({ page }) => {
    await mockDashboardAuxApi(page);
    await page.route("**/api/v1/user/dashboard", async (route) => {
      return route.fulfill({
        status: 200, contentType: "application/json",
        body: JSON.stringify({ ...MOCK_USER_DASHBOARD, deployments: [] }),
      });
    });
    await page.route("**/api/v1/user/billing", async (route) => {
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_USER_BILLING) });
    });
    await page.route("**/api/v1/user/provisioning", async (route) => {
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ deployments: [] }) });
    });
    await page.goto("/dashboard");
    await expect(page.locator("text=No deployments yet")).toBeVisible();
  });

  test("dashboard shows error on API failure", async ({ page }) => {
    await mockDashboardAuxApi(page);
    await page.route("**/api/v1/user/dashboard", async (route) => {
      return route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ error: "server error" }) });
    });
    await page.route("**/api/v1/user/billing", async (route) => {
      return route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({}) });
    });
    await page.route("**/api/v1/user/provisioning", async (route) => {
      return route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({}) });
    });
    await page.goto("/dashboard");
    await expect(page.locator("text=Failed to load dashboard")).toBeVisible();
  });

  test("dashboard shows scoped errors when credential and linked-resource panels fail", async ({ page }) => {
    await mockApi(page, { credentialsStatus: 503, linkedResourcesStatus: 503 });
    await page.goto("/dashboard");
    await expect(page.locator("text=Raven console").first()).toBeVisible();

    await page.locator('button:has-text("security"):visible').first().click();
    await expect(page.getByText("Credential handoff could not be loaded")).toBeVisible();
    await expect(page.locator("body")).not.toContainText("No pending credential handoffs");

    await page.locator('button:has-text("vault"):visible').first().click();
    await expect(page.getByText("Linked resources could not be loaded")).toBeVisible();
    await expect(page.locator("body")).not.toContainText("No linked resources accepted yet");
  });
});

// ---------------------------------------------------------------------------
// No false live-service claims
// ---------------------------------------------------------------------------

test.describe("No false live claims", () => {
  test("no page claims deployment is live and running", async ({ page }) => {
    await mockApi(page);
    const routes = ["/", "/login", "/onboarding"];
    for (const route of routes) {
      await page.goto(route);
      const text = await page.textContent("body");
      expect(text).not.toContain("deployment is live and running");
    }
  });

  test("onboarding shows fake adapter notice", async ({ page }) => {
    await mockApi(page);
    await page.goto("/onboarding");
    await expect(page.locator("text=Fake adapters active")).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// Mobile-specific layout checks
// ---------------------------------------------------------------------------

test.describe("Mobile layout", () => {
  test("dashboard mobile tab bar is visible on narrow viewport", async ({ page, browserName }, testInfo) => {
    if (testInfo.project.name !== "mobile") test.skip();
    await mockApi(page);
    await page.goto("/dashboard");
    await expect(page.locator("text=Raven console").first()).toBeVisible();
    // Mobile tab bar should be visible, sidebar hidden
    const mobileTabs = page.locator(".md\\:hidden").first();
    await expect(mobileTabs).toBeVisible();
  });

  test("admin mobile tab bar wraps without overflow", async ({ page, browserName }, testInfo) => {
    if (testInfo.project.name !== "mobile") test.skip();
    await mockApi(page);
    await page.goto("/admin");
    await expect(page.locator("text=ArcLink Global Operations").first()).toBeVisible();
    // No horizontal scrollbar on main content
    const mainWidth = await page.locator("main").evaluate((el) => el.scrollWidth <= el.clientWidth + 2);
    expect(mainWidth).toBe(true);
  });

  test("landing page hero text does not overflow on mobile", async ({ page }, testInfo) => {
    if (testInfo.project.name !== "mobile") test.skip();
    await page.goto("/");
    const main = page.locator("main");
    await expect(main).toBeVisible();
    const noOverflow = await main.evaluate((el) => el.scrollWidth <= el.clientWidth + 2);
    expect(noOverflow).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// Dashboard tab navigation
// ---------------------------------------------------------------------------

test.describe("Dashboard tabs", () => {
  test("all user dashboard tabs render content", async ({ page }) => {
    await mockApi(page);
    await page.goto("/dashboard");
    await expect(page.locator("text=Raven console").first()).toBeVisible();

    const tabs = ["billing", "provisioning", "services", "vault", "bots", "model", "memory", "security", "support"];
    for (const tab of tabs) {
      await page.locator(`button:has-text("${tab}"):visible`).first().click();
      await expect(page.locator("main h1").first()).toBeVisible();
    }
  });

  test("admin dashboard tabs render content", async ({ page }) => {
    await mockApi(page);
    await page.goto("/admin");
    await expect(page.locator("text=ArcLink Global Operations").first()).toBeVisible();

    const tabs = ["users", "deployments", "health", "provisioning", "dns", "payments", "audit", "actions", "sessions", "provider", "reconciliation"];
    for (const tab of tabs) {
      await page.locator(`button:has-text("${tab}"):visible`).first().click();
      await expect(page.locator("main h1").first()).toBeVisible();
    }
  });

  test("admin actions show executable choices and disabled unsupported states", async ({ page }) => {
    await mockApi(page);
    await page.goto("/admin");
    await page.locator('button:has-text("actions"):visible').first().click();
    await expect(page.getByText("Queue Modeled Action")).toBeVisible();
    await expect(page.getByText("Disabled or proof-gated actions", { exact: true })).toBeVisible();
    await expect(page.getByText("Action readiness matrix")).toBeVisible();
    await expect(page.getByText("PG-PROVISION").first()).toBeVisible();
    await expect(page.getByText("Force resynth")).toBeVisible();
    await expect(page.getByLabel("Action type")).toHaveValue("restart");
  });
});

// ---------------------------------------------------------------------------
// Onboarding flow with mocked API
// ---------------------------------------------------------------------------

test.describe("Onboarding flow", () => {
  test("complete onboarding flow with fake API", async ({ page }) => {
    await mockApi(page);
    await page.goto("/onboarding");

    // Step 1: Pick the Founders onboarding lane without collecting email in ArcLink chat/form
    await page.click("text=Founders - $149/month");
    await expect(page.getByRole("heading", { name: "Name The Agent" })).toBeVisible();

    // Step 2: Answer; the site should prepare Stripe immediately after this.
    await page.fill('input[id="name"]', "New User");
    await page.fill('input[id="agent-name"]', "Atlas");
    await page.fill('input[id="agent-title"]', "the right hand");
    await page.fill('input[id="email"]', "new.user@example.test");
    await page.click('button[type="submit"]');
    await expect(page.getByRole("heading", { name: "Stripe Handoff Ready" })).toBeVisible();
    await expect(page.locator("text=Finish Stripe Checkout").last()).toBeVisible();
    await expect(page.locator("text=Stage 1 is ready").last()).toBeVisible();

    const storageState = await page.evaluate(() => ({
      resume: JSON.parse(window.localStorage.getItem("arclink_onboarding_resume") || "{}") as Record<string, string>,
      proof: JSON.parse(window.sessionStorage.getItem("arclink_onboarding_proof") || "{}") as Record<string, string>,
    }));
    expect(storageState.resume.claimToken).toBeUndefined();
    expect(storageState.resume.cancelToken).toBeUndefined();
    expect(storageState.proof.claimToken).toBe("claim_mock_1");
    expect(storageState.proof.cancelToken).toBe("cancel_mock_1");
  });

  test("preferred Telegram and Discord query params stay web-scoped until platform link", async ({ page }) => {
    const starts: Array<Record<string, unknown>> = [];
    await mockApi(page, { onboardingStarts: starts });

    for (const channel of ["telegram", "discord"] as const) {
      const label = channel === "telegram" ? "Telegram" : "Discord";
      await page.goto(`/onboarding?channel=${channel}`);
      await expect(page.getByText(`Preferred channel: ${label}.`)).toBeVisible();
      await expect(page.getByText(`This browser session is not linked to ${label} yet`)).toBeVisible();
      await expect(page.getByText("Raven will continue there after checkout")).toHaveCount(0);

      await page.click("text=Founders - $149/month");
      await expect(page.getByRole("heading", { name: "Name The Agent" })).toBeVisible();

      const start = starts.at(-1);
      expect(start?.channel).toBe("web");
      expect(String(start?.channel_identity)).toMatch(/^web:/);
      await page.evaluate(() => {
        window.localStorage.clear();
        window.sessionStorage.clear();
      });
    }
  });

  test("checkout success claims from session proof and clears browser proof", async ({ page }) => {
    await mockApi(page);
    await page.goto("/onboarding");
    await page.evaluate(() => {
      window.localStorage.setItem("arclink_onboarding_resume", JSON.stringify({
        step: "done",
        sessionId: "sess_mock_1",
        name: "New User",
        agentName: "Atlas",
        agentTitle: "the right hand",
        email: "new.user@example.test",
        planId: "founders",
        checkoutUrl: "https://checkout.stripe.com/test",
      }));
      window.sessionStorage.setItem("arclink_onboarding_proof", JSON.stringify({
        sessionId: "sess_mock_1",
        claimToken: "claim_mock_1",
        cancelToken: "cancel_mock_1",
      }));
    });

    await page.goto("/checkout/success?session=sess_mock_1");
    await expect(page.getByText("You are signed in as new.user@example.test")).toBeVisible();
    const storageState = await page.evaluate(() => ({
      resume: window.localStorage.getItem("arclink_onboarding_resume"),
      proof: window.sessionStorage.getItem("arclink_onboarding_proof"),
    }));
    expect(storageState.resume).toBeNull();
    expect(storageState.proof).toBeNull();
  });

  test("checkout cancel uses session proof and clears token material", async ({ page }) => {
    await mockApi(page);
    await page.goto("/onboarding");
    await page.evaluate(() => {
      window.localStorage.setItem("arclink_onboarding_resume", JSON.stringify({
        step: "done",
        sessionId: "sess_mock_1",
        name: "New User",
        agentName: "Atlas",
        agentTitle: "the right hand",
        email: "new.user@example.test",
        planId: "founders",
        checkoutUrl: "https://checkout.stripe.com/test",
      }));
      window.sessionStorage.setItem("arclink_onboarding_proof", JSON.stringify({
        sessionId: "sess_mock_1",
        claimToken: "claim_mock_1",
        cancelToken: "cancel_mock_1",
      }));
    });

    await page.goto("/checkout/cancel?session=sess_mock_1");
    await expect(page.getByText("payment-cancelled")).toBeVisible();
    const storageState = await page.evaluate(() => ({
      resume: JSON.parse(window.localStorage.getItem("arclink_onboarding_resume") || "{}") as Record<string, string>,
      proof: window.sessionStorage.getItem("arclink_onboarding_proof"),
    }));
    expect(storageState.proof).toBeNull();
    expect(storageState.resume.claimToken).toBeUndefined();
    expect(storageState.resume.cancelToken).toBeUndefined();
    expect(storageState.resume.step).toBe("start");
    expect(storageState.resume.sessionId).toBe("");
    expect(storageState.resume.checkoutUrl).toBe("");
  });
});
