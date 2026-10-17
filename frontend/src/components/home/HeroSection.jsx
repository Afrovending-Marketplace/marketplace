import { Link } from "react-router-dom";
import { ArrowRight, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { HOME } from "@/constants/testIds";

export const HeroSection = () => (
  <section className="relative overflow-hidden mud-pattern">
    <div className="av-container grid items-center gap-12 py-16 md:grid-cols-12 lg:py-24">
      <div className="md:col-span-7 space-y-8 av-rise">
        <p className="av-eyebrow">African · Caribbean · Diaspora · Global</p>
        <h1 data-testid={HOME.heroTitle} className="text-5xl sm:text-6xl lg:text-7xl font-bold tracking-tight leading-[1.02] text-av-ink">
          From Culture<br />to <em className="text-av-clay">Commerce</em>.
        </h1>
        <p className="max-w-xl text-lg text-av-muted leading-relaxed">
          A secure, multi-vendor marketplace connecting African, Caribbean, diaspora and global
          entrepreneurs with customers who value authentic craft and culture.
        </p>
        <div className="flex flex-wrap gap-3">
          <Button asChild size="lg" data-testid={HOME.exploreButton}>
            <Link to="/shop">Explore the marketplace <ArrowRight /></Link>
          </Button>
          <Button asChild size="lg" variant="outline" data-testid={HOME.vendorButton}>
            <Link to="/become-vendor">Become a vendor</Link>
          </Button>
        </div>
      </div>
      <div className="md:col-span-5 relative av-rise" style={{ animationDelay: "150ms" }}>
        <div className="grain overflow-hidden rounded-[2rem] aspect-[4/5] shadow-2xl shadow-av-indigo/20">
          <img src="/images/hero.jpg" alt="Handcrafted goods from African and diaspora artisans"
            className="h-full w-full object-cover" fetchpriority="high" />
        </div>
        <div className="absolute -bottom-6 -left-4 sm:-left-10 max-w-[16rem] rounded-2xl border border-av-line bg-white/90 p-5 shadow-xl backdrop-blur-md">
          <div className="flex items-center gap-2 text-av-emerald">
            <ShieldCheck className="h-5 w-5" />
            <span className="text-sm font-semibold">Verified vendors</span>
          </div>
          <p className="mt-2 text-xs text-av-muted leading-relaxed">
            Every seller goes through onboarding and verification before listing.
          </p>
        </div>
      </div>
    </div>
  </section>
);
