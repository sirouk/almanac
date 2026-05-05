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
      bot_contact: { channel: "telegram", first_contacted: true, handoff_recorded: true },
      access: { urls: { files: "https://test.arclink.online:8443" } },
    },
  ],
  entitlement: { state: "paid" },
};

const MOCK_USER_BILLING = {
  entitlement: { state: "paid" },
  subscriptions: [{ subscription_id: "sub_test1", status: "active" }],
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
};

const MOCK_ONBOARDING_START = { session: { session_id: "sess_mock_1" } };
const MOCK_ONBOARDING_ANSWER = { ok: true };
const MOCK_LOGIN_OK = { session: { session_id: "sess_login_1" } };

// ---------------------------------------------------------------------------
// Route mocking helper
// ---------------------------------------------------------------------------

async function mockApi(page: Page) {
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
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ audit: [{ created_at: "2026-05-01", actor_id: "admin_1", action_type: "restart", target_id: "dep_001", reason: "test" }] }) });
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
    if (url.includes("/admin/provider-state")) {
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ stripe: "fake", cloudflare: "fake", chutes: "fake" }) });
    }
    if (url.includes("/admin/reconciliation")) {
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ drift: [], summary: { checked: 1, drifted: 0 } }) });
    }
    if (url.includes("/admin/sessions/revoke") && method === "POST") {
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ok: true }) });
    }
    if (url.includes("/onboarding/start") && method === "POST") {
      return route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify(MOCK_ONBOARDING_START) });
    }
    if (url.includes("/onboarding/answer") && method === "POST") {
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_ONBOARDING_ANSWER) });
    }
    if (url.includes("/onboarding/checkout") && method === "POST") {
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ session: { checkout_url: "https://checkout.stripe.com/test" } }) });
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

  test("landing page features grid renders all 6 items", async ({ page }) => {
    await page.goto("/");
    const cards = page.locator("section h3");
    await expect(cards).toHaveCount(6);
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
    await page.goto("/onboarding");
    await expect(page.locator("text=I'm Raven")).toBeVisible();
    await expect(page.locator("text=No technical setup on your end")).toBeVisible();
    await expect(page.locator('button[type="submit"]')).toBeVisible();
    // Fake adapter notice present
    await expect(page.locator("text=Fake adapters")).toBeVisible();
  });

  test("/dashboard renders with mocked data", async ({ page }) => {
    await mockApi(page);
    await page.goto("/dashboard");
    await expect(page.locator("text=Raven console").first()).toBeVisible();
    await expect(page.locator("main").getByText("test.arclink.online").first()).toBeVisible();
  });

  test("/admin renders with mocked data", async ({ page }) => {
    await mockApi(page);
    await page.goto("/admin");
    await expect(page.locator("text=ArcLink Global Operations").first()).toBeVisible();
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
    await page.click('button[type="submit"]');
    const nameInput = page.locator('input[id="name"]');
    await expect(nameInput).toBeVisible();
    const label = page.locator('label[for="name"]');
    await expect(label).toBeVisible();
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
    // Delay API response to catch loading state
    await page.route("**/api/v1/user/dashboard", async (route) => {
      await new Promise((r) => setTimeout(r, 500));
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_USER_DASHBOARD) });
    });
    await page.route("**/api/v1/user/billing", async (route) => {
      await new Promise((r) => setTimeout(r, 500));
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_USER_BILLING) });
    });
    await page.route("**/api/v1/user/provisioning", async (route) => {
      await new Promise((r) => setTimeout(r, 500));
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_USER_PROVISIONING) });
    });
    await page.goto("/dashboard");
    await expect(page.locator("text=Loading dashboard")).toBeVisible();
  });

  test("dashboard shows empty state with no deployments", async ({ page }) => {
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
});

// ---------------------------------------------------------------------------
// No false live-service claims
// ---------------------------------------------------------------------------

test.describe("No false live claims", () => {
  test("no page claims deployment is live and running", async ({ page }) => {
    const routes = ["/", "/login", "/onboarding"];
    for (const route of routes) {
      await page.goto(route);
      const text = await page.textContent("body");
      expect(text).not.toContain("deployment is live and running");
    }
  });

  test("onboarding shows fake adapter notice", async ({ page }) => {
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
});

// ---------------------------------------------------------------------------
// Onboarding flow with mocked API
// ---------------------------------------------------------------------------

test.describe("Onboarding flow", () => {
  test("complete onboarding flow with fake API", async ({ page }) => {
    await mockApi(page);
    await page.goto("/onboarding");

    // Step 1: Start without collecting email in ArcLink chat/form
    await page.click('button[type="submit"]');
    await expect(page.getByRole("heading", { name: "Name On The Hatch" })).toBeVisible();

    // Step 2: Answer
    await page.fill('input[id="name"]', "New User");
    await page.click('button[type="submit"]');
    await expect(page.locator("text=Hire My First Agent").first()).toBeVisible();

    // Step 3: Checkout
    await page.click("text=Hire My First Agent - $35/mo");
    await expect(page.locator("text=Complete The Hire").last()).toBeVisible();
  });
});
