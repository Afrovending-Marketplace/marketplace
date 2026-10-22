import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { StatusAlert } from "@/components/common/StatusAlert";
import { CartLine, TotalsCard } from "@/components/cart/CartParts";
import { useCart } from "@/context/CartContext";
import { api, getErrorMessage } from "@/lib/api";
import { formatPrice } from "@/lib/catalog";

const Option = ({ value, id, children, testId }) => (
  <label htmlFor={id} className="flex cursor-pointer items-start gap-3 rounded-xl border border-av-line bg-white p-3 text-sm has-[[data-state=checked]]:border-av-ink">
    <RadioGroupItem value={value} id={id} data-testid={testId} className="mt-0.5" /><span className="flex-1">{children}</span>
  </label>
);

const Addresses = ({ cart, c }) => {
  const [list, setList] = useState(null);
  useEffect(() => {
    api.get("/account/addresses").then((r) => {
      setList(r.data.data);
      const def = r.data.data.find((a) => a.is_default) || r.data.data[0];
      if (def && !cart.address_id) c.chooseAddress(def.id).catch(() => {});
    });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  if (!list) return null;
  if (!list.length) return <StatusAlert tone="warning" title="Add a delivery address" testId="checkout-no-address">
    <Link to="/account/addresses" className="underline" data-testid="checkout-add-address">Add an address</Link>, then come back to checkout.</StatusAlert>;
  return (
    <RadioGroup value={cart.address_id || ""} onValueChange={(id) => c.chooseAddress(id).catch((e) => toast.error(getErrorMessage(e)))} className="grid gap-3 sm:grid-cols-2">
      {list.map((a) => <Option key={a.id} value={a.id} id={`addr-${a.id}`} testId={`checkout-address-${a.id}`}>
        <b>{a.full_name}</b>{a.label && ` · ${a.label}`}<br />{[a.line1, a.line2, a.city, [a.region, a.postal_code].filter(Boolean).join(" "), a.country].filter(Boolean).join(", ")}</Option>)}
    </RadioGroup>
  );
};

export default function CheckoutPage() {
  const c = useCart();
  const cart = c.cart;
  const nav = useNavigate();
  const [busy, setBusy] = useState(false);
  const key = useMemo(() => `chk-${crypto.randomUUID()}`, []);
  if (!cart) return null;
  if (!cart.item_count) return <div className="av-container py-24 text-center" data-testid="checkout-empty">Your cart is empty. <Link to="/shop" className="underline">Shop now</Link></div>;
  const groups = cart.groups.filter((g) => g.vendor_id && g.subtotal_minor);
  const blocking = [...cart.blocking, !cart.address_id && "Choose a delivery address.", groups.some((g) => !g.shipping_method_id) && "Choose a shipping option for each vendor."].filter(Boolean);
  const start = async () => {
    setBusy(true);
    try {
      const r = await api.post("/checkout/start", null, { headers: { "Idempotency-Key": key } });
      nav(`/checkout/draft/${r.data.order.id}`);
    } catch (err) {
      toast.error(getErrorMessage(err));
      c.refresh();
    } finally {
      setBusy(false);
    }
  };
  return (
    <div data-testid="checkout-page" className="av-container py-12">
      <p className="av-eyebrow"><Link to="/cart" className="hover:underline" data-testid="checkout-back-to-cart">← Cart</Link></p>
      <h1 className="mt-2 text-4xl font-bold tracking-tight text-av-ink">Checkout review</h1>
      <div className="mt-8 grid gap-10 lg:grid-cols-[1fr_360px]">
        <div className="space-y-8">
          <section className="space-y-3"><h2 className="text-xl font-semibold">1. Delivery address</h2><Addresses cart={cart} c={c} /></section>
          <section className="space-y-4"><h2 className="text-xl font-semibold">2. Shipping & items</h2>
            {groups.map((g) => (
              <div key={g.vendor_id} className="space-y-3 rounded-2xl border border-av-line bg-white p-5" data-testid={`checkout-group-${g.vendor_slug}`}>
                <h3 className="font-semibold">Sold by {g.vendor_name}</h3>
                <ul className="divide-y divide-av-line">{g.items.map((l) => <CartLine key={l.variant_id} line={l} readOnly />)}</ul>
                <RadioGroup value={g.shipping_method_id || ""} onValueChange={(m) => c.chooseShipping(g.vendor_id, m).catch((e) => toast.error(getErrorMessage(e)))} className="gap-2">
                  {g.shipping_methods.map((m) => <Option key={m.id} value={m.id} id={`ship-${g.vendor_id}-${m.id}`} testId={`checkout-shipping-${g.vendor_slug}-${m.id}`}>
                    <b>{m.name}</b>{m.type === "pickup" ? ` · Local pickup (free)${m.pickup_address ? ` at ${m.pickup_address}` : ""}` : ` · ${m.amount_minor == null ? "Rate to be confirmed" : formatPrice(m.amount_minor)}`}{m.eta && <span className="block text-xs text-av-muted">{m.eta}</span>}{m.handling_days != null && <span className="block text-xs text-av-muted" data-testid={`checkout-handling-${g.vendor_slug}-${m.id}`}>{m.type === "pickup" ? `Ready for pickup within ${m.handling_days} business day${m.handling_days === 1 ? "" : "s"} after the seller accepts` : `Ships within ${m.handling_days} business day${m.handling_days === 1 ? "" : "s"} after the seller accepts`}</span>}</Option>)}
                </RadioGroup>
              </div>
            ))}
          </section>
          {cart.blocking.length > 0 && <StatusAlert tone="error" title="Fix your cart first" testId="checkout-cart-issues"><Link to="/cart" className="underline">Return to cart</Link> — {cart.blocking.join(" ")}</StatusAlert>}
        </div>
        <TotalsCard totals={cart.totals}>
          {blocking.length > 0 && <ul className="space-y-1 text-xs text-red-700" data-testid="checkout-blocking">{blocking.map((b) => <li key={b}>{b}</li>)}</ul>}
          <Button className="w-full" onClick={start} disabled={busy || blocking.length > 0} data-testid="checkout-start-button">Continue — create order draft</Button>
          <p className="text-xs text-av-muted">You'll review the draft, then pay securely with Stripe (test mode — no real money).</p>
        </TotalsCard>
      </div>
    </div>
  );
}
