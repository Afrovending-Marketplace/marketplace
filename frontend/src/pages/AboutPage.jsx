import { Link } from "react-router-dom";
import { Heart, ShieldCheck, Users, Globe2 } from "lucide-react";
import { PageHero } from "@/components/common/PageHero";
import { Button } from "@/components/ui/button";

const VALUES = [
  [Heart, "Authenticity", "Products rooted in real cultures, made by the people who carry them."],
  [ShieldCheck, "Trust", "Vendor verification, secure payments and clear policies — on both sides."],
  [Users, "Community", "A home for continental, Caribbean and diaspora entrepreneurs."],
  [Globe2, "Global reach", "Connecting makers with customers wherever they are."],
];

export default function AboutPage() {
  return (
    <div data-testid="about-page">
      <PageHero eyebrow="About AfroVending" title="From Culture to Commerce." crumbs={[{ label: "Home", to: "/" }, { label: "About" }]}
        description="AfroVending Online Marketplace connects African, Caribbean, diaspora and global entrepreneurs with customers through a secure, culturally relevant digital marketplace." />
      <section className="av-container grid gap-12 py-16 lg:grid-cols-12 lg:py-24">
        <div className="lg:col-span-5 overflow-hidden rounded-[2rem]">
          <img src="/images/weaving.jpg" alt="Artisan weaving textile" className="h-full w-full object-cover" />
        </div>
        <div className="lg:col-span-7 space-y-6">
          <h2 className="text-3xl sm:text-4xl font-semibold text-av-ink">Our mission</h2>
          <p className="text-av-ink/80 leading-relaxed">We are building a marketplace where culture is the starting point, not an afterthought — giving independent businesses the tools to sell globally and giving customers a trusted place to find them.</p>
          <p data-testid="about-story-placeholder" className="rounded-xl border border-dashed border-av-line p-4 text-sm text-av-muted">[Founder story and company background — to be provided by AfroVending.]</p>
          <div className="grid gap-4 sm:grid-cols-2">
            {VALUES.map(([Icon, t, d]) => (
              <div key={t} className="rounded-2xl border border-av-line bg-white p-5">
                <Icon className="h-5 w-5 text-av-clay" />
                <h3 className="mt-3 font-sans text-base font-semibold text-av-ink">{t}</h3>
                <p className="mt-1 text-sm text-av-muted">{d}</p>
              </div>
            ))}
          </div>
          <div className="flex flex-wrap gap-3 pt-2">
            <Button asChild data-testid="about-shop-button"><Link to="/shop">Start exploring</Link></Button>
            <Button asChild variant="outline" data-testid="about-contact-button"><Link to="/contact">Contact us</Link></Button>
          </div>
        </div>
      </section>
    </div>
  );
}
