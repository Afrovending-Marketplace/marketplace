import { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Heart, Copy, Share2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { useAuth } from "@/context/AuthContext";
import { api, getErrorMessage } from "@/lib/api";
import { formatPrice } from "@/lib/catalog";

export const WishlistButton = ({ slug }) => {
  const { user } = useAuth();
  const [on, setOn] = useState(false);
  useEffect(() => {
    if (user) api.get("/wishlist").then((r) => setOn(r.data.slugs.includes(slug))).catch(() => {});
  }, [user, slug]);
  if (!user) return <Button asChild variant="outline" size="sm" data-testid="wishlist-signin"><Link to="/login"><Heart className="mr-1 h-4 w-4" />Save to wishlist</Link></Button>;
  const toggle = async () => {
    try {
      await (on ? api.delete(`/wishlist/${slug}`) : api.put(`/wishlist/${slug}`));
      setOn(!on);
      toast.success(on ? "Removed from wishlist" : "Saved to your wishlist");
    } catch (e) {
      toast.error(getErrorMessage(e));
    }
  };
  return <Button variant="outline" size="sm" onClick={toggle} aria-pressed={on} data-testid="wishlist-toggle"><Heart className={`mr-1 h-4 w-4 ${on ? "fill-av-clay text-av-clay" : ""}`} />{on ? "Saved" : "Save to wishlist"}</Button>;
};

function PriceDrop({ d, slug }) {
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs" data-testid={`wishlist-price-drop-${slug}`}>
      <span className="rounded-full bg-av-clay px-2 py-0.5 font-semibold text-white" data-testid={`wishlist-price-drop-badge-${slug}`}>Price dropped {d.percent}%</span>
      <span className="text-av-muted line-through" data-testid={`wishlist-price-previous-${slug}`}>{formatPrice(d.previous_minor)}</span>
      <span className="font-semibold text-av-ink" data-testid={`wishlist-price-current-${slug}`}>{formatPrice(d.current_minor)}</span>
    </div>
  );
}

export function WishlistPage() {
  const [d, setD] = useState(null);
  const load = useCallback(() => api.get("/wishlist").then((r) => setD(r.data)), []);
  useEffect(() => {
    load();
  }, [load]);
  if (!d) return null;
  return (
    <div className="space-y-4" data-testid="wishlist-page">
      <h1 className="text-3xl font-bold tracking-tight text-av-ink">Wishlist</h1>
      {d.data.length === 0 && <p className="text-sm text-av-muted" data-testid="wishlist-empty">Nothing saved yet. Tap “Save to wishlist” on any product.</p>}
      <ul className="grid gap-3 sm:grid-cols-2">{d.data.map((p) => <li key={p.slug} className="flex items-center justify-between gap-2 rounded-2xl border border-av-line bg-white p-4 text-sm" data-testid={`wishlist-item-${p.slug}`}>
        <div className="min-w-0 space-y-1">
          <Link to={`/products/${p.slug}`} className="font-semibold hover:underline">{p.title}</Link>
          {p.price_drop ? <PriceDrop d={p.price_drop} slug={p.slug} /> : (p.current_minor != null && <p className="text-xs font-semibold text-av-ink" data-testid={`wishlist-price-${p.slug}`}>{formatPrice(p.current_minor)}</p>)}
          {!p.in_stock && <span className="inline-block rounded-full bg-av-line px-2 py-0.5 text-xs font-semibold text-av-muted" data-testid={`wishlist-out-of-stock-${p.slug}`}>Out of stock</span>}
        </div>
        <Button size="sm" variant="ghost" onClick={() => api.delete(`/wishlist/${p.slug}`).then(load)} data-testid={`wishlist-remove-${p.slug}`}>Remove</Button></li>)}</ul>
    </div>
  );
}

export function ReferralsPage() {
  const [d, setD] = useState(null);
  useEffect(() => {
    api.get("/referrals/me").then((r) => setD(r.data));
  }, []);
  if (!d) return null;
  const copy = () => navigator.clipboard?.writeText(d.link).then(() => toast.success("Link copied"));
  const text = encodeURIComponent("I shop African fashion, beauty and food on AfroVending — take a look:");
  return (
    <div className="space-y-5" data-testid="referrals-page">
      <h1 className="text-3xl font-bold tracking-tight text-av-ink">Invite friends</h1>
      <p className="text-sm text-av-muted">Share your personal link. We'll show you when friends join and place their first order.</p>
      <div className="flex flex-wrap items-center gap-2 rounded-2xl border border-av-line bg-white p-4"><code className="break-all text-sm" data-testid="referral-link">{d.link}</code>
        <Button size="sm" variant="outline" onClick={copy} data-testid="referral-copy"><Copy className="mr-1 h-4 w-4" />Copy</Button>
        <Button asChild size="sm" variant="outline"><a href={`https://wa.me/?text=${text}%20${encodeURIComponent(d.link)}`} target="_blank" rel="noopener noreferrer" data-testid="referral-share-whatsapp"><Share2 className="mr-1 h-4 w-4" />WhatsApp</a></Button>
        <Button asChild size="sm" variant="outline"><a href={`mailto:?subject=AfroVending&body=${text}%20${encodeURIComponent(d.link)}`} data-testid="referral-share-email">Email</a></Button>
        <Button asChild size="sm" variant="outline"><a href={`https://www.facebook.com/sharer/sharer.php?u=${encodeURIComponent(d.link)}`} target="_blank" rel="noopener noreferrer" data-testid="referral-share-facebook">Facebook</a></Button></div>
      <div className="grid gap-3 sm:grid-cols-3">{[["Link visits", d.visits, "visits"], ["Friends joined", d.signups, "signups"], ["First orders", d.first_orders, "orders"]].map(([l, v, k]) =>
        <div key={k} className="rounded-2xl bg-white p-4"><p className="text-xs text-av-muted">{l}</p><p className="text-2xl font-bold" data-testid={`referral-${k}`}>{v}</p></div>)}</div>
      <ul className="divide-y divide-av-line rounded-2xl border border-av-line bg-white text-sm" data-testid="referral-activity">
        {d.activity.length === 0 && <li className="p-4 text-av-muted">No referrals yet.</li>}
        {d.activity.map((a) => <li key={a.label} className="flex justify-between p-4"><span>{a.label}</span><span>{a.status === "converted" ? "Placed first order" : "Joined"}</span></li>)}</ul>
    </div>
  );
}

export const MarketingConsent = () => {
  const [v, setV] = useState(null);
  const [wa, setWa] = useState({});
  useEffect(() => {
    api.get("/account/marketing").then((r) => {
      setV(r.data.marketing_opt_in);
      setWa({ wishlist_price_drop: r.data.wishlist_price_drop, wishlist_back_in_stock: r.data.wishlist_back_in_stock });
    });
  }, []);
  if (v === null) return null;
  const setAlert = (k, on) => api.put("/account/marketing", { marketing_opt_in: v, [k]: on }).then(() => setWa({ ...wa, [k]: on }));
  const change = (on) => api.put("/account/marketing", { marketing_opt_in: on }).then(() => {
    setV(on);
    toast.success(on ? "You're subscribed to AfroVending offers" : "You've been unsubscribed from marketing emails");
  });
  return (
    <section className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-av-line bg-white p-5 text-sm" data-testid="marketing-consent">
      <div><p className="font-semibold">Offers & cart reminders by email</p><p className="text-xs text-av-muted">New campaigns, coupons and reminders about items left in your cart. Unsubscribe any time.</p></div>
      <Switch checked={v} onCheckedChange={change} data-testid="marketing-consent-switch" />
      {v && <div className="w-full space-y-2 border-t border-av-line pt-3 text-xs">
        <label className="flex items-center justify-between">Wishlist price drops (5% or more)<Switch checked={wa.wishlist_price_drop} onCheckedChange={(on) => setAlert("wishlist_price_drop", on)} data-testid="wishlist-alert-price" /></label>
        <label className="flex items-center justify-between">Wishlist items back in stock<Switch checked={wa.wishlist_back_in_stock} onCheckedChange={(on) => setAlert("wishlist_back_in_stock", on)} data-testid="wishlist-alert-stock" /></label></div>}
    </section>
  );
};

export function UnsubscribePage() {
  const [params] = useSearchParams();
  const [state, setState] = useState("working");
  useEffect(() => {
    api.post("/marketing/unsubscribe", { token: params.get("token") || "" }).then(() => setState("done")).catch(() => setState("invalid"));
  }, [params]);
  return (
    <div className="av-container max-w-lg py-16 text-center" data-testid="unsubscribe-page">
      <h1 className="text-3xl font-bold text-av-ink">Email preferences</h1>
      <p className="mt-3" data-testid={`unsubscribe-${state}`}>{state === "done" ? "You've been unsubscribed from AfroVending marketing emails. Order and account emails will still arrive." : state === "invalid" ? "This unsubscribe link isn't valid. You can change email preferences in your account." : "Updating your preferences…"}</p>
    </div>
  );
}
