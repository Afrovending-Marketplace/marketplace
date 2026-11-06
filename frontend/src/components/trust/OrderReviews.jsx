import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { StarInput, Stars } from "@/components/trust/Reviews";
import { api, getErrorMessage } from "@/lib/api";
import { uploadFile } from "@/components/vendor/FileUpload";

const STATUS = { published: "Published", pending_moderation: "Being checked by AfroVending", rejected: "Not published", removed: "Removed" };

export const ReviewForm = ({ url, existing, label, testId, onSaved, showPhotos }) => {
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ rating: existing?.rating || 0, title: existing?.title || "", comment: existing?.comment || "", photo_file_ids: (existing?.photos || []).map((p) => p.id) });
  const [uploading, setUploading] = useState(false);
  const addPhoto = async (file) => {
    if (!file || f.photo_file_ids.length >= 3) return;
    setUploading(true);
    try {
      const doc = await uploadFile(file, "review_photo");
      setF((x) => ({ ...x, photo_file_ids: [...x.photo_file_ids, doc.id] }));
      toast.success("Photo added — it will appear once AfroVending approves it");
    } catch (e) {
      toast.error(getErrorMessage(e));
    } finally {
      setUploading(false);
    }
  };
  const save = async () => {
    try {
      const r = await api.put(url, f);
      toast.success(r.data.review.status === "published" ? "Review published — thank you!" : "Thanks! Your review is being checked before it goes live.");
      setOpen(false);
      onSaved();
    } catch (e) {
      toast.error(getErrorMessage(e));
    }
  };
  if (!open) return (
    <div className="flex flex-wrap items-center gap-2 text-xs" data-testid={testId}>
      {existing && <><Stars value={existing.rating} /><span data-testid={`${testId}-status`}>{STATUS[existing.status]}</span>
        {existing.moderation_note && <span className="text-av-clay">· {existing.moderation_note}</span>}</>}
      {existing?.status !== "removed" && <Button size="sm" variant="outline" className="h-7" onClick={() => setOpen(true)} data-testid={`${testId}-open`}>{existing ? "Edit" : label}</Button>}
    </div>
  );
  return (
    <div className="space-y-2 rounded-xl bg-av-sand p-3" data-testid={`${testId}-form`}>
      <StarInput value={f.rating} onChange={(rating) => setF({ ...f, rating })} testId={`${testId}-stars`} />
      <Input className="bg-white" placeholder="Headline (optional)" maxLength={120} value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} data-testid={`${testId}-title`} />
      <Textarea className="bg-white" placeholder="What did you think? (optional)" maxLength={3000} value={f.comment} onChange={(e) => setF({ ...f, comment: e.target.value })} data-testid={`${testId}-comment`} />
      <p className="text-[11px] text-av-muted">Honest opinions — good or bad — are welcome. Please leave out phone numbers, emails and links.</p>
      {showPhotos && <div className="flex flex-wrap items-center gap-2 text-xs" data-testid={`${testId}-photos`}>
        <span>{f.photo_file_ids.length}/3 photos (checked by AfroVending before they appear)</span>
        {f.photo_file_ids.length < 3 && <label className="cursor-pointer rounded-full border border-av-line bg-white px-3 py-1">{uploading ? "Uploading…" : "Add photo"}
          <input type="file" accept="image/jpeg,image/png,image/webp" className="hidden" onChange={(e) => { addPhoto(e.target.files?.[0]); e.target.value = ""; }} data-testid={`${testId}-photo-input`} /></label>}
        {f.photo_file_ids.length > 0 && <button type="button" className="underline" onClick={() => setF({ ...f, photo_file_ids: [] })} data-testid={`${testId}-photos-clear`}>Remove photos</button>}</div>}
      <div className="flex gap-2"><Button size="sm" disabled={!f.rating} onClick={save} data-testid={`${testId}-submit`}>Submit</Button>
        <Button size="sm" variant="ghost" onClick={() => setOpen(false)}>Cancel</Button></div>
    </div>
  );
};

export const OrderReviews = ({ vo, status, reload }) => {
  if (!status) return null;
  const items = vo.items.filter((i) => status.items[i.id]?.eligible || status.items[i.id]?.review);
  if (!items.length && !status.seller_eligible) return null;
  return (
    <div className="space-y-2 rounded-xl border border-av-line p-3" data-testid={`order-reviews-${vo.vendor_slug}`}>
      <p className="text-xs font-semibold uppercase tracking-wide text-av-muted">Reviews</p>
      {items.map((i) => <div key={i.id} className="flex flex-wrap items-center justify-between gap-2"><span>{i.title}</span>
        <ReviewForm url={`/reviews/items/${i.id}`} existing={status.items[i.id].review} label="Review this item" testId={`review-item-${i.sku}`} onSaved={reload} showPhotos /></div>)}
      {status.seller_eligible && <div className="flex flex-wrap items-center justify-between gap-2 border-t border-av-line pt-2"><span>Seller service · {vo.vendor_name}</span>
        <ReviewForm url={`/reviews/sellers/${vo.id}`} existing={status.seller_rating} label="Rate this seller" testId={`review-seller-${vo.vendor_slug}`} onSaved={reload} /></div>}
    </div>
  );
};
