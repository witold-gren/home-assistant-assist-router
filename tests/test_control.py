"""Control: command parsing, name matching, plan, follow-up questions, execution."""

from __future__ import annotations

import json
from pathlib import Path

from homeassistant.components import conversation
from homeassistant.components.homeassistant.exposed_entities import async_expose_entity
from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers import area_registry as ar, entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_mock_service
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
    AiohttpClientMockResponse,
)

from custom_components.assist_router.control import (
    Command,
    answer_kind,
    build_control_schema,
    collect_home,
    parse_command,
    plan_command,
    resolve_name,
    stems,
)

from .conftest import AGENT_ID, OLLAMA, ROUTER_YAML
from .test_router import _answer, _rows, _speech

CONTROL_TOPIC = """
  sterowanie:
    description: polecenia sterowania urządzeniami
    control: true
"""


def _entity(hass, ent_reg, area_id, entity_id, name, state, aliases=(), **attrs):
    domain, object_id = entity_id.split(".")
    entry = ent_reg.async_get_or_create(domain, "test", object_id, suggested_object_id=object_id)
    ent_reg.async_update_entity(entry.entity_id, area_id=area_id, aliases=set(aliases))
    hass.states.async_set(entity_id, state, {"friendly_name": name, **attrs})
    async_expose_entity(hass, "conversation", entity_id, True)


async def _home(hass: HomeAssistant) -> None:
    """Kitchen: 2 lamps (one with an alias); living room: lamp; hallway: door lock."""
    area_reg, ent_reg = ar.async_get(hass), er.async_get(hass)
    kuchnia = area_reg.async_create("Kuchnia")
    salon = area_reg.async_create("Salon", aliases={"pokój dzienny"})
    korytarz = area_reg.async_create("Korytarz")
    _entity(
        hass, ent_reg, kuchnia.id, "light.kuchnia_sufit", "Kuchnia Sufit", "on", brightness=128,
        supported_color_modes=["color_temp", "xy"],
    )  # fmt: skip
    _entity(
        hass, ent_reg, kuchnia.id, "light.kuchnia_blat", "Oświetlenie blatu", "on",
        aliases=["lampka przy blacie"], brightness=255, supported_color_modes=["color_temp"],
    )  # fmt: skip
    _entity(
        hass, ent_reg, salon.id, "light.salon_lampa", "Lampa stojąca", "off",
        supported_color_modes=["onoff"],
    )  # fmt: skip
    _entity(hass, ent_reg, korytarz.id, "lock.drzwi", "Drzwi wejściowe", "locked")
    hass.states.async_set("light.ukryta", "on", {"friendly_name": "Ukryta"})
    async_expose_entity(hass, "conversation", "light.ukryta", False)  # not exposed


# --- functions ---


def test_stems() -> None:
    assert stems("Lampkę przy biurku!") == ["lamp", "przy", "biur"]
    assert stems("Oświetlenie blatu") == stems("oswietlenie blatem")


async def test_collect_and_resolve(hass: HomeAssistant, setup) -> None:
    await _home(hass)
    home = collect_home(hass)
    assert {t.entity_id for t in home.targets} == {
        "light.kuchnia_sufit", "light.kuchnia_blat", "light.salon_lampa", "lock.drzwi",
    }  # fmt: skip
    assert home.areas["pokój dzienny"] == "Salon"
    assert set(build_control_schema(home)["properties"]["domena"]["enum"]) == {
        "light",
        "lock",
        None,
    }

    match = resolve_name(home, "lampkę przy blacie", Command("HassTurnOn", domain="light"))
    assert match.target.entity_id == "light.kuchnia_blat" and match.score == 1.0
    # the room name in the device name need not be said: „sufit” -> „Kuchnia Sufit”
    match = resolve_name(home, "sufit", Command("HassTurnOn", domain="light"))
    assert match.target.entity_id == "light.kuchnia_sufit" and not match.ambiguous
    assert resolve_name(home, "telewizor", Command("HassTurnOn")).target is None


async def test_parse_and_plan(hass: HomeAssistant, setup) -> None:
    await _home(hass)
    home = collect_home(hass)
    command = parse_command(
        home,
        json.dumps(
            {"intencja": "HassTurnOff", "domena": "light", "obszar": "pokój dzienny",
             "pietro": None, "nazwa": None, "wszystkie": False, "wartosc": None,
             "zmiana": None, "element": None}
        ),
    )  # fmt: skip
    assert command.area == "Salon"  # area alias -> name
    plan = plan_command(hass, home, command)
    assert plan.slots == {"area": "Salon", "domain": ["light"]} and not plan.confirm

    # „zrób jaśniej w kuchni”: average (50% + 100%) / 2 = 75% -> +25 = 100%
    plan = plan_command(
        hass, home, Command("HassLightSet", domain="light", area="Kuchnia", change="więcej")
    )
    assert plan.slots["brightness"] == 100

    # a lock always asks
    # a lock always asks; in HA „otwórz zamek” = HassTurnOff (lock.unlock)
    plan = plan_command(hass, home, Command("HassTurnOff", domain="lock", name="drzwi wejściowe"))
    assert plan.confirm.startswith("urządzenie wrażliwe") and plan.slots == {
        "name": "Drzwi wejściowe"
    }
    assert plan.description == "otworzyć Drzwi wejściowe" and plan.domain == "lock"

    # unknown device without a room or kind - a message, nothing is executed
    plan = plan_command(hass, home, Command("HassTurnOn", name="robot kuchenny"))
    assert plan.error == "Nie znalazłem urządzenia „robot kuchenny”."


def test_answer_kind() -> None:
    for text in ("Tak", "tak, zrób to", "Zrób!", "rób", "dawaj", "Okej."):
        assert answer_kind(text) == "yes", text
    for text in ("Nie.", "nie rób", "nie trzeba", "zostaw", "anuluj"):
        assert answer_kind(text) == "no", text
    # the verb depends on the question (and on the domain: lock, covers)
    assert answer_kind("otwórz", "HassTurnOff", "lock") == "yes"
    assert answer_kind("zamknij", "HassTurnOff", "lock") == "no"
    assert answer_kind("otwórz", "HassTurnOn", "cover") == "yes"
    assert answer_kind("Włącz", "HassTurnOn") == "yes"
    assert answer_kind("wyłącz", "HassTurnOn") == "no"
    assert answer_kind("wyłącz to", "HassTurnOff") == "yes"
    assert answer_kind("zapal", "HassTurnOff") == "no"
    # no known question or a longer sentence - a new command
    assert answer_kind("wyłącz") is None
    assert answer_kind("włącz światło w salonie", "HassTurnOn") is None
    assert answer_kind("może jutro", "HassTurnOn") is None


# --- agent: command -> execution or question ---


def _control_ollama(aioclient_mock: AiohttpClientMocker, parsed: dict) -> None:
    """Router: topic sterowanie; second request (schema with „intencja”): parsing."""

    async def handler(method, url, data):
        if "intencja" in json.dumps(data.get("format", {})):
            content = {"intencja": None, "domena": None, "obszar": None, "pietro": None,
                       "nazwa": None, "wszystkie": False, "wartosc": None, "zmiana": None,
                       "element": None, "kolor": None, "barwa": None, "szukaj": None,
                       "rodzaj": None, "wykonawca": None, "radio": False} | parsed  # fmt: skip
            return AiohttpClientMockResponse(
                method, url, json={"message": {"content": json.dumps(content)}}
            )
        question = data["messages"][-1]["content"]
        topic = "inne" if "pogod" in question else "sterowanie"
        return AiohttpClientMockResponse(method, url, json=_answer(topic))

    aioclient_mock.post(f"{OLLAMA}/api/chat", side_effect=handler)


async def _ask(hass: HomeAssistant, text: str, conversation_id: str | None = None):
    return await conversation.async_converse(
        hass, text, conversation_id, Context(), language="pl", agent_id=AGENT_ID
    )


async def _with_control(hass: HomeAssistant, router: MockConfigEntry) -> None:
    path = Path(hass.config.path("assist", "router.yaml"))
    path.write_text(ROUTER_YAML.replace("  inne:\n", CONTROL_TOPIC + "  inne:\n"), encoding="utf-8")
    await _home(hass)


async def test_control_executes(
    hass: HomeAssistant, router: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    await _with_control(hass, router)
    calls = async_mock_service(hass, "light", "turn_off")
    _control_ollama(
        aioclient_mock, {"intencja": "HassTurnOff", "domena": "light", "obszar": "Kuchnia"}
    )

    result = await _ask(hass, "zgaś światło w kuchni")

    switched = set()
    for call in calls:
        ids = call.data["entity_id"]
        switched |= set(ids if isinstance(ids, list) else [ids])
    assert switched == {"light.kuchnia_sufit", "light.kuchnia_blat"}
    assert _speech(result).startswith("Wyłączono")
    row = _rows(hass)[0]
    assert row["route"].startswith(
        'sterowanie → HassTurnOff {"area": "Kuchnia", "domain": ["light"]}'
    )


async def test_control_confirm_yes_and_no(
    hass: HomeAssistant, router: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    await _with_control(hass, router)
    unlock = async_mock_service(hass, "lock", "unlock")
    _control_ollama(aioclient_mock, {"intencja": "HassTurnOff", "domena": "lock", "nazwa": "drzwi"})

    question = await _ask(hass, "otwórz drzwi")
    assert _speech(question) == "Czy otworzyć Drzwi wejściowe?"
    assert question.continue_conversation is True
    assert "pytanie: urządzenie wrażliwe" in _rows(hass)[0]["route"]
    assert not unlock

    done = await _ask(hass, "tak, zrób to", question.conversation_id)
    assert len(unlock) == 1 and _speech(done).startswith("Otwarto")

    # second time: „nie rób” - nothing happens
    question = await _ask(hass, "otwórz drzwi")
    cancelled = await _ask(hass, "nie rób", question.conversation_id)
    assert _speech(cancelled) == "Dobrze, nic nie zmieniam." and len(unlock) == 1


async def test_control_other_answer_drops_question(
    hass: HomeAssistant, router: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """A different reply to a question - the question is dropped, the sentence runs normally."""
    await _with_control(hass, router)
    unlock = async_mock_service(hass, "lock", "unlock")
    _control_ollama(aioclient_mock, {"intencja": "HassTurnOff", "domena": "lock", "nazwa": "drzwi"})

    question = await _ask(hass, "otwórz drzwi")
    await _ask(hass, "jaka jest pogoda w kosmosie", question.conversation_id)
    late_yes = await _ask(hass, "tak", question.conversation_id)

    assert not unlock
    assert not _speech(late_yes).startswith("Otwarto")


async def test_control_whisper_error_asks(
    hass: HomeAssistant, router: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """„Jaś światło w kuchni” (Whisper) - we guess „zgaś”, but ask first."""
    await _with_control(hass, router)
    calls = async_mock_service(hass, "light", "turn_off")
    _control_ollama(
        aioclient_mock, {"intencja": "HassTurnOff", "domena": "light", "obszar": "Kuchnia"}
    )

    question = await _ask(hass, "Jaś światło w kuchni.")
    assert _speech(question).startswith("Czy dobrze rozumiem, że mam wyłączyć")
    assert "rozumiem jako „zgaś”" in _rows(hass)[0]["route"]
    # the model already got the corrected command
    sent = [
        c[2] for c in aioclient_mock.mock_calls if "intencja" in json.dumps(c[2].get("format", {}))
    ]
    assert sent[0]["messages"][-1]["content"] == "zgaś światło w kuchni."
    assert not calls

    await _ask(hass, "tak", question.conversation_id)
    assert calls


def test_prepare_text() -> None:
    from custom_components.assist_router.control import prepare_text

    assert prepare_text("Otwórz czystkę rolety") == ("Otwórz wszystkie rolety", [])
    text, doubts = prepare_text("Jaś światło w kuchni")
    assert text == "zgaś światło w kuchni" and doubts == ["„jaś” rozumiem jako „zgaś”"]
    assert prepare_text("Lodówka w kuchni")[1] == ["brak znanego czasownika"]


async def test_find_target_checks_area_and_text(hass: HomeAssistant, setup) -> None:
    """An area not said in the command is skipped; weak fragment - the whole command."""
    from custom_components.assist_router.control import find_target

    await _home(hass)
    home = collect_home(hass)
    command = Command("HassTurnOff", domain="light", area="Salon", name="lampkę")
    match = find_target(home, command, "zgaś lampkę przy blacie")
    assert command.area is None  # „Salon” was not said in the command
    assert match.target.entity_id == "light.kuchnia_blat"  # alias „lampka przy blacie”
    # an inflected area alias counts („pokój dzienny”)
    command = Command("HassTurnOff", domain="light", area="Salon")
    find_target(home, command, "zgaś światło w pokój dzienny")
    assert command.area == "Salon"


async def test_bare_answer_is_not_a_command(
    hass: HomeAssistant, router: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """„nie rób” without an open question does not reach control."""
    await _with_control(hass, router)
    _control_ollama(aioclient_mock, {"intencja": "HassTurnOff"})

    result = await _ask(hass, "nie rób")

    assert not _speech(result).startswith("Czy")
    assert _rows(hass)[0]["route"] == "sterowanie (sama odpowiedź tak/nie)"


# --- light color and color temperature, „puść …”, the „always ask” list ---


async def test_light_color_and_white(hass: HomeAssistant, setup) -> None:
    await _home(hass)
    home = collect_home(hass)
    command = parse_command(
        home,
        json.dumps(
            {"intencja": "HassLightSet", "domena": None, "obszar": "Kuchnia", "pietro": None,
             "nazwa": None, "wszystkie": False, "wartosc": None, "zmiana": None,
             "element": None, "kolor": "czerwony", "barwa": None, "szukaj": None,
             "rodzaj": None}
        ),
    )  # fmt: skip
    plan = plan_command(hass, home, command)
    # color without brightness; light domain added although the model did not give it
    assert plan.slots == {"area": "Kuchnia", "domain": ["light"], "color": "red"}
    assert plan.description == "ustawić światło w pomieszczeniu Kuchnia na kolor czerwony"

    plan = plan_command(
        hass, home, Command("HassLightSet", domain="light", area="Kuchnia", white="ciepła")
    )
    assert plan.slots["temperature"] == 2700 and not plan.error

    # on/off-only lamp - neither color nor color temperature
    for command in (
        Command("HassLightSet", name="lampa stojąca", color="niebieski"),
        Command("HassLightSet", name="lampa stojąca", white="zimna"),
    ):
        assert plan_command(hass, home, command).error.startswith("To światło nie zmienia")


def test_done_speech_color() -> None:
    from custom_components.assist_router.control import done_speech

    assert done_speech("HassLightSet", ["Kuchnia Sufit"], {"color": "red"}) == (
        "Ustawiono kolor czerwony: kuchnia sufit."
    )
    assert done_speech("HassLightSet", [], {"temperature": 2700}) == "Ustawiono barwę ciepła."


async def test_always_confirm_list(hass: HomeAssistant, setup) -> None:
    await _home(hass)
    area_reg, ent_reg = ar.async_get(hass), er.async_get(hass)
    kuchnia = area_reg.async_get_area_by_name("Kuchnia")
    _entity(hass, ent_reg, kuchnia.id, "switch.lodowka", "Lodówka", "on")
    home = collect_home(hass)

    by_name = plan_command(
        hass, home, Command("HassTurnOff", name="lodówkę"), confirm_entities=("Lodówka",)
    )
    by_pattern = plan_command(
        hass, home, Command("HassTurnOff", domain="switch", area="Kuchnia"),
        confirm_entities=("switch.lod*",),
    )  # fmt: skip
    assert by_name.confirm == by_pattern.confirm == "urządzenie z listy potwierdzeń"
    # without the list - at once
    assert not plan_command(hass, home, Command("HassTurnOff", name="lodówkę")).confirm


async def _players(hass: HomeAssistant) -> None:
    """Players without an area (as in Music Assistant): one available, one not."""
    ent_reg = er.async_get(hass)
    features = 4194304 | 512  # SEARCH_MEDIA | PLAY_MEDIA
    _entity(
        hass, ent_reg, None, "media_player.salon_homepod", "Salon HomePod", "unavailable",
        supported_features=features,
    )  # fmt: skip
    _entity(
        hass, ent_reg, None, "media_player.salon_voice", "Salon Voice", "idle",
        supported_features=features,
    )  # fmt: skip


async def test_play_picks_player(hass: HomeAssistant, setup) -> None:
    await _home(hass)
    await _players(hass)
    home = collect_home(hass)
    play = Command("HassMediaSearchAndPlay", area="Salon", query="Dawid Podsiadło",
                   media_class="wykonawca")  # fmt: skip

    # list from router.yaml: HomePod unavailable - the next one
    plan = plan_command(
        hass, home, play, "puść Dawida Podsiadło w salonie",
        music_players={"pokój dzienny": ("media_player.salon_homepod", "media_player.salon_voice")},
    )  # fmt: skip
    assert plan.slots == {
        "search_query": "Dawid Podsiadło", "entity_id": "media_player.salon_voice",
        "media_class": "artist",
    }  # fmt: skip
    # without the list - by the room name in the player name
    plan = plan_command(hass, home, play, "puść Dawida Podsiadło w salonie")
    assert plan.slots["entity_id"] == "media_player.salon_voice"
    # no room in the command - the satellite's room
    plan = plan_command(
        hass, home, Command("HassMediaSearchAndPlay", query="jazz"), "puść jazz", here="Salon"
    )
    assert plan.slots["entity_id"] == "media_player.salon_voice"
    # neither room nor satellite; no title
    assert (
        plan_command(hass, home, Command("HassMediaSearchAndPlay", query="jazz"), "puść jazz").error
        == "W którym pomieszczeniu mam puścić?"
    )
    assert (
        plan_command(
            hass, home, Command("HassMediaSearchAndPlay", area="Salon"), "puść coś w salonie"
        ).error
        == "Co mam puścić?"
    )
    # list with only the HomePod, which is unavailable - no other speaker, just a message
    plan = plan_command(
        hass, home, play, "puść Dawida Podsiadło w salonie",
        music_players={"pokój dzienny": ("media_player.salon_homepod",)},
    )  # fmt: skip
    assert plan.error == (
        "W pomieszczeniu Salon nie ma teraz głośnika, na którym mogę puścić muzykę."
    )


async def test_control_plays_music(
    hass: HomeAssistant, router: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    from homeassistant.core import SupportsResponse

    await _with_control(hass, router)
    await _players(hass)
    search = async_mock_service(
        hass, "media_player", "search_media",
        response={"media_player.salon_voice": {"result": [
            {"title": "Małomiasteczkowy", "media_content_id": "library://album/1",
             "media_content_type": "album"},
        ]}},
        supports_response=SupportsResponse.ONLY,
    )  # fmt: skip
    play = async_mock_service(hass, "media_player", "play_media")
    _control_ollama(
        aioclient_mock,
        {"intencja": "HassMediaSearchAndPlay", "obszar": "Salon",
         "szukaj": "Małomiasteczkowy", "rodzaj": "album"},
    )  # fmt: skip

    result = await _ask(hass, "puść album Małomiasteczkowy w salonie")

    assert search[0].data["search_query"] == "Małomiasteczkowy"
    assert search[0].data["media_filter_classes"] == ["album"]
    assert play[0].data["media_content_id"] == "library://album/1"
    assert _speech(result) == "Puszczam Małomiasteczkowy na Salon Voice."


async def test_control_plays_music_with_music_assistant(
    hass: HomeAssistant, router: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """Music Assistant player: music_assistant.play_media (type, artist, radio);
    when MA reports an error - the previous search_media + play_media."""
    from homeassistant.core import SupportsResponse
    from homeassistant.exceptions import HomeAssistantError

    await _with_control(hass, router)
    ent_reg = er.async_get(hass)
    entry = ent_reg.async_get_or_create(
        "media_player", "music_assistant", "ap123", suggested_object_id="salon_homepod_muzyka"
    )
    hass.states.async_set(
        entry.entity_id, "idle",
        {"friendly_name": "Salon HomePod", "supported_features": 4194304 | 512},
    )  # fmt: skip
    ma_calls = []
    fail = {"now": False}

    async def ma_play(call):
        ma_calls.append(dict(call.data))
        if fail["now"]:
            raise HomeAssistantError("nie znaleziono")

    hass.services.async_register("music_assistant", "play_media", ma_play)
    search = async_mock_service(
        hass, "media_player", "search_media",
        response={entry.entity_id: {"result": [
            {"title": "Małomiasteczkowy", "media_content_id": "library://track/1",
             "media_content_type": "track"},
        ]}},
        supports_response=SupportsResponse.ONLY,
    )  # fmt: skip
    play = async_mock_service(hass, "media_player", "play_media")
    async_expose_entity(hass, "conversation", entry.entity_id, True)  # room from the name

    _control_ollama(
        aioclient_mock,
        {"intencja": "HassMediaSearchAndPlay", "obszar": "Salon", "szukaj": "Małomiasteczkowy",
         "rodzaj": "utwór", "wykonawca": "Dawid Podsiadło", "radio": False},
    )  # fmt: skip
    result = await _ask(hass, "puść Małomiasteczkowy Dawida Podsiadło w salonie")
    assert ma_calls[-1] == {
        "entity_id": entry.entity_id, "media_id": "Małomiasteczkowy", "media_type": "track",
        "artist": "Dawid Podsiadło",
    }  # fmt: skip
    assert not search
    assert _speech(result) == "Puszczam Małomiasteczkowy (Dawid Podsiadło) na Salon HomePod."

    # radio mode and MA reports an error - plain HA search
    fail["now"] = True
    aioclient_mock.clear_requests()
    _control_ollama(
        aioclient_mock,
        {"intencja": "HassMediaSearchAndPlay", "obszar": "Salon", "szukaj": "Dawid Podsiadło",
         "rodzaj": "wykonawca", "wykonawca": None, "radio": True},
    )  # fmt: skip
    result = await _ask(hass, "puść coś w stylu Dawida Podsiadło w salonie")
    assert ma_calls[-1]["radio_mode"] is True and ma_calls[-1]["media_type"] == "artist"
    assert search[0].data["search_query"] == "Dawid Podsiadło"
    assert play[0].data["media_content_id"] == "library://track/1"


async def test_named_routine(hass: HomeAssistant, setup) -> None:
    from custom_components.assist_router.control import done_speech, named_routine, routine_plan

    await _home(hass)
    ent_reg = er.async_get(hass)
    _entity(
        hass, ent_reg, None, "script.opusc_rolety_salon", "Opuść rolety wewnętrzne w salonie",
        "off",
    )  # fmt: skip
    _entity(hass, ent_reg, None, "scene.zamkniecie_rolet", "Zamknięcie rolet", "unknown")
    home = collect_home(hass)

    for text in (
        "Opuść rolety wewnętrzne w salonie.",
        "uruchom skrypt opuść rolety wewnętrzne w salonie",
    ):
        assert named_routine(home, text).entity_id == "script.opusc_rolety_salon", text
    # other words or a too short name (2 words) - regular control
    assert named_routine(home, "opuść rolety w salonie") is None
    assert named_routine(home, "zamknięcie rolet") is None

    plan = routine_plan(named_routine(home, "Opuść rolety wewnętrzne w salonie"))
    assert plan.slots == {"name": "Opuść rolety wewnętrzne w salonie"} and not plan.confirm
    assert done_speech(
        "HassTurnOn", ["Opuść rolety wewnętrzne w salonie"], plan.slots, "script"
    ) == ("Uruchomiono: opuść rolety wewnętrzne w salonie.")


async def test_control_runs_named_script(
    hass: HomeAssistant, router: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    await _with_control(hass, router)
    ent_reg = er.async_get(hass)
    _entity(
        hass, ent_reg, None, "script.opusc_rolety_salon", "Opuść rolety wewnętrzne w salonie",
        "off",
    )  # fmt: skip
    calls = async_mock_service(hass, "script", "turn_on")
    _control_ollama(aioclient_mock, {"intencja": "HassTurnOff", "domena": "cover"})

    result = await _ask(hass, "Opuść rolety wewnętrzne w salonie")

    assert calls and _speech(result).startswith("Uruchomiono")
    # no parsing by the model
    assert not any(
        "intencja" in json.dumps(c[2].get("format", {})) for c in aioclient_mock.mock_calls
    )


async def test_alarm_never_goes_to_control(
    hass: HomeAssistant, router: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """Alarm command without a matching automation - a hint, no parsing and no action."""
    await _with_control(hass, router)
    scene = async_mock_service(hass, "scene", "turn_on")
    _control_ollama(aioclient_mock, {"intencja": "HassTurnOn", "domena": "scene"})

    result = await _ask(hass, "aktywuj alarm w trybie domowym proszę")

    assert _speech(result).startswith("Alarmem steruję tylko")
    assert not scene
    assert not any(
        "intencja" in json.dumps(c[2].get("format", {})) for c in aioclient_mock.mock_calls
    )
    assert _rows(hass)[0]["route"] == "sterowanie (alarm)"


# --- actions (scripts) and „czy dobrze rozumiem?” ---

KAWA = {
    "alias": "Ekspres - zrób kawę",
    "description": "Włącza ekspres, czeka na gotowość i parzy kawę.",
    "fields": {"satelita": {"selector": {"entity": {"domain": "assist_satellite"}}}},
    "sequence": [
        {"event": "kawa_test", "event_data": {"satelita": "{{ satelita | default('') }}"}}
    ],
}


async def _with_coffee(hass: HomeAssistant, router: MockConfigEntry) -> None:
    from homeassistant.setup import async_setup_component

    await _with_control(hass, router)
    assert await async_setup_component(hass, "script", {"script": {"kawa": KAWA}})
    await hass.async_block_till_done()
    async_expose_entity(hass, "conversation", "script.kawa", True)


async def test_coffee_misheard_asks_and_runs_script_with_satellite(
    hass: HomeAssistant, router: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """„Zapasz kawę” (Whisper) - the model picks a script by its description, the assistant
    asks, „tak” brews, and the script gets the speaker the command came from."""
    await _with_coffee(hass, router)
    events = []
    hass.bus.async_listen("kawa_test", events.append)
    _control_ollama(
        aioclient_mock,
        {"intencja": "HassTurnOn", "domena": "script", "nazwa": "Ekspres - zrób kawę"},
    )

    question = await _ask(hass, "Zapasz kawę!")
    prompt = next(
        c[2] for c in aioclient_mock.mock_calls if "intencja" in json.dumps(c[2].get("format", {}))
    )["messages"][0]["content"]
    assert "„Ekspres - zrób kawę” - Włącza ekspres" in prompt
    assert _speech(question) == "Czy dobrze rozumiem, że mam uruchomić Ekspres - zrób kawę?"
    assert question.continue_conversation is True

    done = await conversation.async_converse(
        hass, "tak", question.conversation_id, Context(), language="pl", agent_id=AGENT_ID,
        satellite_id="assist_satellite.kuchnia",
    )  # fmt: skip
    await hass.async_block_till_done()
    assert _speech(done) == "Uruchomiono: ekspres - zrób kawę."
    assert events[0].data["satelita"] == "assist_satellite.kuchnia"


async def test_doubt_no_asks_to_repeat_cancel_ends(
    hass: HomeAssistant, router: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """„Nie” to „czy dobrze rozumiem?” - a request to repeat (conversation goes on);
    „anuluj” - the end. To „czy na pewno?” (lock) „nie” = we do nothing."""
    await _with_coffee(hass, router)
    events = []
    hass.bus.async_listen("kawa_test", events.append)
    _control_ollama(
        aioclient_mock,
        {"intencja": "HassTurnOn", "domena": "script", "nazwa": "Ekspres - zrób kawę"},
    )

    question = await _ask(hass, "Zapasz kawę")
    again = await _ask(hass, "nie", question.conversation_id)
    assert _speech(again) == "Przepraszam, źle zrozumiałem. Powtórz, proszę."
    assert again.continue_conversation is True

    question = await _ask(hass, "Zapasz kawę")
    cancelled = await _ask(hass, "anuluj", question.conversation_id)
    assert _speech(cancelled) == "Dobrze, nic nie zmieniam."
    assert not cancelled.continue_conversation
    await hass.async_block_till_done()
    assert not events


async def test_scene_listed_with_its_members(
    hass: HomeAssistant, router: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """Scenes have no description - the model gets a list of what the scene sets."""
    await _with_control(hass, router)
    ent_reg = er.async_get(hass)
    _entity(hass, ent_reg, None, "scene.wieczor", "Wieczór", "unknown")
    hass.states.async_set(
        "scene.wieczor", "unknown",
        {"friendly_name": "Wieczór", "entity_id": ["light.kuchnia_sufit", "light.salon_lampa"]},
    )  # fmt: skip
    _control_ollama(
        aioclient_mock, {"intencja": "HassTurnOn", "domena": "scene", "nazwa": "Wieczór"}
    )

    await _ask(hass, "zrób wieczorny nastrój")

    prompt = next(
        c[2] for c in aioclient_mock.mock_calls if "intencja" in json.dumps(c[2].get("format", {}))
    )["messages"][0]["content"]
    assert "„Wieczór” - scena - ustawia: Kuchnia Sufit, Lampa stojąca" in prompt


def test_bare_answer_vs_command() -> None:
    from custom_components.assist_router.control import is_bare_answer

    for text in ("tak", "Tak, zrób to.", "zrób to proszę", "nie rób", "Nie, dzięki", "dawaj"):
        assert is_bare_answer(text), text
    for text in ("Zrób jaśniej w salonie", "zrób ciepłe światło", "nie zapalaj światła w kuchni"):
        assert not is_bare_answer(text), text


async def test_ambiguous_strong_match_not_replaced_by_other_device(
    hass: HomeAssistant, setup
) -> None:
    """„roletą wewnętrzną okno”: two inner covers match (a question), and the outer
    „Roleta okno”, though its words were said in the command, cannot replace them."""
    from custom_components.assist_router.control import find_target

    area_reg, ent_reg = ar.async_get(hass), er.async_get(hass)
    salon = area_reg.async_create("Salon")
    _entity(hass, ent_reg, salon.id, "cover.okno", "Salon Roleta Okno", "open")
    for size in ("male", "duze"):
        _entity(
            hass, ent_reg, salon.id, f"cover.dn_okno_{size}", f"Salon Roleta Okno {size}", "open",
            aliases=[f"Roleta wewnętrzna okno {size}"],
        )  # fmt: skip
    home = collect_home(hass)
    command = Command("HassTurnOff", domain="cover", area="Salon", name="roletą wewnętrzną okno")

    match = find_target(home, command, "Zasłoń roletą wewnętrzną okno w salonie")

    assert match.target.entity_id.startswith("cover.dn_okno_") and match.ambiguous
