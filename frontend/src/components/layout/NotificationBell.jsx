import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { Bell } from "lucide-react";
import { api } from "@/lib/api";

export const NotificationBell = ({ className }) => {
  const [n, setN] = useState(0);
  const { pathname } = useLocation();
  useEffect(() => {
    const load = () => api.get("/notifications/unread-count").then((r) => setN(r.data.unread)).catch(() => {});
    load();
    const t = setInterval(load, 60000);
    window.addEventListener("av:notifications", load);
    return () => {
      clearInterval(t);
      window.removeEventListener("av:notifications", load);
    };
  }, [pathname]);
  return (
    <Link to="/account/notifications" aria-label={`Notifications, ${n} unread`} className={className} data-testid="header-notifications">
      <Bell className="h-5 w-5" />
      {n > 0 && <span data-testid="header-notifications-count" className="absolute right-0.5 top-0.5 grid h-4 min-w-4 place-items-center rounded-full bg-av-clay px-1 text-[10px] font-bold text-av-linen">{n > 99 ? "99+" : n}</span>}
    </Link>
  );
};
