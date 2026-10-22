from datetime import datetime, timedelta


def add_business_days(start: datetime, days: int, closed: set[str]) -> datetime:
    """Counts forward skipping Saturdays, Sundays and closed dates (YYYY-MM-DD, UTC). Keeps the start time of day."""
    d, left = start, days
    while left > 0:
        d += timedelta(days=1)
        if d.weekday() < 5 and d.date().isoformat() not in closed:
            left -= 1
    return d
