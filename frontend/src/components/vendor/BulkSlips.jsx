import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { api, getErrorMessage } from "@/lib/api";

export const BulkSlips = ({ refreshKey }) => {
  const [rows, setRows] = useState(null);
  const [range, setRange] = useState({});
  const [picked, setPicked] = useState(null);
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => {
    api.get("/vendor/packing-slips/pending", { params: { accepted_from: range.from || undefined, accepted_to: range.to || undefined } })
      .then((r) => { setRows(r.data.data); setPicked(null); });
  }, [range]);
  useEffect(() => {
    load();
  }, [load, refreshKey]);
  if (!rows) return null;
  const chosen = picked ?? new Set(rows.map((r) => r.id));
  const toggle = (id) => {
    const next = new Set(chosen);
    next.has(id) ? next.delete(id) : next.add(id);
    setPicked(next);
  };
  const go = async (print) => {
    setBusy(true);
    try {
      const r = await api.post("/vendor/packing-slips/bulk", { vendor_order_ids: [...chosen], accepted_from: range.from || null, accepted_to: range.to || null }, { responseType: "blob" });
      const url = URL.createObjectURL(new Blob([r.data], { type: "application/pdf" }));
      if (print) {
        const frame = document.createElement("iframe");
        frame.style.cssText = "position:fixed;right:0;bottom:0;width:0;height:0;border:0";
        frame.src = url;
        frame.onload = () => { frame.contentWindow.focus(); frame.contentWindow.print(); setTimeout(() => { frame.remove(); URL.revokeObjectURL(url); }, 60000); };
        document.body.appendChild(frame);
      } else {
        const a = document.createElement("a");
        a.href = url;
        a.download = `packing-slips-${new Date().toISOString().slice(0, 10)}.pdf`;
        a.click();
        setTimeout(() => URL.revokeObjectURL(url), 10000);
      }
    } catch (err) {
      toast.error(getErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="space-y-3 rounded-2xl border border-av-line bg-white p-5" data-testid="bulk-slips">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-xl font-semibold">Pending packing slips</h2>
        <span className="text-sm" data-testid="bulk-slips-count"><b>{chosen.size}</b> of {rows.length} order{rows.length === 1 ? "" : "s"} selected</span>
      </div>
      <p className="text-xs text-av-muted">Accepted delivery orders with items still to ship, oldest first. Printing doesn't change any order status.</p>
      <div className="flex flex-wrap items-center gap-2 text-xs">Accepted from
        <input type="date" className="h-8 rounded border border-av-line px-1" value={range.from || ""} onChange={(e) => setRange({ ...range, from: e.target.value })} data-testid="bulk-from" />to
        <input type="date" className="h-8 rounded border border-av-line px-1" value={range.to || ""} onChange={(e) => setRange({ ...range, to: e.target.value })} data-testid="bulk-to" />
        {(range.from || range.to) && <Button size="sm" variant="ghost" onClick={() => setRange({})} data-testid="bulk-clear">Clear dates</Button>}
      </div>
      {rows.length > 0 && <ul className="max-h-48 space-y-1 overflow-y-auto text-sm">{rows.map((r) => (
        <li key={r.id}><label className="flex items-center gap-2"><input type="checkbox" checked={chosen.has(r.id)} onChange={() => toggle(r.id)} data-testid={`bulk-pick-${r.order_number}`} />
          {r.order_number} · {r.items} item{r.items === 1 ? "" : "s"} to ship · accepted {new Date(r.accepted_at).toLocaleDateString()}</label></li>))}</ul>}
      <div className="flex flex-wrap gap-2">
        <Button disabled={busy || !chosen.size} onClick={() => go(true)} data-testid="bulk-print">Print all pending packing slips ({chosen.size})</Button>
        <Button variant="outline" disabled={busy || !chosen.size} onClick={() => go(false)} data-testid="bulk-download">Download PDF</Button>
      </div>
    </section>
  );
};
