import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Minus, Plus, ShieldCheck, Truck } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/common/StatusBadge";
import { useCart } from "@/context/CartContext";
import { getErrorMessage } from "@/lib/api";
import { formatPrice } from "@/lib/catalog";
import { cn } from "@/lib/utils";

const toOption = (v) => (typeof v === "string" ? { id: v, label: v, in_stock: true } : v);
const idOf = (label) => label.replace(/[^a-z0-9]+/gi, "-").toLowerCase();

export const PurchasePanel = ({ product, vendor }) => {
  const options = product.variants.map(toOption);
  const [variant, setVariant] = useState(options.find((o) => o.in_stock) || options[0]);
  const [qty, setQty] = useState(1);
  const [busy, setBusy] = useState(false);
  const cart = useCart();
  const nav = useNavigate();
  const canBuy = !product.is_dev_data && variant?.in_stock;
  const add = async () => {
    setBusy(true);
    try {
      await cart.add(variant.id, qty, product.slug);
      toast.success(`Added to cart`, { action: { label: "View cart", onClick: () => nav("/cart") } });
    } catch (err) {
      toast.error(getErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };
  const price = variant?.price_minor ?? product.price_minor;
  const showOptions = options.length > 1 || (options[0] && options[0].label !== "Default");
  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <Link to={`/vendors/${vendor?.slug}`} data-testid="pdp-vendor-link" className="text-sm font-medium uppercase tracking-wider text-av-muted hover:text-av-clay">{vendor?.name}</Link>
        <h1 data-testid="pdp-title" className="text-3xl sm:text-4xl lg:text-5xl font-bold tracking-tight text-av-ink">{product.title}</h1>
        <p data-testid="pdp-price" className="text-2xl font-semibold text-av-ink">{formatPrice(price, product.currency)}</p>
        {product.is_dev_data ? <StatusBadge tone="gold">Sample listing · not for sale</StatusBadge>
          : <StatusBadge tone={variant?.in_stock ? (variant.low_stock ? "gold" : "success") : "danger"} testId="pdp-stock-status">
            {variant?.in_stock ? (variant.low_stock ? "Only a few left" : "In stock") : "Out of stock"}</StatusBadge>}
      </div>
      {showOptions && (
        <fieldset>
          <legend className="mb-2 text-sm font-semibold text-av-ink">{product.option_names?.join(" / ") || "Option"}: <span className="font-normal text-av-muted">{variant?.label}</span></legend>
          <div className="flex flex-wrap gap-2">
            {options.map((v) => (
              <button key={v.id} type="button" onClick={() => setVariant(v)} aria-pressed={v.id === variant?.id} data-testid={`pdp-variant-${idOf(v.label)}`}
                className={cn("h-11 min-w-11 rounded-full border px-4 text-sm transition-colors", v.id === variant?.id ? "border-av-ink bg-av-ink text-av-linen" : "border-av-line bg-white hover:border-av-ink/40", !v.in_stock && "line-through opacity-60")}>
                {v.label}
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
        <Button size="lg" disabled={!canBuy || busy} onClick={add} data-testid="pdp-add-to-cart" aria-describedby="pdp-cart-note" className="flex-1 min-w-[200px]">{variant?.in_stock || product.is_dev_data ? "Add to cart" : "Out of stock"}</Button>
      </div>
      <p id="pdp-cart-note" data-testid="pdp-cart-note" className="text-xs text-av-muted">{product.is_dev_data ? "Sample listings can't be added to the cart." : "Prices are checked again at checkout. Payments run in Stripe test mode."}</p>
      <ul className="space-y-3 rounded-2xl border border-av-line bg-white p-5 text-sm">
        <li className="flex gap-3"><Truck className="h-5 w-5 shrink-0 text-av-emerald" /> Ships from the vendor. Shipping options and estimates are shown at checkout.</li>
        <li className="flex gap-3"><ShieldCheck className="h-5 w-5 shrink-0 text-av-emerald" /> Purchase protection and returns policy: [to be confirmed].</li>
      </ul>
    </div>
  );
};
