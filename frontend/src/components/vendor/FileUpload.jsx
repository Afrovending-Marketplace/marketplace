import { useState } from "react";
import { Upload, Loader2 } from "lucide-react";
import { api, getErrorMessage } from "@/lib/api";

export const fileUrl = (path) => (path ? `${process.env.REACT_APP_BACKEND_URL}${path}` : null);

export const uploadFile = async (file, purpose) => {
  const form = new FormData();
  form.append("purpose", purpose);
  form.append("file", file);
  return (await api.post("/files", form)).data;
};

export const ImageUpload = ({ label, purpose, fileId, onChange, testId, accept = "image/png,image/jpeg,image/webp" }) => {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [preview, setPreview] = useState(fileId ? fileUrl(`/api/v1/files/${fileId}`) : null);
  const onFile = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setBusy(true);
    setError("");
    try {
      const res = await uploadFile(file, purpose);
      setPreview(res.url ? fileUrl(res.url) : null);
      onChange(res);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="space-y-2">
      <p className="text-sm font-medium text-av-ink">{label}</p>
      <label className="flex cursor-pointer items-center gap-3 rounded-xl border border-dashed border-av-line bg-white p-3 hover:border-av-ink/40">
        {preview ? <img src={preview} alt="" className="h-14 w-14 rounded-lg object-cover" /> : <span className="grid h-14 w-14 place-items-center rounded-lg bg-av-sand">{busy ? <Loader2 className="h-5 w-5 animate-spin" /> : <Upload className="h-5 w-5" />}</span>}
        <span className="text-sm text-av-muted">{busy ? "Uploading…" : "Choose file"}</span>
        <input type="file" accept={accept} className="sr-only" onChange={onFile} data-testid={testId} aria-label={label} />
      </label>
      {error && <p className="text-xs text-red-700" data-testid={`${testId}-error`}>{error}</p>}
    </div>
  );
};
