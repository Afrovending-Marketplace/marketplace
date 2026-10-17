import { useState } from "react";
import { Link } from "react-router-dom";
import { Minus, Plus, ShieldCheck, Truck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/common/StatusBadge";
import { formatPrice } from "@/lib/catalog";
import { cn } from "@/lib/utils";

export const PurchasePanel = ({ product, vendor }) => {
  const [variant, setVariant] = useState(product.variants[0]);
  const [qty, setQty] = useState(1);
  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <Link to={`/vendors/${vendor.slug}`} data-testid="pdp-vendor-link" className="text-sm font-medium uppercase tracking-wider text-av-muted hover:text-av-clay">{vendor.name}</Link>
        <h1 data-testid="pdp-title" className="text-3xl sm:text-4xl lg:text-5xl font-bold tracking-tight text-av-ink">{product.title}</h1>
        <p data-testid="pdp-price" className="text-2xl font-semibold text-av-ink">{formatPrice(product.price_minor, product.currency)}</p>
        <StatusBadge tone="gold">Sample listing · not for sale</StatusBadge>
      </div>
      {product.variants.length > 0 && (
        <fieldset>
          <legend className="mb-2 text-sm font-semibold text-av-ink">Option: <span className="font-normal text-av-muted">{variant}</span></legend>
          <div className="flex flex-wrap gap-2">
            {product.variants.map((v) => (
              <button key={v} type="button" onClick={() => setVariant(v)} aria-pressed={v === variant} data-testid={`pdp-variant-${v.replace(/\s+/g, "-").toLowerCase()}`}
                className={cn("h-11 min-w-11 rounded-full border px-4 text-sm transition-colors", v === variant ? "border-av-ink bg-av-ink text-av-linen" : "border-av-line bg-white hover:border-av-ink/40")}>
                {v}
              </button>
            ))}
          </div>
        </fieldset>
      )}
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center rounded-full border border-av-line bg-white" role="group" aria-label="Quantity">
          <Button variant="ghost" size="icon" aria-label="Decrease quantity" data-testid="pdp-qty-decrease" onClick={() => setQty((q) => Math.max(1, q - 1))}><Minus /></Button>
          <span data-testid="pdp-qty-value" aria-live="polite" className="w-8 text-center text-sm font-semibold">{qty}</span>
          <Button variant="ghost" size="icon" aria-label="Increase quantity" data-testid="pdp-qty-increase" onClick={() => setQty((q) => Math.min(10, q + 1))}><Plus /></Button>
        </div>
        <Button size="lg" disabled data-testid="pdp-add-to-cart" aria-describedby="pdp-cart-note" className="flex-1 min-w-[200px]">Add to cart</Button>
      </div>
      <p id="pdp-cart-note" data-testid="pdp-cart-note" className="text-xs text-av-muted">Cart and checkout open in Phase 06. This is a template preview.</p>
      <ul className="space-y-3 rounded-2xl border border-av-line bg-white p-5 text-sm">
        <li className="flex gap-3"><Truck className="h-5 w-5 shrink-0 text-av-emerald" /> Ships from the vendor. Rates and delivery times are shown at checkout (planned).</li>
        <li className="flex gap-3"><ShieldCheck className="h-5 w-5 shrink-0 text-av-emerald" /> Purchase protection and returns policy: [to be confirmed].</li>
      </ul>
    </div>
  );
};
