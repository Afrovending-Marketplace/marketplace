import { ShoppingBag, Store } from "lucide-react";
import { SectionHeading } from "@/components/common/SectionHeading";
import { HOME } from "@/constants/testIds";

const TRACKS = [
  {
    icon: ShoppingBag, title: "For customers", tone: "text-av-clay",
    steps: [
      "Discover verified African, Caribbean and diaspora vendors.",
      "Shop several vendors in one secure checkout.",
      "Track every order from workshop to doorstep.",
    ],
  },
  {
    icon: Store, title: "For vendors", tone: "text-av-emerald",
    steps: [
      "Apply, get verified and open your storefront.",
      "List products with variants, stock and media.",
      "Fulfil orders and follow your sales and payouts.",
    ],
  },
];

export const HowItWorks = () => (
  <section data-testid={HOME.howItWorks} className="bg-white border-y border-av-line">
    <div className="av-container py-20 lg:py-28 grid gap-12 lg:grid-cols-12">
      <SectionHeading className="lg:col-span-4" eyebrow="How it works" title="Bridging culture and commerce"
        description="One marketplace, two journeys — built around trust on both sides." />
      <div className="lg:col-span-8 grid gap-6 sm:grid-cols-2">
        {TRACKS.map(({ icon: Icon, title, tone, steps }) => (
          <div key={title} className="rounded-2xl border border-av-line bg-av-linen p-6 md:p-8 transition-shadow duration-300 hover:shadow-lg">
            <Icon className={`h-7 w-7 ${tone}`} />
            <h3 className="mt-4 font-sans text-xl font-semibold text-av-ink">{title}</h3>
            <ol className="mt-6 space-y-5">
              {steps.map((s, i) => (
                <li key={s} className="flex gap-4">
                  <span className="font-serif text-2xl leading-none text-av-gold">{String(i + 1).padStart(2, "0")}</span>
                  <span className="text-sm text-av-ink/80 leading-relaxed">{s}</span>
                </li>
              ))}
            </ol>
          </div>
        ))}
      </div>
    </div>
  </section>
);
