"""Question router: topic from the model (mock Ollama), reference sentence, Wikipedia, options."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from homeassistant.components import conversation
from homeassistant.core import Context, HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
    AiohttpClientMockResponse,
)
import yaml

from custom_components.assist_router.const import (
    CONF_ANSWER_MODEL,
    CONF_LOG_UNRECOGNIZED,
    CONF_OLLAMA_URL,
    CONF_ROUTER_KEEP_ALIVE,
    CONF_ROUTER_MODEL,
    CONF_ROUTER_TIMEOUT,
)
from custom_components.assist_router.router import (
    OllamaSettings,
    RouterConfig,
    answer_messages,
    build_request,
    build_system_prompt,
    clean_extract,
    find_people,
    find_person,
    find_when,
    parse_config,
    parse_route,
    search_phrase,
    summary_messages,
    title_matches,
)

from .conftest import AGENT_ID, OLLAMA, ROUTER_YAML, WIKI
from .test_fallback import FakeLLM, _with_fallback


def _config() -> RouterConfig:
    import yaml

    return parse_config(yaml.safe_load(ROUTER_YAML))


def _answer(topic: str) -> dict:
    return {"message": {"role": "assistant", "content": json.dumps({"temat": topic})}}


async def _ask(hass: HomeAssistant, text: str):
    return await conversation.async_converse(
        hass, text, None, Context(), language="pl", agent_id=AGENT_ID
    )


def _speech(result) -> str:
    return result.response.speech["plain"]["speech"]


def _rows(hass: HomeAssistant) -> list[dict[str, str]]:
    path = Path(hass.config.path("assist", "unrecognized_commands.csv"))
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle, delimiter=";"))


# --- functions without HA ---


def test_parse_config_requires_topics() -> None:
    with pytest.raises(ValueError, match="topics"):
        parse_config({"people": {}})
    with pytest.raises(ValueError, match="unknown search"):
        parse_config({"topics": {"x": {"search": "google"}}})
    with pytest.raises(ValueError, match="bad match"):
        parse_config({"topics": {"x": {}}, "people": {"a": {"match": "("}}})


def test_prompt_and_schema() -> None:
    config = _config()
    prompt = build_system_prompt(config)
    assert "kalendarz (plany i wydarzenia)" in prompt
    assert '"Co mam jutro w pracy?" -> kalendarz' in prompt
    body = build_request(OllamaSettings(OLLAMA, "m", 5, -1), config, "pytanie")
    # the model returns only the topic
    assert body["format"]["properties"] == {
        "temat": {"type": "string", "enum": ["kalendarz", "lekcje", "auto", "wiedza", "inne"]}
    }
    assert body["keep_alive"] == -1
    assert build_request(OllamaSettings(OLLAMA, "m", 5, 30), config, "x")["keep_alive"] == "30m"


def test_parse_route() -> None:
    config = _config()
    route = parse_route(config, '{"temat": "lekcje"}', "Na którą Kasi jutro do szkoły?")
    assert route is not None
    assert (route.topic, route.person, route.when, route.phrase) == (
        "lekcje",
        "kasia",
        "tomorrow",
        None,
    )
    route = parse_route(config, '{"temat": "wiedza"}', "Kim był Mikołaj Kopernik?")
    assert route is not None and route.phrase == "Mikołaj Kopernik" and route.person is None
    assert parse_route(config, '{"temat": "pogoda"}', "x") is None
    assert parse_route(config, "nie json", "x") is None


def test_find_person_and_when() -> None:
    config = _config()
    assert find_person(config, "co ma Katarzyna") == "kasia"
    assert find_person(config, "Jan i Kasia") == "jan"  # first from the start
    assert find_person(config, "a Jaś?") is None  # 4 letters of the name by default: „jan”
    assert find_person(config, "kto ma salon") is None
    assert find_people(config, "ile mają Kasia i Jan") == ["kasia", "jan"]
    assert find_when("jaka pogoda pojutrze") == "day_after_tomorrow"
    assert find_when("JUTRO rano") == "tomorrow"
    assert find_when("co w sobotę") == "saturday"
    assert find_when("co mamy w weekend") == "weekend"
    assert find_when("czy w czwartek coś jest") == "thursday"
    assert find_when("w tym tygodniu") == "week"
    assert find_when("a dzisiaj?") == "today"
    assert find_when("gdzie jest auto") is None


def test_search_phrase_and_title() -> None:
    assert search_phrase("Co to jest czarna dziura?") == "czarna dziura"
    assert search_phrase("Opowiedz mi o fotosyntezie.") == "fotosyntezie"
    assert search_phrase("Gdzie leży Kraków") == "Kraków"
    assert title_matches("fotosyntezie", "Fotosynteza")
    assert not title_matches("Ile kaw dzisiaj wypiłem", "Tonpress")


def test_clean_extract() -> None:
    text = (
        "Mikołaj Kopernik (wym. [mʲiˈkɔwaj kɔˈpɛrɲik]; ur. 19 lutego 1473 w Toruniu) – "
        "astronom, matematyk. Twórca heliocentrycznego modelu Układu Słonecznego. "
        "Studiował m.in. w Krakowie. Był kanonikiem warmińskim. Zmarł we Fromborku."
    )
    result = clean_extract(text, 4)
    assert result is not None
    assert "wym." not in result and result.startswith("Mikołaj Kopernik – astronom")
    assert result.endswith("Był kanonikiem warmińskim.")  # 4 sentences, „m.in.” does not split
    assert clean_extract("Merkury – może oznaczać: planetę, boga.", 4) is None
    assert clean_extract("", 4) is None


# --- agent with the router ---


async def test_routed_to_canonical_sentence(
    hass: HomeAssistant, router: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.post(f"{OLLAMA}/api/chat", json=_answer("kalendarz"))

    result = await _ask(hass, "co mnie czeka jutro")

    assert _speech(result) == "Jutro o 17:30 robotyka."
    sent = aioclient_mock.mock_calls[0][2]
    assert sent["model"] == "bielik-1.5b"
    assert sent["messages"][1]["content"] == "co mnie czeka jutro"
    (row,) = _rows(hass)
    assert row["route"] == "kalendarz → jakie są jutro wydarzenia"
    assert row["response"] == "Jutro o 17:30 robotyka."


async def test_routed_with_person(
    hass: HomeAssistant, router: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.post(f"{OLLAMA}/api/chat", json=_answer("lekcje"))

    result = await _ask(hass, "kiedy Kasia wraca ze szkoły")

    assert _speech(result) == "Kasia kończy o 12:35."


async def test_wikipedia(
    hass: HomeAssistant, router: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.post(f"{OLLAMA}/api/chat", json=_answer("wiedza"))
    extract = "Mikołaj Kopernik – astronom. Twórca teorii heliocentrycznej."
    page = {"title": "Mikołaj Kopernik", "extract": extract}
    aioclient_mock.get(WIKI, json={"query": {"pages": {"1": page}}})

    result = await _ask(hass, "kim był Mikołaj Kopernik")

    assert _speech(result) == extract
    assert aioclient_mock.mock_calls[1][1].query["gsrsearch"] == "Mikołaj Kopernik"
    assert _rows(hass)[0]["route"] == "wiedza → Mikołaj Kopernik"


async def test_wikipedia_unrelated_article(
    hass: HomeAssistant, router: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """Whisper gibberish: the search finds something, but we don't read it out."""
    aioclient_mock.post(f"{OLLAMA}/api/chat", json=_answer("wiedza"))
    page = {"title": "Tonpress", "extract": "Tonpress – wydawnictwo."}
    aioclient_mock.get(WIKI, json={"query": {"pages": {"1": page}}})

    result = await _ask(hass, "wążek z przeznakami")

    assert _speech(result).startswith("Powiedziałeś:")
    assert _rows(hass)[0]["route"] == "wiedza → wążek z przeznakami (brak w Wikipedii)"


async def test_other_topic_goes_to_fallback(
    hass: HomeAssistant, router: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.post(f"{OLLAMA}/api/chat", json=_answer("inne"))
    llm = FakeLLM(answer="Nie umiem robić kanapek.")
    router_options = dict(router.options)
    await _with_fallback(hass, router, llm)  # overwrites options - restore the router
    hass.config_entries.async_update_entry(router, options={**router_options, **router.options})

    result = await _ask(hass, "zrób mi kanapkę")

    assert _speech(result) == "Nie umiem robić kanapek."
    assert _rows(hass)[0]["route"] == "inne"


async def test_router_error_goes_to_fallback(
    hass: HomeAssistant, router: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.post(f"{OLLAMA}/api/chat", status=500)

    result = await _ask(hass, "co mnie czeka jutro")

    # without a fallback agent „Powiedziałeś: …” remains
    assert _speech(result).startswith("Powiedziałeś: co mnie czeka jutro.")
    assert _rows(hass)[0]["route"] == ""


async def test_no_router_file(
    hass: HomeAssistant, router: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    Path(hass.config.path("assist", "router.yaml")).unlink()

    result = await _ask(hass, "co mnie czeka jutro")

    assert _speech(result).startswith("Powiedziałeś:")
    assert aioclient_mock.call_count == 0


async def test_logging_disabled(hass: HomeAssistant, setup: MockConfigEntry) -> None:
    hass.config_entries.async_update_entry(setup, options={CONF_LOG_UNRECOGNIZED: False})

    result = await _ask(hass, "zrób mi kanapkę")

    assert _speech(result).startswith("Powiedziałeś: zrób mi kanapkę.")
    assert _rows(hass) == []


async def test_csv_header_upgrade(hass: HomeAssistant, setup: MockConfigEntry) -> None:
    path = Path(hass.config.path("assist", "unrecognized_commands.csv"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "timestamp;area;device;kind;text;response\r\n"
        "2026-10-01 10:00:00;Salon;Głośnik;no_intent_match;stare;odp\r\n",
        encoding="utf-8-sig",
    )

    await _ask(hass, "zrób mi kanapkę")

    rows = _rows(hass)
    assert [r["text"] for r in rows] == ["stare", "zrób mi kanapkę"]
    assert rows[0]["route"] is None or rows[0]["route"] == ""


async def test_options_flow_router(
    hass: HomeAssistant, setup: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(
        f"{OLLAMA}/api/tags", json={"models": [{"name": "bielik-11b"}, {"name": "bielik-1.5b"}]}
    )
    menu = await hass.config_entries.options.async_init(setup.entry_id)
    assert menu["type"] == "menu"
    flow = await hass.config_entries.options.async_configure(
        menu["flow_id"], {"next_step_id": "settings"}
    )
    result = await hass.config_entries.options.async_configure(
        flow["flow_id"],
        {CONF_LOG_UNRECOGNIZED: False, "fallback_timeout": 30, CONF_OLLAMA_URL: OLLAMA + "/"},
    )
    assert result["type"] == "form" and result["step_id"] == "router"
    aioclient_mock.post(f"{OLLAMA}/api/generate", json={"done": True})
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_ROUTER_MODEL: "bielik-1.5b", CONF_ROUTER_TIMEOUT: 8, CONF_ROUTER_KEEP_ALIVE: -1},
    )
    await hass.async_block_till_done()
    assert result["type"] == "create_entry"
    assert setup.options[CONF_OLLAMA_URL] == OLLAMA
    assert setup.options[CONF_ROUTER_MODEL] == "bielik-1.5b"
    assert setup.options[CONF_LOG_UNRECOGNIZED] is False


async def test_options_flow_cannot_connect(
    hass: HomeAssistant, setup: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(f"{OLLAMA}/api/tags", status=500)
    menu = await hass.config_entries.options.async_init(setup.entry_id)
    assert menu["type"] == "menu"
    flow = await hass.config_entries.options.async_configure(
        menu["flow_id"], {"next_step_id": "settings"}
    )
    result = await hass.config_entries.options.async_configure(
        flow["flow_id"],
        {CONF_LOG_UNRECOGNIZED: True, "fallback_timeout": 30, CONF_OLLAMA_URL: OLLAMA},
    )
    assert result["type"] == "form" and result["errors"] == {CONF_OLLAMA_URL: "cannot_connect"}


# --- answer model ---


async def _with_answer_model(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    hass.config_entries.async_update_entry(
        entry, options={**entry.options, CONF_ANSWER_MODEL: "gemma-mala"}
    )
    await hass.async_block_till_done()
    aioclient_mock.mock_calls.clear()


def _chat_by_model(answers: dict[str, dict]):
    """Mock /api/chat: the reply depends on the model in the request (router or answer)."""

    async def handler(method, url, data):
        from pytest_homeassistant_custom_component.test_util.aiohttp import (
            AiohttpClientMockResponse,
        )

        return AiohttpClientMockResponse(method, url, json=answers[data["model"]])

    return handler


def test_answer_and_summary_messages() -> None:
    from datetime import datetime

    config = _config()
    messages = answer_messages(config, datetime(2026, 10, 21, 16, 1), "Jan: 7:30-12:40", "ile?")
    system = messages[0]["content"]
    assert "środa, 21 października 2026, godzina 16:01" in system
    assert "Domownicy: Tomek" in system and system.endswith("Dane:\nJan: 7:30-12:40")
    assert messages[1] == {"role": "user", "content": "ile?"}
    summary = summary_messages(config, "Tekst artykułu.", "kim był?")[0]["content"]
    assert "3–4 zdaniach" in summary and summary.endswith("Artykuł:\nTekst artykułu.")


async def test_answer_model_rewrites_data(
    hass: HomeAssistant, router: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    await _with_answer_model(hass, router, aioclient_mock)
    aioclient_mock.post(
        f"{OLLAMA}/api/chat",
        side_effect=_chat_by_model(
            {
                "bielik-1.5b": _answer("lekcje"),
                "gemma-mala": {"message": {"content": " Kasia kończy dziś o 12:35. "}},
            }
        ),
    )

    result = await _ask(hass, "kiedy Kasia wraca ze szkoły")

    assert _speech(result) == "Kasia kończy dziś o 12:35."
    answer_call = aioclient_mock.mock_calls[1][2]
    assert answer_call["model"] == "gemma-mala" and answer_call["think"] is False
    assert answer_call["messages"][0]["content"].endswith("Dane:\nKasia kończy o 12:35.")
    assert answer_call["messages"][1]["content"] == "kiedy Kasia wraca ze szkoły"
    assert _rows(hass)[0]["route"] == "lekcje → o której Kasia kończy lekcje + odpowiedź"


async def test_answer_model_error_reads_data(
    hass: HomeAssistant, router: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    await _with_answer_model(hass, router, aioclient_mock)
    calls = []

    async def handler(method, url, data):
        from pytest_homeassistant_custom_component.test_util.aiohttp import (
            AiohttpClientMockResponse,
        )

        calls.append(data["model"])
        if data["model"] == "gemma-mala":
            return AiohttpClientMockResponse(method, url, status=500)
        return AiohttpClientMockResponse(method, url, json=_answer("kalendarz"))

    aioclient_mock.post(f"{OLLAMA}/api/chat", side_effect=handler)

    result = await _ask(hass, "co mnie czeka jutro")

    assert _speech(result) == "Jutro o 17:30 robotyka."
    assert calls == ["bielik-1.5b", "gemma-mala"]


async def test_model_without_think_option(
    hass: HomeAssistant, router: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """A model without „thinking” rejects think (400) - the request is retried without it."""

    async def handler(method, url, data):
        from pytest_homeassistant_custom_component.test_util.aiohttp import (
            AiohttpClientMockResponse,
        )

        if "think" in data:
            return AiohttpClientMockResponse(method, url, status=400)
        return AiohttpClientMockResponse(method, url, json=_answer("kalendarz"))

    aioclient_mock.post(f"{OLLAMA}/api/chat", side_effect=handler)

    result = await _ask(hass, "co mnie czeka jutro")

    assert _speech(result) == "Jutro o 17:30 robotyka."
    assert ["think" in call[2] for call in aioclient_mock.mock_calls] == [True, False]


async def test_wikipedia_summary(
    hass: HomeAssistant, router: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    await _with_answer_model(hass, router, aioclient_mock)
    summary = "Kopernik był astronomem. Stworzył model heliocentryczny. Urodził się w Toruniu."
    aioclient_mock.post(
        f"{OLLAMA}/api/chat",
        side_effect=_chat_by_model(
            {"bielik-1.5b": _answer("wiedza"), "gemma-mala": {"message": {"content": summary}}}
        ),
    )
    article = "== Życiorys ==\nMikołaj Kopernik (ur. 1473 w Toruniu) – astronom[a]."
    page = {"title": "Mikołaj Kopernik", "extract": article}
    aioclient_mock.get(WIKI, json={"query": {"pages": {"1": page}}})

    result = await _ask(hass, "kim był Mikołaj Kopernik")

    assert _speech(result) == summary
    sent = next(
        c[2] for c in aioclient_mock.mock_calls if c[2] and c[2].get("model") == "gemma-mala"
    )["messages"][0]["content"]
    # article without „==” headings and without footnotes
    assert sent.endswith("Artykuł:\nŻyciorys. Mikołaj Kopernik (ur. 1473 w Toruniu) – astronom.")
    assert "exintro" not in aioclient_mock.mock_calls[1][1].query
    assert _rows(hass)[0]["route"] == "wiedza → Mikołaj Kopernik + streszczenie"


async def test_preload_and_context(
    hass: HomeAssistant, router: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """After an options change both models are loaded with the same context as in requests."""
    await _with_answer_model(hass, router, aioclient_mock)  # clears the calls - repeat it
    hass.config_entries.async_update_entry(router, options={**router.options, "answer_timeout": 9})
    await hass.async_block_till_done()
    loads = {c[2]["model"]: c[2] for c in aioclient_mock.mock_calls if c[1].path == "/api/generate"}
    assert loads["bielik-1.5b"]["options"]["num_ctx"] == 4096
    assert loads["gemma-mala"]["options"]["num_ctx"] == 8192
    assert loads["gemma-mala"]["keep_alive"] == -1

    aioclient_mock.mock_calls.clear()
    aioclient_mock.post(f"{OLLAMA}/api/chat", json=_answer("kalendarz"))
    await _ask(hass, "co mnie czeka jutro")
    assert aioclient_mock.mock_calls[0][2]["options"]["num_ctx"] == 4096


async def test_no_valid_targets_routed_only_with_data(
    hass: HomeAssistant, router: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """HA takes „… w szkole” for an area: the router answers only with a topic that has data."""
    aioclient_mock.post(f"{OLLAMA}/api/chat", json=_answer("kalendarz"))
    result = await _ask(hass, "włącz światło w szkole")
    assert _speech(result) == "Jutro o 17:30 robotyka."
    assert _rows(hass)[0]["kind"] == "no_valid_targets"

    aioclient_mock.clear_requests()
    aioclient_mock.post(f"{OLLAMA}/api/chat", json=_answer("inne"))
    result = await _ask(hass, "włącz światło w szkole")
    # no data: HA's message stays, the fallback agent is not asked
    assert "szkole" in _speech(result) and not _speech(result).startswith("Powiedziałeś")


async def test_router_failure_preloads_model(
    hass: HomeAssistant, router: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """The router did not reply (e.g. model evicted from memory) - loading in the background."""
    aioclient_mock.post(f"{OLLAMA}/api/chat", status=500)

    await _ask(hass, "co mnie czeka jutro")
    await hass.async_block_till_done()

    loads = [c[2]["model"] for c in aioclient_mock.mock_calls if c[1].path == "/api/generate"]
    assert loads == ["bielik-1.5b"]


async def test_several_canonical_questions(
    hass: HomeAssistant, router: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """„Dzieci” without a name: several reference questions (;) - data from all of them."""
    path = Path(hass.config.path("assist", "router.yaml"))
    path.write_text(
        ROUTER_YAML.replace(
            'command: "o której {{ osoba }} kończy lekcje"',
            'command: "{% if osoba %}o której {{ osoba }} kończy lekcje{% else %}'
            "o której Kasia kończy lekcje; o której Jan kończy lekcje; "
            'nieznane pytanie{% endif %}"',
        ),
        encoding="utf-8",
    )
    await _with_answer_model(hass, router, aioclient_mock)
    aioclient_mock.post(
        f"{OLLAMA}/api/chat",
        side_effect=_chat_by_model(
            {
                "bielik-1.5b": _answer("lekcje"),
                "gemma-mala": {"message": {"content": "Obie o 12:35."}},
            }
        ),
    )

    result = await _ask(hass, "o której dzieci kończą lekcje")

    assert _speech(result) == "Obie o 12:35."
    data = aioclient_mock.mock_calls[1][2]["messages"][0]["content"]
    # an unrecognized question from the list is skipped
    assert data.endswith("Dane:\nKasia kończy o 12:35.\nJan kończy o 12:35.")


async def test_topic_entities(
    hass: HomeAssistant, router: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """Topic with entities: states (in Polish, without unknown) go to the answer model."""
    attrs = {"friendly_name": "Auto Przebieg", "unit_of_measurement": "km"}
    hass.states.async_set("sensor.auto_przebieg", "156232", attrs)
    hass.states.async_set(
        "binary_sensor.auto_szyba", "on", {"friendly_name": "Auto Szyba", "device_class": "window"}
    )
    hass.states.async_set("binary_sensor.auto_swiatlo", "unknown", {"friendly_name": "Światło"})
    hass.states.async_set("sensor.inne", "5", {"friendly_name": "Inne"})
    await _with_answer_model(hass, router, aioclient_mock)
    aioclient_mock.post(
        f"{OLLAMA}/api/chat",
        side_effect=_chat_by_model(
            {
                "bielik-1.5b": _answer("auto"),
                "gemma-mala": {"message": {"content": "Przebieg to 156232 km."}},
            }
        ),
    )

    result = await _ask(hass, "ile kilometrów przejechało auto")

    assert _speech(result) == "Przebieg to 156232 km."
    data = aioclient_mock.mock_calls[1][2]["messages"][0]["content"]
    assert data.endswith(
        "Dane:\nStany urządzeń:\nAuto Przebieg: 156232 km\nAuto Szyba: otwarte (przed chwilą)"
    )
    assert _rows(hass)[0]["route"] == "auto + 2 encji + odpowiedź"


async def test_topic_entities_without_answer_model(
    hass: HomeAssistant, router: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """Bare entity states are not read aloud - the question goes on (fallback agent)."""
    hass.states.async_set("sensor.auto_przebieg", "156232", {"unit_of_measurement": "km"})
    aioclient_mock.post(f"{OLLAMA}/api/chat", json=_answer("auto"))

    result = await _ask(hass, "ile kilometrów przejechało auto")

    assert _speech(result).startswith("Powiedziałeś:")


async def test_topic_entities_only_exposed(
    hass: HomeAssistant, router: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """only_exposed: true - only entities exposed to Assist."""
    from homeassistant.components.homeassistant.exposed_entities import async_expose_entity

    path = Path(hass.config.path("assist", "router.yaml"))
    path.write_text("only_exposed: true\n" + ROUTER_YAML, encoding="utf-8")
    hass.states.async_set("sensor.auto_przebieg", "156232", {"friendly_name": "Auto Przebieg"})
    hass.states.async_set("sensor.auto_paliwo", "13", {"friendly_name": "Auto Paliwo"})
    async_expose_entity(hass, "conversation", "sensor.auto_paliwo", True)
    async_expose_entity(hass, "conversation", "sensor.auto_przebieg", False)
    await _with_answer_model(hass, router, aioclient_mock)
    aioclient_mock.post(
        f"{OLLAMA}/api/chat",
        side_effect=_chat_by_model(
            {"bielik-1.5b": _answer("auto"), "gemma-mala": {"message": {"content": "13 l."}}}
        ),
    )

    await _ask(hass, "ile paliwa ma auto")

    data = aioclient_mock.mock_calls[1][2]["messages"][0]["content"]
    assert data.endswith("Stany urządzeń:\nAuto Paliwo: 13")


async def test_entity_lines_classes_attributes_skip(hass: HomeAssistant, setup) -> None:
    """Sensor kind filter, thermostat and player attributes, skipping states."""
    from custom_components.assist_router.router import entity_lines

    hass.states.async_set(
        "binary_sensor.okno_salon", "on", {"friendly_name": "Okno salon", "device_class": "window"}
    )
    hass.states.async_set(
        "binary_sensor.ruch_salon", "on", {"friendly_name": "Ruch salon", "device_class": "motion"}
    )
    hass.states.async_set(
        "climate.salon",
        "heat",
        {"friendly_name": "Termostat", "current_temperature": 21.5, "temperature": 22},
    )
    hass.states.async_set(
        "media_player.tv",
        "playing",
        {"friendly_name": "TV", "media_title": "Wiadomości", "volume_level": 0.3},
    )
    hass.states.async_set("media_player.glosnik", "off", {"friendly_name": "Głośnik"})

    assert entity_lines(hass, ("binary_sensor.*|window,door",)) == [
        "Okno salon: otwarte (przed chwilą)"
    ]
    assert entity_lines(hass, ("climate.*",)) == ["Termostat: heat (jest 21.5°, ustawione 22°)"]
    assert entity_lines(hass, ("media_player.*",), skip_states=("off",)) == [
        "TV: playing (gra: Wiadomości, głośność 30%)"
    ]


async def test_entity_lines_unavailable_and_aliases(hass: HomeAssistant, setup) -> None:
    """`unavailable: true` - unavailable as „niedostępne”; registry aliases next to the name."""
    from homeassistant.helpers import entity_registry as er

    from custom_components.assist_router.router import entity_lines, parse_config

    ent_reg = er.async_get(hass)
    lustro = ent_reg.async_get_or_create("switch", "zha", "lustro")
    ent_reg.async_update_entity(lustro.entity_id, aliases={"Lustro", "Oświetlenie lustra"})
    grzanie = ent_reg.async_get_or_create("switch", "zha", "grzanie")
    hass.states.async_set(lustro.entity_id, "on", {"friendly_name": "Łazienka Oświetlenie"})
    hass.states.async_set(
        grzanie.entity_id,
        "unavailable",
        {"friendly_name": "Ogrzewanie lustra", "unit_of_measurement": "W"},
    )
    hass.states.async_set("switch.nieznany", "unknown", {"friendly_name": "Nieznany"})

    assert entity_lines(hass, ("switch.*",)) == [
        "Łazienka Oświetlenie (inaczej: Lustro, Oświetlenie lustra): włączone"
    ]
    assert entity_lines(hass, ("switch.*",), unavailable=True) == [
        "Ogrzewanie lustra: niedostępne",
        "Łazienka Oświetlenie (inaczej: Lustro, Oświetlenie lustra): włączone",
    ]
    config = parse_config({"topics": {"urzadzenia": {"unavailable": True}, "inne": {}}})
    assert config.topics["urzadzenia"].unavailable
    assert not config.topics["inne"].unavailable


async def test_todo_items(hass: HomeAssistant, setup) -> None:
    """To-do list: items from todo.get_items instead of just the count."""
    from homeassistant.core import SupportsResponse

    from custom_components.assist_router.router import async_todo_lines

    hass.states.async_set("todo.zakupy", "2", {"friendly_name": "Zakupy"})

    async def get_items(call):
        return {"todo.zakupy": {"items": [{"summary": "mleko"}, {"summary": "chleb"}]}}

    hass.services.async_register(
        "todo", "get_items", get_items, supports_response=SupportsResponse.ONLY
    )
    lines = await async_todo_lines(hass, ["Zakupy: 2"], ("todo.*",))
    assert lines == ["Zakupy: mleko, chleb"]


async def test_no_valid_targets_routed_to_entities_topic(
    hass: HomeAssistant, router: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """„Czy akwarium jest włączone?” - HA looks for a device „akwarium”; an entity topic helps."""
    attrs = {"friendly_name": "Auto Przebieg", "unit_of_measurement": "km"}
    hass.states.async_set("sensor.auto_przebieg", "156232", attrs)
    await _with_answer_model(hass, router, aioclient_mock)
    aioclient_mock.post(
        f"{OLLAMA}/api/chat",
        side_effect=_chat_by_model(
            {"bielik-1.5b": _answer("auto"), "gemma-mala": {"message": {"content": "156232 km."}}}
        ),
    )

    result = await _ask(hass, "włącz światło w szkole")

    assert _speech(result) == "156232 km."
    assert _rows(hass)[0]["kind"] == "no_valid_targets"


SOURCE_TOPICS = """
  szkola:
    description: plan lekcji
    details: [sensor.plan_lekcji]
    days: dzis
  plany:
    description: kalendarz
    days: "14"
    fetch:
      - action: calendar.get_events
        entities: [calendar.rodzina]
        data: {start_date_time: "{start}", end_date_time: "{end}"}
"""


async def test_topic_details_and_fetch(
    hass: HomeAssistant, router: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """Data from entity attributes (person and day from the question) and a service response."""
    from homeassistant.core import SupportsResponse
    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import async_mock_service

    from custom_components.assist_router.languages import LANG

    path = Path(hass.config.path("assist", "router.yaml"))
    path.write_text(ROUTER_YAML.replace("  wiedza:\n", SOURCE_TOPICS + "  wiedza:\n"), "utf-8")
    today = dt_util.now().date().isoformat()
    hass.states.async_set(
        "sensor.plan_lekcji",
        today,
        {
            "friendly_name": "Plan lekcji",
            "children": [
                {"child": "Katarzyna", "days": [{"date": today, "end": "14:25"},
                                            {"date": "2000-01-01", "end": "9:00"}]},
                {"child": "Jan", "days": [{"date": today, "end": "12:40"}]},
            ],
        },
    )  # fmt: skip
    hass.states.async_set("calendar.rodzina", "off", {"friendly_name": "Rodzina"})
    calls = async_mock_service(
        hass, "calendar", "get_events",
        response={"calendar.rodzina": {"events": [{"start": today, "summary": "Basen"}]}},
        supports_response=SupportsResponse.ONLY,
    )  # fmt: skip
    await _with_answer_model(hass, router, aioclient_mock)
    topic = iter(["szkola", "plany"])

    async def handler(method, url, data):
        if data["model"] == "bielik-1.5b":
            return AiohttpClientMockResponse(method, url, json=_answer(next(topic)))
        return AiohttpClientMockResponse(method, url, json={"message": {"content": "Gotowe."}})

    aioclient_mock.post(f"{OLLAMA}/api/chat", side_effect=handler)

    await _ask(hass, "O której Kasia kończy dziś lekcje?")
    await _ask(hass, "Co mamy w planach?")

    answers = [c[2] for c in aioclient_mock.mock_calls if c[2]["model"] == "gemma-mala"]
    lessons = answers[0]["messages"][0]["content"].split("Dane:")[1]
    assert (
        f"Plan lekcji (stan: {today}):\nchildren:\n- child: Katarzyna\n  days:\n"
        f"  - date: {today} ({LANG.WEEKDAY_NAMES[dt_util.now().weekday()]})\n    end: '14:25'"
        in lessons
    )
    assert "Jan" not in lessons and "9:00" not in lessons
    assert "Rodzina:\nevents:\n- start: " in answers[1]["messages"][0]["content"]
    # no day in the question - 14 days from today
    assert str(calls[0].data["start_date_time"]).startswith(today)
    assert _rows(hass)[0]["route"] == "szkola + 1 źródeł + odpowiedź"


def test_entity_patterns_order_and_exclusions() -> None:
    from types import SimpleNamespace

    from custom_components.assist_router.router import by_pattern

    def state(entity_id, device_class=None):
        return SimpleNamespace(entity_id=entity_id, attributes={"device_class": device_class})

    states = [
        state("binary_sensor.ruch", "motion"), state("person.jan"), state("light.salon"),
        state("light.ipad_ekran"), state("binary_sensor.okno", "window"),
    ]  # fmt: skip
    found = by_pattern(states, ("person.*", "binary_sensor.*|motion", "light.*", "!light.ipad_*"))
    assert [s.entity_id for s in found] == ["person.jan", "binary_sensor.ruch", "light.salon"]


async def test_fetch_only_read_only_services(
    hass: HomeAssistant, router: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """fetch with a service that does something (not only returns data) - skipped, nothing runs."""
    from pytest_homeassistant_custom_component.common import async_mock_service

    path = Path(hass.config.path("assist", "router.yaml"))
    topic = """
  zamek:
    description: zamek
    fetch:
      - action: lock.unlock
        entities: [lock.drzwi]
"""
    path.write_text(ROUTER_YAML.replace("  wiedza:\n", topic + "  wiedza:\n"), "utf-8")
    hass.states.async_set("lock.drzwi", "locked", {"friendly_name": "Drzwi"})
    unlock = async_mock_service(hass, "lock", "unlock")
    await _with_answer_model(hass, router, aioclient_mock)
    aioclient_mock.post(
        f"{OLLAMA}/api/chat",
        side_effect=_chat_by_model(
            {"bielik-1.5b": _answer("zamek"), "gemma-mala": {"message": {"content": "?"}}}
        ),
    )

    await _ask(hass, "czy drzwi są zamknięte")

    assert not unlock


@pytest.mark.parametrize(
    ("file_name", "calendar", "control"),
    [
        ("router.example.yaml", "calendar", "control"),
        ("router.example.pl.yaml", "kalendarz", "sterowanie"),
    ],
)
def test_example_config_is_valid(file_name: str, calendar: str, control: str) -> None:
    """The example router.yaml files from the repository (described in the docs) always load."""
    import yaml

    path = Path(__file__).resolve().parents[1] / file_name
    config = parse_config(yaml.safe_load(path.read_text(encoding="utf-8")))
    assert config.topics[calendar].fetch[0].merge == "events"
    assert config.topics[control].control
    assert not any(topic.command for topic in config.topics.values())


async def test_wikipedia_retries_with_spelling_suggestion(
    hass: HomeAssistant, router: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """Typo in the query („norznej”): no result - Wikipedia's spelling suggestion and a retry."""
    import yaml

    from custom_components.assist_router.router import async_search_wikipedia, parse_config

    async def handler(method, url, data):
        query = dict(url.query)
        if query.get("list") == "search":
            return AiohttpClientMockResponse(
                method,
                url,
                json={
                    "query": {
                        "searchinfo": {"suggestion": "mistrzostwa świata w piłce nożnej"},
                        "search": [],
                    }
                },
            )
        if "norznej" in query.get("gsrsearch", ""):
            return AiohttpClientMockResponse(method, url, json={"batchcomplete": ""})
        page = {
            "title": "Mistrzostwa świata w piłce nożnej",
            "extract": "Mistrzostwa świata w piłce nożnej - turniej. Ostatnio wygrała Argentyna.",
        }
        return AiohttpClientMockResponse(method, url, json={"query": {"pages": {"1": page}}})

    aioclient_mock.get(WIKI, side_effect=handler)
    config = parse_config(yaml.safe_load(ROUTER_YAML))

    article = await async_search_wikipedia(hass, config, "mistrzem świata w piłce norznej", 5)

    assert article and "Argentyna" in article


# --- recognized speaker (Assist Speaker ID integration) ---


def _speaker_config():
    from custom_components.assist_router.router import parse_config

    return parse_config(
        {
            "people": {
                "kasia": {"name": "Kasia", "match": "kasi|katarz"},
                "jan": {"name": "Jan", "speaker": "jan_g"},
            },
            "topics": {"szkola": {"description": "plan lekcji"}},
        }
    )


@pytest.mark.parametrize(
    ("text", "speaker", "people"),
    [
        ("Jakie mam dzisiaj zajęcia?", "kasia", ("kasia",)),
        ("Kiedy kończę lekcje? Czy mam basen?", "kasia", ("kasia",)),
        ("Pokaż moje oceny", "jan_g", ("jan",)),  # own voice identifier
        ("Jakie zajęcia ma Jan?", "kasia", ("jan",)),  # the name in the question wins
        ("Jaki jest plan lekcji na jutro?", "kasia", ()),  # no 1st person - everyone
        ("Co mamy dziś na obiad?", "kasia", ()),  # „mamy” = we, not the speaker
        ("Jakie mam dzisiaj zajęcia?", None, ()),  # unknown speaker
        ("Jakie mam dzisiaj zajęcia?", "gosc", ()),  # voice not in router.yaml
    ],
)
def test_apply_speaker(text: str, speaker: str | None, people: tuple[str, ...]) -> None:
    from custom_components.assist_router.router import Route, apply_speaker, find_people

    config = _speaker_config()
    found = tuple(find_people(config, text))
    route = Route(
        topic="szkola", person=found[0] if found else None, when=None, phrase=None, people=found
    )

    result = apply_speaker(config, route, text, speaker)

    assert result.people == people
    assert result.person == (people[0] if people else None)


def test_answer_prompt_names_speaker() -> None:
    from datetime import datetime

    from custom_components.assist_router.router import answer_messages

    config = _speaker_config()
    with_speaker = answer_messages(config, datetime(2026, 10, 23, 8), "dane", "pytanie", "Kasia")
    without = answer_messages(config, datetime(2026, 10, 23, 8), "dane", "pytanie")

    assert "\nPyta: Kasia.\nDane:\ndane" in with_speaker[0]["content"]
    assert "Pyta:" not in without[0]["content"]


async def test_speaker_question_gets_own_data(
    hass: HomeAssistant,
    router: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """„Jakie mam dzisiaj zajęcia?” from Kasia: only her schedule; model and CSV know who asks."""
    from homeassistant.util import dt as dt_util

    from custom_components.assist_router import conversation as agent_module

    path = Path(hass.config.path("assist", "router.yaml"))
    path.write_text(ROUTER_YAML.replace("  wiedza:\n", SOURCE_TOPICS + "  wiedza:\n"), "utf-8")
    today = dt_util.now().date().isoformat()
    hass.states.async_set(
        "sensor.plan_lekcji",
        today,
        {
            "friendly_name": "Plan lekcji",
            "children": [
                {"child": "Katarzyna", "days": [{"date": today, "end": "14:25"}]},
                {"child": "Jan", "days": [{"date": today, "end": "12:40"}]},
            ],
        },
    )
    await _with_answer_model(hass, router, aioclient_mock)
    aioclient_mock.post(
        f"{OLLAMA}/api/chat",
        side_effect=_chat_by_model(
            {"bielik-1.5b": _answer("szkola"), "gemma-mala": {"message": {"content": "Do 14:25."}}}
        ),
    )
    monkeypatch.setattr(agent_module, "current_speaker", lambda hass: ("kasia", "Katarzyna G."))

    result = await _ask(hass, "Jakie mam dzisiaj zajęcia?")

    assert _speech(result) == "Do 14:25."
    answer = next(c[2] for c in aioclient_mock.mock_calls if c[2]["model"] == "gemma-mala")
    system = answer["messages"][0]["content"]
    assert "Pyta: Kasia." in system  # name from router.yaml, not from Assist Speaker ID
    data = system.split("Dane:")[1]
    assert "Katarzyna" in data and "Jan" not in data and "12:40" not in data
    assert _rows(hass)[0]["speaker"] == "Katarzyna G."


def test_current_speaker_without_integration() -> None:
    from custom_components.assist_router.conversation import current_speaker

    assert current_speaker(None) == (None, None)  # no custom_components.speaker_id


async def test_enrollment_sample_gets_short_reply_without_models(
    hass: HomeAssistant,
    router: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Voice enrollment (Assist Speaker ID): „Nagrano 3 z 10” at once, keeps listening, no model."""
    from custom_components.assist_router import conversation as agent_module

    monkeypatch.setattr(
        agent_module, "enrollment_reply", lambda hass: ("Nagrano 3 z 10. Kolejne zdanie.", True)
    )
    aioclient_mock.mock_calls.clear()

    result = await _ask(hass, "Jaka będzie jutro pogoda we Krakowie?")

    assert _speech(result) == "Nagrano 3 z 10. Kolejne zdanie."
    assert result.continue_conversation
    assert not aioclient_mock.mock_calls  # neither the router nor the answer model
    assert _rows(hass) == []  # this is not an unrecognized command


def test_enrollment_reply_without_integration() -> None:
    from custom_components.assist_router.conversation import enrollment_reply

    assert enrollment_reply(None) is None


# --- people's entities (owns) and the speaker's room (room) ---

OWNERS_YAML = """
household: "Domownicy: Tomek, Kasia, Jan."
people:
  tomek: {name: Tomek, match: "tomek|tat", owns: [calendar.praca_tomek]}
  kasia: {name: Kasia, match: "kasi|katarz", owns: calendar.kalendarz_kasia, room: Pokój Dziewczyn}
  jan: {name: Jan, owns: [calendar.kalendarz_jan]}
topics:
  plany:
    description: kalendarz
    days: "14"
    fetch:
      - action: calendar.get_events
        entities: [calendar.*]
        data: {start_date_time: "{start}", end_date_time: "{end}"}
        merge: events
  inne:
    description: wszystko inne
"""


def test_owned_by_others() -> None:
    from custom_components.assist_router.router import owned_by_others, parse_config

    config = parse_config(yaml.safe_load(OWNERS_YAML))
    assert config.people["kasia"].owns == ("calendar.kalendarz_kasia",)
    assert config.people["kasia"].room == "Pokój Dziewczyn"
    assert owned_by_others(config, ("kasia",), "calendar.praca_tomek")
    assert not owned_by_others(config, ("kasia",), "calendar.kalendarz_kasia")
    assert not owned_by_others(config, ("kasia",), "calendar.family")  # shared
    assert not owned_by_others(config, (), "calendar.praca_tomek")  # nobody indicated


@pytest.mark.parametrize(
    ("text", "speaker", "expected"),
    [
        ("Zgaś światło w moim pokoju", "kasia", "Zgaś światło w Pokój Dziewczyn"),
        ("Zapal lampę u mnie w pokoju", "kasia", "Zapal lampę w Pokój Dziewczyn"),
        ("Zgaś światło w moim pokoju", "jan", "Zgaś światło w moim pokoju"),  # without room
        ("Zgaś światło w salonie", "kasia", "Zgaś światło w salonie"),
        ("Zgaś światło w moim pokoju", None, "Zgaś światło w moim pokoju"),
    ],
)
def test_with_speaker_room(text: str, speaker: str | None, expected: str) -> None:
    from custom_components.assist_router.router import parse_config, with_speaker_room

    config = parse_config(yaml.safe_load(OWNERS_YAML))
    assert with_speaker_room(config, text, speaker) == expected


@pytest.mark.parametrize(
    ("text", "speaker", "calendars"),
    [
        # speaker Kasia, 1st person: shared + her calendar
        ("Co mam jutro w planach?", ("kasia", "Kasia"),
         {"calendar.family", "calendar.kalendarz_kasia"}),
        # the name in the question beats the speaker
        ("Co ma jutro Jan?", ("tomek", "Tomek"), {"calendar.family", "calendar.kalendarz_jan"}),
        # question about everyone (no 1st person, no name) - all calendars
        ("Co się dzieje jutro?", ("kasia", "Kasia"),
         {"calendar.family", "calendar.kalendarz_kasia", "calendar.kalendarz_jan",
          "calendar.praca_tomek"}),
    ],
)  # fmt: skip
async def test_calendar_only_of_the_person_asked_about(
    hass: HomeAssistant,
    router: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    monkeypatch: pytest.MonkeyPatch,
    text: str,
    speaker: tuple[str, str],
    calendars: set[str],
) -> None:
    from homeassistant.core import SupportsResponse
    from pytest_homeassistant_custom_component.common import async_mock_service

    from custom_components.assist_router import conversation as agent_module

    Path(hass.config.path("assist", "router.yaml")).write_text(OWNERS_YAML, "utf-8")
    for entity_id in ("family", "kalendarz_kasia", "kalendarz_jan", "praca_tomek"):
        hass.states.async_set(f"calendar.{entity_id}", "off", {"friendly_name": entity_id})
    calls = async_mock_service(
        hass, "calendar", "get_events", response={}, supports_response=SupportsResponse.ONLY
    )
    await _with_answer_model(hass, router, aioclient_mock)
    aioclient_mock.post(
        f"{OLLAMA}/api/chat",
        side_effect=_chat_by_model(
            {"bielik-1.5b": _answer("plany"), "gemma-mala": {"message": {"content": "Nic."}}}
        ),
    )
    monkeypatch.setattr(agent_module, "current_speaker", lambda hass: speaker)

    await _ask(hass, text)

    targets = calls[0].data["entity_id"]
    assert set(targets if isinstance(targets, list) else [targets]) == calendars


LABELS_YAML = """
household: "Domownicy: Tomek, Kasia, Jan, Ola."
people:
  tomek: {name: Tomek, match: "tomek|tat", labels: Tomek}
  kasia: {name: Kasia, match: "kasi|katarz", labels: [kasia]}
  jan: {name: Jan, labels: [JAN]}
  ola: {name: Ola, match: "ol(a|i)", labels: [ola]}
family:
  parents: [tomek]
  children: [kasia, jan, ola]
topics:
  plany:
    description: kalendarz
    personal: true
    days: "14"
    fetch:
      - action: calendar.get_events
        entities: [calendar.*]
        data: {start_date_time: "{start}", end_date_time: "{end}"}
        merge: events
        title: Wydarzenia w kalendarzach
  inne:
    description: wszystko inne
"""


def test_owners_from_labels() -> None:
    """`labels` of a person (text or list, any case) match the HA labels of an entity."""
    from custom_components.assist_router.router import entity_owners, owned_by_others, parse_config

    config = parse_config(yaml.safe_load(LABELS_YAML))
    assert config.people["tomek"].labels == ("tomek",)
    assert config.people["jan"].labels == ("jan",)
    assert entity_owners(config, "calendar.x", frozenset({"kasia"})) == {"kasia"}
    assert entity_owners(config, "calendar.x", frozenset()) == set()
    assert owned_by_others(config, ("kasia",), "calendar.x", frozenset({"jan"}))
    assert not owned_by_others(config, ("kasia",), "calendar.x", frozenset({"kasia"}))
    assert not owned_by_others(config, ("kasia",), "calendar.family")  # shared


async def _labelled_calendars(hass: HomeAssistant) -> None:
    """calendar.family (shared) + one calendar per person, marked with HA labels."""
    from homeassistant.helpers import entity_registry as er, label_registry as lr

    labels, entities = lr.async_get(hass), er.async_get(hass)
    for name, owner in (("family", None), ("praca_tomek", "Tomek"), ("kalendarz_kasia", "Kasia"),
                        ("kalendarz_jan", "Jan")):  # fmt: skip
        entry = entities.async_get_or_create("calendar", "test", name, suggested_object_id=name)
        if owner:
            label = labels.async_get_label_by_name(owner) or labels.async_create(owner)
            entities.async_update_entity(entry.entity_id, labels={label.label_id})
        hass.states.async_set(entry.entity_id, "off", {"friendly_name": name})


@pytest.mark.parametrize(
    ("text", "speaker", "calendars"),
    [
        # personal topic: the speaker's calendar + the shared one, no 1st person needed
        ("Co jest jutro w kalendarzu?", ("kasia", "Kasia"),
         {"calendar.family", "calendar.kalendarz_kasia"}),
        # a parent also gets the children's calendars
        ("Co jest jutro w kalendarzu?", ("tomek", "Tomek"),
         {"calendar.family", "calendar.praca_tomek", "calendar.kalendarz_kasia",
          "calendar.kalendarz_jan"}),
        # the name in the question beats the speaker
        ("Co ma jutro Jan?", ("kasia", "Kasia"), {"calendar.family", "calendar.kalendarz_jan"}),
        # unknown speaker - everything
        ("Co jest jutro w kalendarzu?", (None, None),
         {"calendar.family", "calendar.praca_tomek", "calendar.kalendarz_kasia",
          "calendar.kalendarz_jan"}),
    ],
)  # fmt: skip
async def test_calendar_owners_from_ha_labels(
    hass: HomeAssistant,
    router: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    monkeypatch: pytest.MonkeyPatch,
    text: str,
    speaker: tuple,
    calendars: set[str],
) -> None:
    from homeassistant.core import SupportsResponse
    from pytest_homeassistant_custom_component.common import async_mock_service

    from custom_components.assist_router import conversation as agent_module

    Path(hass.config.path("assist", "router.yaml")).write_text(LABELS_YAML, "utf-8")
    await _labelled_calendars(hass)
    calls = async_mock_service(
        hass, "calendar", "get_events", response={}, supports_response=SupportsResponse.ONLY
    )
    await _with_answer_model(hass, router, aioclient_mock)
    aioclient_mock.post(
        f"{OLLAMA}/api/chat",
        side_effect=_chat_by_model(
            {"bielik-1.5b": _answer("plany"), "gemma-mala": {"message": {"content": "Nic."}}}
        ),
    )
    monkeypatch.setattr(agent_module, "current_speaker", lambda hass: speaker)

    await _ask(hass, text)

    targets = calls[0].data["entity_id"]
    assert set(targets if isinstance(targets, list) else [targets]) == calendars


async def test_person_without_own_calendar_is_told_so(
    hass: HomeAssistant,
    router: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ola has no calendar of her own: she gets the shared one, and the answer model is told
    that she has no own calendar - instead of saying „there are no events”."""
    from homeassistant.core import SupportsResponse
    from pytest_homeassistant_custom_component.common import async_mock_service

    from custom_components.assist_router import conversation as agent_module

    Path(hass.config.path("assist", "router.yaml")).write_text(LABELS_YAML, "utf-8")
    await _labelled_calendars(hass)
    calls = async_mock_service(
        hass, "calendar", "get_events", response={}, supports_response=SupportsResponse.ONLY
    )
    await _with_answer_model(hass, router, aioclient_mock)
    aioclient_mock.post(
        f"{OLLAMA}/api/chat",
        side_effect=_chat_by_model(
            {"bielik-1.5b": _answer("plany"), "gemma-mala": {"message": {"content": "Nic."}}}
        ),
    )
    monkeypatch.setattr(agent_module, "current_speaker", lambda hass: ("ola", "Ola"))

    await _ask(hass, "Co mam jutro?")

    assert calls[0].data["entity_id"] in ("calendar.family", ["calendar.family"])
    answer_call = next(c for c in aioclient_mock.mock_calls if c[2].get("model") == "gemma-mala")
    system = answer_call[2]["messages"][0]["content"]
    assert "Ola nie ma przypisanego własnego źródła „Wydarzenia w kalendarzach”" in system

    # someone with an own calendar is not told anything like that
    aioclient_mock.mock_calls.clear()
    monkeypatch.setattr(agent_module, "current_speaker", lambda hass: ("kasia", "Kasia"))
    await _ask(hass, "Co mam jutro?")
    answer_call = next(c for c in aioclient_mock.mock_calls if c[2].get("model") == "gemma-mala")
    assert "nie ma przypisanego" not in answer_call[2]["messages"][0]["content"]


async def test_fallback_agent_knows_the_speaker(
    hass: HomeAssistant, setup: MockConfigEntry, monkeypatch: pytest.MonkeyPatch
) -> None:
    from custom_components.assist_router import conversation as agent_module
    from custom_components.assist_router.const import CONF_FALLBACK_AGENT

    got = []

    class Recorder(conversation.AbstractConversationAgent):
        @property
        def supported_languages(self) -> list[str]:
            return ["pl"]

        async def async_process(self, user_input):
            from homeassistant.helpers import intent

            got.append(user_input)
            response = intent.IntentResponse(language="pl")
            response.async_set_speech("Odpowiedź.")
            return conversation.ConversationResult(response=response)

    other = MockConfigEntry(domain="test_fallback")
    other.add_to_hass(hass)
    conversation.async_set_agent(hass, other, Recorder())
    hass.config_entries.async_update_entry(setup, options={CONF_FALLBACK_AGENT: other.entry_id})
    await hass.async_block_till_done()
    monkeypatch.setattr(agent_module, "current_speaker", lambda hass: ("kasia", "Kasia"))

    result = await _ask(hass, "zrób mi kanapkę z serem")

    assert _speech(result) == "Odpowiedź."
    assert got[-1].extra_system_prompt == "Pyta: Kasia."


# --- family terms relative to the speaker (family) ---

FAMILY_YAML = """
people:
  tomek: {name: Tomek, match: "tomek|tat"}
  ania: {name: Ania, match: "ani|mam(a|y)\\\\b"}
  kasia: {name: Kasia, match: "kasi"}
  jan: {name: Jan, match: "jan"}
  tosia: {name: Tosia, match: "tosi"}
family:
  parents: [tomek, ania]
  children: [kasia, jan, tosia]
  men: [tomek, jan]
topics:
  osoby: {description: gdzie ktoś jest}
"""


@pytest.mark.parametrize(
    ("text", "speaker", "people"),
    [
        ("Gdzie jest mój brat?", "kasia", ["jan"]),
        ("Gdzie jest moja siostra?", "kasia", ["tosia"]),
        ("Gdzie są moje siostry?", "jan", ["kasia", "tosia"]),
        ("Co robi moje rodzeństwo?", "tosia", ["kasia", "jan"]),
        ("Gdzie jest mój syn?", "ania", ["jan"]),
        ("Gdzie jest moja córka?", "tomek", ["kasia", "tosia"]),
        ("Gdzie są moje dzieci?", "tomek", ["kasia", "jan", "tosia"]),
        ("Z bratem i siostrą", "tosia", ["jan", "kasia"]),  # order as spoken
        ("Gdzie jest mój syn?", "kasia", []),  # a child has no son
        ("Gdzie jest mój brat?", "jan", []),  # the only boy - no brother
        ("Gdzie jest mój brat?", None, []),  # unknown speaker
        ("Synoptyk mówi o deszczu", "tomek", []),  # „syn” only as a whole word
    ],
)
def test_relatives(text: str, speaker: str | None, people: list[str]) -> None:
    from custom_components.assist_router.router import parse_config, relatives

    config = parse_config(yaml.safe_load(FAMILY_YAML))
    assert relatives(config, text, speaker) == people


def test_relatives_join_names_and_skip_speaker() -> None:
    from custom_components.assist_router.router import (
        Route,
        apply_relatives,
        apply_speaker,
        find_people,
        parse_config,
    )

    config = parse_config(yaml.safe_load(FAMILY_YAML))
    text = "Czy mama i mój brat są w domu?"
    found = tuple(find_people(config, text))
    route = Route(topic="osoby", person=found[0], when=None, phrase=None, people=found)

    route = apply_speaker(config, apply_relatives(config, route, text, "kasia"), text, "kasia")

    assert route.people == ("ania", "jan")  # not Kasia, despite „mój”


def test_family_with_unknown_person() -> None:
    from custom_components.assist_router.router import parse_config

    data = yaml.safe_load(FAMILY_YAML)
    data["family"]["children"].append("ola")
    with pytest.raises(ValueError, match=r"family\.children"):
        parse_config(data)


# --- personal topics (personal): day summary from the speaker ---

PERSONAL_YAML = """
people:
  tomek: {name: Tomek, match: "tom|tat"}
  ania: {name: Ania, match: "ani|mam(a|y)\\\\b"}
  ola: {name: Ola, match: "ol(a|i)\\\\b"}
  kuba: {name: Kuba, match: "kub"}
family:
  parents: [tomek, ania]
  children: [ola, kuba]
  men: [tomek, kuba]
topics:
  dzien:
    description: podsumowanie dnia, dzień dobry
    personal: true
    answer_hint: "Przywitaj się po imieniu. Do 5 zdań."
    answer_tokens: 320
    details: [sensor.plan_lekcji]
    days: dzis
  inne:
    description: wszystko inne
"""


@pytest.mark.parametrize(
    ("text", "speaker", "people"),
    [
        ("Dzień dobry", "ania", ("ania", "ola", "kuba")),  # parent: themselves and the children
        ("Dzień dobry", "ola", ("ola",)),  # child: only themselves
        ("Dzień dobry", None, ()),  # unknown: everyone
        ("Jak wygląda dzień Kuby?", "ania", ("kuba",)),  # the name wins
    ],
)
def test_apply_personal(text: str, speaker: str | None, people: tuple[str, ...]) -> None:
    from custom_components.assist_router.router import Route, apply_personal, find_people

    config = parse_config(yaml.safe_load(PERSONAL_YAML))
    found = tuple(find_people(config, text))
    route = Route(topic="dzien", person=found[0] if found else None, when=None, phrase=None,
                  people=found)  # fmt: skip

    assert apply_personal(config, route, speaker).people == people


@pytest.mark.parametrize(
    ("speaker", "children_in_data"),
    [(("ania", "Ania"), {"Ola", "Kuba"}), (("ola", "Ola"), {"Ola"})],
)
async def test_good_morning_personal_summary(
    hass: HomeAssistant,
    router: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    monkeypatch: pytest.MonkeyPatch,
    speaker: tuple[str, str],
    children_in_data: set[str],
) -> None:
    """„Dzień dobry” without „mam”: parent - children's schedule in the data, child - only own;
    the topic hint and a longer limit go to the model."""
    from homeassistant.util import dt as dt_util

    from custom_components.assist_router import conversation as agent_module

    Path(hass.config.path("assist", "router.yaml")).write_text(PERSONAL_YAML, "utf-8")
    today = dt_util.now().date().isoformat()
    hass.states.async_set(
        "sensor.plan_lekcji",
        today,
        {"children": [{"child": "Ola", "days": [{"date": today, "end": "13:00"}]},
                      {"child": "Kuba", "days": [{"date": today, "end": "12:00"}]}]},
    )  # fmt: skip
    await _with_answer_model(hass, router, aioclient_mock)
    aioclient_mock.post(
        f"{OLLAMA}/api/chat",
        side_effect=_chat_by_model(
            {"bielik-1.5b": _answer("dzien"), "gemma-mala": {"message": {"content": "Hej!"}}}
        ),
    )
    monkeypatch.setattr(agent_module, "current_speaker", lambda hass: speaker)

    result = await _ask(hass, "Dzień dobry")

    assert _speech(result) == "Hej!"
    answer = next(c[2] for c in aioclient_mock.mock_calls if c[2]["model"] == "gemma-mala")
    system = answer["messages"][0]["content"]
    assert f"Pyta: {speaker[1]}." in system
    assert "Przywitaj się po imieniu. Do 5 zdań." in system
    assert answer["options"]["num_predict"] == 320
    data = system.split("Dane:")[1]
    assert {c for c in ("Ola", "Kuba") if c in data} == children_in_data


async def test_personal_topic_without_speaker_says_unknown(
    hass: HomeAssistant,
    router: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from custom_components.assist_router import conversation as agent_module

    Path(hass.config.path("assist", "router.yaml")).write_text(PERSONAL_YAML, "utf-8")
    hass.states.async_set("sensor.plan_lekcji", "x", {"children": []})
    await _with_answer_model(hass, router, aioclient_mock)
    aioclient_mock.post(
        f"{OLLAMA}/api/chat",
        side_effect=_chat_by_model(
            {"bielik-1.5b": _answer("dzien"), "gemma-mala": {"message": {"content": "Hej!"}}}
        ),
    )
    monkeypatch.setattr(agent_module, "current_speaker", lambda hass: (None, None))

    await _ask(hass, "Jak wygląda mój dzień?")

    answer = next(c[2] for c in aioclient_mock.mock_calls if c[2]["model"] == "gemma-mala")
    system = answer["messages"][0]["content"]
    assert "Nie wiadomo, kto pyta" in system
    assert "Pyta:" not in system


@pytest.mark.parametrize(
    ("speaker", "expected"),
    [
        ("ola", "dla Oli"),  # the person key wins
        ("kuba", "chłopiec"),  # child, boy
        ("tomek", "rodzic"),
        (None, "nieznany"),
        ("gosc", "nieznany"),  # voice not in router.yaml
    ],
)
def test_hint_for(speaker: str | None, expected: str) -> None:
    from custom_components.assist_router.router import hint_for

    data = yaml.safe_load(PERSONAL_YAML)
    data["topics"]["dzien"]["answer_hints"] = {
        "ola": "dla Oli",
        "boy": "chłopiec",
        "girl": "dziewczynka",
        "parent": "rodzic",
        "unknown": "nieznany",
    }
    config = parse_config(data)
    assert hint_for(config, config.topics["dzien"], speaker) == expected


def test_hint_for_falls_back_to_answer_hint() -> None:
    from custom_components.assist_router.router import hint_for

    data = yaml.safe_load(PERSONAL_YAML)
    data["topics"]["dzien"]["answer_hints"] = {"child": "dziecko"}
    config = parse_config(data)
    topic = config.topics["dzien"]
    assert hint_for(config, topic, "ola") == "dziecko"  # no girl -> child
    assert hint_for(config, topic, "tomek") == topic.answer_hint  # no parent -> shared


async def test_verbatim_command_is_read_as_is(
    hass: HomeAssistant, router: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """`verbatim: true` - the automation's reply from the reference sentence, no answer model
    (e.g. news in a fixed layout)."""
    path = Path(hass.config.path("assist", "router.yaml"))
    path.write_text(
        ROUTER_YAML.replace(
            "    command: >-\n      jakie są",
            "    verbatim: true\n    command: >-\n      jakie są",
            1,
        ),
        "utf-8",
    )
    await _with_answer_model(hass, router, aioclient_mock)
    aioclient_mock.post(
        f"{OLLAMA}/api/chat",
        side_effect=_chat_by_model(
            {"bielik-1.5b": _answer("kalendarz"), "gemma-mala": {"message": {"content": "X"}}}
        ),
    )

    result = await _ask(hass, "Co tam mamy jutro w planach?")

    assert _speech(result) == "Jutro o 17:30 robotyka."
    assert not [c for c in aioclient_mock.mock_calls if c[2]["model"] == "gemma-mala"]


def test_topic_days_accept_codes_and_language_pack_names() -> None:
    """`days:` takes day codes and the pack's names (Polish `jutro` = `tomorrow`)."""
    topics = {
        "a": {"description": "a", "days": "tomorrow"},
        "b": {"description": "b", "days": "jutro"},
        "c": {"description": "c", "days": 14},
    }
    config = parse_config({"topics": topics})
    assert [t.days for t in config.topics.values()] == ["tomorrow", "tomorrow", "14"]
    with pytest.raises(ValueError, match="unknown days 'kiedyś'"):
        parse_config({"topics": {"x": {"description": "x", "days": "kiedyś"}}})


async def test_entity_lines_skip_alias_markers(hass: HomeAssistant, setup) -> None:
    """Newer HA keeps markers (ComputedNameType - "use the entity name") among entity
    aliases; only text aliases are listed, and nothing breaks on the marker."""
    import enum

    from homeassistant.helpers import entity_registry as er

    from custom_components.assist_router.control import collect_home
    from custom_components.assist_router.router import entity_lines

    class ComputedNameType(enum.Enum):  # stand-in for the HA marker
        NAME = "name"

    ent_reg = er.async_get(hass)
    lustro = ent_reg.async_get_or_create("switch", "zha", "lustro")
    ent_reg.async_update_entity(lustro.entity_id, aliases={ComputedNameType.NAME, "Lustro"})
    hass.states.async_set(lustro.entity_id, "on", {"friendly_name": "Łazienka Oświetlenie"})

    assert entity_lines(hass, ("switch.*",)) == ["Łazienka Oświetlenie (inaczej: Lustro): włączone"]
    target = next(t for t in collect_home(hass).targets if t.entity_id == lustro.entity_id)
    assert target.names == ["Łazienka Oświetlenie", "Lustro"]


# --- probable speaker (Assist Speaker ID: voice below the threshold, but close) ---

PROBABLE_YAML = OWNERS_YAML.replace(
    "    description: kalendarz\n", "    description: kalendarz\n    personal: true\n"
).replace(
    "  inne:\n",
    "  pogoda:\n    description: pogoda\n    fetch:\n      - action: weather.get_forecasts\n"
    "        entities: [weather.dom]\n        data: {type: daily}\n"
    "  sterowanie:\n    description: sterowanie\n    control: true\n  inne:\n",
)


async def _probable_setup(
    hass: HomeAssistant,
    router: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    monkeypatch: pytest.MonkeyPatch,
    topic: str,
    probable: tuple[str | None, str | None] = ("kasia", "Kasia"),
    speaker: tuple[str | None, str | None] = (None, None),
):
    from homeassistant.core import SupportsResponse
    from pytest_homeassistant_custom_component.common import async_mock_service

    from custom_components.assist_router import conversation as agent_module

    Path(hass.config.path("assist", "router.yaml")).write_text(PROBABLE_YAML, "utf-8")
    for entity_id in ("family", "kalendarz_kasia", "kalendarz_jan", "praca_tomek"):
        hass.states.async_set(f"calendar.{entity_id}", "off", {"friendly_name": entity_id})
    hass.states.async_set("weather.dom", "sunny")
    calls = async_mock_service(
        hass, "calendar", "get_events", response={}, supports_response=SupportsResponse.ONLY
    )
    async_mock_service(
        hass,
        "weather",
        "get_forecasts",
        response={"weather.dom": {"forecast": [{"condition": "sunny", "temperature": 20}]}},
        supports_response=SupportsResponse.ONLY,
    )
    await _with_answer_model(hass, router, aioclient_mock)
    aioclient_mock.post(
        f"{OLLAMA}/api/chat",
        side_effect=_chat_by_model(
            {"bielik-1.5b": _answer(topic), "gemma-mala": {"message": {"content": "Masz basen."}}}
        ),
    )
    monkeypatch.setattr(agent_module, "current_speaker", lambda hass: speaker)
    monkeypatch.setattr(agent_module, "probable_speaker", lambda hass: probable)
    return calls


def _answer_system(aioclient_mock: AiohttpClientMocker) -> str:
    call = next(c for c in aioclient_mock.mock_calls if c[2].get("model") == "gemma-mala")
    return call[2]["messages"][0]["content"]


async def test_probable_speaker_gets_own_calendar_and_is_named(
    hass: HomeAssistant,
    router: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = await _probable_setup(hass, router, aioclient_mock, monkeypatch, "plany")

    result = await _ask(hass, "Co mam jutro w planach?")

    assert _speech(result) == "Wydaje mi się, że pyta Kasia. Masz basen."
    targets = calls[0].data["entity_id"]
    assert set(targets) == {"calendar.family", "calendar.kalendarz_kasia"}
    system = _answer_system(aioclient_mock)
    assert "Pyta: Kasia." in system
    assert "Nie wiadomo, kto pyta" not in system
    row = _rows(hass)[-1]
    assert row["speaker"] == "Kasia?"
    assert "(prawdopodobnie Kasia)" in row["route"]


async def test_recognized_speaker_is_not_named(
    hass: HomeAssistant,
    router: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _probable_setup(
        hass, router, aioclient_mock, monkeypatch, "plany", speaker=("kasia", "Kasia")
    )

    result = await _ask(hass, "Co mam jutro w planach?")

    assert _speech(result) == "Masz basen."


@pytest.mark.parametrize(
    ("topic", "text"),
    [
        ("pogoda", "Jaka będzie jutro pogoda?"),  # the speaker does not matter
        ("plany", "Co ma jutro Jan?"),  # the name in the question beats the speaker
    ],
)
async def test_probable_speaker_not_used_is_not_said(
    hass: HomeAssistant,
    router: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    monkeypatch: pytest.MonkeyPatch,
    topic: str,
    text: str,
) -> None:
    await _probable_setup(hass, router, aioclient_mock, monkeypatch, topic)

    result = await _ask(hass, text)

    assert _speech(result) == "Masz basen."
    assert "Pyta:" not in _answer_system(aioclient_mock)


async def test_probable_speaker_room_in_control(
    hass: HomeAssistant,
    router: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from homeassistant.helpers import intent

    from custom_components.assist_router import conversation as agent_module

    await _probable_setup(hass, router, aioclient_mock, monkeypatch, "sterowanie")
    got = []

    async def control(self, user_input, text, conversation_id, config, ollama):
        got.append(text)
        response = intent.IntentResponse(language="pl")
        response.async_set_speech("Wyłączono: lampa.")
        return conversation.ConversationResult(response=response), "sterowanie"

    monkeypatch.setattr(agent_module.AssistRouterAgent, "_control", control)

    result = await _ask(hass, "Zgaś światło w moim pokoju")

    assert got == ["Zgaś światło w Pokój Dziewczyn"]
    assert _speech(result) == "Wydaje mi się, że pyta Kasia. Wyłączono: lampa."


async def test_fallback_agent_does_not_get_probable_speaker(
    hass: HomeAssistant, setup: MockConfigEntry, monkeypatch: pytest.MonkeyPatch
) -> None:
    from custom_components.assist_router import conversation as agent_module
    from custom_components.assist_router.const import CONF_FALLBACK_AGENT

    got = []

    class Recorder(conversation.AbstractConversationAgent):
        @property
        def supported_languages(self) -> list[str]:
            return ["pl"]

        async def async_process(self, user_input):
            from homeassistant.helpers import intent

            got.append(user_input)
            response = intent.IntentResponse(language="pl")
            response.async_set_speech("Odpowiedź.")
            return conversation.ConversationResult(response=response)

    other = MockConfigEntry(domain="test_fallback")
    other.add_to_hass(hass)
    conversation.async_set_agent(hass, other, Recorder())
    hass.config_entries.async_update_entry(setup, options={CONF_FALLBACK_AGENT: other.entry_id})
    await hass.async_block_till_done()
    monkeypatch.setattr(agent_module, "current_speaker", lambda hass: (None, None))
    monkeypatch.setattr(agent_module, "probable_speaker", lambda hass: ("kasia", "Kasia"))

    await _ask(hass, "zrób mi kanapkę z serem")

    assert not got[-1].extra_system_prompt


def test_probable_speaker_from_result(monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    from custom_components.assist_router import conversation as agent_module

    monkeypatch.setattr(
        agent_module,
        "speaker_result",
        lambda hass: SimpleNamespace(probable="kasia", probable_name="Kasia"),
    )
    assert agent_module.probable_speaker(None) == ("kasia", "Kasia")
    # Assist Speaker ID 0.1.x - no such field
    monkeypatch.setattr(agent_module, "speaker_result", lambda hass: SimpleNamespace(speaker=None))
    assert agent_module.probable_speaker(None) == (None, None)
    monkeypatch.setattr(agent_module, "speaker_result", lambda hass: None)
    assert agent_module.probable_speaker(None) == (None, None)


async def test_legacy_sensor_ids_are_migrated(hass: HomeAssistant, tmp_path) -> None:
    """Polish default sensor ids of earlier versions get the English ones; own ids stay."""
    from homeassistant.helpers import entity_registry as er
    from homeassistant.setup import async_setup_component

    from custom_components.assist_router.const import DOMAIN

    hass.config.config_dir = str(tmp_path)
    hass.config.language = "pl"
    assert await async_setup_component(hass, "homeassistant", {})
    assert await async_setup_component(hass, "conversation", {})
    entry = MockConfigEntry(domain=DOMAIN, title="Assist Router")
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    for key, object_id in (
        ("unrecognized", "assist_router_nierozpoznane_komendy"),
        ("examples", "moje_przyklady"),  # changed by the user
    ):
        registry.async_get_or_create(
            "sensor", DOMAIN, f"{entry.entry_id}-{key}",
            config_entry=entry, suggested_object_id=object_id,
        )  # fmt: skip

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.assist_router_unrecognized_commands") is not None
    assert hass.states.get("sensor.assist_router_nierozpoznane_komendy") is None
    assert hass.states.get("sensor.moje_przyklady") is not None


async def test_sensor_ids_are_english(hass: HomeAssistant, setup: MockConfigEntry) -> None:
    assert hass.config.language == "pl"
    assert hass.states.get("sensor.assist_router_unrecognized_commands") is not None
    assert hass.states.get("sensor.assist_router_example_commands") is not None
