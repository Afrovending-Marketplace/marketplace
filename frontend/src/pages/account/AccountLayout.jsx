import { NavLink, Outlet } from "react-router-dom";
import { LayoutDashboard, User, MapPin, ShieldCheck, LogOut } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { cn } from "@/lib/utils";

const LINKS = [
  ["/account", "Overview", LayoutDashboard, "overview"],
  ["/account/profile", "Profile & password", User, "profile"],
  ["/account/addresses", "Address book", MapPin, "addresses"],
  ["/account/privacy", "Privacy & account", ShieldCheck, "privacy"],
];

export default function AccountLayout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const signOut = async () => {
    await logout();
    navigate("/", { replace: true });
  };
  return (
    <div data-testid="account-layout" className="av-container py-10 lg:py-14">
      <p className="av-eyebrow">My account</p>
      <h1 className="mt-2 text-3xl sm:text-4xl lg:text-5xl font-bold tracking-tight text-av-ink">Hello, {user.name.split(" ")[0]}</h1>
      <div className="mt-8 grid gap-8 lg:grid-cols-[240px_1fr]">
        <nav aria-label="Account" className="flex gap-2 overflow-x-auto lg:flex-col [scrollbar-width:none]">
          {LINKS.map(([to, label, Icon, id]) => (
            <NavLink key={to} to={to} end data-testid={`account-nav-${id}`}
              className={({ isActive }) => cn("flex shrink-0 items-center gap-2 whitespace-nowrap rounded-full px-4 py-2.5 text-sm transition-colors",
                isActive ? "bg-av-ink text-av-linen" : "text-av-ink/80 hover:bg-av-sand")}>
              <Icon className="h-4 w-4" />{label}
            </NavLink>
          ))}
          <button type="button" onClick={signOut} data-testid="logout-button"
            className="flex shrink-0 items-center gap-2 whitespace-nowrap rounded-full px-4 py-2.5 text-sm text-av-clay hover:bg-av-clay-light">
            <LogOut className="h-4 w-4" />Sign out
          </button>
        </nav>
        <div className="min-w-0"><Outlet /></div>
      </div>
    </div>
  );
}
