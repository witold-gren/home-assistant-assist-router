"""Frigate as topic data: who the cameras saw, where and when (topic option ``frigate``)."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
import re
from zoneinfo import ZoneInfo

from homeassistant.components import conversation
from homeassistant.core import Context, HomeAssistant
from homeassistant.util import dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.assist_router.frigate import (
    cameras_in_question,
    parse_frigate,
    past_range,
    visit_line,
    visits,
)
from custom_components.assist_router.languages import LANG

from .conftest import AGENT_ID, OLLAMA, ROUTER_YAML
from .test_router import _answer, _chat_by_model, _speech, _with_answer_model

FRIGATE = "http://frigate:5000"
WARSAW = ZoneInfo("Europe/Warsaw")
MONDAY = date(2026, 11, 9)

CAMERAS_TOPIC = f"""
  kamery:
    description: kto był w pokoju, kiedy ktoś był widziany na kamerze
    frigate:
      url: {FRIGATE}
      cameras: {{salon: Salon, pokoj_dzieci: Pokój dzieci}}
      days: 3
"""


def event(camera: str, start: float, end: float | None, name: str | None = None) -> dict:
    return {"camera": camera, "label": "person", "sub_label": name, "start_time": start,
            "end_time": end}  # fmt: skip


# --- configuration ------------------------------------------------------------------


def test_frigate_address_alone_is_enough() -> None:
    source = parse_frigate("kamery", "http://frigate:5000/")
    assert source.url == FRIGATE
    assert source.cameras == {}
    assert source.labels == ("person",)


def test_camera_list_gets_spoken_names() -> None:
    source = parse_frigate("kamery", {"url": FRIGATE, "cameras": ["pokoj_dzieci"]})
    assert source.cameras == {"pokoj_dzieci": "Pokoj dzieci"}


def test_frigate_without_address_is_an_error() -> None:
    with pytest.raises(ValueError, match="frigate needs 'url"):
        parse_frigate("kamery", {"cameras": ["salon"]})


# --- days looking back ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("when", "text", "expected"),
    [
        (None, "Czy Kasia była wczoraj w salonie?", (MONDAY - timedelta(1),) * 2),
        (None, "Kto był przedwczoraj w domu?", (MONDAY - timedelta(2),) * 2),
        ("today", "Kto był dziś w salonie?", (MONDAY, MONDAY)),
        ("friday", "Czy Jan był w piątek w salonie?", (date(2026, 11, 6),) * 2),
        ("monday", "Kto był w poniedziałek w salonie?", (MONDAY, MONDAY)),
        ("weekend", "Kto był w weekend w salonie?", (date(2026, 11, 7), date(2026, 11, 8))),
        ("week", "Kto był w tym tygodniu w salonie?", (MONDAY - timedelta(6), MONDAY)),
        (None, "Kiedy ostatnio Kasia była w salonie?", (MONDAY - timedelta(2), MONDAY)),
    ],
    ids=[
        "yesterday",
        "day_before_yesterday",
        "today",
        "last_friday",
        "monday_is_today",
        "last_weekend",
        "last_week",
        "no_day",
    ],
)
def test_days_look_back(when, text, expected) -> None:
    assert past_range(when, text, MONDAY, 3) == expected


def test_weekend_asked_on_saturday_is_this_weekend() -> None:
    saturday = date(2026, 11, 14)
    assert past_range("weekend", "Kto był w weekend?", saturday, 3) == (saturday, saturday)


CAMERAS = {"salon": "Salon", "pokoj_dzieci": "Pokój dzieci", "pokoj_jana": "Pokój Jana"}


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Kto był dziś w salonie?", ["salon"]),
        ("Czy Kasia była w pokoju dzieci?", ["pokoj_dzieci"]),
        ("Czy Jan był wczoraj w pokoju dzieci?", ["pokoj_dzieci"]),
        ("Kiedy ostatnio Kasia była w domu?", ["salon", "pokoj_dzieci", "pokoj_jana"]),
    ],
    ids=["inflected_name", "two_word_name", "person_name_is_not_a_room", "no_room"],
)
def test_cameras_named_in_the_question(text, expected) -> None:
    assert cameras_in_question(CAMERAS, text) == expected


# --- visits ---------------------------------------------------------------------------


def test_events_of_one_person_on_one_camera_join_into_a_visit() -> None:
    found = visits(
        [
            event("salon", 1300, 1400, "Kasia"),  # API order: newest first
            event("salon", 1000, 1100, "Kasia"),
            event("salon", 1050, 1200, "Jan"),
        ],
        gap=120,
    )
    assert [(v["name"], v["start"], v["end"]) for v in found] == [
        ("Kasia", 1000, 1100),
        ("Jan", 1050, 1200),
        ("Kasia", 1300, 1400),
    ]
    joined = visits([event("salon", 1000, 1100, "Kasia"), event("salon", 1150, 1300, "Kasia")], 120)
    assert [(v["start"], v["end"]) for v in joined] == [(1000, 1300)]


def test_visit_still_going_on_stays_open() -> None:
    found = visits([event("salon", 1000, None, "Kasia"), event("salon", 1010, 1020, "Kasia")], 120)
    assert len(found) == 1
    assert found[0]["end"] is None


def test_visit_line_in_local_time() -> None:
    start = datetime(2026, 11, 9, 18, 35, tzinfo=WARSAW).timestamp()
    visit = {"camera": "salon", "name": None, "label": "person", "start": start,
             "end": start + 300}  # fmt: skip
    assert visit_line(visit, {"salon": "Salon"}, False, WARSAW) == (
        f"{LANG.FRIGATE_UNKNOWN} - Salon: 18:35-18:40"
    )
    assert visit_line({**visit, "end": None}, {}, True, WARSAW) == (
        f"{LANG.FRIGATE_UNKNOWN} - salon: 9.11 (poniedziałek) 18:35-{LANG.FRIGATE_NOW}"
    )


# --- the whole question ---------------------------------------------------------------


async def _ask(hass: HomeAssistant, text: str):
    return await conversation.async_converse(
        hass, text, None, Context(), language="pl", agent_id=AGENT_ID
    )


async def _with_cameras_topic(
    hass: HomeAssistant, router: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    path = Path(hass.config.path("assist", "router.yaml"))
    path.write_text(ROUTER_YAML.replace("  wiedza:\n", CAMERAS_TOPIC + "  wiedza:\n"), "utf-8")
    await _with_answer_model(hass, router, aioclient_mock)
    aioclient_mock.post(
        f"{OLLAMA}/api/chat",
        side_effect=_chat_by_model(
            {"bielik-1.5b": _answer("kamery"),
             "gemma-mala": {"message": {"content": "Kasia była wczoraj w salonie."}}}
        ),
    )  # fmt: skip


async def test_question_about_a_person_asks_frigate_for_her_visits(
    hass: HomeAssistant, router: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    await _with_cameras_topic(hass, router, aioclient_mock)
    yesterday = dt_util.now().date() - timedelta(days=1)
    start = datetime.combine(yesterday, datetime.min.time(), dt_util.get_default_time_zone())
    at = (start + timedelta(hours=18, minutes=35)).timestamp()
    aioclient_mock.get(
        re.compile(rf"{FRIGATE}/api/events"), json=[event("salon", at, at + 300, "Kasia")]
    )
    review = {"camera": "salon", "start_time": at,
              "data": {"sub_labels": ["Kasia"],
                       "metadata": {"shortSummary": "Kasia czyta na kanapie."}}}  # fmt: skip
    other = {"camera": "salon", "start_time": at,
             "data": {"sub_labels": ["Jan"], "metadata": {"shortSummary": "Jan gra."}}}  # fmt: skip
    aioclient_mock.get(re.compile(rf"{FRIGATE}/api/review"), json=[other, review])

    result = await _ask(hass, "Czy Kasia była wczoraj w salonie?")

    assert _speech(result) == "Kasia była wczoraj w salonie."
    request = next(c[1] for c in aioclient_mock.mock_calls if "/api/events" in str(c[1]))
    assert request.query["sub_labels"] == "Kasia"
    assert request.query["cameras"] == "salon"  # „w salonie” in the question
    assert request.query["include_thumbnails"] == "0"
    assert request.query["labels"] == "person"
    assert int(request.query["after"]) == int(start.timestamp())
    assert int(request.query["before"]) == int((start + timedelta(days=1)).timestamp())
    data = next(
        c[2] for c in aioclient_mock.mock_calls if c[2] and c[2].get("model") == "gemma-mala"
    )
    content = data["messages"][0]["content"]
    assert f"{LANG.FRIGATE_VISITS}:\nKasia - Salon: 18:35-18:40" in content
    assert f"{LANG.FRIGATE_SUMMARIES}:\nSalon 18:35: Kasia czyta na kanapie." in content
    assert "Jan gra" not in content  # summaries of other people are left out


async def test_frigate_down_is_said_instead_of_no_visits(
    hass: HomeAssistant, router: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    await _with_cameras_topic(hass, router, aioclient_mock)
    aioclient_mock.get(re.compile(rf"{FRIGATE}/api/events"), status=500)

    await _ask(hass, "Kto był dziś w salonie?")

    data = next(
        c[2] for c in aioclient_mock.mock_calls if c[2] and c[2].get("model") == "gemma-mala"
    )
    assert f"{LANG.FRIGATE_VISITS}: {LANG.FRIGATE_UNAVAILABLE}" in data["messages"][0]["content"]
