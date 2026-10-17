import { Link } from "react-router-dom";
import { ShieldAlert, LayoutDashboard } from "lucide-react";
import { Button } from "@/components/ui/button";

const Panel = ({ icon: Icon, title, text, testId }) => (
  <section data-testid={testId} className="av-container max-w-2xl py-24 text-center">
    <Icon className="mx-auto h-10 w-10 text-av-clay" />
    <h1 className="mt-5 text-4xl sm:text-5xl font-bold tracking-tight text-av-ink">{title}</h1>
    <p className="mt-4 text-av-muted">{text}</p>
    <Button asChild variant="outline" className="mt-8"><Link to="/">Back to home</Link></Button>
  </section>
);

export const AdminConsolePage = () => (
  <div>
    <Panel testId="admin-console-page" icon={LayoutDashboard} title="Admin console"
      text="The full administration dashboard is built in Phase 10. Vendor review is available now." />
    <div className="-mt-16 pb-16 text-center"><Button asChild data-testid="admin-vendors-link"><Link to="/admin/vendors">Vendor applications & vendors</Link></Button></div>
  </div>
);

export const ForbiddenPage = () => (
  <Panel testId="forbidden-page" icon={ShieldAlert} title="Access denied" text="Your account doesn't have permission to view this page." />
);
