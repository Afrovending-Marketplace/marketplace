import { useState } from "react";
import { Star, Flag, BadgeCheck } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/context/AuthContext";
import { api, getErrorMessage } from "@/lib/api";
import { fileUrl } from "@/components/vendor/FileUpload";

export const Stars = ({ value, size = "h-4 w-4", testId }) => (
  <span className="inline-flex items-center gap-0.5 text-av-gold" aria-label={`${value} out of 5 stars`} data-testid={testId}>
    {[1, 2, 3, 4, 5].map((n) => <Star key={n} className={`${size} ${n <= Math.round(value) ? "fill-current" : "text-av-line"}`} />)}
  </span>
);

export const StarInput = ({ value, onChange, testId }) => (
  <span className="inline-flex gap-1" role="radiogroup" data-testid={testId}>
    {[1, 2, 3, 4, 5].map((n) => (
      <button key={n} type="button" role="radio" aria-checked={value === n} aria-label={`${n} star${n > 1 ? "s" : ""}`} onClick={() => onChange(n)}
        className="transition-transform duration-150 hover:scale-110" data-testid={`${testId}-${n}`}>
        <Star className={`h-6 w-6 ${n <= value ? "fill-av-gold text-av-gold" : "text-av-line"}`} />
      </button>))}
  </span>
);

const ReportButton = ({ kind, id, part }) => {
  const { user } = useAuth();
  const [open, setOpen] = useState(false);
  if (!user) return null;
  const send = async (reason) => {
    try {
      await api.post(`/reviews/${kind}/${id}/report`, { part, reason });
      toast.success("Thanks — our team will take a look");
      setOpen(false);
    } catch (e) {
      toast.error(getErrorMessage(e));
    }
  };
  return open ? (
    <span className="flex flex-wrap gap-1 text-xs" data-testid={`report-options-${part}-${id}`}>
      {["spam", "abuse", "contact_info", "fake", "off_topic"].map((r) => <Button key={r} size="sm" variant="outline" className="h-7" onClick={() => send(r)} data-testid={`report-${part}-${id}-${r}`}>{r.replace("_", " ")}</Button>)}
    </span>
  ) : <button type="button" className="inline-flex items-center gap-1 text-xs text-av-muted hover:text-av-clay" onClick={() => setOpen(true)} data-testid={`report-${part}-${id}`}><Flag className="h-3 w-3" />Report</button>;
};

export const ReviewItem = ({ r }) => (
  <li className="space-y-2 py-4" data-testid={`review-${r.id}`}>
    <div className="flex flex-wrap items-center gap-2 text-sm"><Stars value={r.rating} /><b>{r.title}</b></div>
    {r.comment && <p className="whitespace-pre-line text-sm text-av-ink/85">{r.comment}</p>}
    {r.photos?.length > 0 && <div className="flex gap-2" data-testid={`review-photos-${r.id}`}>{r.photos.map((p) => <img key={p.id} src={fileUrl(p.url)} alt="Customer photo" loading="lazy" className="h-20 w-20 rounded-lg object-cover" />)}</div>}
    <p className="flex flex-wrap items-center gap-2 text-xs text-av-muted">{r.author} · {new Date(r.created_at).toLocaleDateString()}{r.edited && " · edited"}
      <span className="inline-flex items-center gap-1 font-semibold text-av-forest" data-testid={`review-verified-${r.id}`}><BadgeCheck className="h-3.5 w-3.5" />Verified Purchase</span>
      <ReportButton kind={r.kind} id={r.id} part="review" /></p>
    {r.response && <div className="ml-4 rounded-xl border-l-4 border-av-clay bg-av-sand/60 p-3 text-sm" data-testid={`review-response-${r.id}`}>
      <p className="text-xs font-semibold uppercase tracking-wide text-av-clay">Vendor Response</p>
      <p className="whitespace-pre-line">{r.response.body}</p><ReportButton kind={r.kind} id={r.id} part="response" /></div>}
  </li>
);

export const RatingSummary = ({ s, empty, testId }) => (
  <div className="flex flex-wrap items-center gap-6" data-testid={testId}>
    {s.total === 0 ? <p className="text-sm text-av-muted" data-testid={`${testId}-empty`}>{empty}</p> : <>
      <div><p className="text-4xl font-bold" data-testid={`${testId}-average`}>{s.average.toFixed(1)}</p><Stars value={s.average} /><p className="text-xs text-av-muted" data-testid={`${testId}-count`}>{s.total} review{s.total === 1 ? "" : "s"}</p></div>
      <ul className="min-w-[180px] flex-1 space-y-1 text-xs">{Object.entries(s.distribution).sort((a, b) => b[0] - a[0]).map(([k, n]) => (
        <li key={k} className="flex items-center gap-2"><span className="w-6">{k}★</span><span className="h-2 flex-1 overflow-hidden rounded-full bg-av-sand"><span className="block h-full bg-av-gold" style={{ width: `${(n / s.total) * 100}%` }} /></span><span className="w-6 text-right">{n}</span></li>))}</ul></>}
  </div>
);
