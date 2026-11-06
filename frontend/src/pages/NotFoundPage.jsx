import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { PAGES } from "@/constants/testIds";
import { api } from "@/lib/api";

export default function NotFoundPage() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const [checked, setChecked] = useState(false);
  useEffect(() => {
    api.get("/redirects/resolve", { params: { path: pathname } })
      .then((r) => navigate(r.data.to, { replace: true }))
      .catch(() => setChecked(true));
  }, [pathname, navigate]);
  if (!checked) return <div className="av-container py-24" data-testid="legacy-redirect-checking" />;
  return (
    <section data-testid={PAGES.notFound} className="av-container py-24 lg:py-32 grid gap-10 md:grid-cols-12 items-center">
      <p className="md:col-span-5 font-serif text-[8rem] sm:text-[11rem] leading-none text-av-clay/90">404</p>
      <div className="md:col-span-7 space-y-5">
        <div className="kente-strip h-1.5 w-24 rounded-full" aria-hidden="true" />
        <h1 className="text-4xl sm:text-5xl font-bold tracking-tight text-av-ink">This route took a detour.</h1>
        <p className="text-lg text-av-muted">The page you're looking for doesn't exist or has moved.</p>
        <Button asChild data-testid={PAGES.notFoundHome}><Link to="/">Return to home</Link></Button>
      </div>
    </section>
  );
}
