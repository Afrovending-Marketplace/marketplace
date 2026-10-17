import { Link, useLocation } from "react-router-dom";
import { Hammer, ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/common/StatusBadge";
import { routeByPath } from "@/config/site";
import { PAGES } from "@/constants/testIds";

export default function ComingSoonPage() {
  const { pathname } = useLocation();
  const route = routeByPath(pathname);
  return (
    <section data-testid={PAGES.comingSoon} className="mud-pattern">
      <div className="av-container py-24 lg:py-32 max-w-3xl">
        <Hammer className="h-10 w-10 text-av-clay av-rise" />
        <StatusBadge tone="gold" className="mt-6" testId={PAGES.comingSoonPhase}>
          Planned · Phase {route?.phase}
        </StatusBadge>
        <h1 className="mt-4 text-4xl sm:text-5xl lg:text-6xl font-bold tracking-tight text-av-ink">{route?.title}</h1>
        <p className="mt-5 text-lg text-av-muted leading-relaxed">
          We're crafting this part of AfroVending ({route?.module}). It will open when its development phase is
          completed and approved.
        </p>
        <Button asChild variant="outline" className="mt-10" data-testid={PAGES.comingSoonHome}>
          <Link to="/"><ArrowLeft /> Back to home</Link>
        </Button>
      </div>
    </section>
  );
}
