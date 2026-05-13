import { LegalList, LegalSection, LegalShell } from "@/components/marketing/legal-page";

export default function TermsPage() {
  return (
    <LegalShell title="Terms of Service">
      <LegalSection title="1. Agreement">
        <p>
          By creating an account or using ArcLink, you agree to these Terms of Service. If you do not agree, do not use
          the platform. These terms apply to trial, founder, monthly, annual, and paid plans.
        </p>
      </LegalSection>

      <LegalSection title="2. The service">
        <p className="mb-4">
          ArcLink provides AI-powered automation agents that connect to third-party tools and execute tasks on your behalf.
          The service includes:
        </p>
        <LegalList
          items={[
            "Agent provisioning and configuration",
            "Integration management for tools such as Notion, GitHub, webhooks, APIs, Telegram, and Discord",
            "Task scheduling, memory, retrieval, and reporting",
            "Dashboard access for deployment status, billing, credentials, and workspace links",
          ]}
        />
      </LegalSection>

      <LegalSection title="3. Accounts">
        <p>
          You are responsible for maintaining the security of your account credentials. You must be at least 18 years old
          to create an account. You are responsible for activity performed by your account and by agents acting under your
          instructions.
        </p>
      </LegalSection>

      <LegalSection title="4. Billing">
        <p>
          Subscriptions are billed monthly or annually in advance. Prices are listed in USD unless otherwise stated. Plan
          limits, included agents, and expansion pricing are shown during checkout. ArcLink may change pricing with notice
          to existing subscribers where required.
        </p>
      </LegalSection>

      <LegalSection title="5. Acceptable use">
        <p className="mb-4">You may not use ArcLink to:</p>
        <LegalList
          items={[
            "Send spam, unsolicited messages, or mass outreach without recipient consent",
            "Scrape, crawl, or extract data from third-party services in violation of their terms",
            "Engage in illegal, fraudulent, deceptive, or harmful activity",
            "Attempt to reverse-engineer, resell, or overload ArcLink infrastructure",
            "Bypass security, billing, or access controls",
          ]}
        />
        <p className="mt-4">Violations may result in suspension or termination.</p>
      </LegalSection>

      <LegalSection title="6. Third-party integrations">
        <p>
          When you connect Raven to third-party platforms, you remain subject to those platforms&apos; terms. ArcLink is not
          responsible for provider outages, API changes, rate limits, access revocations, or third-party actions that
          affect agent functionality.
        </p>
      </LegalSection>

      <LegalSection title="7. Availability">
        <p>
          We work to keep ArcLink reliable, but we do not guarantee uninterrupted service unless a separate written SLA
          applies. Scheduled maintenance, provider outages, and force majeure events may cause downtime.
        </p>
      </LegalSection>

      <LegalSection title="8. Limitation of liability">
        <p>
          ArcLink is provided &quot;as is&quot; to the maximum extent permitted by law. ArcLink is not liable for indirect,
          incidental, special, consequential, or punitive damages, including lost revenue, lost data, or business
          interruption.
        </p>
      </LegalSection>

      <LegalSection title="9. Termination">
        <p>
          You may cancel your subscription from your account dashboard or by contacting support. Access remains active until
          the end of the current billing period unless these terms are violated. Data deletion follows the retention policy
          described in the Privacy Policy.
        </p>
      </LegalSection>

      <LegalSection title="10. Contact">
        <p>
          Questions about these terms can be directed to <span className="text-[#FB5005]">support@arclink.online</span>.
        </p>
      </LegalSection>
    </LegalShell>
  );
}
