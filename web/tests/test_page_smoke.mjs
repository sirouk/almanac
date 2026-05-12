/**
 * Page smoke tests for the ArcLink web app.
 *
 * Validates that page modules export default components and that the API
 * client covers all required routes matching the hosted API boundary.
 * Runs with `node --test web/tests/test_page_smoke.mjs` from repo root.
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, existsSync } from "node:fs";
import { resolve } from "node:path";

const ROOT = resolve(import.meta.dirname, "..");

describe("Page files exist and export default", () => {
  const pages = [
    { path: "src/app/page.tsx", name: "Landing" },
    { path: "src/app/login/page.tsx", name: "Login" },
    { path: "src/app/onboarding/page.tsx", name: "Onboarding" },
    { path: "src/app/checkout/success/page.tsx", name: "Checkout Success" },
    { path: "src/app/checkout/cancel/page.tsx", name: "Checkout Cancel" },
    { path: "src/app/dashboard/page.tsx", name: "Dashboard" },
    { path: "src/app/admin/page.tsx", name: "Admin" },
  ];

  for (const page of pages) {
    it(`${page.name} page exists at ${page.path}`, () => {
      const full = resolve(ROOT, page.path);
      assert.ok(existsSync(full), `missing page: ${full}`);
    });

    it(`${page.name} page has default export`, () => {
      const content = readFileSync(resolve(ROOT, page.path), "utf-8");
      assert.ok(
        content.includes("export default function"),
        `${page.path} missing default export`,
      );
    });
  }
});

describe("Page content smoke checks", () => {
  it("Landing page has ArcLink brand and onboarding CTA", () => {
    const content = readFileSync(resolve(ROOT, "src/app/page.tsx"), "utf-8");
    assert.ok(content.includes("ARCLINK") || content.includes("ArcLink"), "missing brand");
    assert.ok(content.includes("/onboarding"), "missing onboarding link");
    assert.ok(content.includes("signal-orange"), "missing brand color");
  });

  it("Login page has user and admin mode", () => {
    const content = readFileSync(resolve(ROOT, "src/app/login/page.tsx"), "utf-8");
    assert.ok(content.includes("user"), "missing user mode");
    assert.ok(content.includes("admin"), "missing admin mode");
    assert.ok(content.includes("type=\"password\""), "missing admin password input");
    assert.ok(content.includes("api.login"), "missing login API call");
  });

  it("Onboarding page has step flow", () => {
    const content = readFileSync(resolve(ROOT, "src/app/onboarding/page.tsx"), "utf-8");
    assert.ok(content.includes("startOnboarding"), "missing start API call");
    assert.ok(content.includes("answerOnboarding"), "missing answer API call");
    assert.ok(content.includes("openCheckout"), "missing checkout API call");
    assert.ok(content.includes("Fake adapters"), "missing fake adapter notice");
    assert.ok(content.includes("/checkout/success"), "missing checkout success redirect");
    assert.ok(content.includes("/checkout/cancel"), "missing checkout cancel redirect");
  });

  it("Checkout result pages exist for Stripe redirects", () => {
    const success = readFileSync(resolve(ROOT, "src/app/checkout/success/page.tsx"), "utf-8");
    const cancel = readFileSync(resolve(ROOT, "src/app/checkout/cancel/page.tsx"), "utf-8");
    assert.ok(success.includes("Agent onboard ArcLink"), "missing success copy");
    assert.ok(cancel.includes("Checkout paused"), "missing cancel copy");
    assert.ok(cancel.includes("api.cancelOnboarding"), "Stripe cancel should call the backend cancel path when proof is available");
  });

  it("Dashboard page has all required tabs", () => {
    const content = readFileSync(resolve(ROOT, "src/app/dashboard/page.tsx"), "utf-8");
    const requiredTabs = ["overview", "billing", "provisioning", "services", "model", "memory", "security", "support"];
    for (const tab of requiredTabs) {
      assert.ok(content.includes(`"${tab}"`), `missing tab: ${tab}`);
    }
    assert.ok(content.includes("api.userDashboard"), "missing dashboard API call");
    assert.ok(content.includes("api.userBilling"), "missing billing API call");
    assert.ok(content.includes("Drive"), "dashboard should link to Drive");
    assert.ok(content.includes("Code"), "dashboard should link to Code");
    assert.ok(content.includes("Recovery Actions"), "dashboard should expose recovery actions");
    assert.ok(content.includes("Workspace Readiness"), "dashboard should group readiness signals");
    assert.ok(!content.includes("Files (Nextcloud)"), "dashboard should not advertise legacy Nextcloud access");
    assert.ok(!content.includes("Code (code-server)"), "dashboard should not advertise legacy code-server access");
  });

  it("Admin page has all required tabs", () => {
    const content = readFileSync(resolve(ROOT, "src/app/admin/page.tsx"), "utf-8");
    const requiredTabs = [
      "overview", "users", "deployments", "onboarding", "health", "provisioning",
      "dns", "payments", "infrastructure", "bots", "security", "releases",
      "audit", "events", "actions", "sessions",
    ];
    for (const tab of requiredTabs) {
      assert.ok(content.includes(`"${tab}"`), `missing tab: ${tab}`);
    }
    assert.ok(content.includes("api.adminDashboard"), "missing admin dashboard API call");
    assert.ok(content.includes("api.queueAdminAction"), "missing admin action API call");
    assert.ok(content.includes("Operations Triage"), "admin page should expose operations triage");
    assert.ok(content.includes("Disabled and proof-gated actions"), "admin page should label disabled operations");
    assert.ok(content.includes("Disabled or proof-gated actions"), "admin action form should not imply every disabled action only lacks worker wiring");
  });

  it("No page claims live provisioning with fake adapters", () => {
    const pages = [
      "src/app/page.tsx",
      "src/app/onboarding/page.tsx",
      "src/app/dashboard/page.tsx",
      "src/app/admin/page.tsx",
    ];
    for (const page of pages) {
      const content = readFileSync(resolve(ROOT, page), "utf-8");
      // Pages should not claim "your deployment is live" without qualification
      assert.ok(
        !content.includes("deployment is live and running"),
        `${page} falsely claims live provisioning`,
      );
    }
  });
});

describe("API client route parity with hosted API", () => {
  it("api.ts covers all hosted API routes", () => {
    const apiContent = readFileSync(resolve(ROOT, "src/lib/api.ts"), "utf-8");
    const requiredPaths = [
      "/onboarding/start",
      "/onboarding/answer",
      "/onboarding/checkout",
      "/onboarding/status?session_id=",
      "/onboarding/claim-session",
      "/onboarding/cancel",
      "/user/dashboard",
      "/user/billing",
      "/user/provisioning",
      "/user/credentials",
      "/user/credentials/acknowledge",
      "/user/linked-resources",
      "/user/share-grants",
      "/user/share-grants/approve",
      "/user/share-grants/deny",
      "/user/share-grants/accept",
      "/user/share-grants/revoke",
      "/user/portal",
      "/user/provider-state",
      "/admin/dashboard",
      "/admin/service-health",
      "/admin/provisioning-jobs",
      "/admin/dns-drift",
      "/admin/audit",
      "/admin/events",
      "/admin/actions",
      "/admin/provider-state",
      "/admin/reconciliation",
      "/admin/operator-snapshot",
      "/admin/scale-operations",
      "/admin/sessions/revoke",
      "/auth/${kind}/login",
      "/auth/${kind}/logout",
      "/health",
      "/adapter-mode",
    ];
    for (const path of requiredPaths) {
      assert.ok(apiContent.includes(path), `missing API route: ${path}`);
    }
  });
});

describe("Component infrastructure", () => {
  it("UI components exist", () => {
    const uiDir = resolve(ROOT, "src/components");
    assert.ok(existsSync(uiDir), "missing components directory");
  });

  it("API client module exists", () => {
    assert.ok(existsSync(resolve(ROOT, "src/lib/api.ts")), "missing api.ts");
  });
});

console.log("PASS all ArcLink web page smoke tests");
