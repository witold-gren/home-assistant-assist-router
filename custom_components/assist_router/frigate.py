"""Frigate NVR as topic data: who the cameras saw, where and when (topic option ``frigate``).

Frigate's face recognition writes the person's name to the tracked object's ``sub_label``.
The people and the day from the question narrow the query to the Frigate HTTP API;
consecutive events of one person on one camera are joined into one visit, and the GenAI
review summaries of the same period are added. The answer model gets a short chronological
list with local times - no tool calling, so a small model answers reliably and nothing in
Frigate can be switched by voice.

Cameras look into the past, so day codes are read backwards: a weekday is its last
occurrence, ``14`` the last 14 days; „yesterday” comes from the question text
(``LANG.PAST_DAYS``), because the classifier's day codes only look ahead.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
import logging
from typing import Any

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .languages import LANG
from .sources import TODAY, WEEK, WEEKDAYS, WEEKEND

_LOGGER = logging.getLogger(__name__)

FRIGATE_TIMEOUT = 10  # s per Frigate API call
# events read from the API (newest first) before joining into visits; ~1 kB each, and a busy
# living room camera alone can track 2000 people a day
EVENTS_FETCHED = 2000
REVIEWS_FETCHED = 200  # review items read when looking for GenAI summaries


@dataclass(frozen=True)
class FrigateSource:
    url: str  # Frigate address, e.g. http://192.168.1.10:5000 (port 5000 = no login)
    cameras: dict[str, str] = field(default_factory=dict)  # camera -> spoken name; {} = all
    labels: tuple[str, ...] = ("person",)
    days: int = 7  # days back when the question gives no day
    limit: int = 30  # most visits for the model
    summaries: int = 10  # most GenAI review summaries; 0 = none
    gap: int = 120  # s between events of one person on one camera that still make one visit


def parse_frigate(topic: str, raw: Any) -> FrigateSource:
    """``frigate:`` of a topic: an address or a mapping with ``url`` and options."""
    raw = {"url": raw} if isinstance(raw, str) else raw
    if not isinstance(raw, dict) or not str(raw.get("url", "")).startswith("http"):
        raise ValueError(f"router.yaml: topic '{topic}': frigate needs 'url: http://…'")
    cameras = raw.get("cameras") or {}
    if isinstance(cameras, list):
        cameras = {str(c): str(c).replace("_", " ").capitalize() for c in cameras}
    labels = raw.get("labels") or ("person",)
    return FrigateSource(
        url=str(raw["url"]).rstrip("/"),
        cameras={str(k): str(v) for k, v in cameras.items()},
        labels=(labels,) if isinstance(labels, str) else tuple(str(x) for x in labels),
        days=int(raw.get("days") or 7),
        limit=int(raw.get("limit") or 30),
        summaries=int(raw.get("summaries", 10)),
        gap=int(raw.get("gap") or 120),
    )


def past_range(when: str | None, text: str, today: date, days: int) -> tuple[date, date]:
    """Days the question asks about, looking back: „wczoraj” from the text, a day code from
    the classifier, otherwise the last ``days`` days."""
    for word, back in LANG.PAST_DAYS:
        if word.search(text):
            day = today - timedelta(days=back)
            return day, day
    if when == TODAY:
        return today, today
    if when in WEEKDAYS:
        day = today - timedelta(days=(today.weekday() - WEEKDAYS.index(when)) % 7)
        return day, day
    if when == WEEKEND:
        if today.weekday() >= 5:  # this weekend is going on
            return today - timedelta(days=today.weekday() - 5), today
        sunday = today - timedelta(days=today.weekday() + 1)
        return sunday - timedelta(days=1), sunday
    if when == WEEK:
        return today - timedelta(days=6), today
    if when and when.isdigit() and int(when) > 0:
        return today - timedelta(days=int(when) - 1), today
    return today - timedelta(days=days - 1), today


def cameras_in_question(cameras: dict[str, str], text: str) -> list[str]:
    """Cameras whose spoken name is in the question („w pokoju dziewczyn” - Pokój dziewczyn):
    all stems of the name, so inflected forms match. None named - all cameras."""
    asked = set(LANG.stems(text))
    named = [camera for camera, name in cameras.items() if set(LANG.stems(name)) <= asked]
    return named or list(cameras)


def visits(events: list[dict[str, Any]], gap: int) -> list[dict[str, Any]]:
    """Events (any order) as visits, oldest first: one person on one camera with breaks of
    at most ``gap`` seconds is one visit. Events still in progress have ``end_time`` None."""
    joined: list[dict[str, Any]] = []
    last: dict[tuple[str, str | None, str], dict[str, Any]] = {}
    for event in sorted(events, key=lambda e: e["start_time"]):
        key = (event["camera"], event.get("sub_label") or None, event["label"])
        visit = last.get(key)
        if visit and (visit["end"] is None or event["start_time"] - visit["end"] <= gap):
            if visit["end"] is not None:
                end = event.get("end_time")
                visit["end"] = None if end is None else max(visit["end"], end)
            continue
        visit = {
            "camera": event["camera"],
            "name": key[1],
            "label": event["label"],
            "start": event["start_time"],
            "end": event.get("end_time"),
        }
        joined.append(visit)
        last[key] = visit
    return joined


def _clock(timestamp: float, several_days: bool, tz: Any) -> str:
    moment = datetime.fromtimestamp(timestamp, tz)
    if several_days:
        weekday = LANG.WEEKDAY_NAMES[moment.weekday()]
        return f"{moment.day}.{moment.month:02d} ({weekday}) {moment:%H:%M}"
    return f"{moment:%H:%M}"


def visit_line(visit: dict[str, Any], cameras: dict[str, str], several_days: bool, tz: Any) -> str:
    """„Kasia - Salon: 18:35-18:40”; unknown person and a visit still going on by name."""
    who = visit["name"] or (LANG.FRIGATE_UNKNOWN if visit["label"] == "person" else visit["label"])
    where = cameras.get(visit["camera"], visit["camera"])
    start = _clock(visit["start"], several_days, tz)
    end = LANG.FRIGATE_NOW if visit["end"] is None else _clock(visit["end"], False, tz)
    return f"{who} - {where}: {start}-{end}"


async def _get(hass: HomeAssistant, url: str, params: dict[str, Any]) -> Any:
    session = async_get_clientsession(hass)
    async with asyncio.timeout(FRIGATE_TIMEOUT):
        response = await session.get(url, params={k: v for k, v in params.items() if v})
        response.raise_for_status()
        return await response.json()


async def async_frigate_sources(
    hass: HomeAssistant,
    source: FrigateSource,
    names: list[str],
    when: str | None,
    text: str,
    now: datetime,
) -> list[str]:
    """Visits (and GenAI summaries) for the people and days from the question."""
    first, last = past_range(when, text, now.date(), source.days)
    after = datetime.combine(first, time.min, now.tzinfo).timestamp()
    before = datetime.combine(last + timedelta(days=1), time.min, now.tzinfo).timestamp()
    cameras = ",".join(cameras_in_question(source.cameras, text))
    try:
        events = await _get(hass, f"{source.url}/api/events", {
            "cameras": cameras, "labels": ",".join(source.labels),
            "sub_labels": ",".join(names), "after": int(after), "before": int(before),
            "limit": EVENTS_FETCHED, "include_thumbnails": "0",
        })  # fmt: skip
        reviews = []
        if source.summaries:
            reviews = await _get(hass, f"{source.url}/api/review", {
                "cameras": cameras, "after": int(after), "before": int(before),
                "limit": REVIEWS_FETCHED,
            })  # fmt: skip
    except (TimeoutError, aiohttp.ClientError, ValueError):
        _LOGGER.warning("Router frigate %s failed", source.url, exc_info=True)
        return [f"{LANG.FRIGATE_VISITS}: {LANG.FRIGATE_UNAVAILABLE}"]

    several_days = first != last
    found = visits(events, source.gap)[-source.limit :]
    lines = [visit_line(v, source.cameras, several_days, now.tzinfo) for v in found]
    out = [
        f"{LANG.FRIGATE_VISITS}:\n" + "\n".join(lines)
        if lines
        else f"{LANG.FRIGATE_VISITS}: {LANG.EMPTY}"
    ]

    wanted = {name.lower() for name in names}
    summaries = []
    for item in reversed(reviews):  # the API returns the newest first
        metadata = (item.get("data") or {}).get("metadata") or {}
        summary = metadata.get("shortSummary") or metadata.get("title")
        seen = {str(name).lower() for name in (item.get("data") or {}).get("sub_labels") or ()}
        if not summary or (wanted and not wanted & seen):
            continue
        where = source.cameras.get(item["camera"], item["camera"])
        summaries.append(
            f"{where} {_clock(item['start_time'], several_days, now.tzinfo)}: {summary}"
        )
    if summaries:
        out.append(f"{LANG.FRIGATE_SUMMARIES}:\n" + "\n".join(summaries[-source.summaries :]))
    return out
