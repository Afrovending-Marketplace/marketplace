import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useAuth } from "@/context/AuthContext";
import { api, getErrorMessage } from "@/lib/api";

// Shown after sign-in when a material policy update needs explicit acceptance. No pre-ticked box; closing it doesn't count as acceptance.
export const PolicyAcceptancePrompt = () => {
  const { user } = useAuth();
  const [pending, setPending] = useState([]);
  const [open, setOpen] = useState(false);
  const [checked, setChecked] = useState(false);
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => {
    api.get("/account/policy-status").then((r) => { setPending(r.data.pending); setOpen(r.data.pending.length > 0); setChecked(false); }).catch(() => {});
  }, []);
  useEffect(() => { if (user) load(); }, [user, load]);
  useEffect(() => {
    const h = () => load();
    window.addEventListener("av:policy-required", h);
    return () => window.removeEventListener("av:policy-required", h);
  }, [load]);
  if (!user || !pending.length) return null;
  const accept = async () => {
    setBusy(true);
    try {
      const r = await api.post("/account/policy-acceptances", { version_ids: pending.map((p) => p.version_id), accept: true });
      setPending(r.data.pending);
      setOpen(false);
      toast.success("Thanks — your acceptance has been recorded.");
    } catch (e) {
      toast.error(getErrorMessage(e));
      load();
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      {!open && (
        <button type="button" onClick={() => setOpen(true)} className="fixed bottom-4 left-4 z-40 rounded-full bg-av-clay px-4 py-2 text-sm text-white shadow-lg" data-testid="policy-review-reopen">
          Review updated policies
        </button>
      )}
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent data-testid="policy-acceptance-dialog">
          <DialogHeader>
            <DialogTitle>We've updated our policies</DialogTitle>
            <DialogDescription>Please review the changes. You can keep browsing, but you'll need to accept before your next purchase or selling activity.</DialogDescription>
          </DialogHeader>
          <ul className="space-y-3 text-sm">
            {pending.map((p) => (
              <li key={p.version_id} className="rounded-xl bg-av-sand p-3" data-testid={`policy-pending-${p.slug}`}>
                <Link to={p.path} target="_blank" className="font-semibold text-av-clay underline">{p.title} (version {p.version})</Link>
                {p.change_summary && <p className="mt-1 text-av-ink/80">{p.change_summary}</p>}
              </li>
            ))}
          </ul>
          <label className="flex items-start gap-2 text-sm">
            <input type="checkbox" className="mt-1" checked={checked} onChange={(e) => setChecked(e.target.checked)} data-testid="policy-accept-checkbox" />
            <span>I have read and accept the updated {pending.map((p) => p.title).join(", ")}.</span>
          </label>
          <Button onClick={accept} disabled={!checked || busy} data-testid="policy-accept-button">{busy ? "Saving…" : "Accept and continue"}</Button>
        </DialogContent>
      </Dialog>
    </>
  );
};
