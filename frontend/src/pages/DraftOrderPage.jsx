import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { StatusAlert } from "@/components/common/StatusAlert";
import { StatusBadge } from "@/components/common/StatusBadge";
import { TotalsCard } from "@/components/cart/CartParts";
import { api, getErrorMessage } from "@/lib/api";
import { formatPrice } from "@/lib/catalog";

const PayButton = ({ order }) => {
  const [busy, setBusy] = useState(false);
  const nav = useNavigate();
  if (["paid", "partially_refunded", "refunded"].includes(order.status)) {
    return <Button className="w-full" onClick={() => nav(`/account/orders/${order.id}`)} data-testid="draft-view-receipt">View receipt</Button>;
  }
  const pay = async () => {
    setBusy(true);
    try {
      const r = await api.post(`/payments/orders/${order.id}/checkout`, { origin_url: window.location.origin });
      window.location.assign(r.data.checkout_url);
    } catch (err) {
      toast.error(getErrorMessage(err));
      setBusy(false);
    }
  };
  return <Button className="w-full" onClick={pay} disabled={busy || !["draft", "pending_payment"].includes(order.status)} data-testid="draft-pay-button">
    {busy ? "Opening secure payment…" : `Pay ${formatPrice(order.totals.estimated_total_minor)} securely`}</Button>;
};

export default function DraftOrderPage() {
  const { id } = useParams();
  const [order, setOrder] = useState(undefined);
  useEffect(() => {
    api.get(`/checkout/orders/${id}`).then((r) => setOrder(r.data.order)).catch(() => setOrder(null));
  }, [id]);
  if (order === undefined) return null;
  if (!order) return <div className="av-container py-24 text-center" data-testid="draft-not-found">Order not found.</div>;
  const a = order.shipping_address;
  return (
    <div data-testid="draft-order-page" className="av-container max-w-5xl py-12">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-3xl sm:text-4xl font-bold tracking-tight text-av-ink">Order draft <span data-testid="draft-order-number">{order.order_number}</span></h1>
        <StatusBadge tone={order.status === "draft" ? "gold" : "neutral"} testId="draft-order-status">{order.status}</StatusBadge>
      </div>
      <StatusAlert tone="info" title="Test mode payments" className="mt-6" testId="draft-payment-note">
        Prices were checked by our server. Payment is taken by Stripe in TEST MODE: use card 4242 4242 4242 4242, any future date and any CVC. No real money moves.
        Tax shows as an estimate from configured rates; if no rate is configured, no tax is collected. Drafts expire after 24 hours.
      </StatusAlert>
      <div className="mt-8 grid gap-10 lg:grid-cols-[1fr_340px]">
        <div className="space-y-6">
          <section className="rounded-2xl border border-av-line bg-white p-5 text-sm"><h2 className="mb-2 font-semibold">Deliver to</h2>
            {a.full_name}<br />{a.line1}{a.line2 && `, ${a.line2}`}<br />{a.city}{a.region && `, ${a.region}`} {a.postal_code}<br />{a.country}</section>
          {order.vendor_groups.map((g) => (
            <section key={g.vendor_id} className="rounded-2xl border border-av-line bg-white p-5" data-testid={`draft-group-${g.vendor_slug}`}>
              <h2 className="font-semibold">Sold by {g.vendor_name}</h2>
              <ul className="mt-3 divide-y divide-av-line text-sm">{g.items.map((l) => (
                <li key={l.variant_id} className="flex justify-between gap-3 py-2"><span>{l.title}{l.label !== "Default" && ` (${l.label})`} × {l.quantity}</span><span>{formatPrice(l.line_total_minor)}</span></li>))}</ul>
              <p className="mt-3 text-xs text-av-muted">Shipping: {g.shipping_method.name} · {g.shipping_minor == null ? "rate to be confirmed" : `${formatPrice(g.shipping_minor)} (estimate)`}</p>
            </section>
          ))}
        </div>
        <TotalsCard totals={order.totals}><PayButton order={order} /><Link to="/shop" className="block text-center text-sm underline" data-testid="draft-continue-shopping">Continue shopping</Link></TotalsCard>
      </div>
    </div>
  );
}
