"""Topic data from entity attributes and HA service responses - without Assist automations.

Attributes (e.g. the lesson plan from the Rodzina integration) and service responses
(calendar.get_events, weather.get_forecasts) are trimmed to what was asked: people (key
``child`` or ``person``) and days (key ``date`` or ``datetime``), without noise (html,
avatars, colors), and written compactly (YAML) for the answer model.

The module does not depend on HA - the same code runs in the integration and in test tools.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, tzinfo
import re
from typing import Any

import yaml

from .languages import LANG

# keys that add nothing to the answer but take up model context
NOISE_KEYS = frozenset({
    "friendly_name", "icon", "entity_picture", "attribution", "supported_features",
    "device_class", "state_class", "unit_of_measurement", "avatar", "color", "child_color",
    "fetched_at", "account", "html", "html_timetable", "editable", "order", "id", "uid",
    "recurrence_id", "rrule",
})  # fmt: skip
PERSON_KEYS = ("child", "person")
DATE_KEYS = ("date", "datetime")
# Day codes: what a question asks about (router.find_when) and `days:` in router.yaml.
# Language packs map spoken words (and their own names for `days:`) to these codes.
TODAY = "today"
TOMORROW = "tomorrow"
DAY_AFTER_TOMORROW = "day_after_tomorrow"
WEEKEND = "weekend"
WEEK = "week"
WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
DAY_CODES = (TODAY, TOMORROW, DAY_AFTER_TOMORROW, WEEKEND, WEEK, *WEEKDAYS)
MAX_ITEMS = 40  # most items in one list
SOURCE_CHARS = 6000  # most characters of one source


def day_range(when: str | None, today: date) -> tuple[date, date] | None:
    """Day range for a day code (``tomorrow``, ``weekend``, ``thursday``, ``14``); None = no
    filter."""
    if when == TODAY:
        return today, today
    if when == TOMORROW:
        return today + timedelta(days=1), today + timedelta(days=1)
    if when == DAY_AFTER_TOMORROW:
        return today + timedelta(days=2), today + timedelta(days=2)
    if when == WEEKEND:
        saturday = today + timedelta(days=(5 - today.weekday()) % 7)
        if today.weekday() == 6:  # Sunday - this weekend is already today
            saturday = today
        return saturday, today + timedelta(days=(6 - today.weekday()) % 7)
    if when == WEEK:
        return today, today + timedelta(days=6)
    if when in WEEKDAYS:
        day = today + timedelta(days=(WEEKDAYS.index(when) - today.weekday()) % 7)
        return day, day
    if when and when.isdigit() and int(when) > 0:  # „14” = today and the next 13 days
        return today, today + timedelta(days=int(when) - 1)
    return None


def range_bounds(days: tuple[date, date]) -> tuple[str, str]:
    """Start and end of the day range (local, naive) for services with ``{start}``/``{end}``."""
    start = datetime.combine(days[0], time.min)
    end = datetime.combine(days[1] + timedelta(days=1), time.min)
    return start.isoformat(), end.isoformat()


_ISO_TIME = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?([+-]\d{2}:\d{2}|Z)$")


_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}$")


def _local(value: str, tz: tzinfo | None) -> str:
    """A time with a zone (forecasts are in UTC) as local „2026-10-24 12:00”."""
    if tz is None or not _ISO_TIME.match(value):
        return value
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    return moment.astimezone(tz).strftime("%Y-%m-%d %H:%M")


def _with_weekday(value: str) -> str:
    """„2026-10-24 12:00” -> „2026-10-24 12:00 (sobota)” - the model need not count days."""
    if not (_ISO_DATE.match(value) or (_ISO_DATE.match(value[:10]) and value[10:11] in (" ", "T"))):
        return value
    try:
        day = date.fromisoformat(value[:10])
    except ValueError:
        return value
    return f"{value} ({LANG.WEEKDAY_NAMES[day.weekday()]})"


def _date_of(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and re.match(r"\d{4}-\d{2}-\d{2}", value):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def _person_values(value: Any) -> list[str]:
    """Values of person keys in the whole tree („Aleksandra”, „Kuba”…)."""
    if isinstance(value, dict):
        found = [str(value[k]) for k in PERSON_KEYS if isinstance(value.get(k), str)]
        return found + [v for x in value.values() for v in _person_values(x)]
    if isinstance(value, list):
        return [v for x in value for v in _person_values(x)]
    return []


class _Skip:
    """An item rejected by the person or day filter."""


_SKIP = _Skip()


def compact(
    value: Any,
    people: list[re.Pattern[str]] | None = None,
    days: tuple[date, date] | None = None,
    drop: frozenset[str] = frozenset(),
    tz: tzinfo | None = None,
    max_items: int = MAX_ITEMS,
) -> Any:
    """Attribute tree trimmed to people and days, without noise and empty values.

    The person filter applies only when any of the people appears in the data at all - a
    father's question about the children's bank does not remove all children. The filters
    do not apply to the root itself (an entity's „date” attribute is the read date, not a day
    in the data). ``tz`` - zoned times converted to local ones (also for the day filter).
    """
    if people and not any(p.search(v) for v in _person_values(value) for p in people):
        people = None
    filters = _Filters(people, days, NOISE_KEYS | drop, tz, max_items)
    if isinstance(value, dict):
        return _compact_dict(value, filters)
    result = _compact(value, filters)
    return [] if result is _SKIP else result


class _Filters:
    def __init__(self, people, days, drop, tz, max_items) -> None:
        self.people, self.days, self.drop, self.tz, self.max_items = (
            people, days, drop, tz, max_items,
        )  # fmt: skip


def _compact(value: Any, f: _Filters) -> Any:
    if isinstance(value, dict):
        if f.people:
            who = next((value[k] for k in PERSON_KEYS if isinstance(value.get(k), str)), None)
            if who is not None and not any(p.search(who) for p in f.people):
                return _SKIP
        if f.days:
            raw = next((value[k] for k in DATE_KEYS if k in value), None)
            when = _date_of(_local(raw, f.tz) if isinstance(raw, str) else raw)
            if when is not None and not f.days[0] <= when <= f.days[1]:
                return _SKIP
        return _compact_dict(value, f)
    if isinstance(value, list):
        items = [_compact(item, f) for item in value]
        kept = [item for item in items if item is not _SKIP and item not in (None, "", [], {})]
        if value and not kept and any(item is _SKIP for item in items):
            return LANG.EMPTY
        if len(kept) > f.max_items:
            kept = [*kept[: f.max_items], LANG.MORE_ITEMS.format(count=len(kept) - f.max_items)]
        return kept
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        return _with_weekday(_local(value, f.tz))
    return value


def _compact_dict(value: dict, f: _Filters) -> dict:
    out = {}
    for key, item in value.items():
        if key in f.drop or key.endswith("_color") or "html" in key:
            continue
        item = _compact(item, f)
        if item is _SKIP or item is False or item in (None, "", [], {}):
            continue  # false („canceled: false”) is noise - only true flags stay
        out[key] = item
    return out


def merge(responses: dict[str, Any], key: str, names: dict[str, str]) -> dict[str, Any]:
    """``key`` lists from the responses of several entities merged into one, sorted by start,
    with the source name - e.g. events from all calendars in time order."""
    items = []
    for entity_id, data in responses.items():
        for item in (data or {}).get(key) or []:
            if isinstance(item, dict):
                items.append({LANG.SOURCE_KEY: names.get(entity_id, entity_id), **item})
    items.sort(key=lambda i: str(i.get("start") or i.get("datetime") or i.get("date") or ""))
    return {key: items}


def render(title: str, value: Any, limit: int = SOURCE_CHARS) -> str:
    """Source for the model: a title and compact YAML (Polish characters, no quotes)."""
    if isinstance(value, (dict, list)):
        body = yaml.safe_dump(
            value, allow_unicode=True, sort_keys=False, default_flow_style=False, width=1000
        ).strip()
    else:
        body = str(value)
    if len(body) > limit:
        body = body[:limit].rsplit("\n", 1)[0] + "\n…"
    return f"{title}:\n{body}"


def fill(data: Any, start: str, end: str) -> Any:
    """Service data from router.yaml with the range substituted: ``{start}``, ``{end}``."""
    if isinstance(data, dict):
        return {k: fill(v, start, end) for k, v in data.items()}
    if isinstance(data, list):
        return [fill(v, start, end) for v in data]
    if isinstance(data, str):
        return data.replace("{start}", start).replace("{end}", end)
    return data
