import { Link, NavLink } from "react-router-dom";
import { Search, User, ShoppingBag } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { BrandLogo } from "@/components/layout/BrandLogo";
import { MobileNav } from "@/components/layout/MobileNav";
import { NAV_LINKS } from "@/config/site";
import { SHELL } from "@/constants/testIds";
import { cn } from "@/lib/utils";

const ACTIONS = [
  { icon: Search, label: "Search the marketplace", testId: SHELL.searchButton, note: "Search arrives in Phase 05." },
  { icon: User, label: "Your account", testId: SHELL.accountButton, note: "Accounts arrive in Phase 01." },
  { icon: ShoppingBag, label: "Cart", testId: SHELL.cartButton, note: "Cart and checkout arrive in Phase 06." },
];

const navClass = ({ isActive }, highlight) =>
  cn(
    "px-3 py-2 rounded-full text-sm font-medium transition-colors duration-200",
    highlight ? "text-av-clay hover:bg-av-clay-light" : "text-av-ink/80 hover:text-av-ink hover:bg-av-sand",
    isActive && "bg-av-sand text-av-ink"
  );

export const SiteHeader = () => (
  <header className="sticky top-0 z-50 border-b border-av-line bg-av-linen/85 backdrop-blur-xl">
    <div className="kente-strip h-1" aria-hidden="true" />
    <div className="av-container flex h-16 items-center justify-between gap-4 lg:h-20">
      <div className="flex items-center gap-2">
        <MobileNav />
        <BrandLogo testId={SHELL.brandLogo} />
      </div>
      <nav aria-label="Primary" className="hidden lg:flex items-center gap-1">
        {NAV_LINKS.map((l) => (
          <NavLink key={l.path} to={l.path} data-testid={l.testId} className={(s) => navClass(s, l.highlight)}>
            {l.label}
          </NavLink>
        ))}
      </nav>
      <div className="flex items-center gap-1">
        {ACTIONS.map(({ icon: Icon, label, testId, note }) => (
          <Button key={testId} variant="ghost" size="icon" aria-label={label} title={label}
            data-testid={testId} onClick={() => toast(label, { description: note })}>
            <Icon className="!size-5" />
          </Button>
        ))}
      </div>
    </div>
  </header>
);
