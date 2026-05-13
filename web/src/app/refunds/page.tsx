import { LegalList, LegalSection, LegalShell } from "@/components/marketing/legal-page";

export default function RefundsPage() {
  return (
    <LegalShell title="Refund Policy">
      <LegalSection title="Our approach">
        <p>
          We stand behind the quality of every agent we provision. If something is not working as expected, our first step
          is to make it right. This policy explains when refunds, credits, or cancellations apply.
        </p>
      </LegalSection>

      <div className="my-8 grid gap-px overflow-hidden rounded-lg bg-white/5 sm:grid-cols-3">
        {[
          { label: "Founders", value: "14-day guarantee", note: "full monthly refund" },
          { label: "Monthly plans", value: "14-day guarantee", note: "first billing period" },
          { label: "Annual plans", value: "Prorated up to 30 days", note: "minus months used" },
        ].map((item) => (
          <div key={item.label} className="bg-[#0F0F0E] p-6">
            <p className="mb-2 font-mono text-[10px] uppercase tracking-widest text-[#FB5005]/60">{item.label}</p>
            <p className="font-heading mb-1 text-sm font-semibold text-[#E7E6E6]/90">{item.value}</p>
            <p className="text-xs text-[#E7E6E6]/30">{item.note}</p>
          </div>
        ))}
      </div>

      <LegalSection title="Monthly subscriptions">
        <p>
          Monthly plans include a 14-day money-back guarantee during the first billing period. If you are not satisfied,
          contact us and we will issue a refund for that first monthly charge.
        </p>
      </LegalSection>

      <LegalSection title="Annual subscriptions">
        <p>
          Annual plans are eligible for a prorated refund within the first 30 days. After 30 days, annual plans are
          non-refundable except where required by law or agreed in writing.
        </p>
      </LegalSection>

      <LegalSection title="Additional agents">
        <p>
          Additional agents follow the same refund window as the plan they are attached to. If an additional agent is added
          mid-cycle, the guarantee window starts from the date that additional agent is activated.
        </p>
      </LegalSection>

      <LegalSection title="Service failures">
        <p>
          If ArcLink experiences a service failure that causes significant agent downtime, affected customers may receive a
          prorated credit applied to a future billing cycle. Credits are not transferable and have no cash value.
        </p>
      </LegalSection>

      <LegalSection title="Exceptions">
        <p className="mb-4">Refunds may not be issued for:</p>
        <LegalList
          items={[
            "Account suspension due to violations of the Terms of Service",
            "Disruptions caused by third-party platform changes, API limits, or access revocations",
            "Incorrect or incomplete third-party configuration outside ArcLink control",
            "Requests made outside the applicable refund windows",
          ]}
        />
      </LegalSection>

      <LegalSection title="How to request a refund">
        <p className="mb-4">
          Email <span className="text-[#FB5005]">support@arclink.online</span> with:
        </p>
        <LegalList items={["Your account email", "The charge date and amount", "A brief description of the issue"]} />
        <p className="mt-4">We aim to respond within 1 business day.</p>
      </LegalSection>
    </LegalShell>
  );
}
