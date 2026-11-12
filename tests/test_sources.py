"""Topic data from entity attributes and services: person and day filter, trimming, logging."""

from __future__ import annotations

from datetime import date
import re

from custom_components.assist_router.languages import LANG
from custom_components.assist_router.sources import (
    compact,
    day_range,
    fill,
    range_bounds,
    render,
)

THURSDAY = date(2026, 10, 22)
KASIA = re.compile(r"\b(?:kasi|katarz)", re.IGNORECASE)

PLAN = {
    "week_start": "2026-10-19",
    "friendly_name": "Plan lekcji",
    "children": [
        {
            "child": "Katarzyna",
            "avatar": "http://…",
            "child_color": "#f5ec00",
            "days": [
                {"date": "2026-10-22", "lessons": [{"start": "08:00", "subject": "Matematyka",
                                                    "canceled": False}]},
                {"date": "2026-10-23", "lessons": [{"start": "09:00", "subject": "Biologia",
                                                    "canceled": True}]},
            ],
        },
        {"child": "Jan", "days": [{"date": "2026-10-22", "lessons": [{"start": "07:30"}]}]},
    ],
}  # fmt: skip


def test_day_range() -> None:
    assert day_range("today", THURSDAY) == (THURSDAY, THURSDAY)
    assert day_range("tomorrow", THURSDAY) == (date(2026, 10, 23),) * 2
    assert day_range("weekend", THURSDAY) == (date(2026, 10, 24), date(2026, 10, 25))
    assert day_range("weekend", date(2026, 10, 25)) == (date(2026, 10, 25),) * 2
    assert day_range("monday", THURSDAY) == (date(2026, 10, 26),) * 2
    assert day_range("thursday", THURSDAY) == (THURSDAY, THURSDAY)
    assert day_range("14", THURSDAY) == (THURSDAY, date(2026, 11, 4))
    assert day_range(None, THURSDAY) is None
    assert range_bounds((THURSDAY, THURSDAY)) == ("2026-10-22T00:00:00", "2026-10-23T00:00:00")


def test_compact_filters_person_day_and_noise() -> None:
    value = compact(PLAN, [KASIA], day_range("tomorrow", THURSDAY))
    # only Kasia, only Friday; no avatar, color, entity name or „canceled: false”
    assert value == {
        "week_start": "2026-10-19 (poniedziałek)",
        "children": [
            {
                "child": "Katarzyna",
                "days": [
                    {"date": "2026-10-23 (piątek)",
                     "lessons": [{"start": "09:00", "subject": "Biologia", "canceled": True}]},
                ],
            }
        ],
    }  # fmt: skip
    # person not in the data (tata) - no person filter
    assert len(compact(PLAN, [re.compile("tomek")])["children"]) == 2
    # day without lessons - „brak” instead of an empty list
    saturday = compact(PLAN, None, day_range("weekend", THURSDAY))
    assert saturday["children"][0]["days"] == LANG.EMPTY
    assert compact(PLAN, drop=frozenset({"days"}))["children"][1] == {"child": "Jan"}


def test_render_and_fill() -> None:
    text = render("Plan lekcji", {"children": [{"child": "Katarzyna", "lekcje": 8}]})
    assert text == "Plan lekcji:\nchildren:\n- child: Katarzyna\n  lekcje: 8"
    assert render("X", {"a": "x" * 50}, limit=20).endswith("…")
    assert fill({"start_date_time": "{start}", "n": 1}, "S", "E") == {
        "start_date_time": "S",
        "n": 1,
    }


def test_local_time_root_and_limit() -> None:
    from datetime import timedelta, timezone

    warsaw = timezone(timedelta(hours=2))
    forecast = {
        "date": "2026-10-22",  # reading date at the root - does not filter everything
        "forecast": [
            {"datetime": "2026-10-23T22:30:00+00:00", "temperature": 9.0},  # 24.10 local time
            {"datetime": "2026-10-24T10:00:00+00:00", "temperature": 12.5},
        ],
    }
    value = compact(forecast, days=day_range("sobota", THURSDAY), tz=warsaw)
    assert value["forecast"] == [
        {"datetime": "2026-10-24 00:30 (sobota)", "temperature": 9},
        {"datetime": "2026-10-24 12:00 (sobota)", "temperature": 12.5},
    ]
    assert compact(forecast, tz=warsaw, max_items=1)["forecast"][1] == "… i 1 więcej"


def test_merge_sorts_by_start() -> None:
    from custom_components.assist_router.sources import merge

    merged = merge(
        {
            "calendar.praca": {"events": [{"start": "2026-10-22T12:00", "summary": "Standup"}]},
            "calendar.rodzina": {"events": [{"start": "2026-10-22T08:00", "summary": "Szkoła"}]},
        },
        "events",
        {"calendar.praca": "Praca", "calendar.rodzina": "Rodzina"},
    )
    assert [(e["źródło"], e["summary"]) for e in merged["events"]] == [
        ("Rodzina", "Szkoła"),
        ("Praca", "Standup"),
    ]


def test_past_events_dropped_or_marked() -> None:
    """At 16:00 a 12:00 meeting is over: a day summary leaves it out, a calendar question
    keeps it marked; a meeting going on, a later one and an all-day item stay."""
    from datetime import datetime, timedelta, timezone

    from custom_components.assist_router.sources import PAST_DROP, PAST_MARK, past

    warsaw = timezone(timedelta(hours=1))
    now = datetime(2026, 11, 10, 16, 0, tzinfo=warsaw)
    data = {
        "events": [
            {
                "start": "2026-11-10T09:30:00+01:00",
                "end": "2026-11-10T10:30:00+01:00",
                "summary": "Ortodonta",
            },
            {"start": "2026-11-10T11:00:00Z", "end": "2026-11-10T11:15:00Z", "summary": "Standup"},
            {
                "start": "2026-11-10T15:30:00+01:00",
                "end": "2026-11-10T16:30:00+01:00",
                "summary": "Trwa",
            },
            {"start": "2026-11-10T18:45", "end": "2026-11-10T19:45", "summary": "Zumba"},
            {"start": "2026-11-10", "end": "2026-11-11", "summary": "Święto"},
            {"start": "2026-11-10T15:00", "summary": "Bez końca"},
        ],
        "note": "x",
    }
    kept = past(data, now, PAST_DROP)
    assert [e["summary"] for e in kept["events"]] == ["Trwa", "Zumba", "Święto"]
    assert kept["note"] == "x"
    marked = past(data, now, PAST_MARK)["events"]
    assert [e["summary"] for e in marked if e.get(LANG.PAST_KEY)] == [
        "Ortodonta",
        "Standup",
        "Bez końca",
    ]
    assert len(marked) == 6
    assert "już_było: true" in render("Wydarzenia", compact({"events": marked[:1]}, tz=warsaw))


def test_past_leaves_other_data_alone() -> None:
    from datetime import datetime

    from custom_components.assist_router.sources import PAST_DROP, past

    now = datetime(2026, 11, 10, 16, 0)
    assert past(["a"], now, PAST_DROP) == ["a"]
    assert past({"events": ["tekst", {"start": "jutro"}]}, now, PAST_DROP) == {
        "events": ["tekst", {"start": "jutro"}]
    }
    # naive now, zoned event (tools without HA)
    ended = {"events": [{"end": "2000-01-01T10:00:00+00:00"}]}
    assert past(ended, now, PAST_DROP) == {"events": []}
