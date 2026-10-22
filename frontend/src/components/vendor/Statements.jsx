import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { api, getErrorMessage } from "@/lib/api";

export const download = async (url, name) => {
  try {
    const r = await api.get(url, { responseType: "blob" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(r.data);
    a.download = name;
    a.click();
    URL.revokeObjectURL(a.href);
  } catch (err) {
    toast.error(getErrorMessage(err));
  }
};

export const Statements = ({ listUrl, fileUrl, testId }) => {
  const [rows, setRows] = useState(null);
  useEffect(() => {
    api.get(listUrl).then((r) => setRows(r.data.data)).catch(() => setRows([]));
  }, [listUrl]);
  return (
    <section className="space-y-2 rounded-2xl border border-av-line bg-white p-5" data-testid={testId}>
      <h2 className="text-xl font-semibold">Monthly payout statements</h2>
      <p className="text-xs text-av-muted">Built from AfroVending's permanent ledger. Corrections appear as separate entries in later months.</p>
      {rows?.length === 0 && <p className="text-sm text-av-muted">No statements yet.</p>}
      <ul className="divide-y divide-av-line text-sm">{rows?.map((s) => {
        const base = fileUrl(s);
        const id = s.statement_id || `${s.vendor_name}-${s.period}`;
        return (
          <li key={id} className="flex flex-wrap items-center justify-between gap-2 py-2" data-testid={`statement-${s.period}${s.vendor_id ? `-${s.vendor_id}` : ""}`}>
            <span>{s.vendor_name && <b>{s.vendor_name} · </b>}{s.period}{s.statement_id && ` · ${s.statement_id}`}</span>
            <span className="flex gap-2">
              <Button size="sm" variant="outline" onClick={() => download(`${base}.pdf`, `${id}.pdf`)} data-testid={`statement-pdf-${s.period}`}>PDF</Button>
              <Button size="sm" variant="outline" onClick={() => download(`${base}.csv`, `${id}.csv`)} data-testid={`statement-csv-${s.period}`}>CSV</Button>
            </span>
          </li>
        );
      })}</ul>
    </section>
  );
};
