import { Link } from "react-router-dom";
import { BadgeCheck, Store, Package, LineChart, Wallet, Globe2 } from "lucide-react";
import { PageHero } from "@/components/common/PageHero";
import { Button } from "@/components/ui/button";

const FEATURES = [
  [Store, "Your own storefront", "A branded store page with your story, products and policies."],
  [Package, "Product & inventory tools", "Variants, stock levels and media in one place."],
  [Globe2, "Reach diaspora customers", "A marketplace built around the communities you serve."],
  [Wallet, "Transparent payouts", "Clear commission accounting and payout history."],
  [LineChart, "Sales analytics", "See what sells and where customers come from."],
  [BadgeCheck, "Verified badge", "Verification builds buyer trust from the first visit."],
];

const STEPS = ["Apply with your business details", "Complete verification", "Set up your storefront", "List products and start selling"];

export default function SellPage() {
  return (
    <div data-testid="sell-page">
      <PageHero eyebrow="Sell on AfroVending" title="Bring your craft to a global audience." crumbs={[{ label: "Home", to: "/" }, { label: "Sell" }]}
        description="For continental, Caribbean and diaspora entrepreneurs. Vendor applications open soon.">
        <div className="flex flex-wrap gap-3 pt-2">
          <Button size="lg" disabled data-testid="sell-apply-button" aria-describedby="sell-apply-note">Apply to sell</Button>
          <Button asChild size="lg" variant="outline" data-testid="sell-contact-button"><Link to="/contact">Ask a question</Link></Button>
        </div>
        <p id="sell-apply-note" className="text-xs text-av-muted">Applications open in Phase 03 (vendor onboarding & verification).</p>
      </PageHero>
      <section className="av-container py-16 lg:py-24">
        <h2 className="text-3xl sm:text-4xl font-semibold text-av-ink">What you'll get</h2>
        <p className="mt-2 text-sm text-av-muted">Planned vendor capabilities, delivered across the build phases.</p>
        <div className="mt-10 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map(([Icon, t, d]) => (
            <div key={t} className="rounded-2xl border border-av-line bg-white p-6 transition-shadow hover:shadow-lg">
              <Icon className="h-6 w-6 text-av-clay" />
              <h3 className="mt-4 font-sans text-lg font-semibold text-av-ink">{t}</h3>
              <p className="mt-1 text-sm text-av-muted">{d}</p>
            </div>
          ))}
        </div>
      </section>
      <section className="bg-av-indigo text-av-linen">
        <div className="av-container grid gap-10 py-16 lg:grid-cols-12 lg:py-24">
          <h2 className="lg:col-span-4 text-3xl sm:text-4xl font-semibold">How it works</h2>
          <ol className="lg:col-span-8 grid gap-6 sm:grid-cols-2">
            {STEPS.map((s, i) => (
              <li key={s} className="flex gap-4 rounded-2xl border border-av-indigo-line p-5">
                <span className="font-serif text-3xl text-av-gold">{String(i + 1).padStart(2, "0")}</span>
                <span className="pt-2">{s}</span>
              </li>
            ))}
          </ol>
        </div>
      </section>
      <section className="av-container grid gap-6 py-16 md:grid-cols-2 lg:py-20">
        <div className="rounded-2xl border border-dashed border-av-line p-6">
          <h3 className="font-sans text-lg font-semibold text-av-ink">Requirements</h3>
          <p data-testid="sell-requirements-placeholder" className="mt-2 text-sm text-av-muted">[Eligibility, documents and supported seller countries — to be confirmed.]</p>
        </div>
        <div className="rounded-2xl border border-dashed border-av-line p-6">
          <h3 className="font-sans text-lg font-semibold text-av-ink">Fees</h3>
          <p data-testid="sell-fees-placeholder" className="mt-2 text-sm text-av-muted">[Commission and fees — to be published before onboarding opens.]</p>
        </div>
        <p className="md:col-span-2 text-sm text-av-muted">More answers in the <Link to="/faq#vendors" data-testid="sell-faq-link" className="font-semibold text-av-clay hover:underline">vendor FAQ</Link>.</p>
      </section>
    </div>
  );
}
