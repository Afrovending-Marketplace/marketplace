import { Link } from "react-router-dom";
import { Bookmark, Minus, Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/common/StatusBadge";
import { absUrl, formatPrice } from "@/lib/catalog";

const ISSUE = { unavailable: "No longer available", out_of_stock: "Out of stock", insufficient_stock: "Not enough stock" };

export const CartLine = ({ line, onQty, onRemove, onSave, readOnly }) => (
  <li className="flex gap-4 py-4" data-testid={`cart-line-${line.sku || line.variant_id}`}>
    <div className="h-20 w-20 shrink-0 overflow-hidden rounded-xl bg-av-sand">{line.image && <img src={absUrl(line.image)} alt="" className="h-full w-full object-cover" />}</div>
    <div className="min-w-0 flex-1 space-y-1">
      {line.slug ? <Link to={`/products/${line.slug}`} className="font-semibold text-av-ink hover:underline">{line.title}</Link> : <p className="font-semibold">{line.title}</p>}
      <p className="text-xs text-av-muted">{line.label !== "Default" && `${line.label} · `}{line.sku}</p>
      {line.status !== "ok" && <StatusBadge tone="danger" testId={`cart-line-issue-${line.variant_id}`}>{ISSUE[line.status]}{line.available ? ` — ${line.available} left` : ""}</StatusBadge>}
      {line.previous_price_minor != null && <p className="text-xs text-av-clay" data-testid={`cart-line-price-changed-${line.variant_id}`}>Price changed from {formatPrice(line.previous_price_minor)} to {formatPrice(line.unit_price_minor)}</p>}
      {!readOnly && (
        <div className="flex flex-wrap items-center gap-2 pt-1">
          <div className="flex items-center rounded-full border border-av-line bg-white">
            <Button size="icon" variant="ghost" className="h-8 w-8" aria-label="Decrease quantity" onClick={() => onQty(line.quantity - 1)} data-testid={`cart-qty-dec-${line.variant_id}`}><Minus /></Button>
            <span className="w-6 text-center text-sm font-semibold" data-testid={`cart-qty-${line.variant_id}`}>{line.quantity}</span>
            <Button size="icon" variant="ghost" className="h-8 w-8" aria-label="Increase quantity" onClick={() => onQty(line.quantity + 1)} disabled={line.status !== "ok"} data-testid={`cart-qty-inc-${line.variant_id}`}><Plus /></Button>
          </div>
          <Button size="sm" variant="ghost" onClick={onRemove} data-testid={`cart-remove-${line.variant_id}`}><Trash2 /> Remove</Button>
          {onSave && <Button size="sm" variant="ghost" onClick={onSave} data-testid={`cart-save-later-${line.variant_id}`}><Bookmark /> Save for later</Button>}
        </div>
      )}
      {readOnly && <p className="text-xs text-av-muted">Qty {line.quantity}</p>}
    </div>
    <p className="shrink-0 text-sm font-semibold" data-testid={`cart-line-total-${line.variant_id}`}>{line.status === "ok" ? formatPrice(line.line_total_minor) : "—"}</p>
  </li>
);

const Row = ({ label, value, testId, note }) => (
  <div className="flex justify-between gap-4 py-1.5 text-sm"><span className="text-av-muted">{label}{note && <span className="block text-[11px]">{note}</span>}</span><span data-testid={testId} className="text-right font-medium text-av-ink">{value}</span></div>
);

export const TotalsCard = ({ totals, children }) => (
  <div className="space-y-2 self-start rounded-2xl border border-av-line bg-white p-6 lg:sticky lg:top-24" data-testid="cart-totals">
    <Row label="Subtotal" value={formatPrice(totals.subtotal_minor)} testId="totals-subtotal" />
    {totals.discount_minor > 0 && <Row label="Discount" value={`−${formatPrice(totals.discount_minor)}`} testId="totals-discount" />}
    <Row label="Shipping (estimated)" value={totals.shipping_minor != null ? formatPrice(totals.shipping_minor) : totals.shipping_known_minor ? `${formatPrice(totals.shipping_known_minor)} + TBC` : totals.shipping_status === "not_selected" ? "Choose an option" : "To be confirmed"} testId="totals-shipping"
      note={totals.shipping_minor == null ? "Rates are confirmed before payment" : "Estimate — confirmed before payment"} />
    <Row label="Tax (estimated)" value={totals.tax_estimate_minor == null ? "Not yet calculated" : formatPrice(totals.tax_estimate_minor)} testId="totals-tax"
      note={totals.tax_estimate_minor == null ? "Calculated before payment" : totals.tax_rate_label} />
    <div className="flex justify-between border-t border-av-line pt-3 font-semibold"><span>Estimated total</span><span data-testid="totals-estimated-total">{formatPrice(totals.estimated_total_minor)}</span></div>
    <p className="text-xs text-av-muted" data-testid="totals-not-final">{totals.final ? "This is the amount you'll pay. Tax is $0.00 where no rate is configured." : "Not final. Shipping and tax are confirmed before payment; you won't be charged at this step."}</p>
    {children}
  </div>
);
