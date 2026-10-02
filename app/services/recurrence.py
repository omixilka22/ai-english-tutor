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


def week_monday(now=None):
    now = aware_utc(now or datetime.now(timezone.utc))
    local = now.astimezone(ZoneInfo('Europe/Kyiv')).date()
    return local - timedelta(days=local.weekday())


def week_bounds(week):
    return (local_instant(week, datetime.min.time(), 'Europe/Kyiv'),
            local_instant(week + timedelta(days=7), datetime.min.time(), 'Europe/Kyiv'))


def weekly_slots(schedule, now):
    """A saved entry belongs to exactly one calendar week, never a rolling horizon."""
    now = aware_utc(now)
    week = schedule.week_start
    if week is None:
        return
    instant = local_instant(week + timedelta(days=schedule.day_of_week),
                            schedule.start_time, schedule.timezone)
    if instant is not None and instant > now:
        yield week, instant
