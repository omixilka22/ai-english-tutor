"""Local weekly slots; UTC instants. Nonexistent DST times are skipped."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


def aware_utc(value):
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('Дата повинна містити часовий пояс.')
    return value.astimezone(timezone.utc)


def local_instant(day, clock, zone_name, *, strict=False):
    naive = datetime.combine(day, clock.replace(tzinfo=None))
    zone = ZoneInfo(zone_name)
    candidates = []
    for fold in (0, 1):
        utc = naive.replace(tzinfo=zone, fold=fold).astimezone(timezone.utc)
        if utc.astimezone(zone).replace(tzinfo=None) == naive and utc not in candidates:
            candidates.append(utc)
    if not candidates:
        if strict:
            raise ValueError('Цього часу не існує через переведення годинника. Оберіть інший час.')
        return None
    if strict and len(candidates) > 1:
        raise ValueError('Цей час повторюється при переведенні годинника. Оберіть однозначний час.')
    return min(candidates)  # Weekly recurrence uses the first occurrence in an autumn fold.


def weekly_slots(schedule, now, days=28):
    now = aware_utc(now)
    end = now + timedelta(days=days)
    local = now.astimezone(ZoneInfo(schedule.timezone)).date()
    monday = local - timedelta(days=local.weekday())
    # Include the boundary week, then filter by the half-open UTC horizon.
    for offset in range(days // 7 + 2):
        week = monday + timedelta(weeks=offset)
        instant = local_instant(week + timedelta(days=schedule.day_of_week),schedule.start_time,schedule.timezone)
        if instant is not None and now <= instant < end:
            yield week, instant
