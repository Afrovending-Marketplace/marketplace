import { Link } from "react-router-dom";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { PageHero } from "@/components/common/PageHero";

const GROUPS = [
  { id: "shopping", title: "Shopping", items: [
    ["What is AfroVending?", "AfroVending is a multi-vendor online marketplace connecting independent businesses with customers through one digital shopping platform."],
    ["Can I purchase products from multiple vendors?", "The marketplace is being designed to support purchases from multiple vendors through one shopping experience."],
    ["How do payments work?", "Secure payment processing will be available through supported payment providers once checkout and payment integration are launched."],
    ["How are orders shipped?", "Shipping options and delivery estimates will depend on the individual vendor, product, and destination."],
  ] },
  { id: "vendors", title: "Vendors", items: [
    ["Who can sell on AfroVending?", "AfroVending is designed for eligible entrepreneurs, independent brands, and businesses offering products that comply with marketplace policies."],
    ["How do I become a vendor?", "Select Become a Vendor, create an account, and submit your business information for review."],
  ] },
  { id: "contact", title: "Contact", items: [
    ["How can I contact AfroVending?", <>Use the <Link to="/contact" className="font-semibold text-av-clay hover:underline">Contact Us form</Link> or email <a href="mailto:info@afrovending.com" data-testid="faq-support-email" className="font-semibold text-av-clay hover:underline">info@afrovending.com</a>.</>],
  ] },
];

export default function FaqPage() {
  return (
    <div data-testid="faq-page">
      <PageHero eyebrow="Help" title="Frequently asked questions" crumbs={[{ label: "Home", to: "/" }, { label: "FAQ" }]}
        description="Common questions about shopping and selling on AfroVending." />
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
