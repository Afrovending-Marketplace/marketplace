import { useState } from "react";
import { Link } from "react-router-dom";
import { Package, Heart, MapPin, MailWarning } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/context/AuthContext";
import { api, getErrorMessage } from "@/lib/api";

const Panel = ({ icon: Icon, title, children, testId }) => (
  <section data-testid={testId} className="rounded-2xl border border-av-line bg-white p-6">
    <div className="flex items-center gap-2"><Icon className="h-5 w-5 text-av-clay" /><h2 className="font-sans text-lg font-semibold text-av-ink">{title}</h2></div>
    <div className="mt-4 text-sm text-av-muted">{children}</div>
  </section>
);

const VerifyBanner = () => {
  const [busy, setBusy] = useState(false);
  const resend = async () => {
    setBusy(true);
    try {
      await api.post("/auth/resend-verification");
      toast.success("Verification email sent. Check your inbox.");
    } catch (err) {
      toast.error(getErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div data-testid="verify-email-banner" className="flex flex-col gap-3 rounded-2xl border border-av-gold/40 bg-av-gold-light p-5 sm:flex-row sm:items-center sm:justify-between">
      <p className="flex items-start gap-2 text-sm text-av-gold-deep"><MailWarning className="mt-0.5 h-4 w-4 shrink-0" />Please verify your email address to secure your account.</p>
      <Button variant="outline" size="sm" onClick={resend} disabled={busy} data-testid="resend-verification-button">Resend email</Button>
    </div>
  );
};

export default function AccountOverview() {
  const { user } = useAuth();
  return (
    <div className="space-y-6" data-testid="account-overview">
      {!user.email_verified && <VerifyBanner />}
      <div className="grid gap-6 md:grid-cols-2">
        <Panel icon={Package} title="Orders" testId="account-orders-section">
          <p>You have no orders yet. Order history and tracking arrive with checkout (Phase 06) and order management (Phase 08).</p>
          <Button asChild variant="outline" size="sm" className="mt-4"><Link to="/shop">Start shopping</Link></Button>
        </Panel>
        <Panel icon={Heart} title="Wishlist" testId="account-wishlist-section">
          <p>Items you save appear in your <Link to="/account/wishlist" className="font-semibold text-av-clay hover:underline" data-testid="account-wishlist-link">wishlist</Link>, with current prices, stock and price drops.</p>
        </Panel>
        <Panel icon={MapPin} title="Addresses" testId="account-addresses-summary">
          <p>Manage the delivery addresses you'll use at checkout.</p>
          <Button asChild variant="outline" size="sm" className="mt-4"><Link to="/account/addresses" data-testid="overview-addresses-link">Manage addresses</Link></Button>
        </Panel>
        <Panel icon={MailWarning} title="Account details" testId="account-details-summary">
          <p data-testid="account-email">{user.email}</p>
          <p className="mt-1">Status: <span data-testid="account-status" className="font-semibold text-av-ink">{user.email_verified ? "Verified" : "Awaiting email verification"}</span></p>
        </Panel>
      </div>
    </div>
  );
}
