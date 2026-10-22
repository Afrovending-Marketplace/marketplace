import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { StatusBadge } from "@/components/common/StatusBadge";
import { api } from "@/lib/api";
import { formatPrice } from "@/lib/catalog";

export default function AccountOrdersPage() {
  const [rows, setRows] = useState(null);
  useEffect(() => {
    api.get("/payments/orders").then((r) => setRows(r.data.data)).catch(() => setRows([]));
  }, []);
  if (!rows) return null;
  return (
    <div className="space-y-4" data-testid="account-orders-page">
      <h1 className="text-3xl font-bold tracking-tight text-av-ink">Orders & receipts</h1>
      {rows.length === 0 && <p className="text-av-muted" data-testid="account-orders-empty">No orders yet.</p>}
      <ul className="divide-y divide-av-line rounded-2xl border border-av-line bg-white">
        {rows.map((o) => (
          <li key={o.id} data-testid={`account-order-${o.order_number}`}>
            <Link to={`/account/orders/${o.id}`} className="flex flex-wrap items-center justify-between gap-3 p-4 text-sm hover:bg-av-sand">
            <span className="font-semibold">{o.order_number}</span>
            <span className="text-av-muted">{new Date(o.paid_at || o.created_at).toLocaleDateString()}</span>
            <StatusBadge tone={o.status === "paid" ? "success" : o.status === "pending_payment" ? "gold" : "neutral"}>{o.status.replace("_", " ")}</StatusBadge>
            <span className="font-semibold">{formatPrice(o.totals.estimated_total_minor)}</span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
