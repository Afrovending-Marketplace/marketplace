import { Link, NavLink } from "react-router-dom";
import { User, ShoppingBag } from "lucide-react";
import { BrandLogo } from "@/components/layout/BrandLogo";
import { MobileNav } from "@/components/layout/MobileNav";
import { SearchEntry } from "@/components/layout/SearchEntry";
import { CategoryNav } from "@/components/layout/CategoryNav";
import { SHELL } from "@/constants/testIds";
import { useAuth } from "@/context/AuthContext";
import { cn } from "@/lib/utils";

const iconCls = "relative inline-flex h-10 w-10 items-center justify-center rounded-full text-av-ink hover:bg-av-sand transition-colors";
const textCls = ({ isActive }) =>
  cn("hidden xl:inline-flex rounded-full px-3 py-2 text-sm font-medium transition-colors hover:bg-av-sand", isActive && "bg-av-sand");

export const SiteHeader = () => {
  const { user } = useAuth();
  return (
  <header className="sticky top-0 z-50 border-b border-av-line bg-av-linen/90 backdrop-blur-xl">
    <div className="av-container flex h-16 items-center gap-2 sm:gap-4 lg:h-[72px]">
      <MobileNav />
      <BrandLogo testId={SHELL.brandLogo} />
      <SearchEntry className="hidden md:block flex-1 max-w-xl mx-auto" />
      <div className="ml-auto flex items-center gap-1">
        <NavLink to="/vendors" className={textCls} data-testid={SHELL.navVendors}>Vendors</NavLink>
        <NavLink to="/sell" data-testid={SHELL.navBecomeVendor}
          className="hidden lg:inline-flex rounded-full px-4 py-2 text-sm font-semibold text-av-clay hover:bg-av-clay-light transition-colors">
          Sell on AfroVending
        </NavLink>
        <SearchEntry compact className="md:hidden" />
        <Link to={user ? "/account" : "/login"} aria-label={user ? `Your account (${user.name})` : "Sign in"} data-testid={SHELL.accountButton} className={iconCls}>
          {user ? <span data-testid="header-account-initial" className="grid h-8 w-8 place-items-center rounded-full bg-av-indigo text-sm font-semibold text-av-linen">{user.name[0]?.toUpperCase()}</span> : <User className="h-5 w-5" />}
        </Link>
        <Link to="/cart" aria-label="Cart, 0 items" data-testid={SHELL.cartButton} className={iconCls}>
          <ShoppingBag className="h-5 w-5" />
          <span data-testid={SHELL.cartCount} className="absolute right-0.5 top-0.5 grid h-4 min-w-4 place-items-center rounded-full bg-av-clay px-1 text-[10px] font-bold text-av-linen">0</span>
        </Link>
      </div>
    </div>
    <CategoryNav />
  </header>
  );
};
