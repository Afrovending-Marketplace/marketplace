import { Link } from "react-router-dom";
import { ArrowRight, ShieldCheck, Store, Globe2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { HOME } from "@/constants/testIds";

const VALUES = [
  [ShieldCheck, "Vendor verification", "Sellers are reviewed before they list."],
  [Store, "Many makers, one cart", "Shop several vendors in a single checkout."],
  [Globe2, "Culture-first curation", "African, Caribbean and diaspora creators."],
];

export const HeroSection = () => (
  <section className="relative overflow-hidden mud-pattern">
    <div className="av-container grid items-center gap-10 py-12 lg:grid-cols-12 lg:py-20">
      <div className="lg:col-span-7 space-y-7 av-rise">
        <p className="av-eyebrow">African · Caribbean · Diaspora · Global</p>
        <h1 data-testid={HOME.heroTitle} className="text-5xl sm:text-6xl lg:text-7xl font-bold tracking-tight leading-[1.02] text-av-ink">
          From Culture<br />to <em className="text-av-clay">Commerce</em>.
        </h1>
        <p className="max-w-xl text-lg text-av-muted leading-relaxed">
          Discover fashion, beauty, food, art and heritage goods from independent entrepreneurs — all in one marketplace.
        </p>
        <div className="flex flex-wrap gap-3">
          <Button asChild size="lg" data-testid={HOME.exploreButton}><Link to="/shop">Shop the marketplace <ArrowRight /></Link></Button>
          <Button asChild size="lg" variant="outline" data-testid={HOME.vendorButton}><Link to="/sell">Sell on AfroVending</Link></Button>
        </div>
      </div>
      <div className="lg:col-span-5 relative av-rise max-w-xl" style={{ animationDelay: "150ms" }}>
        <div className="grain overflow-hidden rounded-[2rem] aspect-[4/5] shadow-2xl shadow-av-indigo/20">
          <img src="/images/hero.jpg" alt="Woman in kente-print dress at an artisan market" className="h-full w-full object-cover" fetchPriority="high" />
        </div>
        <Link to="/categories/fashion" data-testid="hero-promo-card"
          className="group absolute -bottom-5 left-4 right-4 sm:left-auto sm:-left-8 sm:right-auto sm:max-w-[18rem] flex items-center gap-4 rounded-2xl border border-av-line bg-white/95 p-4 shadow-xl backdrop-blur-md">
          <img src="/images/dev/cat-fashion.jpg" alt="" className="h-14 w-14 rounded-xl object-cover" />
          <div className="min-w-0">
            <p className="text-[10px] font-semibold uppercase tracking-widest text-av-gold-deep">Featured collection</p>
            <p className="font-serif text-lg text-av-ink">Heritage Textiles</p>
            <p className="text-xs text-av-clay group-hover:underline">Explore fashion →</p>
          </div>
        </Link>
      </div>
    </div>
    <div className="av-container grid gap-4 pb-12 pt-6 sm:grid-cols-3">
      {VALUES.map(([Icon, title, text]) => (
        <div key={title} className="flex items-start gap-3 rounded-2xl border border-av-line bg-white/70 p-4">
          <Icon className="mt-0.5 h-5 w-5 shrink-0 text-av-emerald" />
          <div><p className="text-sm font-semibold text-av-ink">{title}</p><p className="text-xs text-av-muted">{text}</p></div>
        </div>
      ))}
    </div>
  </section>
);
