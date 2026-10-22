import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { StatusAlert } from "@/components/common/StatusAlert";
import { StatusBadge } from "@/components/common/StatusBadge";
import { api } from "@/lib/api";
import { formatPrice } from "@/lib/catalog";

const PAID = ["paid", "partially_refunded", "refunded"];

const Receipt = ({ order }) => (
  <div className="space-y-4" data-testid="receipt">
    {order.vendor_orders.map((v) => (
      <section key={v.id} className="rounded-2xl border border-av-line bg-white p-5 text-sm" data-testid={`receipt-vendor-${v.vendor_slug}`}>
        <h2 className="font-semibold">Sold by {v.vendor_name}</h2>
        <ul className="mt-2 divide-y divide-av-line">{v.items.map((i) => (
          <li key={i.title + i.label} className="flex justify-between gap-3 py-2"><span>{i.title}{i.label !== "Default" && ` (${i.label})`} × {i.quantity}
            {i.refunded_qty > 0 && <span className="ml-2 text-xs text-av-clay">{i.refunded_qty} refunded</span>}</span><span>{formatPrice(i.line_total_minor)}</span></li>))}</ul>
        <div className="mt-2 space-y-1 text-xs text-av-muted">
          {v.discount_minor > 0 && <p>Discount −{formatPrice(v.discount_minor)}</p>}
          <p>Shipping {formatPrice(v.shipping_minor)} · Tax {formatPrice(v.tax_minor)}</p>
          <p className="font-semibold text-av-ink">Paid to AfroVending for this seller: {formatPrice(v.charged_minor)}</p>
          {v.refunded_minor > 0 && <p className="text-av-clay" data-testid={`receipt-refunded-${v.vendor_slug}`}>Refunded {formatPrice(v.refunded_minor)}</p>}
        </div>
      </section>
    ))}
  </div>
);

export default function PaymentStatusPage() {
  const { id } = useParams();
  const [params] = useSearchParams();
  const [order, setOrder] = useState(undefined);
  const tries = useRef(0);
  const load = useCallback(async () => {
    try {
      const r = params.get("cancelled") && tries.current === 0 ? await api.post(`/payments/orders/${id}/cancel`) : await api.get(`/payments/orders/${id}`);
      setOrder(r.data.order);
      return r.data.order;
    } catch {
      setOrder(null);
      return null;
    }
  }, [id, params]);
  useEffect(() => {
    let timer;
    const tick = async () => {
      const o = await load();
      tries.current += 1;
      if (o && o.status === "pending_payment" && tries.current < 15) timer = setTimeout(tick, 2000);
    };
    tick();
    return () => clearTimeout(timer);
  }, [load]);
  if (order === undefined) return null;
  if (!order) return <div className="av-container py-24 text-center" data-testid="payment-not-found">Order not found.</div>;
  const paid = PAID.includes(order.status);
  return (
    <div data-testid="payment-status-page" className="av-container max-w-4xl space-y-6 py-12">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-3xl sm:text-4xl font-bold tracking-tight text-av-ink">{paid ? "Receipt" : "Order"} <span data-testid="payment-order-number">{order.order_number}</span></h1>
        <StatusBadge tone={paid ? "success" : "gold"} testId="payment-order-status">{order.status.replace("_", " ")}</StatusBadge>
        {order.payment?.mode === "test" && <StatusBadge tone="neutral" testId="payment-test-mode">TEST MODE</StatusBadge>}
      </div>
      {paid && <StatusAlert tone="success" title="Payment confirmed" testId="payment-confirmed">Stripe confirmed your payment of {formatPrice(order.payment.amount_minor)}. A receipt was emailed to you.</StatusAlert>}
      {order.status === "pending_payment" && <StatusAlert tone="info" title="Confirming your payment…" testId="payment-pending">We only mark orders paid after Stripe confirms it. This page updates automatically.</StatusAlert>}
      {order.status === "draft" && <StatusAlert tone="warning" title="Payment not completed" testId="payment-not-completed">
        You weren't charged. <Link to={`/checkout/draft/${order.id}`} className="underline" data-testid="payment-retry-link">Return to your order</Link> to try again.</StatusAlert>}
      {paid ? <Receipt order={order} /> : <Button asChild variant="outline"><Link to={`/checkout/draft/${order.id}`} data-testid="payment-back-to-draft">Back to order</Link></Button>}
      {order.refunds?.length > 0 && <p className="text-sm text-av-muted" data-testid="payment-refunds">Refunds: {order.refunds.map((r) => `${formatPrice(r.amount_minor)} (${r.status})`).join(", ")}</p>}
    </div>
  );
}
