import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { StatusBadge } from "@/components/common/StatusBadge";
import { STOCK_REASONS } from "@/components/vendor/products/productUtils";
import { api, getErrorMessage } from "@/lib/api";

const AdjustRow = ({ v, onDone, disabled }) => {
  const [mode, setMode] = useState("add");
  const [qty, setQty] = useState("");
  const [reason, setReason] = useState("restock");
  const [note, setNote] = useState("");
  const apply = async () => {
    const n = parseInt(qty, 10);
    if (Number.isNaN(n) || (mode !== "set" && n <= 0) || n < 0) return toast.error("Enter a whole number.");
    try {
      await api.post(`/vendor/inventory/${v.id}/adjust`, { mode: mode === "set" ? "set" : "delta", quantity: mode === "remove" ? -n : n, reason, note });
      setQty("");
      setNote("");
      toast.success(`Stock updated for ${v.label}`);
      onDone();
    } catch (err) {
      toast.error(getErrorMessage(err));
    }
  };
  return (
    <tr className="flex flex-col border-t border-av-line align-top sm:table-row" data-testid={`inventory-row-${v.sku}`}>
      <td className="p-3 pb-0 sm:pb-3"><p className="font-medium">{v.label}</p><p className="text-xs text-av-muted">{v.sku}</p></td>
      <td className="px-3 sm:p-3"><span data-testid={`inventory-qty-${v.sku}`} className="font-semibold">{v.quantity_on_hand}</span>
        {v.low_stock && <StatusBadge tone="danger" className="ml-2" testId={`inventory-low-${v.sku}`}>Low</StatusBadge>}</td>
      <td className="p-2">
        <div className="flex flex-wrap gap-2">
          <Select value={mode} onValueChange={setMode} disabled={disabled}><SelectTrigger className="h-9 w-28 bg-white" data-testid={`inventory-mode-${v.sku}`}><SelectValue /></SelectTrigger>
            <SelectContent><SelectItem value="add">Add</SelectItem><SelectItem value="remove">Remove</SelectItem><SelectItem value="set">Set to</SelectItem></SelectContent></Select>
          <Input aria-label="Quantity" type="number" min="0" className="h-9 w-20" value={qty} onChange={(e) => setQty(e.target.value)} disabled={disabled} data-testid={`inventory-qty-input-${v.sku}`} />
          <Select value={reason} onValueChange={setReason} disabled={disabled}><SelectTrigger className="h-9 w-40 bg-white" data-testid={`inventory-reason-${v.sku}`}><SelectValue /></SelectTrigger>
            <SelectContent>{STOCK_REASONS.map(([k, l]) => <SelectItem key={k} value={k}>{l}</SelectItem>)}</SelectContent></Select>
          <Input aria-label="Note" placeholder="Note (optional)" className="h-9 w-40" value={note} onChange={(e) => setNote(e.target.value)} disabled={disabled} data-testid={`inventory-note-${v.sku}`} />
          <Button size="sm" onClick={apply} disabled={disabled} data-testid={`inventory-apply-${v.sku}`}>Apply</Button>
        </div>
      </td>
    </tr>
  );
};

export const InventoryPanel = ({ productId, variants, threshold, onChanged, disabled }) => {
  const [history, setHistory] = useState([]);
  const loadHistory = useCallback(async () => {
    setHistory((await api.get(`/vendor/products/${productId}/stock-history`)).data.data);
  }, [productId]);
  useEffect(() => {
    loadHistory();
  }, [loadHistory]);
  const done = () => { onChanged(); loadHistory(); };
  return (
    <div className="space-y-8" data-testid="inventory-panel">
      <p className="text-sm text-av-muted">You'll get an email and a dashboard alert when a variant drops to {threshold} or fewer.</p>
      <div className="rounded-xl border border-av-line bg-white sm:overflow-x-auto">
        <table className="w-full text-sm sm:min-w-[640px]">
          <thead className="hidden bg-av-sand text-left text-xs uppercase tracking-wider text-av-muted sm:table-header-group"><tr><th className="p-3">Variant</th><th className="p-3">On hand</th><th className="p-3">Adjust</th></tr></thead>
          <tbody>{variants.filter((v) => v.status === "active").map((v) => <AdjustRow key={v.id} v={v} onDone={done} disabled={disabled} />)}</tbody>
        </table>
      </div>
      <section>
        <h3 className="mb-3 text-lg font-semibold">Stock history</h3>
        <ul className="divide-y divide-av-line rounded-xl border border-av-line bg-white text-sm" data-testid="stock-history">
          {history.length === 0 && <li className="p-4 text-av-muted">No stock movements yet.</li>}
          {history.map((h) => (
            <li key={h.id} className="flex flex-wrap items-center justify-between gap-2 p-3">
              <span><b className={h.delta > 0 ? "text-av-emerald" : "text-red-700"}>{h.delta > 0 ? "+" : ""}{h.delta}</b> {h.variant_label} · {h.reason}{h.note ? ` — ${h.note}` : ""}</span>
              <span className="text-xs text-av-muted">{h.before} → {h.after} · {new Date(h.created_at).toLocaleString()}</span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
};
