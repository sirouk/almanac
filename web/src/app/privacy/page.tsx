import { LegalList, LegalSection, LegalShell } from "@/components/marketing/legal-page";

export default function PrivacyPage() {
  return (
    <LegalShell title="Privacy Policy">
      <LegalSection title="1. Who we are">
        <p>
          ArcLink operates the Raven AI agent platform. When you sign up, connect integrations, or interact with Raven,
          ArcLink processes information on your behalf. References to &quot;we&quot;, &quot;us&quot;, or &quot;ArcLink&quot; refer to the ArcLink
          platform and its operators.
        </p>
      </LegalSection>

      <LegalSection title="2. What we collect">
        <p className="mb-4">We collect information in the following categories:</p>
        <LegalList
          items={[
            <><span className="text-[#E7E6E6]/80">Account data</span> - name, email address, and billing information provided during sign-up.</>,
            <><span className="text-[#E7E6E6]/80">Usage data</span> - agent activity logs, task history, integration events, and command inputs sent through Telegram, Discord, or the web dashboard.</>,
            <><span className="text-[#E7E6E6]/80">Integration credentials</span> - OAuth tokens and API keys you provide so agents can access third-party tools. These are encrypted at rest.</>,
            <><span className="text-[#E7E6E6]/80">Technical data</span> - IP address, browser type, device identifiers, and access timestamps collected automatically.</>,
          ]}
        />
      </LegalSection>

      <LegalSection title="3. How we use your information">
        <p className="mb-4">We use the information we collect to:</p>
        <LegalList
          items={[
            "Provision and operate your agents and integrations",
            "Deliver Raven onboarding, dashboard access, and account support",
            "Process billing and communicate about your subscription",
            "Diagnose errors, improve reliability, and develop new features",
            "Comply with legal obligations",
          ]}
        />
        <p className="mt-4">We do not sell your data. We do not use your task content to train shared AI models.</p>
      </LegalSection>

      <LegalSection title="4. Data sharing">
        <p className="mb-4">We share data only as needed to deliver the service:</p>
        <LegalList
          items={[
            <><span className="text-[#E7E6E6]/80">Infrastructure providers</span> - hosting, databases, observability, and related services that process data on our behalf.</>,
            <><span className="text-[#E7E6E6]/80">Payment processors</span> - billing providers handle payment card data under their own PCI-compliant environments.</>,
            <><span className="text-[#E7E6E6]/80">Legal requirements</span> - we may disclose data if required by law or to protect ArcLink, users, and the service.</>,
          ]}
        />
      </LegalSection>

      <LegalSection title="5. Data retention">
        <p>
          We retain account data for the duration of your subscription and for a limited period after cancellation. Agent
          task logs are retained according to the plan and operating profile in effect for your deployment. You may request
          deletion by contacting support.
        </p>
      </LegalSection>

      <LegalSection title="6. Your rights">
        <p className="mb-4">You may request access, correction, deletion, or credential revocation for data associated with your account.</p>
        <p>
          To exercise these rights, contact <span className="text-[#FB5005]">support@arclink.online</span>.
        </p>
      </LegalSection>

      <LegalSection title="7. Security">
        <p>
          We use encryption in transit and at rest for stored credentials. Production access is restricted, logged, and
          reviewed. No system is perfectly secure; if you believe your account has been compromised, contact us immediately.
        </p>
      </LegalSection>

      <LegalSection title="8. Changes and contact">
        <p>
          We may update this policy from time to time. Questions can be directed to{" "}
          <span className="text-[#FB5005]">support@arclink.online</span>.
        </p>
      </LegalSection>
    </LegalShell>
  );
}
