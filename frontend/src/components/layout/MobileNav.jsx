import { useState } from "react";
import { NavLink } from "react-router-dom";
import { Menu, ChevronRight } from "lucide-react";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { BrandLogo } from "@/components/layout/BrandLogo";
import { NAV_LINKS, COMPANY_LINKS } from "@/config/site";
import { getCategories } from "@/lib/catalog";
import { SHELL } from "@/constants/testIds";

const Group = ({ title, links, close, large }) => (
  <div className="mt-6">
    <p className="av-eyebrow mb-2">{title}</p>
    <ul>
      {links.map((l) => (
        <li key={l.path}>
          <NavLink to={l.path} onClick={close} data-testid={`mobile-nav-${l.path.replace(/\//g, "-").slice(1)}`}
            className={`flex items-center justify-between border-b border-av-line py-3 text-av-ink hover:text-av-clay transition-colors ${large ? "font-serif text-xl" : "text-base"}`}>
            {l.label}<ChevronRight className="h-4 w-4 text-av-muted" />
          </NavLink>
        </li>
      ))}
    </ul>
  </div>
);

export const MobileNav = () => {
  const [open, setOpen] = useState(false);
  const close = () => setOpen(false);
  const categories = getCategories().map((c) => ({ label: c.name, path: `/categories/${c.slug}` }));
  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <Button variant="ghost" size="icon" className="lg:hidden" aria-label="Open menu" data-testid={SHELL.mobileMenuButton}>
          <Menu className="!size-5" />
        </Button>
      </SheetTrigger>
      <SheetContent side="left" className="w-[88vw] max-w-sm overflow-y-auto bg-av-linen" data-testid={SHELL.mobileMenu}>
        <SheetHeader className="text-left">
          <SheetTitle asChild><div><BrandLogo testId="mobile-menu-brand-logo" /></div></SheetTitle>
          <SheetDescription className="sr-only">Main navigation</SheetDescription>
        </SheetHeader>
        <div className="kente-strip mt-6 h-1 rounded-full" aria-hidden="true" />
        <Group title="Marketplace" links={NAV_LINKS} close={close} large />
        <Group title="Categories" links={categories} close={close} />
        <Group title="Company" links={COMPANY_LINKS} close={close} />
      </SheetContent>
    </Sheet>
  );
};
