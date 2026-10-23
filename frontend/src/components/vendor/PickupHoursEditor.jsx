import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { DAYS } from "@/components/common/PickupHours";

const ZONES = ["America/New_York", "America/Chicago", "America/Denver", "America/Phoenix", "America/Los_Angeles", "America/Anchorage", "Pacific/Honolulu"];
export const emptyHours = () => ({
  timezone: Intl.DateTimeFormat().resolvedOptions().timeZone?.startsWith("America/") ? Intl.DateTimeFormat().resolvedOptions().timeZone : "America/New_York",
  weekly: Object.fromEntries(DAYS.map(([k]) => [k, ["sat", "sun"].includes(k) ? [] : [{ open: "09:00", close: "17:00" }]])),
  exceptions: [],
  instructions: "",
});

const Intervals = ({ ivs, onChange, tid }) => (
  <span className="flex flex-wrap items-center gap-1">
    {ivs.map((iv, n) => (
      <span key={n} className="flex items-center gap-1">
        <input type="time" className="h-8 rounded border border-av-line px-1" value={iv.open} onChange={(e) => onChange(ivs.map((x, i) => (i === n ? { ...x, open: e.target.value } : x)))} data-testid={`${tid}-open-${n}`} />–
        <input type="time" className="h-8 rounded border border-av-line px-1" value={iv.close} onChange={(e) => onChange(ivs.map((x, i) => (i === n ? { ...x, close: e.target.value } : x)))} data-testid={`${tid}-close-${n}`} />
        <button type="button" className="px-1 text-av-muted" onClick={() => onChange(ivs.filter((_, i) => i !== n))} aria-label="Remove period" data-testid={`${tid}-remove-${n}`}>×</button>
      </span>))}
    {ivs.length < 4 && <Button type="button" size="sm" variant="ghost" onClick={() => onChange([...ivs, { open: ivs.length ? "14:00" : "09:00", close: ivs.length ? "18:00" : "17:00" }])} data-testid={`${tid}-add`}>+ period</Button>}
  </span>
);

const Exceptions = ({ list, onChange }) => {
  const [f, setF] = useState({ closed: true });
  const add = () => {
    onChange([...list, { from: f.from, to: f.to || f.from, closed: f.closed, intervals: f.closed ? [] : [{ open: f.open || "10:00", close: f.close || "14:00" }], note: f.note || "" }]);
    setF({ closed: true });
  };
  return (
    <div className="space-y-1" data-testid="hours-exceptions">
      <p className="font-semibold">Holidays & temporary closures (your weekly hours stay unchanged)</p>
      {list.map((e, n) => <p key={n} className="flex items-center gap-2" data-testid={`hours-exception-${n}`}>{e.from}{e.to !== e.from && ` → ${e.to}`}: {e.closed ? "Closed" : `${e.intervals[0].open}–${e.intervals[0].close}`} {e.note}
        <button type="button" className="text-av-muted" onClick={() => onChange(list.filter((_, i) => i !== n))} data-testid={`hours-exception-remove-${n}`}>remove</button></p>)}
      <div className="flex flex-wrap items-center gap-1">
        <input type="date" className="h-8 rounded border border-av-line px-1" value={f.from || ""} onChange={(e) => setF({ ...f, from: e.target.value })} data-testid="exc-from" />→
        <input type="date" className="h-8 rounded border border-av-line px-1" value={f.to || ""} onChange={(e) => setF({ ...f, to: e.target.value })} data-testid="exc-to" />
        <label className="flex items-center gap-1"><input type="checkbox" checked={f.closed} onChange={(e) => setF({ ...f, closed: e.target.checked })} data-testid="exc-closed" />Closed</label>
        {!f.closed && <><input type="time" className="h-8 rounded border border-av-line px-1" value={f.open || "10:00"} onChange={(e) => setF({ ...f, open: e.target.value })} data-testid="exc-open" />–
          <input type="time" className="h-8 rounded border border-av-line px-1" value={f.close || "14:00"} onChange={(e) => setF({ ...f, close: e.target.value })} data-testid="exc-close" /></>}
        <Input className="h-8 w-40" placeholder="Note (e.g. Thanksgiving)" value={f.note || ""} onChange={(e) => setF({ ...f, note: e.target.value })} data-testid="exc-note" />
        <Button type="button" size="sm" variant="outline" disabled={!f.from} onClick={add} data-testid="exc-add">Add</Button>
      </div>
    </div>
  );
};

export const PickupHoursEditor = ({ value, onChange }) => {
  const h = value || emptyHours();
  const set = (patch) => onChange({ ...h, ...patch });
  return (
    <div className="w-full space-y-2 rounded-xl bg-av-sand p-3 text-xs" data-testid="pickup-hours-editor">
      <label className="flex items-center gap-2">Time zone
        <select className="h-8 rounded border border-av-line bg-white px-2" value={h.timezone} onChange={(e) => set({ timezone: e.target.value })} data-testid="hours-timezone">
          {[...new Set([h.timezone, ...ZONES])].map((z) => <option key={z} value={z}>{z.replace("_", " ")}</option>)}</select></label>
      {DAYS.map(([k, l]) => {
        const ivs = h.weekly[k] || [];
        return (
          <div key={k} className="flex flex-wrap items-center gap-2" data-testid={`hours-day-${k}`}>
            <b className="w-9">{l}</b>
            <label className="flex items-center gap-1"><input type="checkbox" checked={!ivs.length} onChange={(e) => set({ weekly: { ...h.weekly, [k]: e.target.checked ? [] : [{ open: "09:00", close: "17:00" }] } })} data-testid={`hours-closed-${k}`} />Closed</label>
            {ivs.length > 0 && <Intervals ivs={ivs} tid={`hours-${k}`} onChange={(v) => set({ weekly: { ...h.weekly, [k]: v } })} />}
          </div>);
      })}
      <Exceptions list={h.exceptions} onChange={(v) => set({ exceptions: v })} />
      <Input className="h-8 bg-white" placeholder="Pickup instructions (e.g. use side entrance, bring order number)" value={h.instructions} onChange={(e) => set({ instructions: e.target.value })} data-testid="hours-instructions" />
    </div>
  );
};
