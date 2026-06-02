import { LegalList, LegalSection, LegalShell } from "@/components/marketing/legal-page";

export default function OperatingPolicyPage() {
  return (
    <LegalShell title="ArcLink Operating Policy" eyebrow="Policy" lastUpdated="June 2026">
      <LegalSection title="Security and secrets">
        <p>
          ArcLink never intentionally exposes raw secrets in dashboard responses, public chat replies, logs, or Academy
          artifacts. Browser mutations use sessions and CSRF checks, credential handoffs are masked, and high-risk
          operator actions require explicit confirmation.
        </p>
      </LegalSection>

      <LegalSection title="Privacy and public lanes">
        <p>
          Raven routes onboarding, support, and control messages. Captain-owned Agent state stays scoped to that Captain,
          their ArcPods, approved brokered APIs, and accepted shares. Public Academy lanes store only redacted,
          derived notes; private strategy and personal data do not become shared material.
        </p>
      </LegalSection>

      <LegalSection title="Academy crawling">
        <p>
          Academy continuing education can crawl approved public source URLs on a weekly cadence. Crawls respect source
          permissions, HTTPS transport, robots policy, rate limits, and third-party terms. ArcLink records metadata and
          content hashes, not raw pages, and changed or unsafe sources must pass review before Agent updates.
        </p>
      </LegalSection>

      <LegalSection title="Operator controls">
        <LegalList
          items={[
            "Read-only previews and diagnostics should be available before risky work is queued.",
            "Upgrades, rollouts, repairs, and admin actions require verified operator identity plus confirm=true or an approval code.",
            "Actions are audited and should fail closed when proof, scope, or worker readiness is missing.",
          ]}
        />
      </LegalSection>

      <LegalSection title="Dashboard access">
        <p>
          User and admin sessions are separate. Admin access is role, CSRF, and network-scope protected. Hermes Agent
          dashboards use signed expiring session or SSO cookies; Drive, Code, Terminal, and dashboard access should not
          rely on browser-facing Basic Auth.
        </p>
      </LegalSection>

      <LegalSection title="Shared folders">
        <p>
          Accepted Drive and Code shared folders are projected into Linked roots with read/write access by default.
          Shared folders cannot be reshared, and destructive or ownership-changing operations must remain
          confirmation-aware.
        </p>
      </LegalSection>
    </LegalShell>
  );
}
