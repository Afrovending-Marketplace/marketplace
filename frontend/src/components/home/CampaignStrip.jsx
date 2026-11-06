import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "@/lib/api";

export const CampaignStrip = () => {
  const [rows, setRows] = useState([]);
  useEffect(() => {
    api.get("/campaigns/active").then((r) => setRows(r.data.data)).catch(() => setRows([]));
  }, []);
  if (!rows.length) return null;
  return (
    <section className="av-container space-y-3 py-6" data-testid="homepage-campaigns">
      {rows.map((c) => (
        <div key={c.id} className={`flex flex-wrap items-center justify-between gap-3 rounded-2xl p-6 ${c.placement === "homepage_hero" ? "bg-av-indigo text-av-linen" : "bg-av-sand"}`} data-testid={`campaign-${c.id}`}>
          <div><p className="text-xl font-bold">{c.headline}</p>{c.subtext && <p className="text-sm opacity-80">{c.subtext}</p>}
            {c.coupon_code && <p className="mt-1 text-sm">Use code <b data-testid={`campaign-code-${c.id}`}>{c.coupon_code}</b> at checkout</p>}</div>
          {c.cta_url.startsWith("/") ? <Link to={c.cta_url} className="rounded-full bg-av-clay px-5 py-2 text-sm font-semibold text-white" data-testid={`campaign-cta-${c.id}`}>{c.cta_label}</Link>
            : <a href={c.cta_url} rel="noopener noreferrer" className="rounded-full bg-av-clay px-5 py-2 text-sm font-semibold text-white" data-testid={`campaign-cta-${c.id}`}>{c.cta_label}</a>}
        </div>))}
    </section>
  );
};
