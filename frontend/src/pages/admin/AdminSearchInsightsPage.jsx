import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { StatusAlert } from "@/components/common/StatusAlert";
import { api, getErrorMessage } from "@/lib/api";

const Stat = ({ label, value, testId }) => (
  <div className="rounded-2xl border border-av-line bg-white p-5"><p className="text-xs uppercase tracking-wider text-av-muted">{label}</p>
    <p className="mt-2 text-3xl font-bold text-av-ink" data-testid={testId}>{value}</p></div>
);

const QueryTable = ({ title, rows, testId }) => (
  <section><h2 className="mb-3 text-xl font-semibold">{title}</h2>
    <ul className="divide-y divide-av-line rounded-2xl border border-av-line bg-white text-sm" data-testid={testId}>
      {rows.length === 0 && <li className="p-4 text-av-muted">Nothing to show yet.</li>}
      {rows.map((r) => <li key={r.query} className="flex justify-between gap-3 p-3"><span className="truncate">{r.query}</span>
        <span className="shrink-0 text-av-muted">{r.count} searches · {r.avg_results} avg results</span></li>)}
    </ul>
  </section>
);

export default function AdminSearchInsightsPage() {
  const [days, setDays] = useState("30");
  const [d, setD] = useState(null);
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    setError("");
    try {
      setD((await api.get("/admin/search-analytics", { params: { days } })).data);
    } catch (err) {
      setError(getErrorMessage(err));
    }
  }, [days]);
  useEffect(() => {
    load();
  }, [load]);
  const purge = async () => {
    if (!window.confirm("Delete all stored search queries? This can't be undone.")) return;
    try {
      const r = await api.delete("/admin/search-analytics");
      toast.success(`${r.data.deleted} search records deleted`);
      load();
    } catch (err) {
      toast.error(getErrorMessage(err));
    }
  };
  if (error) return <div className="av-container max-w-3xl py-16"><StatusAlert tone="error" title={error} testId="search-insights-error" /><Button className="mt-4" variant="outline" onClick={load} data-testid="search-insights-retry">Try again</Button></div>;
  if (!d) return <div className="av-container py-24 text-center text-sm text-av-muted" data-testid="search-insights-loading">Loading…</div>;
  return (
    <div data-testid="admin-search-insights-page" className="av-container max-w-5xl space-y-8 py-12">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <h1 className="text-4xl font-bold tracking-tight text-av-ink">Search insights</h1>
        <div className="flex gap-2">
          <Select value={days} onValueChange={setDays}><SelectTrigger className="h-10 w-36 bg-white" data-testid="search-insights-days"><SelectValue /></SelectTrigger>
            <SelectContent>{["7", "30", "90", "180"].map((v) => <SelectItem key={v} value={v}>Last {v} days</SelectItem>)}</SelectContent></Select>
          <Button variant="outline" onClick={purge} data-testid="search-insights-purge">Delete all search data</Button>
        </div>
      </div>
      <div className="grid gap-4 sm:grid-cols-3">
        <Stat label="Searches" value={d.total_searches} testId="search-insights-total" />
        <Stat label="No-result searches" value={d.zero_result_searches} testId="search-insights-zero" />
        <Stat label="No-result rate" value={`${Math.round(d.zero_result_rate * 100)}%`} testId="search-insights-zero-rate" />
      </div>
      <div className="grid gap-8 lg:grid-cols-2">
        <QueryTable title="Top searches" rows={d.top_queries} testId="search-insights-top" />
        <QueryTable title="Searches with no results" rows={d.zero_result_queries} testId="search-insights-zero-list" />
      </div>
      <StatusAlert tone="info" title="Privacy" testId="search-insights-privacy">
        {d.privacy.stored} Only queries searched at least {d.privacy.min_count} times are listed ({d.hidden_rare_queries} rarer queries hidden). Records are deleted automatically after {d.privacy.retention_days} days.
      </StatusAlert>
    </div>
  );
}
