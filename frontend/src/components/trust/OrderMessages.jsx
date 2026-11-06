import { useCallback, useEffect, useState } from "react";
import { MessageCircle, ShieldAlert } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { api, getErrorMessage } from "@/lib/api";

export const OrderMessages = ({ path, testId, unread = 0 }) => {
  const [open, setOpen] = useState(false);
  const [t, setT] = useState(null);
  const [body, setBody] = useState("");
  const load = useCallback(() => api.get(path).then((r) => setT(r.data)).catch((e) => toast.error(getErrorMessage(e))), [path]);
  useEffect(() => {
    if (open) {
      load();
    }
  }, [open, load]);
  const send = async () => {
    try {
      const r = await api.post(path, { body });
      setBody("");
      if (r.data.message.notice) toast.warning(r.data.message.notice);
      load();
    } catch (e) {
      toast.error(getErrorMessage(e));
    }
  };
  if (!open) return <Button size="sm" variant="outline" onClick={() => setOpen(true)} data-testid={`${testId}-open`}><MessageCircle className="mr-1 h-4 w-4" />Messages{unread > 0 && <span className="ml-1 rounded-full bg-av-clay px-1.5 text-[10px] text-white" data-testid={`${testId}-unread`}>{unread}</span>}</Button>;
  return (
    <div className="space-y-2 rounded-xl border border-av-line bg-av-linen/60 p-3 text-sm" data-testid={testId}>
      <div className="flex items-center justify-between"><p className="text-xs font-semibold uppercase tracking-wide text-av-muted">Order messages</p>
        <button type="button" className="text-xs underline" onClick={() => setOpen(false)} data-testid={`${testId}-close`}>Close</button></div>
      {t && <p className="flex items-start gap-1 text-[11px] text-av-muted"><ShieldAlert className="h-3.5 w-3.5 shrink-0" />{t.policy}</p>}
      <ul className="max-h-72 space-y-2 overflow-y-auto">{(t?.messages || []).map((m) => (
        <li key={m.id} className={`max-w-[85%] rounded-xl px-3 py-2 ${m.mine ? "ml-auto bg-av-indigo text-av-linen" : "bg-white"}`} data-testid={`msg-${m.id}`}>
          <p className="text-[11px] opacity-70">{m.mine ? "You" : m.sender_name} · {new Date(m.created_at).toLocaleString()}</p>
          <p className={`whitespace-pre-line ${m.held ? "italic opacity-70" : ""}`}>{m.body}</p>
          {m.notice && <p className="mt-1 text-[11px] text-av-gold" data-testid={`msg-notice-${m.id}`}>{m.notice}</p>}</li>))}
        {t && t.messages.length === 0 && <li className="text-xs text-av-muted" data-testid={`${testId}-empty`}>No messages yet.</li>}</ul>
      <Textarea className="bg-white" maxLength={2000} placeholder="Ask about this order, delivery or pickup…" value={body} onChange={(e) => setBody(e.target.value)} data-testid={`${testId}-input`} />
      <Button size="sm" disabled={!body.trim()} onClick={send} data-testid={`${testId}-send`}>Send</Button>
    </div>
  );
};
