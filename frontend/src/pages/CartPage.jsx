import { useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { StatusAlert } from "@/components/common/StatusAlert";
import { CartLine, TotalsCard } from "@/components/cart/CartParts";
import { useCart } from "@/context/CartContext";
import { getErrorMessage } from "@/lib/api";
import { formatPrice } from "@/lib/catalog";

const Coupon = ({ cart, c }) => {
  const [code, setCode] = useState("");
  const apply = async (e) => {
    e.preventDefault();
    try {
      await c.applyCoupon(code);
      setCode("");
      toast.success("Coupon applied");
    } catch (err) {
      toast.error(getErrorMessage(err));
    }
  };
  if (cart.coupon?.applied) {
    return <div className="flex items-center gap-2 text-sm" data-testid="cart-coupon-applied"><span className="flex-1">Coupon <b>{cart.coupon.code}</b> · −{formatPrice(cart.coupon.discount_minor)}</span>
      <Button size="sm" variant="ghost" onClick={c.removeCoupon} data-testid="cart-coupon-remove">Remove</Button></div>;
  }
  return (
    <form onSubmit={apply} className="flex gap-2">
      <Input aria-label="Coupon code" placeholder="Coupon code" value={code} onChange={(e) => setCode(e.target.value)} className="h-10 bg-white" data-testid="cart-coupon-input" />
      <Button type="submit" variant="outline" disabled={code.trim().length < 2} data-testid="cart-coupon-apply">Apply</Button>
    </form>
  );
};

export default function CartPage() {
  const c = useCart();
  const cart = c.cart;
  const run = (fn) => fn().catch((err) => toast.error(getErrorMessage(err)));
  if (!cart) return null;
  if (!cart.item_count) {
    return (
      <div className="av-container max-w-2xl py-24 text-center" data-testid="cart-empty">
        <h1 className="text-4xl font-bold tracking-tight text-av-ink">Your cart is empty</h1>
        <p className="mt-3 text-av-muted">Find something made with culture and care.</p>
        <Button asChild className="mt-8"><Link to="/shop" data-testid="cart-empty-shop">Start shopping</Link></Button>
      </div>
    );
  }
  const priceChanged = cart.groups.some((g) => g.items.some((l) => l.previous_price_minor != null));
  return (
    <div data-testid="cart-page" className="av-container py-12">
      <h1 className="text-4xl font-bold tracking-tight text-av-ink">Your cart <span className="text-lg font-normal text-av-muted">({cart.item_count} items)</span></h1>
      <div className="mt-8 grid grid-cols-1 gap-10 lg:grid-cols-[1fr_360px]">
        <div className="min-w-0 space-y-6">
          {priceChanged && <StatusAlert tone="warning" title="Some prices changed" testId="cart-price-alert">
            Review the new prices below. <Button size="sm" variant="outline" className="ml-2" onClick={() => run(c.acceptPrices)} data-testid="cart-accept-prices">Accept new prices</Button></StatusAlert>}
          {cart.groups.map((g) => (
            <section key={g.vendor_id || "unavailable"} className="rounded-2xl border border-av-line bg-white p-5" data-testid={`cart-group-${g.vendor_slug || "unavailable"}`}>
              <div className="flex items-center justify-between border-b border-av-line pb-3">
                <h2 className="font-semibold">{g.vendor_slug ? <Link to={`/vendors/${g.vendor_slug}`} className="hover:underline">Sold by {g.vendor_name}</Link> : g.vendor_name}</h2>
                <span className="text-sm text-av-muted" data-testid={`cart-group-subtotal-${g.vendor_slug || "unavailable"}`}>{formatPrice(g.subtotal_minor)}</span>
              </div>
              <ul className="divide-y divide-av-line">
                {g.items.map((l) => <CartLine key={l.variant_id} line={l} onQty={(q) => run(() => c.setQty(l.variant_id, q))} onRemove={() => run(() => c.remove(l.variant_id))} />)}
              </ul>
            </section>
          ))}
        </div>
        <TotalsCard totals={cart.totals}>
          <Coupon cart={cart} c={c} />
          {cart.blocking.length > 0 && <ul className="space-y-1 text-xs text-red-700" data-testid="cart-blocking">{cart.blocking.map((b) => <li key={b}>{b}</li>)}</ul>}
          <Button asChild={!cart.blocking.length} className="w-full" disabled={!!cart.blocking.length} data-testid="cart-checkout-button">
            {cart.blocking.length ? <span>Checkout</span> : <Link to="/checkout">Checkout</Link>}
          </Button>
        </TotalsCard>
      </div>
    </div>
  );
}
