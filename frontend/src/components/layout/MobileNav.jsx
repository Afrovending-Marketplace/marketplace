import { useState } from "react";
import { NavLink } from "react-router-dom";
import { Menu, ChevronRight } from "lucide-react";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { BrandLogo } from "@/components/layout/BrandLogo";
import { NAV_LINKS } from "@/config/site";
import { SHELL } from "@/constants/testIds";

export const MobileNav = () => {
  const [open, setOpen] = useState(false);
  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <Button variant="ghost" size="icon" className="lg:hidden" aria-label="Open menu" data-testid={SHELL.mobileMenuButton}>
          <Menu className="!size-5" />
        </Button>
      </SheetTrigger>
      <SheetContent side="left" className="bg-av-linen w-[85vw] max-w-sm" data-testid={SHELL.mobileMenu}>
        <SheetHeader className="text-left">
          <SheetTitle asChild><div><BrandLogo testId="mobile-menu-brand-logo" /></div></SheetTitle>
        </SheetHeader>
        <div className="kente-strip h-1 my-6 rounded-full" aria-hidden="true" />
        <nav aria-label="Mobile" className="flex flex-col">
          {NAV_LINKS.map((l) => (
            <NavLink key={l.path} to={l.path} onClick={() => setOpen(false)} data-testid={`mobile-${l.testId}`}
              className="flex items-center justify-between border-b border-av-line py-4 font-serif text-xl text-av-ink hover:text-av-clay transition-colors">
              {l.label}
              <ChevronRight className="h-5 w-5 text-av-muted" />
            </NavLink>
          ))}
        </nav>
      </SheetContent>
    </Sheet>
  );
};
