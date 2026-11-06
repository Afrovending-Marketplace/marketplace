import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { StatusAlert } from "@/components/common/StatusAlert";
import { StatusBadge } from "@/components/common/StatusBadge";
import { PickupHours } from "@/components/common/PickupHours";
import { PickupBooking } from "@/components/account/PickupBooking";
import { OrderReviews } from "@/components/trust/OrderReviews";
import { OrderMessages } from "@/components/trust/OrderMessages";
import { api, getErrorMessage } from "@/lib/api";
import { formatPrice } from "@/lib/catalog";

const label = (s) => s.replace(/_/g, " ");
const tone = (s) => (s === "delivered" ? "success" : s === "cancelled" ? "neutral" : "gold");

const Actions = ({ orderId, vo, reload }) => {
  const [mode, setMode] = useState(null);
  const [reason, setReason] = useState("");
  const [qty, setQty] = useState({});
  const send = async () => {
    try {
      if (mode === "cancel") {
        const r = await api.post(`/orders/${orderId}/vendor-orders/${vo.id}/cancel`, { reason }, { headers: { "Idempotency-Key": `cx-${crypto.randomUUID()}` } });
        toast.success(r.data.result === "cancelled" ? "Cancelled — refund pending with Stripe" : "Cancellation request sent to the seller");
      } else {
        await api.post(`/orders/${orderId}/vendor-orders/${vo.id}/returns`, { reason, lines: Object.entries(qty).filter(([, q]) => Number(q) > 0).map(([order_item_id, q]) => ({ order_item_id, quantity: Number(q) })) });
        toast.success("Return request sent");
      }
      setMode(null);
      reload();
    } catch (err) {
      toast.error(getErrorMessage(err));
    }
  };
  const openCancel = vo.requests.find((r) => r.type === "cancel" && r.status === "requested");
  const canCancel = ["pending", "accepted", "processing"].includes(vo.status) && !openCancel;
  const canReturn = vo.status === "delivered";
  if (openCancel) return <p className="text-xs" data-testid={`order-cancel-pending-${vo.vendor_slug}`}>Cancellation requested — awaiting the seller (reply due {new Date(openCancel.due_at).toLocaleString()}).</p>;
  if (!canCancel && !canReturn) return null;
  return (
    <div className="space-y-2">
      {!mode && <div className="flex gap-2">
        {canCancel && <Button size="sm" variant="outline" onClick={() => setMode("cancel")} data-testid={`order-cancel-${vo.vendor_slug}`}>{vo.status === "pending" ? "Cancel these items" : "Request cancellation"}</Button>}
        {canReturn && <Button size="sm" variant="outline" onClick={() => setMode("return")} data-testid={`order-return-${vo.vendor_slug}`}>Request a return</Button>}</div>}
      {mode && <div className="space-y-2 rounded-xl bg-av-sand p-3 text-sm" data-testid={`order-${mode}-form-${vo.vendor_slug}`}>
        {mode === "return" && vo.items.map((i) => <label key={i.id} className="flex items-center gap-2">{i.title} ({i.shipped_qty - i.returned_qty} delivered)
          <Input className="h-8 w-16 bg-white" value={qty[i.id] || ""} onChange={(e) => setQty({ ...qty, [i.id]: e.target.value })} data-testid={`order-return-qty-${i.sku}`} /></label>)}
        <Input className="bg-white" placeholder="Reason" value={reason} onChange={(e) => setReason(e.target.value)} data-testid={`order-${mode}-reason`} />
        <div className="flex gap-2"><Button size="sm" onClick={send} disabled={reason.trim().length < 3} data-testid={`order-${mode}-submit`}>Submit</Button>
          <Button size="sm" variant="ghost" onClick={() => setMode(null)}>Close</Button></div></div>}
    </div>
  );
};

const VendorOrder = ({ orderId, vo, reload, reviews, reloadReviews }) => (
  <section className="space-y-3 rounded-2xl border border-av-line bg-white p-5 text-sm" data-testid={`order-vendor-${vo.vendor_slug}`}>
    <div className="flex flex-wrap items-center gap-2"><h2 className="font-semibold">Sold by {vo.vendor_name}</h2>
      <StatusBadge tone={tone(vo.status)} testId={`order-status-${vo.vendor_slug}`}>{label(vo.status)}</StatusBadge>
      <span className="text-xs text-av-muted">{vo.fulfillment_type === "pickup" ? `Local pickup · ${vo.shipping_method?.pickup_address || ""}` : vo.shipping_method?.name}</span></div>
    {vo.fulfillment_type === "pickup" && <PickupHours hours={vo.shipping_method?.pickup_hours} testId={`order-pickup-hours-${vo.vendor_slug}`} />}
    {vo.fulfillment_type === "pickup" && (vo.status === "ready_for_pickup" || vo.pickup_booking) && <PickupBooking orderId={orderId} vo={vo} onChange={reload} />}
    {vo.handling && ["accepted", "processing", "partially_shipped"].includes(vo.status) && <p className={`text-xs ${vo.handling.overdue ? "text-av-clay" : "text-av-muted"}`} data-testid={`order-expected-${vo.vendor_slug}`}>
      {vo.handling.kind === "pickup" ? "Expected ready for pickup by" : "Expected to ship by"} {new Date(vo.handling.deadline_at).toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" })}
      {vo.handling.overdue && (vo.handling.kind === "pickup" ? " — preparation is running late; we've asked the seller to hurry." : " — running late; we've asked the seller to ship right away.")}</p>}
    {!vo.handling && vo.status === "pending" && vo.shipping_method?.handling_days != null && <p className="text-xs text-av-muted" data-testid={`order-handling-${vo.vendor_slug}`}>
      {vo.fulfillment_type === "pickup" ? "Ready for pickup" : "Ships"} within {vo.shipping_method.handling_days} business day{vo.shipping_method.handling_days === 1 ? "" : "s"} after the seller accepts.</p>}
    <ul className="divide-y divide-av-line">{vo.items.map((i) => <li key={i.id} className="flex justify-between gap-3 py-2"><span>{i.title}{i.label !== "Default" && ` (${i.label})`} × {i.quantity}
      <span className="block text-xs text-av-muted">{vo.fulfillment_type === "pickup" ? (vo.status === "delivered" ? `${i.shipped_qty} collected` : vo.status === "ready_for_pickup" ? `${i.shipped_qty} ready to collect` : "0 ready yet") : `${i.shipped_qty} shipped`}{i.cancelled_qty ? ` · ${i.cancelled_qty} cancelled` : ""}{i.returned_qty ? ` · ${i.returned_qty} returned` : ""}</span></span><span>{formatPrice(i.line_total_minor)}</span></li>)}</ul>
    {vo.shipments.map((s) => <p key={s.id} data-testid={`order-shipment-${s.tracking_number}`}>{s.carrier_name} · {s.tracking_url ? <a href={s.tracking_url} target="_blank" rel="noreferrer" className="underline">{s.tracking_number}</a> : s.tracking_number} · {label(s.status)}</p>)}
    {vo.requests.map((r) => <p key={r.id} className="text-xs" data-testid={`order-request-${r.id}`}>{r.type} request (“{r.reason}”): <b>{r.status}</b>{r.rma_number && ` · ${r.rma_number}`}
      {r.history.length > 1 && r.history[r.history.length - 1].note && ` · ${r.history[r.history.length - 1].note}`}</p>)}
    {vo.refunds.map((r) => <p key={r.created_at} className="text-xs text-av-clay">Refund {formatPrice(r.amount_minor)} · {r.status === "succeeded" ? "sent by Stripe (your bank may take 5–10 business days)" : "pending with Stripe"}</p>)}
    <Actions orderId={orderId} vo={vo} reload={reload} />
    <OrderReviews vo={vo} status={reviews} reload={reloadReviews} />
    <OrderMessages path={`/orders/${orderId}/vendor-orders/${vo.id}/messages`} testId={`order-messages-${vo.vendor_slug}`} />
    <details className="text-xs text-av-muted"><summary data-testid={`order-timeline-toggle-${vo.vendor_slug}`}>Timeline</summary>
      <ol className="mt-2 space-y-1">{vo.events.map((e) => <li key={e.at + e.type}>{new Date(e.at).toLocaleString()} — {e.message}</li>)}</ol></details>
  </section>
);

export default function OrderDetailPage() {
  const { id } = useParams();
  const [d, setD] = useState(undefined);
  const [rs, setRs] = useState({});
  const load = useCallback(() => api.get(`/orders/${id}/detail`).then((r) => setD(r.data)).catch(() => setD(null)), [id]);
  const loadReviews = useCallback(() => api.get(`/orders/${id}/review-status`).then((r) => setRs(r.data.vendor_orders)).catch(() => {}), [id]);
  useEffect(() => {
    load();
    loadReviews();
  }, [load, loadReviews]);
  if (d === undefined) return null;
  if (!d) return <p data-testid="order-not-found">Order not found.</p>;
  const a = d.order.shipping_address;
  return (
    <div className="space-y-5" data-testid="order-detail-page">
      <p className="text-sm"><Link to="/account/orders" className="underline">← Orders</Link></p>
      <h1 className="text-3xl font-bold tracking-tight text-av-ink">Order {d.order.order_number}</h1>
      <StatusAlert tone="info" title={d.vendor_orders.every((v) => v.fulfillment_type === "pickup") ? "Local pickup order" : "Delivery address (as ordered)"} testId="order-address">
        {!d.vendor_orders.every((v) => v.fulfillment_type === "pickup") && <>{a.full_name}, {[a.line1, a.line2, a.city, a.region, a.postal_code, a.country].filter(Boolean).join(", ")}</>}
        {d.vendor_orders.some((v) => v.fulfillment_type === "pickup") && <span className="block text-xs">Local pickup items are collected from the seller's pickup address shown below.</span>}
        <span className="block text-xs">Returns can be requested within {d.return_window_days} days of delivery.</span></StatusAlert>
      {d.vendor_orders.map((vo) => <VendorOrder key={vo.id} orderId={id} vo={vo} reload={() => { load(); loadReviews(); }} reviews={rs[vo.id]} reloadReviews={loadReviews} />)}
      <Button asChild variant="outline" size="sm"><Link to={`/checkout/payment/${id}`} data-testid="order-receipt-link">Payment receipt</Link></Button>
    </div>
  );
}
