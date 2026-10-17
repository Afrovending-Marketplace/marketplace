import { ArrowRight, ShieldCheck, Star } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/common/StatusBadge";
import { DsSection } from "@/components/design-system/DsSection";
import { DS } from "@/constants/testIds";

const BUTTONS = [
  ["default", "Primary", DS.buttonPrimary],
  ["gold", "Secondary gold", DS.buttonSecondary],
  ["indigo", "Indigo", DS.buttonIndigo],
  ["outline", "Outline", DS.buttonOutline],
  ["ghost", "Ghost", DS.buttonGhost],
];

export const ButtonSection = () => (
  <DsSection id="buttons" title="Buttons" description="Pill-shaped, 44px default height for touch, visible focus ring, press scale.">
    <div className="flex flex-wrap items-center gap-3">
      {BUTTONS.map(([variant, label, testId]) => (
        <Button key={variant} variant={variant} data-testid={testId} onClick={() => toast.success(`${label} button pressed`)}>
          {label}
        </Button>
      ))}
      <Button disabled data-testid={DS.buttonDisabled}>Disabled</Button>
      <Button size="sm" variant="outline" data-testid="ds-button-small">Small</Button>
      <Button size="lg" data-testid="ds-button-large">Large <ArrowRight /></Button>
    </div>
  </DsSection>
);

export const CardSection = () => (
  <DsSection id="cards" title="Cards" description="Rounded-2xl surfaces on linen. Sample content only.">
    <div className="grid gap-6 md:grid-cols-3">
      <article data-testid="ds-card-product" className="group overflow-hidden rounded-2xl border border-av-line bg-white transition-shadow hover:shadow-lg">
        <div className="aspect-[4/3] overflow-hidden">
          <img src="/images/weaving.jpg" alt="Sample product" className="h-full w-full object-cover transition-transform duration-500 group-hover:scale-105" />
        </div>
        <div className="space-y-2 p-5">
          <StatusBadge tone="clay">Sample product</StatusBadge>
          <h3 className="font-sans text-lg font-semibold text-av-ink">Handwoven Textile Throw</h3>
          <p className="text-sm text-av-muted">By [Vendor name]</p>
          <p className="font-semibold text-av-ink">$0.00</p>
        </div>
      </article>
      <article data-testid="ds-card-vendor" className="rounded-2xl border border-av-line bg-white p-6 md:p-8">
        <img src="/images/pottery.jpg" alt="Sample vendor" className="h-16 w-16 rounded-full object-cover" />
        <h3 className="mt-4 font-sans text-lg font-semibold text-av-ink">[Vendor store name]</h3>
        <StatusBadge tone="success" className="mt-2"><ShieldCheck className="h-3 w-3" /> Verified vendor</StatusBadge>
        <p className="mt-4 text-sm text-av-muted">Vendor storefront card used from Phase 04.</p>
      </article>
      <article data-testid="ds-card-feature" className="grain relative overflow-hidden rounded-2xl bg-av-indigo p-6 md:p-8 text-av-linen">
        <Star className="h-6 w-6 text-av-gold" />
        <h3 className="mt-4 font-serif text-2xl">Feature card</h3>
        <p className="mt-2 text-sm text-av-linen/70">Dark surface for promotional or bento highlights.</p>
      </article>
    </div>
  </DsSection>
);
