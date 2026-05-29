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
    const content = [
      readFileSync(resolve(ROOT, "src/app/page.tsx"), "utf-8"),
      readFileSync(resolve(ROOT, "src/components/marketing/marketing-home.tsx"), "utf-8"),
      readFileSync(resolve(ROOT, "src/components/marketing/nav.tsx"), "utf-8"),
    ].join("\n");
    assert.ok(content.includes("ARCLINK") || content.includes("ArcLink"), "missing brand");
    assert.ok(content.includes("/onboarding"), "missing onboarding link");
    assert.ok(content.includes("#FB5005"), "missing brand color");
  });

  it("Login page uses unified role-resolving sign in", () => {
    const content = readFileSync(resolve(ROOT, "src/app/login/page.tsx"), "utf-8");
    assert.ok(content.includes("Raven opens the right console"), "missing unified login copy");
    assert.ok(content.includes("session_kind"), "missing session kind redirect handling");
    assert.ok(content.includes("type=\"password\""), "missing password input");
    assert.ok(content.includes("api.login"), "missing login API call");
    assert.ok(!content.includes("LoginKind"), "login page should not expose a role mode type");
    assert.ok(!content.includes("setKind"), "login page should not let users choose a role mode");
    assert.ok(!content.includes("Sign In as"), "login submit should not include a selected role");
    assert.ok(!content.includes("Dashboard password"), "login placeholder should not imply a user-only mode");
    assert.ok(!content.includes("Admin password"), "login placeholder should not imply an admin-only mode");
  });

  it("Onboarding page has step flow", () => {
    const content = readFileSync(resolve(ROOT, "src/app/onboarding/page.tsx"), "utf-8");
    assert.ok(content.includes("startOnboarding"), "missing start API call");
    assert.ok(content.includes("answerOnboarding"), "missing answer API call");
    assert.ok(content.includes("openCheckout"), "missing checkout API call");
    assert.ok(content.includes("Agent Name"), "missing Agent Name input");
    assert.ok(content.includes("Agent Title"), "missing Agent Title input");
    assert.ok(content.includes("agent_name"), "missing agent_name payload");
    assert.ok(content.includes("agent_title"), "missing agent_title payload");
    assert.ok(content.includes("Fake adapters"), "missing fake adapter notice");
    assert.ok(content.includes("/checkout/success"), "missing checkout success redirect");
    assert.ok(content.includes("/checkout/cancel"), "missing checkout cancel redirect");
  });

  it("Onboarding preferred-channel copy stays honest about web identity", () => {
    const content = readFileSync(resolve(ROOT, "src/app/onboarding/page.tsx"), "utf-8");
    assert.ok(
      content.includes('api.startOnboarding({ channel: "web"'),
      "web onboarding must remain web-scoped until a real platform identity is linked",
    );
    assert.ok(
      content.includes("This browser session is not linked to"),
      "preferred-channel query copy must disclose that Telegram/Discord is not linked yet",
    );
    assert.ok(
      !content.includes("Raven will continue there after checkout"),
      "preferred-channel query copy must not promise platform continuation without identity",
    );
    assert.ok(
      !content.includes("continues the setup in your preferred channel"),
      "hero copy must not promise preferred-channel continuation from a web-only session",
    );
  });

  it("Checkout result pages exist for Stripe redirects", () => {
    const success = readFileSync(resolve(ROOT, "src/app/checkout/success/page.tsx"), "utf-8");
    const cancel = readFileSync(resolve(ROOT, "src/app/checkout/cancel/page.tsx"), "utf-8");
    assert.ok(success.includes("Launch queue engaged") || success.includes("ArcPod online"), "missing success copy");
    assert.ok(cancel.includes("Checkout paused"), "missing cancel copy");
    assert.ok(cancel.includes("api.cancelOnboarding"), "Stripe cancel should call the backend cancel path when proof is available");
  });

  it("Onboarding proof tokens use session-only storage", () => {
    const onboarding = readFileSync(resolve(ROOT, "src/app/onboarding/page.tsx"), "utf-8");
    const success = readFileSync(resolve(ROOT, "src/app/checkout/success/page.tsx"), "utf-8");
    const cancel = readFileSync(resolve(ROOT, "src/app/checkout/cancel/page.tsx"), "utf-8");
    const resumeType = onboarding.match(/type ResumeState = \{[\s\S]*?\n\};/);
    const resumeSnapshot = onboarding.match(/const snapshot: ResumeState = \{[\s\S]*?\};/);

    assert.ok(onboarding.includes("PROOF_STORAGE_KEY"), "onboarding missing dedicated proof storage key");
    assert.ok(onboarding.includes("window.sessionStorage.setItem(PROOF_STORAGE_KEY"), "onboarding proof tokens must be session-only");
    assert.ok(success.includes("window.sessionStorage.getItem(PROOF_STORAGE_KEY"), "success page must read claim proof from session storage");
    assert.ok(success.includes("window.sessionStorage.removeItem(PROOF_STORAGE_KEY"), "success page must clear proof storage after claim");
    assert.ok(cancel.includes("window.sessionStorage.getItem(PROOF_STORAGE_KEY"), "cancel page must read cancel proof from session storage");
    assert.ok(cancel.includes("window.sessionStorage.removeItem(PROOF_STORAGE_KEY"), "cancel page must clear proof storage after cancel");
    assert.ok(resumeType, "missing onboarding ResumeState type");
    assert.ok(resumeSnapshot, "missing onboarding resume snapshot");
    assert.ok(!/claimToken|cancelToken/.test(resumeType[0]), "ResumeState must not contain browser proof tokens");
    assert.ok(!/claimToken|cancelToken/.test(resumeSnapshot[0]), "localStorage resume snapshot must not persist proof tokens");
  });

  it("Dashboard page has all required tabs", () => {
    const content = readFileSync(resolve(ROOT, "src/app/dashboard/page.tsx"), "utf-8");
    const requiredTabs = ["overview", "billing", "provisioning", "services", "model", "memory", "security", "support"];
    for (const tab of requiredTabs) {
      assert.ok(content.includes(`"${tab}"`), `missing tab: ${tab}`);
    }
    assert.ok(content.includes("api.userDashboard"), "missing dashboard API call");
    assert.ok(content.includes("api.updateAgentIdentity"), "missing Agent identity API call");
    assert.ok(content.includes("Crew Training"), "missing Crew Training UI");
    assert.ok(content.includes("Academy Review"), "missing Academy Review panel");
    assert.ok(content.includes("Weekly:"), "dashboard should show Academy weekly review status");
    assert.ok(content.includes("Graduation:"), "dashboard should show Academy graduation gate status");
    assert.ok(content.includes("Next review:"), "dashboard should show Academy next-review status");
    assert.ok(content.includes("Blocked sources:"), "dashboard should show Academy blocked-source count");
    assert.ok(content.includes("api.previewCrewRecipe"), "missing Crew Training preview API call");
    assert.ok(content.includes("api.applyCrewRecipe"), "missing Crew Training apply API call");
    assert.ok(content.includes('"academy"'), "missing Academy tab");
    assert.ok(content.includes("ArcLink Academy"), "missing ArcLink Academy panel");
    assert.ok(content.includes("Enter Academy Mode"), "missing Academy Mode entry control");
    assert.ok(content.includes("Graduate (close mode)"), "missing Captain-ends-mode control");
    assert.ok(content.includes("Academy Graduates"), "missing Academy graduates gallery");
    assert.ok(content.includes("api.enrollAcademyTrainee"), "missing Academy enroll API call");
    assert.ok(content.includes("api.endAcademyMode"), "missing Academy mode-end API call");
    assert.ok(content.includes("api.adoptAcademyGraduate"), "missing Academy adopt API call");
    assert.ok(content.includes("api.userBilling"), "missing billing API call");
    assert.ok(content.includes("Drive"), "dashboard should link to Drive");
    assert.ok(content.includes("Code"), "dashboard should link to Code");
    assert.ok(content.includes("Recovery Actions"), "dashboard should expose recovery actions");
    assert.ok(content.includes("Workspace Readiness"), "dashboard should group readiness signals");
    assert.ok(content.includes("backup_setup"), "dashboard should consume backup setup status");
    assert.ok(content.includes("BackupStatusPanel"), "dashboard should render backup setup status");
    assert.ok(content.includes("pending_key_setup"), "dashboard should show pending backup key setup");
    assert.ok(content.includes("api.requestBackupDeployKey"), "dashboard should stage backup deploy keys through the user API");
    assert.ok(content.includes("api.requestBackupWriteCheck"), "dashboard should record backup write-check state through the user API");
    assert.ok(content.includes("Staged Public Key"), "dashboard should show the staged public key");
    assert.ok(content.includes("Open GitHub deploy key settings"), "dashboard should link to GitHub deploy-key settings");
    assert.ok(content.includes("Record write check"), "dashboard should expose the fail-closed write-check action");
    assert.ok(content.includes("restore proof remains live-gated"), "dashboard should not claim live restore proof");
    assert.ok(content.includes("api.userShareGrants"), "dashboard should load the share approval inbox");
    assert.ok(content.includes("ShareApprovalsPanel"), "dashboard should render the share approval inbox");
    assert.ok(content.includes("Pending Share Approvals"), "dashboard should label pending share approvals");
    assert.ok(content.includes("Dashboard actions stay available"), "dashboard should surface no-channel share recovery");
    assert.ok(content.includes("api.retryShareGrantNotification"), "dashboard should retry share notifications through the user API");
    assert.ok(content.includes("Retry Raven prompt"), "dashboard should label retry as Raven prompt queueing");
    assert.ok(content.includes("live bot delivery remains proof-gated"), "dashboard should not claim retry proves live bot delivery");
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
    assert.ok(content.includes("Action readiness matrix"), "admin action form should render the source-owned readiness matrix");
    assert.ok(content.includes("Provisioning readiness"), "admin page should label ArcPod provisioning readiness separately");
    assert.ok(content.includes("Control-plane health, action-worker readiness, and ArcPod provisioning readiness are separate"), "admin page should separate provisioning readiness from general health and action readiness");
    assert.ok(content.includes("PG-FLEET/PG-PROVISION"), "admin page should keep live worker proof gates visible");
    assert.ok(content.includes("PG-UPGRADE/PG-HERMES"), "admin page should keep rollout live proof gates visible");
    assert.ok(content.includes("ArcPod rollout jobs use local preflight"), "admin page should describe rollout jobs as local preflight gated");
  });

  it("No page claims live provisioning with fake adapters", () => {
    const pages = [
      "src/app/page.tsx",
      "src/components/marketing/marketing-home.tsx",
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
      "/user/agent-identity",
      "/user/backup-deploy-key",
      "/user/backup-write-check",
      "/user/crew-recipe",
      "/user/crew-recipe/preview",
      "/user/crew-recipe/apply",
      "/user/linked-resources",
      "/user/share-grants",
      "/user/share-grants/approve",
      "/user/share-grants/deny",
      "/user/share-grants/accept",
      "/user/share-grants/revoke",
      "/user/share-grants/retry-notification",
      "/user/portal",
      "/user/provider-state",
      "/admin/dashboard",
      "/admin/service-health",
      "/admin/provisioning-jobs",
      "/admin/dns-drift",
      "/admin/audit",
      "/admin/events",
      "/admin/actions",
      "/admin/crew-recipe/apply",
      "/admin/provider-state",
      "/admin/reconciliation",
      "/admin/operator-snapshot",
      "/admin/scale-operations",
      "/admin/sessions/revoke",
      "/auth/login",
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
