import { Navigate, Outlet, useLocation } from "react-router-dom";
import { Loader2 } from "lucide-react";
import { useAuth } from "@/context/AuthContext";

export const ProtectedRoute = ({ roles }) => {
  const { user } = useAuth();
  const location = useLocation();
  if (user === null) {
    return (
      <div data-testid="auth-loading" className="grid min-h-[50vh] place-items-center text-av-muted">
        <Loader2 className="h-6 w-6 animate-spin" aria-label="Loading" />
      </div>
    );
  }
  if (!user) return <Navigate to={`/login?next=${encodeURIComponent(location.pathname)}`} replace />;
  if (roles && !roles.some((r) => user.roles.includes(r))) return <Navigate to="/forbidden" replace />;
  return <Outlet />;
};
