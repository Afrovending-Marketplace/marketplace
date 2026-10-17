import { NavLink } from "react-router-dom";
import { getCategories } from "@/lib/catalog";
import { SHELL } from "@/constants/testIds";
import { cn } from "@/lib/utils";

const linkCls = ({ isActive }) =>
  cn("shrink-0 whitespace-nowrap rounded-full px-3 py-1.5 text-sm transition-colors duration-200",
    isActive ? "bg-av-ink text-av-linen" : "text-av-ink/75 hover:bg-av-sand hover:text-av-ink");

export const CategoryNav = () => (
  <nav aria-label="Categories" data-testid={SHELL.categoryNav} className="border-t border-av-line/70">
    <ul className="av-container flex items-center gap-1 overflow-x-auto py-2 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
      <li><NavLink to="/shop" end className={linkCls} data-testid={SHELL.navShop}>Shop all</NavLink></li>
      {getCategories().map((c) => (
        <li key={c.slug}>
          <NavLink to={`/categories/${c.slug}`} className={linkCls} data-testid={`category-nav-${c.slug}`}>{c.name}</NavLink>
        </li>
      ))}
      <li className="xl:hidden"><NavLink to="/vendors" className={linkCls} data-testid="category-nav-vendors">Vendors</NavLink></li>
    </ul>
  </nav>
);
