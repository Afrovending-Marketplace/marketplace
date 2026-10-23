import re
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, available_timezones

DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
DAY_NAMES = dict(zip(DAYS, ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")))
_HHMM = re.compile(r"([01]\d|2[0-3]):[0-5]\d")


def _intervals(raw: list, where: str) -> list[dict]:
    out = []
    for iv in raw or []:
        o, c = str(iv.get("open", "")), str(iv.get("close", ""))
        if not (_HHMM.fullmatch(o) and _HHMM.fullmatch(c)):
            raise ValueError(f"{where}: times must be HH:MM (24-hour).")
        if o >= c:
            raise ValueError(f"{where}: opening time must be before closing time.")
        out.append({"open": o, "close": c})
    out.sort(key=lambda i: i["open"])
    for a, b in zip(out, out[1:]):
        if b["open"] < a["close"]:
            raise ValueError(f"{where}: opening hours overlap.")
    if len(out) > 4:
        raise ValueError(f"{where}: at most 4 opening periods per day.")
    return out


def validate(h: dict) -> dict:
    """Returns a normalised pickup-hours document or raises ValueError with a plain-language message."""
    tz = h.get("timezone") or ""
    if tz not in available_timezones():
        raise ValueError("Choose a valid time zone for this pickup location.")
    weekly = {d: _intervals((h.get("weekly") or {}).get(d, []), DAY_NAMES[d]) for d in DAYS}
    exceptions = []
    for e in h.get("exceptions") or []:
        try:
            start, end = date.fromisoformat(e["from"]), date.fromisoformat(e.get("to") or e["from"])
        except (KeyError, ValueError):
            raise ValueError("Closure dates must look like 2026-12-25.") from None
        if end < start:
            raise ValueError("A closure can't end before it starts.")
        if (end - start).days > 90:
            raise ValueError("A single closure or exception can cover at most 90 days.")
        closed = bool(e.get("closed", True))
        ivs = [] if closed else _intervals(e.get("intervals"), f"Exception {start}")
        if not closed and not ivs:
            raise ValueError(f"Exception {start}: add special hours or mark it closed.")
        exceptions.append({"from": start.isoformat(), "to": end.isoformat(), "closed": closed, "intervals": ivs, "note": str(e.get("note", ""))[:80]})
    if len(exceptions) > 60:
        raise ValueError("At most 60 closures and exceptions.")
    exceptions.sort(key=lambda e: e["from"])
    for a, b in zip(exceptions, exceptions[1:]):
        if b["from"] <= a["to"]:
            raise ValueError("Closures and exceptions can't overlap each other.")
    return {"timezone": tz, "weekly": weekly, "exceptions": exceptions, "instructions": str(h.get("instructions", ""))[:300]}


def intervals_on(h: dict, day: date) -> list[dict]:
    """Opening periods for a calendar date in the location's own time zone (exceptions override the weekly grid)."""
    iso = day.isoformat()
    for e in h.get("exceptions") or []:
        if e["from"] <= iso <= e["to"]:
            return [] if e["closed"] else e["intervals"]
    return (h.get("weekly") or {}).get(DAYS[day.weekday()], [])


def is_open_at(h: dict, moment: datetime) -> bool:
    """Basis for future pickup appointments: a slot is only bookable when this is True."""
    local = moment.astimezone(ZoneInfo(h["timezone"]))
    t = local.strftime("%H:%M")
    return any(iv["open"] <= t < iv["close"] for iv in intervals_on(h, local.date()))


def slots(h: dict, now: datetime, minutes: int, days: int = 14, lead_minutes: int = 60) -> list[tuple[datetime, datetime]]:
    """Bookable (start, end) UTC pairs that fit fully inside an opening period, from lead time up to `days` ahead."""
    tz = ZoneInfo(h["timezone"])
    earliest, step = now + timedelta(minutes=lead_minutes), timedelta(minutes=minutes)
    today = now.astimezone(tz).date()
    out = []
    for n in range(days):
        d = today + timedelta(days=n)
        for iv in intervals_on(h, d):
            start = datetime.combine(d, time.fromisoformat(iv["open"]), tz)
            close = datetime.combine(d, time.fromisoformat(iv["close"]), tz)
            while start + step <= close:
                if start >= earliest:
                    out.append((start.astimezone(timezone.utc), (start + step).astimezone(timezone.utc)))
                start += step
    return out


def local_label(h: dict, moment: datetime) -> str:
    loc = moment.astimezone(ZoneInfo(h["timezone"]))
    return f"{loc.strftime('%a %b %d')}, {_fmt(loc.strftime('%H:%M'))} ({loc.tzname()})"


def _fmt(t: str) -> str:
    hh, mm = int(t[:2]), t[3:]
    return f"{(hh % 12) or 12}:{mm} {'AM' if hh < 12 else 'PM'}"


def _span(ivs: list[dict]) -> str:
    return ", ".join(f"{_fmt(i['open'])}–{_fmt(i['close'])}" for i in ivs) or "Closed"


def weekly_lines(h: dict) -> list[str]:
    return [f"{DAY_NAMES[d]}: {_span(h['weekly'].get(d, []))}" for d in DAYS]


def upcoming_exceptions(h: dict, now: datetime, days: int = 30) -> list[str]:
    today = now.astimezone(ZoneInfo(h["timezone"])).date()
    horizon = (today + timedelta(days=days)).isoformat()
    out = []
    for e in h.get("exceptions") or []:
        if e["to"] >= today.isoformat() and e["from"] <= horizon:
            when = e["from"] if e["from"] == e["to"] else f"{e['from']} to {e['to']}"
            note = f" ({e['note']})" if e["note"] else ""
            out.append(f"{when}: {'Closed' if e['closed'] else _span(e['intervals'])}{note}")
    return out
