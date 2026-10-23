const DAYS = [["mon", "Mon"], ["tue", "Tue"], ["wed", "Wed"], ["thu", "Thu"], ["fri", "Fri"], ["sat", "Sat"], ["sun", "Sun"]];
const fmt = (t) => {
  const h = Number(t.slice(0, 2));
  return `${h % 12 || 12}:${t.slice(3)} ${h < 12 ? "AM" : "PM"}`;
};
export const span = (ivs) => (ivs?.length ? ivs.map((i) => `${fmt(i.open)}–${fmt(i.close)}`).join(", ") : "Closed");
const tzLabel = (tz) => {
  try {
    return new Intl.DateTimeFormat("en-US", { timeZone: tz, timeZoneName: "short" }).formatToParts(new Date()).find((p) => p.type === "timeZoneName")?.value || tz;
  } catch {
    return tz;
  }
};
const upcoming = (h) => {
  const today = new Intl.DateTimeFormat("en-CA", { timeZone: h.timezone }).format(new Date());
  const horizon = new Date(Date.now() + 30 * 864e5).toISOString().slice(0, 10);
  return (h.exceptions || []).filter((e) => e.to >= today && e.from <= horizon);
};

export const PickupHours = ({ hours, compact = false, testId }) => {
  if (!hours) return null;
  const exc = upcoming(hours);
  return (
    <div className="text-xs text-av-muted" data-testid={testId}>
      <p className="font-semibold text-av-ink">Pickup hours ({tzLabel(hours.timezone)})</p>
      <ul className={compact ? "flex flex-wrap gap-x-3" : "space-y-0.5"}>
        {DAYS.map(([k, l]) => <li key={k}>{l}: {span(hours.weekly?.[k])}</li>)}
      </ul>
      {exc.length > 0 && <ul className="mt-1 text-av-clay" data-testid={testId && `${testId}-exceptions`}>
        {exc.map((e) => <li key={e.from}>{e.from === e.to ? e.from : `${e.from} → ${e.to}`}: {e.closed ? "Closed" : span(e.intervals)}{e.note && ` (${e.note})`}</li>)}</ul>}
      {!compact && hours.instructions && <p className="mt-1">Instructions: {hours.instructions}</p>}
    </div>
  );
};

export { DAYS };
