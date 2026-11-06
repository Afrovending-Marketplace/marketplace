import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { captureReferral, getConsent, initAnalytics, setConsent, track } from "@/lib/analytics";

export const CookieConsent = () => {
  const [show, setShow] = useState(!getConsent());
  const [manage, setManage] = useState(false);
  const [c, setC] = useState({ analytics: false, marketing: false });
  useEffect(() => {
    const open = () => setShow(true);
    window.addEventListener("av:open-consent", open);
    return () => window.removeEventListener("av:open-consent", open);
  }, []);
  if (!show) return null;
  const save = (v) => {
    setConsent(v);
    setShow(false);
  };
  return (
    <div role="dialog" aria-label="Cookie preferences" className="fixed inset-x-3 bottom-3 z-50 mx-auto max-w-2xl rounded-2xl border border-av-line bg-white p-5 shadow-xl" data-testid="cookie-consent">
      <p className="text-sm font-semibold">Cookies on AfroVending</p>
      <p className="mt-1 text-sm text-av-ink/80">We use essential cookies to run the site. With your OK we also use analytics cookies to understand what shoppers look for. <Link to="/privacy" className="underline" data-testid="cookie-privacy-link">Privacy policy</Link></p>
      {manage && <div className="mt-3 space-y-2 text-sm" data-testid="cookie-manage">
        <label className="flex items-center justify-between">Essential (always on)<Switch checked disabled /></label>
        <label className="flex items-center justify-between">Analytics<Switch checked={c.analytics} onCheckedChange={(v) => setC({ ...c, analytics: v })} data-testid="cookie-analytics-switch" /></label>
        <label className="flex items-center justify-between">Marketing<Switch checked={c.marketing} onCheckedChange={(v) => setC({ ...c, marketing: v })} data-testid="cookie-marketing-switch" /></label>
      </div>}
      <div className="mt-4 flex flex-wrap gap-2">
        <Button size="sm" onClick={() => save({ analytics: true, marketing: true })} data-testid="cookie-accept">Accept all</Button>
        <Button size="sm" variant="outline" onClick={() => save({ analytics: false, marketing: false })} data-testid="cookie-reject">Reject optional</Button>
        {manage ? <Button size="sm" variant="ghost" onClick={() => save(c)} data-testid="cookie-save">Save choices</Button>
          : <Button size="sm" variant="ghost" onClick={() => setManage(true)} data-testid="cookie-manage-open">Manage preferences</Button>}
      </div>
    </div>
  );
};

export const RouteTracker = () => {
  const { pathname, search } = useLocation();
  useEffect(() => {
    initAnalytics();
  }, []);
  useEffect(() => {
    track("page_view");
    captureReferral(search);
  }, [pathname, search]);
  return null;
};
