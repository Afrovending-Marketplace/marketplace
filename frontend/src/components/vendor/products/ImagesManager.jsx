import { useState } from "react";
import { ArrowLeft, ArrowRight, Loader2, Trash2, Upload } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { fileUrl } from "@/components/vendor/FileUpload";
import { api, getErrorMessage } from "@/lib/api";

const MAX = 8;

export const ImagesManager = ({ productId, images, onChange, disabled }) => {
  const [busy, setBusy] = useState("");
  const upload = async (e) => {
    const files = [...(e.target.files || [])].slice(0, MAX - images.length);
    e.target.value = "";
    for (const [i, file] of files.entries()) {
      setBusy(`Optimizing ${i + 1} of ${files.length}…`);
      const form = new FormData();
      form.append("file", file);
      try {
        onChange((await api.post(`/vendor/products/${productId}/images`, form, { timeout: 120000 })).data);
      } catch (err) {
        toast.error(`${file.name}: ${getErrorMessage(err)}`);
      }
    }
    setBusy("");
  };
  const remove = async (img) => {
    try {
      onChange((await api.delete(`/vendor/products/${productId}/images/${img.id}`)).data);
    } catch (err) {
      toast.error(getErrorMessage(err));
    }
  };
  const move = async (i, dir) => {
    const ids = images.map((x) => x.id);
    [ids[i], ids[i + dir]] = [ids[i + dir], ids[i]];
    try {
      onChange((await api.put(`/vendor/products/${productId}/images/order`, { image_ids: ids })).data);
    } catch (err) {
      toast.error(getErrorMessage(err));
    }
  };
  return (
    <div className="space-y-5" data-testid="images-manager">
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        {images.map((img, i) => (
          <figure key={img.id} className="group relative overflow-hidden rounded-xl border border-av-line bg-white" data-testid={`product-image-${i}`}>
            <img src={fileUrl(img.thumb_url)} alt={img.alt} className="aspect-square w-full object-cover" />
            {i === 0 && <span className="absolute left-2 top-2 rounded-full bg-av-ink/80 px-2 py-0.5 text-[10px] font-semibold uppercase text-av-linen">Cover</span>}
            <figcaption className="flex items-center justify-between gap-1 p-2 text-[11px] text-av-muted">
              <span>{img.width}×{img.height} · {Math.round((img.size || 0) / 1024)} KB</span>
              <span className="flex">
                <Button size="icon" variant="ghost" className="h-7 w-7" aria-label="Move left" disabled={disabled || i === 0} onClick={() => move(i, -1)} data-testid={`product-image-${i}-left`}><ArrowLeft /></Button>
                <Button size="icon" variant="ghost" className="h-7 w-7" aria-label="Move right" disabled={disabled || i === images.length - 1} onClick={() => move(i, 1)} data-testid={`product-image-${i}-right`}><ArrowRight /></Button>
                <Button size="icon" variant="ghost" className="h-7 w-7 text-red-700" aria-label="Delete image" disabled={disabled} onClick={() => remove(img)} data-testid={`product-image-${i}-delete`}><Trash2 /></Button>
              </span>
            </figcaption>
          </figure>
        ))}
        {images.length < MAX && (
          <label className={`grid aspect-square cursor-pointer place-items-center rounded-xl border border-dashed border-av-line bg-white text-center text-sm text-av-muted hover:border-av-ink/40 ${disabled ? "pointer-events-none opacity-50" : ""}`}>
            <span className="space-y-2">{busy ? <Loader2 className="mx-auto h-6 w-6 animate-spin" /> : <Upload className="mx-auto h-6 w-6" />}<span className="block px-2">{busy || "Add images"}</span></span>
            <input type="file" multiple accept="image/png,image/jpeg,image/webp" className="sr-only" onChange={upload} disabled={disabled || !!busy} data-testid="product-image-input" aria-label="Upload product images" />
          </label>
        )}
      </div>
      <p className="text-xs text-av-muted">Up to {MAX} images, JPG/PNG/WEBP under 10 MB. Images are resized (max 1600px), converted to WebP and stripped of location data automatically. The first image is the cover.</p>
    </div>
  );
};
