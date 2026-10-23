import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/common/StatusBadge";
import { formatPrice } from "@/lib/catalog";
import { download } from "@/components/vendor/Statements";

const money = (m) => formatPrice((m ?? 0) || 0);
const etDate = (iso) => new Date(iso).toLocaleDateString("en-US", { timeZone: "America/New_York" });
const label = (s) => s.replace(/_/g, " ");

export const Card = ({ title, testId, action, children, className = "" }) => (
  <section className={`space-y-3 rounded-2xl border border-av-line bg-white p-5 ${className}`} data-testid={testId}>
    <div className="flex flex-wrap items-center justify-between gap-2"><h2 className="text-lg font-semibold text-av-ink">{title}</h2>{action}</div>
    {children}
  </section>
);

const Kpi = ({ name, value, hint, testId, strong }) => (
  <div className={`rounded-xl p-4 ${strong ? "bg-av-ink text-white" : "bg-av-sand"}`} data-testid={testId}>
    <p className={`text-xs ${strong ? "text-white/70" : "text-av-muted"}`}>{name}</p>
    <p className="mt-1 text-2xl font-bold tracking-tight">{value}</p>
    {hint && <p className={`mt-1 text-xs ${strong ? "text-white/70" : "text-av-muted"}`}>{hint}</p>}
  </div>
);

export const SalesKpis = ({ s }) => {
  const t = s.totals;
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4" data-testid="dash-kpis">
      <Kpi strong name="Net item sales" value={money(t.net_item_sales_minor)} hint={`${money(t.gross_item_sales_minor)} paid − ${money(-t.item_refunds_minor)} refunded`} testId="kpi-net-item-sales" />
      <Kpi name="Orders" value={t.orders} hint={`${t.cancelled_orders} cancelled · avg ${money(t.average_order_minor)}`} testId="kpi-orders" />
      <Kpi name="Your earnings (after fees)" value={money(t.vendor_earnings_minor)} hint="Not the same as your payout balance" testId="kpi-earnings" />
      <Kpi name="Refunds" value={money(-t.refunds_minor)} hint="Items and shipping" testId="kpi-refunds" />
    </div>
  );
};

export const SalesChart = ({ series }) => {
  const max = Math.max(1, ...series.map((d) => d.net_item_sales_minor));
  return (
    <div className="flex h-36 items-end gap-[2px]" data-testid="dash-sales-chart" role="img" aria-label="Daily net item sales">
      {series.map((d) => (
        <div key={d.date} className="group relative flex-1" style={{ height: "100%" }}>
          <div className="absolute bottom-0 w-full rounded-t bg-av-clay/80 transition-colors group-hover:bg-av-clay" style={{ height: `${Math.max(0, d.net_item_sales_minor) / max * 100}%`, minHeight: d.net_item_sales_minor > 0 ? 2 : 0 }} />
          <span className="pointer-events-none absolute -top-8 left-1/2 z-10 hidden -translate-x-1/2 whitespace-nowrap rounded bg-av-ink px-2 py-1 text-[10px] text-white group-hover:block">{d.date}: {money(d.net_item_sales_minor)} · {d.orders} orders</span>
        </div>))}
    </div>
  );
};

export const Breakdown = ({ s, plan }) => {
  const t = s.totals;
  const rows = [["Net item sales", t.net_item_sales_minor, "net"], ["Shipping charged", t.shipping_charged_minor, "ship"], ["Shipping refunded", t.shipping_refunds_minor, "ship-ref"],
    ["Marketplace commission", t.commission_minor, "commission"], ["Card processing fees (your share)", t.processing_fees_minor, "fees"],
    ["Chargebacks & adjustments", t.dispute_adjustments_minor, "disputes"], ["Your earnings", t.vendor_earnings_minor, "earnings"]];
  return (
    <Card title="Earnings & commission" testId="dash-breakdown">
      <p className="text-xs text-av-muted" data-testid="dash-plan">Plan: <b>{plan.name}</b> ({plan.monthly_fee_minor ? `${money(plan.monthly_fee_minor)}/month` : "$0/month"}) · {(plan.override_bps ?? plan.rate_bps) / 100}% commission{plan.override_bps != null && " (approved override)"}{plan.note && ` (${plan.note})`}. Category rules may apply to some items.</p>
      <dl className="divide-y divide-av-line text-sm">{rows.map(([n, v, k]) => <div key={k} className={`flex justify-between py-1.5 ${k === "earnings" ? "font-semibold" : ""}`} data-testid={`breakdown-${k}`}><dt>{n}</dt><dd>{money(v)}</dd></div>)}</dl>
      <p className="text-xs text-av-muted">Sales tax collected ({money(t.tax_collected_minor + t.tax_refunded_minor)} net) is held for remittance and isn't part of your earnings.</p>
    </Card>
  );
};

export const Alerts = ({ items }) => (
  <Card title="Alerts" testId="dash-alerts">
    {items.length === 0 ? <p className="text-sm text-av-muted" data-testid="dash-alerts-empty">Nothing needs your attention.</p> :
      <ul className="space-y-2 text-sm">{items.map((a) => (
        <li key={a.code} className="flex items-start justify-between gap-2" data-testid={`alert-${a.code}`}>
          <span className="flex items-start gap-2"><StatusBadge tone={a.level === "error" ? "danger" : a.level === "warning" ? "gold" : "neutral"}>{a.level}</StatusBadge>{a.text}</span>
          <Link to={a.link} className="shrink-0 text-xs underline">Open</Link></li>))}</ul>}
  </Card>
);

export const OrdersCard = ({ ops }) => (
  <Card title="New & open orders" testId="dash-orders" action={<Button asChild size="sm" variant="outline"><Link to="/vendor/orders" data-testid="dash-orders-link">Fulfil orders</Link></Button>}>
    <div className="flex flex-wrap gap-2 text-xs">{Object.entries(ops.open_orders).map(([k, v]) => <span key={k} className="rounded-full bg-av-sand px-3 py-1" data-testid={`dash-open-${k}`}>{label(k)}: <b>{v}</b></span>)}
      {ops.overdue_orders > 0 && <span className="rounded-full bg-av-clay px-3 py-1 text-white" data-testid="dash-overdue">overdue: <b>{ops.overdue_orders}</b></span>}</div>
    {ops.queue.length === 0 ? <p className="text-sm text-av-muted">No open orders.</p> :
      <ul className="divide-y divide-av-line text-sm">{ops.queue.map((o) => <li key={o.id} className="flex flex-wrap justify-between gap-2 py-1.5" data-testid={`dash-queue-${o.order_number}`}>
        <span><b>{o.order_number}</b> · {label(o.status)} · {o.fulfillment_type === "pickup" ? "pickup" : "delivery"}</span>
        <span className="text-xs text-av-muted">{o.deadline_at ? `due ${etDate(o.deadline_at)}` : etDate(o.created_at)} · {money(o.charged_minor)}</span></li>)}</ul>}
  </Card>
);

export const InventoryCard = ({ inv }) => (
  <Card title="Products & inventory" testId="dash-inventory" action={<Button asChild size="sm" variant="outline"><Link to="/vendor/products" data-testid="dash-products-link">Manage products</Link></Button>}>
    <p className="text-sm" data-testid="dash-product-counts">{inv.products_total} products ({Object.entries(inv.products_by_status).map(([k, v]) => `${v} ${label(k)}`).join(", ") || "none yet"}) · {inv.units_available} units available</p>
    {[["Out of stock", inv.out_of_stock, "out"], ["Low stock", inv.low_stock, "low"]].map(([n, rows, k]) => rows.length > 0 && (
      <div key={k} data-testid={`dash-stock-${k}`}><p className="text-xs font-semibold">{n} ({rows.length})</p>
        <ul className="text-xs text-av-muted">{rows.slice(0, 6).map((r) => <li key={r.sku}><Link className="underline" to={`/vendor/products/${r.product_id}`}>{r.title}</Link>{r.variant && r.variant !== "Default" ? ` (${r.variant})` : ""} · {r.sku} · {r.available} left{r.reserved ? ` · ${r.reserved} reserved` : ""}</li>)}</ul></div>))}
  </Card>
);

export const PayoutsCard = ({ pay }) => {
  const b = pay.balances;
  return (
    <Card title="Payouts" testId="dash-payouts" action={<Button asChild size="sm" variant="outline"><Link to="/vendor/earnings" data-testid="dash-earnings-link">Earnings & statements</Link></Button>}>
      <div className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-3">{[["Pending (7-day hold)", b.pending_minor, "pending"], ["Ready to transfer", b.eligible_minor, "eligible"], ["On hold", b.held_minor, "held"],
        ["Transferred", b.transferred_minor, "transferred"], ["Paid out", b.paid_minor, "paid"], ["Owed", b.owed_minor, "owed"]].map(([n, v, k]) => <div key={k} data-testid={`dash-balance-${k}`}><p className="text-xs text-av-muted">{n}</p><p className="font-semibold">{money(v)}</p></div>)}</div>
      {pay.history.length === 0 ? <p className="text-sm text-av-muted" data-testid="dash-payouts-empty">No payouts yet.</p> :
        <ul className="divide-y divide-av-line text-xs">{pay.history.slice(0, 6).map((p) => <li key={p.id} className="flex justify-between gap-2 py-1.5" data-testid={`dash-payout-${p.id}`}><span>{p.order_number} · {etDate(p.created_at)}{p.transfer_ref && ` · ${p.transfer_ref}`}</span><span>{money(p.amount_minor)} · <b>{p.status}</b></span></li>)}</ul>}
    </Card>
  );
};

export const ReviewsCard = ({ r }) => (
  <Card title="Customer reviews" testId="dash-reviews">
    <div className="flex gap-6 text-sm"><div><p className="text-xs text-av-muted">Total reviews</p><p className="text-2xl font-bold" data-testid="reviews-total">{r.total}</p></div>
      <div><p className="text-xs text-av-muted">Average rating</p><p className="text-2xl font-bold" data-testid="reviews-average">{r.average == null ? "—" : r.average.toFixed(1)}</p></div></div>
    {r.total === 0 ? <p className="text-sm text-av-muted" data-testid="reviews-empty">No reviews yet.{!r.available && " Customer reviews are coming in a later update."}</p> :
      <ul className="text-xs">{Object.entries(r.distribution).map(([star, n]) => <li key={star}>{star}★ · {n}</li>)}</ul>}
  </Card>
);

export const TopProducts = ({ rows }) => (
  <Card title="Top products in this period" testId="dash-top-products">
    {rows.length === 0 ? <p className="text-sm text-av-muted">No sales in this period.</p> :
      <ul className="divide-y divide-av-line text-sm">{rows.map((p) => <li key={p.product_id} className="flex justify-between gap-2 py-1.5" data-testid={`top-${p.product_id}`}><span>{p.title} · {p.units} sold{p.refunded_units ? ` · ${p.refunded_units} refunded` : ""}</span><b>{money(p.net_item_sales_minor)}</b></li>)}</ul>}
  </Card>
);

export const Reports = ({ range }) => {
  const q = `from=${range.from}&to=${range.to}`;
  const items = [["summary", "Sales summary (totals + daily)"], ["transactions", "Transactions (every ledger entry)"], ["orders", "Orders (per order, with commission & fees)"], ["products", "Products (units and net sales)"]];
  return (
    <Card title="CSV reports" testId="dash-reports">
      <p className="text-xs text-av-muted">For {range.from} to {range.to}, US Eastern time. Built from the same records as the dashboard and your monthly statements.</p>
      <div className="flex flex-wrap gap-2">{items.map(([k, n]) => <Button key={k} size="sm" variant="outline" onClick={() => download(`/vendor/reports/${k}.csv?${q}`, `afrovending-${k}-${range.from}_${range.to}.csv`)} data-testid={`report-${k}`}>{n}</Button>)}</div>
    </Card>
  );
};
