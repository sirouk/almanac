import Footer from "@/components/marketing/footer";
import Nav from "@/components/marketing/nav";

export function LegalShell({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="bg-[#080808]">
      <Nav />
      <main className="pb-24 pt-32">
        <div className="mx-auto max-w-3xl px-6 lg:px-8">
          <span className="font-mono text-xs uppercase tracking-widest text-[#FB5005]">Legal</span>
          <h1 className="font-heading mt-4 mb-3 text-4xl font-normal leading-tight text-[#E7E6E6] lg:text-5xl">
            {title}
          </h1>
          <p className="font-body mb-16 text-sm text-[#E7E6E6]/30">Last updated: May 2026</p>
          <div className="font-body space-y-12 text-sm leading-relaxed text-[#E7E6E6]/60">{children}</div>
        </div>
      </main>
      <Footer />
    </div>
  );
}

export function LegalSection({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section>
      <h2 className="font-heading mb-4 text-lg font-semibold text-[#E7E6E6]/90">{title}</h2>
      {children}
    </section>
  );
}

export function LegalList({ items }: { items: React.ReactNode[] }) {
  return (
    <ul className="space-y-2 border-l border-white/5 pl-4">
      {items.map((item, index) => (
        <li key={index}>{item}</li>
      ))}
    </ul>
  );
}
