import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { api, getErrorMessage } from "@/lib/api";

const fmt = (iso, tz, opts) => new Intl.DateTimeFormat("en-US", { timeZone: tz, ...opts }).format(new Date(iso));

export const PickupBooking = ({ orderId, vo, onChange }) => {
  const [d, setD] = useState(null);
  const [day, setDay] = useState(null);
  const [busy, setBusy] = useState(false);
  const base = `/orders/${orderId}/vendor-orders/${vo.id}`;
  const load = useCallback(() => api.get(`${base}/pickup-slots`).then((r) => setD(r.data)).catch(() => setD(null)), [base]);
  useEffect(() => {
    load();
  }, [load]);
  if (!d) return null;
  const tz = d.timezone;
  const booking = vo.pickup_booking;
  if (!d.bookable) {
    return booking ? <p className="text-xs" data-testid={`pickup-booked-${vo.vendor_slug}`}>Pickup time: <b>{fmt(booking.start, tz || undefined, { dateStyle: "medium", timeStyle: "short" })}</b></p> : null;
  }
  const byDay = d.slots.reduce((acc, s) => {
    const k = fmt(s.start, tz, { weekday: "short", month: "short", day: "numeric" });
    (acc[k] = acc[k] || []).push(s);
    return acc;
  }, {});
  const days = Object.keys(byDay);
  const current = day && byDay[day] ? day : days[0];
  const run = async (fn, msg) => {
    setBusy(true);
    try {
      await fn();
      toast.success(msg);
      await load();
      onChange();
    } catch (err) {
      toast.error(getErrorMessage(err));
      load();
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="space-y-2 rounded-xl bg-av-sand p-3 text-xs" data-testid={`pickup-booking-${vo.vendor_slug}`}>
      <p className="font-semibold text-av-ink">{booking ? "Your pickup time" : "Choose a pickup time"} <span className="font-normal text-av-muted">(times shown in the shop's time zone, {fmt(new Date().toISOString(), tz, { timeZoneName: "short" }).split(" ").pop()})</span></p>
      {booking && <p data-testid={`pickup-booked-${vo.vendor_slug}`}><b>{fmt(booking.start, tz, { weekday: "long", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}–{fmt(booking.end, tz, { hour: "numeric", minute: "2-digit" })}</b>
        <Button size="sm" variant="ghost" disabled={busy} onClick={() => run(() => api.delete(`${base}/pickup-booking`), "Pickup time cancelled")} data-testid={`pickup-cancel-${vo.vendor_slug}`}>Cancel time</Button></p>}
      {days.length === 0 ? <p className="text-av-muted" data-testid={`pickup-no-slots-${vo.vendor_slug}`}>No open pickup times in the next two weeks — please contact the seller.</p> : <>
        <div className="flex gap-1 overflow-x-auto">{days.map((k) => <Button key={k} size="sm" variant={k === current ? "default" : "outline"} className="shrink-0" onClick={() => setDay(k)} data-testid={`pickup-day-${k.replace(/[\s,]+/g, "-")}`}>{k}</Button>)}</div>
        <div className="flex flex-wrap gap-1">{byDay[current].map((s) => (
          <Button key={s.start} size="sm" variant={s.mine ? "default" : "outline"} disabled={busy || s.mine || s.remaining === 0} onClick={() => run(() => api.post(`${base}/pickup-booking`, { start: s.start }), booking ? "Pickup time changed" : "Pickup time booked")}
            data-testid={`pickup-slot-${s.start}`}>{fmt(s.start, tz, { hour: "numeric", minute: "2-digit" })}{s.remaining === 0 && !s.mine ? " · full" : ""}</Button>))}</div></>}
    </div>
  );
};
