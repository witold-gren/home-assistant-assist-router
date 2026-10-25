"""Control from a sentence to the called service: every intent, actions (scripts, scenes),
„czy dobrze rozumiem?” and „czy na pewno?” questions with answers, errors and safeguards.

Only the model (command parsing) and device services are mocked - HA intents
(target matching, exposure, device features) run for real.
"""

from __future__ import annotations

from pathlib import Path

from homeassistant.components import conversation
from homeassistant.components.climate import ClimateEntityFeature
from homeassistant.components.cover import CoverEntityFeature
from homeassistant.components.media_player import MediaPlayerEntityFeature as MP
from homeassistant.components.vacuum import VacuumEntityFeature
from homeassistant.core import Context, HomeAssistant, SupportsResponse
from homeassistant.helpers import (
    area_registry as ar,
    entity_registry as er,
    floor_registry as fr,
)
from homeassistant.setup import async_setup_component
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_mock_service
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.assist_router import conversation as agent_module

from .conftest import AGENT_ID, ROUTER_YAML
from .test_control import CONTROL_TOPIC, _control_ollama, _entity
from .test_router import _rows, _speech

UNCLEAR_TOPIC = """
  niezrozumiale:
    description: zdanie bez sensu - błąd rozpoznawania mowy
    unclear: true
"""
SETTINGS = """
confirm_entities:
  - switch.lodowka
  - scene.dobranoc
music_players:
  Salon: [media_player.salon_glosnik]
"""

KAWA = {
    "alias": "Ekspres - zrób kawę",
    "description": "Parzy kawę: włącza ekspres, czeka na gotowość i robi kawę.",
    "fields": {"satelita": {"selector": {"entity": {"domain": "assist_satellite"}}}},
    "sequence": [{"event": "skrypt", "event_data": {"kto": "kawa", "satelita": "{{ satelita | default('') }}"}}],
}  # fmt: skip
ROLETY_TV = {
    "alias": "Opuść rolety do oglądania TV",
    "description": "Przymyka rolety w salonie do oglądania telewizji.",
    "sequence": [{"event": "skrypt", "event_data": {"kto": "rolety_tv"}}],
}

# services we record (HA intents really call them)
SERVICES = [
    ("light", "turn_on"), ("light", "turn_off"), ("switch", "turn_on"), ("switch", "turn_off"),
    ("cover", "open_cover"), ("cover", "close_cover"), ("cover", "set_cover_position"),
    ("lock", "lock"), ("lock", "unlock"), ("climate", "set_temperature"),
    ("media_player", "media_pause"), ("media_player", "media_play"),
    ("media_player", "media_next_track"), ("media_player", "media_previous_track"),
    ("media_player", "volume_set"), ("media_player", "play_media"),
    ("vacuum", "start"), ("vacuum", "return_to_base"), ("scene", "turn_on"),
]  # fmt: skip
PLAYER = (
    MP.PAUSE | MP.PLAY | MP.VOLUME_SET | MP.NEXT_TRACK | MP.PREVIOUS_TRACK | MP.SEARCH_MEDIA
    | MP.PLAY_MEDIA
)  # fmt: skip


@pytest.fixture
async def dom(hass: HomeAssistant, router: MockConfigEntry) -> dict:
    """Home: Kuchnia and Salon (ground floor), Sypialnia, Garaż; one device of each kind.

    Returns a dict of service calls: {"light.turn_off": [ServiceCall, ...], ...}.
    """
    from homeassistant.components.climate.intent import async_setup_intents as climate_intents
    from homeassistant.components.cover.intent import async_setup_intents as cover_intents
    from homeassistant.components.light.intent import async_setup_intents as light_intents
    from homeassistant.components.media_player.intent import async_setup_intents as media_intents
    from homeassistant.components.vacuum.intent import async_setup_intents as vacuum_intents

    for setup_intents in (
        light_intents,
        cover_intents,
        climate_intents,
        media_intents,
        vacuum_intents,
    ):
        await setup_intents(hass)
    path = Path(hass.config.path("assist", "router.yaml"))
    path.write_text(
        ROUTER_YAML.replace("topics:", SETTINGS + "topics:", 1).replace(
            "  inne:\n", CONTROL_TOPIC + UNCLEAR_TOPIC + "  inne:\n"
        ),
        encoding="utf-8",
    )
    area_reg, ent_reg, floor_reg = ar.async_get(hass), er.async_get(hass), fr.async_get(hass)
    parter = floor_reg.async_create("Parter")
    kuchnia = area_reg.async_create("Kuchnia", floor_id=parter.floor_id)
    salon = area_reg.async_create("Salon", aliases={"pokój dzienny"}, floor_id=parter.floor_id)
    sypialnia = area_reg.async_create("Sypialnia")
    garaz = area_reg.async_create("Garaż")
    e = _entity  # (hass, ent_reg, area_id, entity_id, name, state, aliases=(), **attributes)
    e(hass, ent_reg, kuchnia.id, "light.kuchnia_sufit", "Kuchnia Sufit", "on", brightness=128,
      supported_color_modes=["color_temp", "xy"])  # fmt: skip
    e(hass, ent_reg, salon.id, "light.salon_lampa", "Lampa stojąca", "off",
      supported_color_modes=["onoff"])  # fmt: skip
    e(hass, ent_reg, sypialnia.id, "light.sypialnia_nocna", "Lampka nocna", "off",
      supported_color_modes=["color_temp"])  # fmt: skip
    e(hass, ent_reg, salon.id, "cover.salon_roleta", "Roleta salon", "open", current_position=40,
      device_class="blind", supported_features=CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE
      | CoverEntityFeature.SET_POSITION)  # fmt: skip
    e(hass, ent_reg, garaz.id, "cover.garaz_brama", "Brama garażowa", "closed",
      device_class="garage", supported_features=CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE)  # fmt: skip
    e(hass, ent_reg, salon.id, "lock.drzwi", "Drzwi wejściowe", "locked")
    e(hass, ent_reg, salon.id, "climate.salon", "Termostat salon", "heat", temperature=21,
      current_temperature=20.5, supported_features=ClimateEntityFeature.TARGET_TEMPERATURE)  # fmt: skip
    e(hass, ent_reg, salon.id, "media_player.salon_glosnik", "Głośnik salon", "playing",
      volume_level=0.3, supported_features=PLAYER)  # fmt: skip
    e(hass, ent_reg, None, "vacuum.robot", "Robot", "docked",
      supported_features=VacuumEntityFeature.START | VacuumEntityFeature.RETURN_HOME)  # fmt: skip
    e(hass, ent_reg, kuchnia.id, "switch.lodowka", "Lodówka", "on")
    e(hass, ent_reg, salon.id, "switch.akwarium", "Akwarium", "on")
    e(hass, ent_reg, None, "scene.wieczor", "Wieczór", "unknown")
    e(hass, ent_reg, None, "scene.dobranoc", "Dobranoc", "unknown")
    # scene attribute „entity_id” (what it sets) - separately, it clashes with the _entity param
    hass.states.async_set(
        "scene.wieczor",
        "unknown",
        {"friendly_name": "Wieczór", "entity_id": ["light.salon_lampa", "cover.salon_roleta"]},
    )
    hass.states.async_set(
        "scene.dobranoc", "unknown", {"friendly_name": "Dobranoc", "entity_id": ["lock.drzwi"]}
    )
    hass.states.async_set(
        "light.ukryta", "on", {"friendly_name": "Ukryta lampa"}
    )  # not exposed to Assist

    assert await async_setup_component(
        hass, "script", {"script": {"kawa": KAWA, "rolety_tv": ROLETY_TV}}
    )
    await hass.async_block_till_done()
    from homeassistant.components.homeassistant.exposed_entities import async_expose_entity

    for script in ("script.kawa", "script.rolety_tv"):
        async_expose_entity(hass, "conversation", script, True)
    async_expose_entity(hass, "conversation", "light.ukryta", False)  # not exposed

    calls = {f"{d}.{s}": async_mock_service(hass, d, s) for d, s in SERVICES}
    calls["media_player.search_media"] = async_mock_service(
        hass, "media_player", "search_media",
        response={"media_player.salon_glosnik": {"result": [
            {"title": "Jazz na wieczór", "media_content_id": "lib://1", "media_content_type": "playlist"},
        ]}},
        supports_response=SupportsResponse.ONLY,
    )  # fmt: skip
    events: list = []
    hass.bus.async_listen("skrypt", events.append)
    calls["skrypt"] = events
    return calls


async def _say(
    hass: HomeAssistant, text: str, conversation_id: str | None = None, satellite: str | None = None
):
    return await conversation.async_converse(
        hass, text, conversation_id, Context(), language="pl", agent_id=AGENT_ID,
        satellite_id=satellite,
    )  # fmt: skip


def _entities(calls) -> set[str]:
    found = set()
    for call in calls:
        ids = call.data.get("entity_id", [])
        found |= set(ids if isinstance(ids, list) else [ids])
    return found


def _called(dom: dict) -> dict[str, int]:
    return {name: len(c) for name, c in dom.items() if c}


# --- commands executed immediately: every intent ---

DIRECT = [
    # (sentence, model parse, service, entities, data check, reply prefix)
    ("zgaś światło w kuchni", {"intencja": "HassTurnOff", "domena": "light", "obszar": "Kuchnia"},
     "light.turn_off", {"light.kuchnia_sufit"}, None, "Wyłączono"),
    ("zapal lampę stojącą w salonie",
     {"intencja": "HassTurnOn", "domena": "light", "obszar": "Salon", "nazwa": "lampę stojącą"},
     "light.turn_on", {"light.salon_lampa"}, None, "Włączono"),
    ("ustaw światło w kuchni na 30 procent",
     {"intencja": "HassLightSet", "domena": "light", "obszar": "Kuchnia", "wartosc": 30},
     "light.turn_on", {"light.kuchnia_sufit"}, {"brightness_pct": 30}, "Ustawiono światło"),
    ("zrób jaśniej w kuchni",  # 50% + 25
     {"intencja": "HassLightSet", "domena": "light", "obszar": "Kuchnia", "zmiana": "więcej"},
     "light.turn_on", {"light.kuchnia_sufit"}, {"brightness_pct": 75}, "Ustawiono światło"),
    ("przyciemnij światło w kuchni",
     {"intencja": "HassLightSet", "domena": "light", "obszar": "Kuchnia", "zmiana": "mniej"},
     "light.turn_on", {"light.kuchnia_sufit"}, {"brightness_pct": 25}, "Ustawiono światło"),
    ("zrób ciepłe światło w kuchni",
     {"intencja": "HassLightSet", "obszar": "Kuchnia", "barwa": "ciepła"},
     "light.turn_on", {"light.kuchnia_sufit"}, {"color_temp_kelvin": 2700}, "Ustawiono barwę ciepła"),
    ("zmień kolor w kuchni na czerwony",
     {"intencja": "HassLightSet", "obszar": "Kuchnia", "kolor": "czerwony"},
     "light.turn_on", {"light.kuchnia_sufit"}, {"rgb_color": (255, 0, 0)}, "Ustawiono kolor czerwony"),
    ("opuść roletę w salonie do połowy",
     {"intencja": "HassSetPosition", "domena": "cover", "obszar": "Salon", "wartosc": 50},
     "cover.set_cover_position", {"cover.salon_roleta"}, {"position": 50}, "Ustawiono"),
    ("podnieś trochę roletę w salonie",  # 40% + 25
     {"intencja": "HassSetPosition", "domena": "cover", "obszar": "Salon", "zmiana": "więcej"},
     "cover.set_cover_position", {"cover.salon_roleta"}, {"position": 65}, "Ustawiono"),
    ("otwórz roletę w salonie", {"intencja": "HassTurnOn", "domena": "cover", "obszar": "Salon"},
     "cover.open_cover", {"cover.salon_roleta"}, None, "Otwarto"),
    ("zasłoń roletę w salonie", {"intencja": "HassTurnOff", "domena": "cover", "obszar": "Salon"},
     "cover.close_cover", {"cover.salon_roleta"}, None, "Zamknięto"),
    ("ustaw w salonie 22 stopnie",
     {"intencja": "HassClimateSetTemperature", "domena": "climate", "obszar": "Salon", "wartosc": 22},
     "climate.set_temperature", {"climate.salon"}, {"temperature": 22}, "Ustawiono temperaturę"),
    ("zrób cieplej w salonie",  # 21 + 1
     {"intencja": "HassClimateSetTemperature", "domena": "climate", "obszar": "Salon",
      "zmiana": "więcej"},
     "climate.set_temperature", {"climate.salon"}, {"temperature": 22}, "Ustawiono temperaturę"),
    ("ustaw głośność w salonie na 40 procent",
     {"intencja": "HassSetVolume", "domena": "media_player", "obszar": "Salon", "wartosc": 40},
     "media_player.volume_set", {"media_player.salon_glosnik"}, {"volume_level": 0.4},
     "Ustawiono głośność"),
    ("zatrzymaj muzykę w salonie", {"intencja": "HassMediaPause", "obszar": "Salon"},
     "media_player.media_pause", {"media_player.salon_glosnik"}, None, "Wstrzymano"),
    ("następna piosenka w salonie", {"intencja": "HassMediaNext", "obszar": "Salon"},
     "media_player.media_next_track", {"media_player.salon_glosnik"}, None, "Następny utwór"),
    ("poprzednia piosenka w salonie", {"intencja": "HassMediaPrevious", "obszar": "Salon"},
     "media_player.media_previous_track", {"media_player.salon_glosnik"}, None, "Poprzedni utwór"),
    ("niech robot posprząta", {"intencja": "HassVacuumStart", "domena": "vacuum", "nazwa": "robot"},
     "vacuum.start", {"vacuum.robot"}, None, "Uruchomiono odkurzacz"),
    ("odeślij odkurzacz do bazy",
     {"intencja": "HassVacuumReturnToBase", "domena": "vacuum", "nazwa": "robot"},
     "vacuum.return_to_base", {"vacuum.robot"}, None, "Odkurzacz wraca do bazy"),
    ("niech akwarium się świeci", {"intencja": "HassTurnOn", "domena": "switch", "nazwa": "akwarium"},
     "switch.turn_on", {"switch.akwarium"}, None, "Włączono"),
    ("zrób wieczór", {"intencja": "HassTurnOn", "domena": "scene", "nazwa": "Wieczór"},
     "scene.turn_on", {"scene.wieczor"}, None, "Uruchomiono"),
    ("pogaś wszystkie światła w całym mieszkaniu",
     {"intencja": "HassTurnOff", "domena": "light", "wszystkie": True},
     "light.turn_off", {"light.kuchnia_sufit", "light.salon_lampa", "light.sypialnia_nocna"},
     None, "Wyłączono"),
    ("zgaś światła na parterze", {"intencja": "HassTurnOff", "domena": "light", "pietro": "Parter"},
     "light.turn_off", {"light.kuchnia_sufit", "light.salon_lampa"}, None, "Wyłączono"),
]  # fmt: skip


@pytest.mark.parametrize(("text", "parsed", "service", "entities", "data", "speech"), DIRECT)
async def test_direct_commands(
    hass: HomeAssistant, dom: dict, aioclient_mock: AiohttpClientMocker,
    text, parsed, service, entities, data, speech,
) -> None:  # fmt: skip
    """Confident command: the right service is called on the right entities at once, no question."""
    _control_ollama(aioclient_mock, parsed)

    result = await _say(hass, text)

    assert _speech(result).startswith(speech), _speech(result)
    assert not result.continue_conversation
    # via router control, not via HA's built-in sentences
    assert _rows(hass) and _rows(hass)[-1]["route"].startswith("sterowanie →"), _rows(hass)
    assert _entities(dom[service]) == entities
    for key, value in (data or {}).items():
        got = dom[service][0].data[key]
        assert (tuple(got) if isinstance(got, list) else got) == value, (key, got)
    # nothing besides this one service
    assert set(_called(dom)) == {service}
    assert "light.ukryta" not in _entities(dom[service])  # not exposed


async def test_play_music_search(hass: HomeAssistant, dom: dict, aioclient_mock) -> None:
    _control_ollama(
        aioclient_mock,
        {"intencja": "HassMediaSearchAndPlay", "obszar": "Salon", "szukaj": "jazz",
         "rodzaj": "gatunek"},
    )  # fmt: skip

    result = await _say(hass, "puść jazz w salonie")

    assert dom["media_player.search_media"][0].data["search_query"] == "jazz"
    assert dom["media_player.search_media"][0].data["media_filter_classes"] == ["genre"]
    assert dom["media_player.play_media"][0].data["media_content_id"] == "lib://1"
    assert _speech(result) == "Puszczam Jazz na wieczór na Głośnik salon."


# --- actions: scripts and scenes ---


async def test_script_with_known_verb_runs_with_satellite(
    hass: HomeAssistant, dom: dict, aioclient_mock: AiohttpClientMocker
) -> None:
    """„Zaparz mi kawę” - known verb, unambiguous script: runs at once, with the speaker."""
    _control_ollama(
        aioclient_mock,
        {"intencja": "HassTurnOn", "domena": "script", "nazwa": "Ekspres - zrób kawę"},
    )

    result = await _say(hass, "Zaparz mi kawę", satellite="assist_satellite.kuchnia")
    await hass.async_block_till_done()

    assert _speech(result) == "Uruchomiono: ekspres - zrób kawę."
    assert [(e.data["kto"], e.data["satelita"]) for e in dom["skrypt"]] == [
        ("kawa", "assist_satellite.kuchnia")
    ]


async def test_script_said_by_name_runs_without_model(
    hass: HomeAssistant, dom: dict, aioclient_mock: AiohttpClientMocker
) -> None:
    """Script name (min. 3 words) spoken directly - no parsing by the model."""
    _control_ollama(aioclient_mock, {"intencja": "HassTurnOff"})

    result = await _say(hass, "Opuść rolety do oglądania TV")
    await hass.async_block_till_done()

    assert [e.data["kto"] for e in dom["skrypt"]] == ["rolety_tv"]
    assert _speech(result).startswith("Uruchomiono")
    assert not [c for c in aioclient_mock.mock_calls if "intencja" in str(c[2].get("format"))]


async def test_actions_in_prompt(
    hass: HomeAssistant, dom: dict, aioclient_mock: AiohttpClientMocker
) -> None:
    """The model sees scripts with descriptions and scenes with what they set."""
    _control_ollama(aioclient_mock, {"intencja": "HassTurnOn"})

    await _say(hass, "zrób coś miłego")

    prompt = next(c[2] for c in aioclient_mock.mock_calls if "intencja" in str(c[2].get("format")))[
        "messages"
    ][0]["content"]
    assert "„Ekspres - zrób kawę” - Parzy kawę" in prompt
    assert "„Opuść rolety do oglądania TV” - Przymyka rolety" in prompt
    assert "„Wieczór” - scena - ustawia: Lampa stojąca, Roleta salon" in prompt


# --- questions and answers ---

SENSITIVE = [
    # (sentence, parse, question, „tak” answer, service after „tak”, entity)
    ("otwórz drzwi", {"intencja": "HassTurnOff", "domena": "lock", "nazwa": "drzwi wejściowe"},
     "Czy otworzyć Drzwi wejściowe?", "tak", "lock.unlock", "lock.drzwi"),
    ("zamknij drzwi na klucz", {"intencja": "HassTurnOn", "domena": "lock", "nazwa": "drzwi wejściowe"},
     "Czy zamknąć Drzwi wejściowe?", "zamknij", "lock.lock", "lock.drzwi"),
    ("otwórz bramę garażu", {"intencja": "HassTurnOn", "domena": "cover", "nazwa": "brama garażowa"},
     "Czy otworzyć Brama garażowa?", "otwórz", "cover.open_cover", "cover.garaz_brama"),
    ("wyłącz lodówkę", {"intencja": "HassTurnOff", "domena": "switch", "nazwa": "lodówkę"},
     "Czy wyłączyć Lodówka?", "dawaj", "switch.turn_off", "switch.lodowka"),
    ("pora spać, włącz tryb nocny", {"intencja": "HassTurnOn", "domena": "scene", "nazwa": "Dobranoc"},
     "Czy uruchomić Dobranoc?", "tak, zrób to", "scene.turn_on", "scene.dobranoc"),
]  # fmt: skip


@pytest.mark.parametrize(("text", "parsed", "question", "yes", "service", "entity"), SENSITIVE)
async def test_sensitive_yes(
    hass: HomeAssistant, dom: dict, aioclient_mock: AiohttpClientMocker,
    text, parsed, question, yes, service, entity,
) -> None:  # fmt: skip
    """Lock, gate, „always ask” list: „Czy …?”, nothing before consent, executed after consent."""
    _control_ollama(aioclient_mock, parsed)

    asked = await _say(hass, text)
    assert _speech(asked) == question
    assert asked.continue_conversation is True
    assert not _called(dom)

    done = await _say(hass, yes, asked.conversation_id)
    assert _entities(dom[service]) == {entity}
    assert not done.continue_conversation


@pytest.mark.parametrize("no", ["nie", "nie rób", "zostaw", "anuluj", "otwórz"])
async def test_sensitive_no(
    hass: HomeAssistant, dom: dict, aioclient_mock: AiohttpClientMocker, no: str
) -> None:
    """„Czy zamknąć drzwi?” - refusal (also with the opposite verb) = nothing, conversation ends."""
    _control_ollama(
        aioclient_mock, {"intencja": "HassTurnOn", "domena": "lock", "nazwa": "drzwi wejściowe"}
    )

    asked = await _say(hass, "zarygluj drzwi")
    answer = await _say(hass, no, asked.conversation_id)

    assert _speech(answer) == "Dobrze, nic nie zmieniam."
    assert not answer.continue_conversation
    assert not _called(dom)


DOUBT = [
    # uncertain understanding: a garbled word or no known verb
    ("Jaś światło w kuchni.", {"intencja": "HassTurnOff", "domena": "light", "obszar": "Kuchnia"},
     "Czy dobrze rozumiem, że mam wyłączyć światła w pomieszczeniu Kuchnia?", "light.turn_off"),
    ("Zapasz kawę!", {"intencja": "HassTurnOn", "domena": "script", "nazwa": "Ekspres - zrób kawę"},
     "Czy dobrze rozumiem, że mam uruchomić Ekspres - zrób kawę?", "skrypt"),
    ("wieczorny klimacik", {"intencja": "HassTurnOn", "domena": "scene", "nazwa": "Wieczór"},
     "Czy dobrze rozumiem, że mam uruchomić Wieczór?", "scene.turn_on"),
]  # fmt: skip


@pytest.mark.parametrize(("text", "parsed", "question", "service"), DOUBT)
@pytest.mark.parametrize("yes", ["tak", "Tak, zrób to.", "dawaj", "jasne"])
async def test_doubt_yes(
    hass: HomeAssistant, dom: dict, aioclient_mock: AiohttpClientMocker,
    text, parsed, question, service, yes,
) -> None:  # fmt: skip
    _control_ollama(aioclient_mock, parsed)

    asked = await _say(hass, text)
    assert _speech(asked) == question
    assert not _called(dom)

    await _say(hass, yes, asked.conversation_id)
    await hass.async_block_till_done()
    assert set(_called(dom)) == {service}


@pytest.mark.parametrize(("text", "parsed", "question", "service"), DOUBT)
async def test_doubt_no_asks_to_repeat_then_new_command_works(
    hass: HomeAssistant, dom: dict, aioclient_mock: AiohttpClientMocker,
    text, parsed, question, service,
) -> None:  # fmt: skip
    """„Nie” to „czy dobrze rozumiem?” - apology and a request to repeat, conversation goes on;
    the next sentence is a new command (here: the confident „włącz akwarium”)."""
    _control_ollama(aioclient_mock, parsed)
    asked = await _say(hass, text)

    again = await _say(hass, "nie", asked.conversation_id)
    assert _speech(again) == "Przepraszam, źle zrozumiałem. Powtórz, proszę."
    assert again.continue_conversation is True
    assert not _called(dom)

    aioclient_mock.clear_requests()
    _control_ollama(
        aioclient_mock, {"intencja": "HassTurnOn", "domena": "switch", "nazwa": "akwarium"}
    )
    await _say(hass, "włącz akwarium", again.conversation_id)
    assert set(_called(dom)) == {"switch.turn_on"}


@pytest.mark.parametrize("cancel", ["anuluj", "nie trzeba", "daj spokój", "nieważne", "nie rób"])
async def test_doubt_cancel_ends(
    hass: HomeAssistant, dom: dict, aioclient_mock: AiohttpClientMocker, cancel: str
) -> None:
    _control_ollama(
        aioclient_mock,
        {"intencja": "HassTurnOn", "domena": "script", "nazwa": "Ekspres - zrób kawę"},
    )
    asked = await _say(hass, "Zapasz kawę!")

    answer = await _say(hass, cancel, asked.conversation_id)

    assert _speech(answer) == "Dobrze, nic nie zmieniam."
    assert not answer.continue_conversation
    await hass.async_block_till_done()
    assert not _called(dom)


async def test_question_expires(
    hass: HomeAssistant, dom: dict, aioclient_mock: AiohttpClientMocker, monkeypatch
) -> None:
    """A late „tak” (after the answer timeout) executes nothing."""
    monkeypatch.setattr(agent_module, "CONFIRM_SECONDS", -1)
    _control_ollama(
        aioclient_mock, {"intencja": "HassTurnOff", "domena": "lock", "nazwa": "drzwi wejściowe"}
    )
    asked = await _say(hass, "otwórz drzwi")

    late = await _say(hass, "tak", asked.conversation_id)

    assert not _called(dom)
    assert not _speech(late).startswith("Otwarto")


async def test_question_belongs_to_its_conversation(
    hass: HomeAssistant, dom: dict, aioclient_mock: AiohttpClientMocker
) -> None:
    """„Tak” in another conversation (another speaker) does not confirm someone else's question."""
    _control_ollama(
        aioclient_mock, {"intencja": "HassTurnOff", "domena": "lock", "nazwa": "drzwi wejściowe"}
    )
    await _say(hass, "otwórz drzwi")

    await _say(hass, "tak")  # new conversation

    assert not _called(dom)


async def test_ambiguous_name_asks(
    hass: HomeAssistant, dom: dict, aioclient_mock: AiohttpClientMocker
) -> None:
    """Weak name fragment („lampę”) without a room - a question, not a guess."""
    _control_ollama(aioclient_mock, {"intencja": "HassTurnOn", "domena": "light", "nazwa": "lampę"})

    asked = await _say(hass, "zapal lampę")

    assert _speech(asked).startswith("Czy dobrze rozumiem, że mam włączyć")
    assert not _called(dom)


# --- errors and safeguards ---

ERRORS = [
    ("włącz mikser", {"intencja": "HassTurnOn", "nazwa": "mikser"},
     "Nie znalazłem urządzenia „mikser”."),
    ("ustaw światło w kuchni", {"intencja": "HassLightSet", "domena": "light", "obszar": "Kuchnia"},
     "Nie wiem, na jaką wartość ustawić."),
    ("zmień kolor lampy stojącej na niebieski",
     {"intencja": "HassLightSet", "nazwa": "lampy stojącej", "kolor": "niebieski"},
     "To światło nie zmienia koloru."),
    ("zrób zimne światło przy lampie stojącej",
     {"intencja": "HassLightSet", "nazwa": "lampie stojącej", "barwa": "zimna"},
     "To światło nie zmienia barwy."),
    ("ustaw głośność w salonie", {"intencja": "HassSetVolume", "obszar": "Salon"},
     "Nie wiem, jaką ustawić głośność."),
    ("puść coś w salonie", {"intencja": "HassMediaSearchAndPlay", "obszar": "Salon"},
     "Co mam puścić?"),
    ("puść jazz", {"intencja": "HassMediaSearchAndPlay", "szukaj": "jazz"},
     "W którym pomieszczeniu mam puścić?"),
]  # fmt: skip


@pytest.mark.parametrize(("text", "parsed", "speech"), ERRORS)
async def test_errors_say_why_and_do_nothing(
    hass: HomeAssistant, dom: dict, aioclient_mock: AiohttpClientMocker, text, parsed, speech
) -> None:
    _control_ollama(aioclient_mock, parsed)

    result = await _say(hass, text)

    assert _speech(result) == speech
    assert not _called(dom)


@pytest.mark.parametrize(
    "text", ["rozbrój alarm teraz proszę", "uzbrój czuwanie na noc", "aktywuj ochronę domu"]
)
async def test_alarm_only_by_sentences(
    hass: HomeAssistant, dom: dict, aioclient_mock: AiohttpClientMocker, text: str
) -> None:
    _control_ollama(
        aioclient_mock, {"intencja": "HassTurnOn", "domena": "scene", "nazwa": "Dobranoc"}
    )

    result = await _say(hass, text)

    assert _speech(result).startswith("Alarmem steruję tylko")
    assert not _called(dom)


@pytest.mark.parametrize("text", ["tak", "nie rób", "tak, zrób to", "dawaj"])
async def test_bare_answer_without_question_does_nothing(
    hass: HomeAssistant, dom: dict, aioclient_mock: AiohttpClientMocker, text: str
) -> None:
    _control_ollama(
        aioclient_mock, {"intencja": "HassTurnOn", "domena": "switch", "nazwa": "akwarium"}
    )

    await _say(hass, text)

    assert not _called(dom)
    assert _rows(hass)[-1]["route"] == "sterowanie (sama odpowiedź tak/nie)"


async def test_broken_model_answer_does_nothing(
    hass: HomeAssistant, dom: dict, aioclient_mock: AiohttpClientMocker
) -> None:
    """The model returned something unparsable - no action, on to the fallback agent."""
    _control_ollama(aioclient_mock, {"intencja": "HassZrobCos"})

    await _say(hass, "niech akwarium się świeci")

    assert not _called(dom)
    assert _rows(hass)[-1]["route"] == "sterowanie (nie rozebrano)"


async def test_unexposed_entity_never_chosen(
    hass: HomeAssistant, dom: dict, aioclient_mock: AiohttpClientMocker
) -> None:
    """An unexposed entity is not among the targets: at most a question about another,
    similar lamp, without execution - and never about the hidden one."""
    _control_ollama(aioclient_mock, {"intencja": "HassTurnOff", "nazwa": "ukrytą lampę"})

    result = await _say(hass, "zgaś ukrytą lampę")

    assert "Ukryta" not in _speech(result)
    assert not _called(dom)
    prompt = next(c[2] for c in aioclient_mock.mock_calls if "intencja" in str(c[2].get("format")))[
        "messages"
    ][0]["content"]
    assert "Ukryta" not in prompt


@pytest.mark.parametrize(
    ("parsed", "why"),
    [
        ({"intencja": "HassTurnOff", "domena": "script", "nazwa": "Ekspres - zrób kawę"},
         "„wyłącz” na skrypcie by go zatrzymał - akcja zawsze jest uruchamiana"),
        ({"intencja": "HassTurnOn", "domena": "scene", "nazwa": "Ekspres - zrób kawę"},
         "model pomylił skrypt ze sceną - nazwy szukamy w obu"),
    ],
)  # fmt: skip
async def test_action_model_mistakes_are_corrected(
    hass: HomeAssistant, dom: dict, aioclient_mock: AiohttpClientMocker, parsed, why
) -> None:
    _control_ollama(aioclient_mock, parsed)

    result = await _say(hass, "zaparz kawę i wyłącz ekspres potem")
    await hass.async_block_till_done()

    assert [e.data["kto"] for e in dom["skrypt"]] == ["kawa"], why
    assert _speech(result).startswith("Uruchomiono")


# --- speech recognition gibberish: „Czy chodziło o …?” ---


def _unclear_ollama(aioclient_mock: AiohttpClientMocker, guess: str | None) -> None:
    """Router: gibberish -> niezrozumiale, the rest -> sterowanie; guessing returns ``guess``."""
    import json as _json

    from pytest_homeassistant_custom_component.test_util.aiohttp import (
        AiohttpClientMockResponse,
    )

    from .conftest import OLLAMA
    from .test_router import _answer

    async def handler(method, url, data):
        schema = _json.dumps(data.get("format", {}))
        if "zdanie" in schema:
            content = _json.dumps({"zdanie": guess})
        elif "intencja" in schema:
            content = _json.dumps({"intencja": "HassTurnOn", "domena": "switch",
                                   "nazwa": "akwarium"})  # fmt: skip
        else:
            question = data["messages"][-1]["content"]
            return AiohttpClientMockResponse(
                method,
                url,
                json=_answer("niezrozumiale" if "pisarow" in question else "sterowanie"),
            )
        return AiohttpClientMockResponse(method, url, json={"message": {"content": content}})

    aioclient_mock.post(f"{OLLAMA}/api/chat", side_effect=handler)


async def test_gibberish_guess_yes_runs_corrected_sentence(
    hass: HomeAssistant, dom: dict, aioclient_mock: AiohttpClientMocker
) -> None:
    """„Głup nastrój w pisarowie” - a suggestion, we do nothing; „tak” - the corrected sentence
    takes the whole usual path (here: HA itself already understands it)."""
    _unclear_ollama(aioclient_mock, "włącz akwarium")

    asked = await _say(hass, "Głup nastrój w pisarowie")
    assert _speech(asked) == (
        "Nie jestem pewien, czy dobrze usłyszałem. Czy chodziło o: włącz akwarium?"
    )
    assert asked.continue_conversation is True
    assert not _called(dom)
    assert _rows(hass)[-1]["route"] == "niezrozumiałe → włącz akwarium"

    await _say(hass, "tak", asked.conversation_id)
    assert _entities(dom["switch.turn_on"]) == {"switch.akwarium"}


async def test_gibberish_guess_no_asks_to_repeat_cancel_ends(
    hass: HomeAssistant, dom: dict, aioclient_mock: AiohttpClientMocker
) -> None:
    _unclear_ollama(aioclient_mock, "włącz akwarium")

    asked = await _say(hass, "Głup nastrój w pisarowie")
    again = await _say(hass, "nie", asked.conversation_id)
    assert _speech(again) == "Przepraszam, źle zrozumiałem. Powtórz, proszę."
    assert again.continue_conversation is True

    asked = await _say(hass, "Głup nastrój w pisarowie")
    cancelled = await _say(hass, "anuluj", asked.conversation_id)
    assert _speech(cancelled) == "Dobrze, nic nie robię."
    assert not cancelled.continue_conversation
    assert not _called(dom)


async def test_gibberish_without_guess_asks_to_repeat(
    hass: HomeAssistant, dom: dict, aioclient_mock: AiohttpClientMocker
) -> None:
    _unclear_ollama(aioclient_mock, None)

    result = await _say(hass, "Głup nastrój w pisarowie")

    assert _speech(result) == "Nie zrozumiałem. Powtórz, proszę."
    assert result.continue_conversation is True
    assert _rows(hass)[-1]["route"] == "niezrozumiałe (bez propozycji)"


async def test_gibberish_then_new_sentence_drops_guess(
    hass: HomeAssistant, dom: dict, aioclient_mock: AiohttpClientMocker
) -> None:
    """A new sentence instead of „tak/nie”: the suggestion is dropped, the new sentence works
    normally, and a later „tak” executes nothing."""
    _unclear_ollama(aioclient_mock, "włącz akwarium")
    asked = await _say(hass, "Głup nastrój w pisarowie")

    await _say(hass, "niech akwarium się świeci", asked.conversation_id)  # control -> akwarium
    assert len(dom["switch.turn_on"]) == 1
    await _say(hass, "tak", asked.conversation_id)
    assert len(dom["switch.turn_on"]) == 1


# --- one answer vocabulary for all questions ---

YES = ["tak", "dokładnie", "dokładnie tak", "Tak, dokładnie tak, o to mi chodzi.", "o to chodzi",
       "działaj", "zrób", "zrób to", "wykonaj", "dawaj"]  # fmt: skip
REPEAT = ["nie", "Nie, o coś innego.", "o coś innego", "jeszcze raz", "powtórzę", "może powtórzę",
          "nie o to chodzi"]  # fmt: skip
CANCEL = ["anuluj", "koniec", "nieważne", "zostaw to", "nic nie rób", "daj sobie z tym spokój",
          "daj spokój", "olej to"]  # fmt: skip


def test_answer_vocabulary() -> None:
    from custom_components.assist_router.control import (
        answer_kind,
        is_bare_answer,
        is_cancel,
        is_repeat,
    )

    for text in YES:
        assert answer_kind(text) == "yes" and is_bare_answer(text), text
    for text in REPEAT + CANCEL:
        assert answer_kind(text) == "no" and is_bare_answer(text), text
    for text in CANCEL:
        assert is_cancel(text) and not is_repeat(text), text
    for text in REPEAT:
        assert not is_cancel(text), text
        assert is_repeat(text) == (text != "nie"), text
    # commands starting with answer words are still commands
    for text in ("zrób jaśniej w salonie", "wykonaj sprzątanie kuchni", "nie zapalaj lampy"):
        assert not is_bare_answer(text), text


@pytest.mark.parametrize("answer", YES)
async def test_all_questions_yes(
    hass: HomeAssistant, dom: dict, aioclient_mock: AiohttpClientMocker, answer: str
) -> None:
    """Every „tak” works for both „czy dobrze rozumiem?” and „czy chodziło o…?”."""
    _unclear_ollama(aioclient_mock, "włącz akwarium")
    asked = await _say(hass, "Głup nastrój w pisarowie")
    await _say(hass, answer, asked.conversation_id)
    assert _entities(dom["switch.turn_on"]) == {"switch.akwarium"}, answer

    aioclient_mock.clear_requests()
    _control_ollama(
        aioclient_mock,
        {"intencja": "HassTurnOn", "domena": "script", "nazwa": "Ekspres - zrób kawę"},
    )
    asked = await _say(hass, "Zapasz kawę!")
    await _say(hass, answer, asked.conversation_id)
    await hass.async_block_till_done()
    assert [e.data["kto"] for e in dom["skrypt"]] == ["kawa"], answer


@pytest.mark.parametrize("answer", REPEAT)
async def test_all_questions_repeat(
    hass: HomeAssistant, dom: dict, aioclient_mock: AiohttpClientMocker, answer: str
) -> None:
    for setup, text in (
        (lambda: _unclear_ollama(aioclient_mock, "włącz akwarium"), "Głup nastrój w pisarowie"),
        (lambda: _control_ollama(aioclient_mock, {"intencja": "HassTurnOn", "domena": "script",
                                                  "nazwa": "Ekspres - zrób kawę"}), "Zapasz kawę!"),
    ):  # fmt: skip
        aioclient_mock.clear_requests()
        setup()
        asked = await _say(hass, text)
        reply = await _say(hass, answer, asked.conversation_id)
        assert _speech(reply) == "Przepraszam, źle zrozumiałem. Powtórz, proszę.", answer
        assert reply.continue_conversation is True
    await hass.async_block_till_done()
    assert not _called(dom)


@pytest.mark.parametrize("answer", CANCEL)
async def test_all_questions_cancel(
    hass: HomeAssistant, dom: dict, aioclient_mock: AiohttpClientMocker, answer: str
) -> None:
    for setup, text, speech in (
        (lambda: _unclear_ollama(aioclient_mock, "włącz akwarium"), "Głup nastrój w pisarowie",
         "Dobrze, nic nie robię."),
        (lambda: _control_ollama(aioclient_mock, {"intencja": "HassTurnOn", "domena": "script",
                                                  "nazwa": "Ekspres - zrób kawę"}), "Zapasz kawę!",
         "Dobrze, nic nie zmieniam."),
        (lambda: _control_ollama(aioclient_mock, {"intencja": "HassTurnOff", "domena": "lock",
                                                  "nazwa": "drzwi wejściowe"}), "otwórz drzwi",
         "Dobrze, nic nie zmieniam."),
    ):  # fmt: skip
        aioclient_mock.clear_requests()
        setup()
        asked = await _say(hass, text)
        reply = await _say(hass, answer, asked.conversation_id)
        assert _speech(reply) == speech, answer
        assert not reply.continue_conversation
    await hass.async_block_till_done()
    assert not _called(dom)


async def test_sensitive_plain_no_ends_but_explicit_repeat_asks_again(
    hass: HomeAssistant, dom: dict, aioclient_mock: AiohttpClientMocker
) -> None:
    """„Czy otworzyć drzwi?” - „nie” = don't open (end); „jeszcze raz” = repeat the question."""
    _control_ollama(
        aioclient_mock, {"intencja": "HassTurnOff", "domena": "lock", "nazwa": "drzwi wejściowe"}
    )
    asked = await _say(hass, "otwórz drzwi")
    assert _speech(await _say(hass, "nie", asked.conversation_id)) == "Dobrze, nic nie zmieniam."

    asked = await _say(hass, "otwórz drzwi")
    again = await _say(hass, "jeszcze raz", asked.conversation_id)
    assert _speech(again) == "Przepraszam, źle zrozumiałem. Powtórz, proszę."
    assert not _called(dom)


# --- „Wyłącz halaryn w domu” -> 64 lights turned off (22.10.2026) ---


async def _satellite_in(hass: HomeAssistant, router: MockConfigEntry, area_name: str) -> str:
    """Speaker device in an area - like an Assist satellite in a room."""
    from homeassistant.helpers import device_registry as dr

    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=router.entry_id, identifiers={("test", "glosnik")}, name="Głośnik"
    )
    area = ar.async_get(hass).async_get_area_by_name(area_name)
    dr.async_get(hass).async_update_device(device.id, area_id=area.id)
    return device.id


async def test_misheard_alarm_goes_to_alarm_hint(
    hass: HomeAssistant, dom: dict, aioclient_mock: AiohttpClientMocker
) -> None:
    _control_ollama(aioclient_mock, {"intencja": "HassTurnOff", "domena": "light"})

    result = await _say(hass, "Wyłącz halaryn w domu.")

    assert _speech(result).startswith("Alarmem steruję tylko")
    assert not _called(dom)


async def test_no_room_uses_speaker_room_not_whole_house(
    hass: HomeAssistant, dom: dict, router: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """No area in the command - the speaker's room (HA would take every light in the house)."""
    device_id = await _satellite_in(hass, router, "Kuchnia")
    _control_ollama(aioclient_mock, {"intencja": "HassTurnOff", "domena": "light"})

    await conversation.async_converse(
        hass, "pogaś mi te światła", None, Context(), language="pl", agent_id=AGENT_ID,
        device_id=device_id,
    )  # fmt: skip

    assert _entities(dom["light.turn_off"]) == {"light.kuchnia_sufit"}


async def test_no_room_and_no_speaker_asks_where(
    hass: HomeAssistant, dom: dict, aioclient_mock: AiohttpClientMocker
) -> None:
    _control_ollama(aioclient_mock, {"intencja": "HassTurnOff", "domena": "light"})

    result = await _say(hass, "pogaś mi te światła")

    assert _speech(result) == "W którym pomieszczeniu?"
    assert not _called(dom)


async def test_guessed_device_kind_asks(
    hass: HomeAssistant, dom: dict, aioclient_mock: AiohttpClientMocker
) -> None:
    """The model guessed „światło” but the sentence says nothing about light - ask, don't run."""
    _control_ollama(
        aioclient_mock, {"intencja": "HassTurnOff", "domena": "light", "obszar": "Kuchnia"}
    )

    result = await _say(hass, "wyłącz kalafiora w kuchni")

    assert _speech(result).startswith("Czy dobrze rozumiem, że mam wyłączyć")
    assert not _called(dom)


async def test_large_scope_asks_unless_said_all(
    hass: HomeAssistant, dom: dict, aioclient_mock: AiohttpClientMocker, monkeypatch
) -> None:
    """Many devices at once without „wszystkie/cały” - a question; with „wszystkie” - at once."""
    from custom_components.assist_router import control

    monkeypatch.setattr(control, "LARGE_SCOPE", 1)
    _control_ollama(
        aioclient_mock, {"intencja": "HassTurnOff", "domena": "light", "pietro": "Parter"}
    )

    asked = await _say(hass, "zgaś światła na parterze")
    assert _speech(asked).startswith("Czy dobrze rozumiem")
    assert not _called(dom)

    await _say(hass, "zgaś wszystkie światła na parterze")
    assert _entities(dom["light.turn_off"]) == {"light.kuchnia_sufit", "light.salon_lampa"}


# --- not understood twice: apology and end of conversation ---

GIVE_UP = "Przepraszam, nie rozumiem. Jeśli będziesz czegoś potrzebować, poproś mnie jeszcze raz."


async def test_second_misunderstanding_ends_conversation(
    hass: HomeAssistant, dom: dict, aioclient_mock: AiohttpClientMocker
) -> None:
    _unclear_ollama(aioclient_mock, None)

    first = await _say(hass, "Głup nastrój w pisarowie")
    assert _speech(first) == "Nie zrozumiałem. Powtórz, proszę."
    assert first.continue_conversation is True

    second = await _say(hass, "Głup nastrój w pisarowie", first.conversation_id)
    assert _speech(second) == GIVE_UP
    assert not second.continue_conversation
    assert _rows(hass)[-1]["route"] == "niezrozumiałe - koniec rozmowy (2× bez zrozumienia)"


async def test_no_to_guess_then_gibberish_ends_conversation(
    hass: HomeAssistant, dom: dict, aioclient_mock: AiohttpClientMocker
) -> None:
    """„nie” to „Czy chodziło o…?” (1st request to repeat), then gibberish again (2nd)."""
    _unclear_ollama(aioclient_mock, "włącz akwarium")
    asked = await _say(hass, "Głup nastrój w pisarowie")
    again = await _say(hass, "nie", asked.conversation_id)
    assert _speech(again) == "Przepraszam, źle zrozumiałem. Powtórz, proszę."

    aioclient_mock.clear_requests()
    _unclear_ollama(aioclient_mock, None)
    last = await _say(hass, "Głup nastrój w pisarowie", again.conversation_id)
    assert _speech(last) == GIVE_UP and not last.continue_conversation
    assert not _called(dom)


async def test_understood_sentence_resets_counter(
    hass: HomeAssistant, dom: dict, aioclient_mock: AiohttpClientMocker
) -> None:
    """Gibberish, then an understood command, then gibberish again - a request to repeat,
    not the end (only consecutive misunderstandings count)."""
    _unclear_ollama(aioclient_mock, None)
    first = await _say(hass, "Głup nastrój w pisarowie")
    ok = await _say(hass, "niech akwarium się świeci", first.conversation_id)
    assert _entities(dom["switch.turn_on"]) == {"switch.akwarium"}

    again = await _say(hass, "Głup nastrój w pisarowie", ok.conversation_id)
    assert _speech(again) == "Nie zrozumiałem. Powtórz, proszę."
    assert again.continue_conversation is True


async def test_counter_is_per_conversation(
    hass: HomeAssistant, dom: dict, aioclient_mock: AiohttpClientMocker
) -> None:
    _unclear_ollama(aioclient_mock, None)
    await _say(hass, "Głup nastrój w pisarowie")

    other = await _say(hass, "Głup nastrój w pisarowie")  # new conversation (another speaker)

    assert _speech(other) == "Nie zrozumiałem. Powtórz, proszę."


@pytest.mark.parametrize("guess", ["null", "None", "brak"])
async def test_guess_text_null_means_no_guess(
    hass: HomeAssistant, dom: dict, aioclient_mock: AiohttpClientMocker, guess: str
) -> None:
    """The model returned the string „null” instead of null - ask to repeat, not „Czy chodziło o: null?”."""
    _unclear_ollama(aioclient_mock, guess)

    result = await _say(hass, "Głup nastrój w pisarowie")

    assert _speech(result) == "Nie zrozumiałem. Powtórz, proszę."


# --- twins: one device from two integrations (HomePod: Apple TV and Music Assistant) ---


def _homepod_twins(hass: HomeAssistant, ma_state: str = "playing") -> None:
    """Two „Sypialnia HomePod” entities in one room - the HA intent rejects such a name."""
    sypialnia = ar.async_get(hass).async_get_area_by_name("Sypialnia")
    ent_reg = er.async_get(hass)
    _entity(hass, ent_reg, sypialnia.id, "media_player.sypialnia_homepod", "Sypialnia HomePod",
            "idle", volume_level=0.65, supported_features=PLAYER)  # fmt: skip
    _entity(hass, ent_reg, sypialnia.id, "media_player.sypialnia_homepod_2", "Sypialnia HomePod",
            ma_state, volume_level=0.2, supported_features=PLAYER)  # fmt: skip


async def test_twins_volume_set_on_both_without_question(
    hass: HomeAssistant, dom: dict, aioclient_mock: AiohttpClientMocker
) -> None:
    """„Ustaw głośność HomePoda na 60% w sypialni”: no „several matching” question, and volume
    set on both entities (the HA intent would return DUPLICATE_NAME and do nothing)."""
    _homepod_twins(hass)
    _control_ollama(
        aioclient_mock,
        {"intencja": "HassSetVolume", "domena": "media_player", "nazwa": "Sypialnia HomePod",
         "obszar": "Sypialnia", "wartosc": 60},
    )  # fmt: skip

    result = await _say(hass, "Ustaw głośność głośnika HomePod na 60% w sypialni.")

    assert _speech(result).startswith("Ustawiono głośność na 60%"), _rows(hass)[-1]["route"]
    assert not result.continue_conversation
    assert _entities(dom["media_player.volume_set"]) == {
        "media_player.sypialnia_homepod",
        "media_player.sypialnia_homepod_2",
    }
    assert {c.data["volume_level"] for c in dom["media_player.volume_set"]} == {0.6}
    assert set(_called(dom)) == {"media_player.volume_set"}


async def test_twins_after_yes_still_executed(
    hass: HomeAssistant, dom: dict, aioclient_mock: AiohttpClientMocker
) -> None:
    """When the question had another reason (uncertain name), „tak” executes on the twins."""
    _homepod_twins(hass)
    _control_ollama(
        aioclient_mock,
        {"intencja": "HassSetVolume", "domena": "media_player", "nazwa": "głośnika HomePod",
         "obszar": "Sypialnia", "wartosc": 30},
    )  # fmt: skip

    asked = await _say(hass, "ustaw głośność głośnika HomePod na 30 w sypialni")
    assert asked.continue_conversation, _speech(asked)
    done = await _say(hass, "tak", asked.conversation_id)

    assert _speech(done).startswith("Ustawiono głośność na 30%"), _speech(done)
    assert len(dom["media_player.volume_set"]) == 2


async def test_twins_pause_only_the_playing_one(
    hass: HomeAssistant, dom: dict, aioclient_mock: AiohttpClientMocker
) -> None:
    """Pause only the entity that is playing (the other has no queue)."""
    _homepod_twins(hass)
    _control_ollama(
        aioclient_mock,
        {"intencja": "HassMediaPause", "domena": "media_player", "nazwa": "HomePod",
         "obszar": "Sypialnia"},
    )  # fmt: skip

    result = await _say(hass, "zatrzymaj HomePod w sypialni")

    assert not result.continue_conversation, _speech(result)
    assert _entities(dom["media_player.media_pause"]) == {"media_player.sypialnia_homepod_2"}


async def test_bare_scene_name_is_not_a_command(hass: HomeAssistant, dom: dict) -> None:
    """Scene only when explicit („uruchom scenę dobranoc”); a bare „Dobranoc” or „Dzień dobry”
    is a greeting (summary topic), not a scene activation."""
    from custom_components.assist_router.control import collect_home, named_routine

    home = collect_home(hass)
    assert named_routine(home, "Dobranoc") is None
    assert named_routine(home, "Dobranoc!") is None
