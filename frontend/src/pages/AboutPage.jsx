import { Link } from "react-router-dom";
import { Target, Telescope, Quote } from "lucide-react";
import { PageHero } from "@/components/common/PageHero";
import { Button } from "@/components/ui/button";

const PILLARS = [
  [Target, "Our Mission", "To empower entrepreneurs and small businesses through accessible digital commerce, increased visibility, and meaningful connections with customers worldwide."],
  [Telescope, "Our Vision", "To become a leading global marketplace for African, Caribbean, and diaspora-inspired products and businesses."],
  [Quote, "Our Motto", "From Culture to Commerce."],
];

export default function AboutPage() {
  return (
    <div data-testid="about-page">
      <PageHero eyebrow="About us" title="From Culture to Commerce." crumbs={[{ label: "Home", to: "/" }, { label: "About" }]}
        description="AfroVending Online Marketplace is a digital marketplace created to connect African, Caribbean, diaspora, and global entrepreneurs with customers who value culture, creativity, quality, and entrepreneurship." />
      <section className="av-container grid gap-12 py-16 lg:grid-cols-12 lg:py-24">
        <div className="lg:col-span-5 overflow-hidden rounded-[2rem]">
          <img src="/images/weaving.jpg" alt="Artisan weaving textile" className="h-full w-full object-cover" />
        </div>
        <div className="lg:col-span-7 space-y-6">
          <h2 className="text-3xl sm:text-4xl font-semibold text-av-ink">Our story</h2>
          <p data-testid="about-founder" className="text-av-ink/80 leading-relaxed">
            Founded by Olabode Emmanuel Idowu, AfroVending aims to provide independent businesses with a platform to showcase their products, reach new customers, and grow beyond geographical boundaries.
          </p>
          <p className="text-av-ink/80 leading-relaxed">Our vision is to create a thriving digital marketplace where cultural identity and economic opportunity come together.</p>
          <div className="grid gap-4 sm:grid-cols-3">
            {PILLARS.map(([Icon, t, d]) => (
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
