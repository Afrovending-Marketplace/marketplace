import { Link } from "react-router-dom";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { PageHero } from "@/components/common/PageHero";

const GROUPS = [
  { id: "shopping", title: "Shopping", items: [
    ["What is AfroVending?", "A multi-vendor marketplace connecting African, Caribbean, diaspora and global entrepreneurs with customers."],
    ["Can I buy products today?", "Not yet. AfroVending is in development and the products shown are sample data. Checkout opens in a later phase."],
    ["Which countries do you ship to?", "[Supported markets and shipping countries — to be confirmed.] Each vendor ships its own orders."],
    ["What is the returns policy?", "[Returns policy — to be confirmed before launch.]"],
  ] },
  { id: "vendors", title: "Vendors", items: [
    ["How do I become a vendor?", "Vendor applications open in an upcoming phase. Every vendor goes through onboarding and verification before listing."],
    ["What does it cost to sell?", "[Commission and fees — to be published before vendor onboarding opens.]"],
    ["How do vendors get paid?", "Payouts to vendors are planned through a secure payment provider. Details will be published with vendor onboarding."],
  ] },
  { id: "account", title: "Account & security", items: [
    ["Do I need an account?", "Accounts arrive in Phase 02. Browsing will always be open to guests."],
    ["How is my data protected?", "See our Privacy Policy (draft). Security hardening and audits are part of the build plan."],
  ] },
];

export default function FaqPage() {
  return (
    <div data-testid="faq-page">
      <PageHero eyebrow="Help" title="Frequently asked questions" crumbs={[{ label: "Home", to: "/" }, { label: "FAQ" }]}
        description="Answers marked [to be confirmed] are awaiting final business decisions." />
      <div className="av-container max-w-3xl space-y-12 py-14 lg:py-20">
        {GROUPS.map((g) => (
          <section key={g.id} id={g.id} aria-labelledby={`faq-${g.id}`} className="scroll-mt-40">
            <h2 id={`faq-${g.id}`} className="mb-4 text-2xl font-semibold text-av-ink">{g.title}</h2>
            <Accordion type="single" collapsible className="rounded-2xl border border-av-line bg-white px-5">
              {g.items.map(([q, a], i) => (
                <AccordionItem key={q} value={`${g.id}-${i}`} className="border-av-line last:border-b-0">
                  <AccordionTrigger data-testid={`faq-q-${g.id}-${i}`} className="text-left font-semibold hover:no-underline">{q}</AccordionTrigger>
                  <AccordionContent className="text-av-ink/75">{a}</AccordionContent>
                </AccordionItem>
              ))}
            </Accordion>
          </section>
        ))}
        <p className="text-sm text-av-muted">Still need help? <Link to="/contact" data-testid="faq-contact-link" className="font-semibold text-av-clay hover:underline">Contact us</Link>.</p>
      </div>
    </div>
  );
}
