import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Stars } from "@/components/trust/Reviews";
import { api, getErrorMessage } from "@/lib/api";

const Preferences = () => {
  const [p, setP] = useState(null);
  useEffect(() => {
    api.get("/notifications/preferences").then((r) => setP(r.data));
  }, []);
  if (!p) return null;
  const toggle = async (cat, ch, v) => {
    const next = { ...p.preferences, [cat]: { ...p.preferences[cat], [ch]: v } };
    try {
      await api.put("/notifications/preferences", next);
      setP({ ...p, preferences: next });
      toast.success("Preferences saved");
    } catch (e) {
      toast.error(getErrorMessage(e));
    }
  };
  return (
    <section className="space-y-3 rounded-2xl border border-av-line bg-white p-5" data-testid="notification-preferences">
      <h2 className="font-semibold">Notification preferences</h2>
      <table className="w-full text-sm"><thead><tr className="text-left text-xs text-av-muted"><th className="py-1">Topic</th><th>Email</th><th>In-app</th></tr></thead>
        <tbody>{Object.entries(p.labels).map(([cat, lbl]) => <tr key={cat} className="border-t border-av-line"><td className="py-2">{lbl}</td>
          {["email", "in_app"].map((ch) => <td key={ch}><Switch checked={p.preferences[cat][ch]} onCheckedChange={(v) => toggle(cat, ch, v)} data-testid={`pref-${cat}-${ch}`} /></td>)}</tr>)}</tbody></table>
      <p className="text-xs text-av-muted">{p.always_sent}</p>
    </section>
  );
};

export default function NotificationsPage() {
  const [d, setD] = useState(null);
  const load = useCallback(() => api.get("/notifications").then((r) => setD(r.data)), []);
  useEffect(() => {
    load();
  }, [load]);
  const read = (n) => !n.read && api.post(`/notifications/${n.id}/read`).then(load);
  return (
    <div className="space-y-5" data-testid="notifications-page">
      <div className="flex flex-wrap items-center justify-between gap-2"><h1 className="text-3xl font-bold tracking-tight text-av-ink">Notifications</h1>
        {d?.unread > 0 && <Button size="sm" variant="outline" onClick={() => api.post("/notifications/read-all").then(load)} data-testid="notifications-read-all">Mark all as read</Button>}</div>
      <ul className="divide-y divide-av-line rounded-2xl border border-av-line bg-white" data-testid="notifications-list">
        {d && d.data.length === 0 && <li className="p-5 text-sm text-av-muted" data-testid="notifications-empty">You're all caught up.</li>}
        {(d?.data || []).map((n) => <li key={n.id} className={`flex gap-3 p-4 text-sm ${n.read ? "" : "bg-av-sand/50"}`} data-testid={`notification-${n.id}`}>
          {!n.read && <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-av-clay" />}
          <div className="min-w-0 flex-1"><p className="font-semibold">{n.title}</p><p className="text-av-ink/80">{n.body}</p>
            <p className="text-xs text-av-muted">{new Date(n.created_at).toLocaleString()} · <Link className="underline" to={n.link} onClick={() => read(n)} data-testid={`notification-open-${n.id}`}>Open</Link></p></div></li>)}
      </ul>
      <Preferences />
    </div>
  );
}

const STATUS = { published: "Published", pending_moderation: "Being checked", rejected: "Not published — edit to resubmit", removed: "Removed" };

export function MyReviewsPage() {
  const [d, setD] = useState(null);
  useEffect(() => {
    api.get("/reviews/mine").then((r) => setD(r.data));
  }, []);
  if (!d) return null;
  const rows = [...d.product, ...d.seller];
  return (
    <div className="space-y-4" data-testid="my-reviews-page">
      <h1 className="text-3xl font-bold tracking-tight text-av-ink">My reviews</h1>
      <p className="text-sm text-av-muted">You can review items and rate sellers from each order once it's delivered or collected.</p>
      {rows.length === 0 && <p className="text-sm" data-testid="my-reviews-empty">You haven't written any reviews yet.</p>}
      <ul className="space-y-3">{rows.map((r) => <li key={r.id} className="space-y-1 rounded-2xl border border-av-line bg-white p-4 text-sm" data-testid={`my-review-${r.id}`}>
        <p className="text-xs text-av-muted">{r.kind === "seller" ? `Seller · ${r.vendor_name}` : r.product_title} · <span data-testid={`my-review-status-${r.id}`}>{STATUS[r.status]}</span></p>
        <Stars value={r.rating} /><p className="font-semibold">{r.title}</p><p>{r.comment}</p>
        {r.moderation_note && <p className="text-xs text-av-clay">Reason: {r.moderation_note}. To appeal, <Link className="underline" to="/account/support">contact support</Link>.</p>}
        {r.response && <p className="rounded-lg bg-av-sand p-2 text-xs"><b>Vendor Response:</b> {r.response.body}</p>}</li>)}</ul>
    </div>
  );
}
