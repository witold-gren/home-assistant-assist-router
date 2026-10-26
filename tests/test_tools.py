"""Benchmark tools (tools/): scoring, prompts, model bookkeeping and topic data outside HA."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest
import yaml

from custom_components.assist_router.router import parse_config

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import model_benchmark as bench
import topic_data

CONFIG_YAML = """
household: "Domownicy: Witold (tata), Zosia (córka)."
people:
  witold: {name: Witold, match: "witold|tat(a|y)", owns: ["calendar.witold"]}
  zosia: {name: Zosia, match: "zosi|zofi", owns: ["calendar.zosia"]}
family: {parents: [witold], children: [zosia]}
topics:
  samochod:
    description: Volvo
    entities: ["sensor.volvo_*"]
  listy:
    description: listy
    entities: ["todo.*"]
  kalendarz:
    description: kalendarz
    personal: true
    days: "14"
    answer_tokens: 300
    answer_hints: {child: "Mów do dziecka."}
    fetch:
      - action: calendar.get_events
        entities: ["calendar.*"]
        data: {start_date_time: "{start}", end_date_time: "{end}"}
        title: Wydarzenia
        merge: events
  inne:
    description: wszystko inne
"""


def _config():
    return parse_config(yaml.safe_load(CONFIG_YAML))


def _state(entity_id, state, name, **attributes):
    return SimpleNamespace(
        entity_id=entity_id,
        domain=entity_id.split(".")[0],
        state=state,
        attributes={"friendly_name": name, **attributes},
        name=name,
        last_changed=datetime.now(UTC),
    )


class FakeHA:
    """Service responses by "domain.service"; records the calls."""

    def __init__(self, responses):
        self.responses, self.calls = responses, []

    def service(self, domain, service, body):
        self.calls.append((f"{domain}.{service}", body))
        return self.responses[f"{domain}.{service}"]


# --- scoring and prompts ---------------------------------------------------------------


def test_check_must_never_and_length() -> None:
    case = {"must": ["12:35", ["tak", "deszcz"]], "never": ["11:30"]}
    assert bench.check("Tak, o 12:35.", case, 1, 3) == []
    problems = bench.check("O 11:30. Raz. Dwa. Trzy.", case, 1, 3)
    assert "missing: 12:35" in problems
    assert "missing: tak / deszcz" in problems
    assert "forbidden: 11:30" in problems
    assert "too long: 4 sentences" in problems
    assert bench.check("12:35 tak", case, 2, 3) == ["too short: 1 sentences"]


def test_topic_ok_single_and_alternatives() -> None:
    assert bench.topic_ok("pogoda", "pogoda")
    assert not bench.topic_ok("czujniki", "pogoda")
    assert bench.topic_ok("czujniki", ["pogoda", "czujniki"])
    assert not bench.topic_ok("(bad JSON)", ["pogoda", "czujniki"])


def test_expect_ok() -> None:
    assert bench.expect_ok("Kuchnia", "Pokój: kuchnia")
    assert not bench.expect_ok("Salon", "Kuchnia")
    assert bench.expect_ok(30, 30.0)
    assert not bench.expect_ok(30, None)
    assert bench.expect_ok(True, True)
    assert not bench.expect_ok(True, 1)
    assert bench.expect_ok(["HassMediaPause", "HassTurnOff"], "HassTurnOff")
    assert not bench.expect_ok(["HassMediaPause", "HassTurnOff"], "HassTurnOn")


def test_case_data_sources() -> None:
    snapshot = {"a": {"text": "A."}, "b": {"text": "B."}, "x": {"data": "X."}}
    assert bench.case_data({"data": "D."}, snapshot) == "D."
    assert bench.case_data({"source": ["a", "b"]}, snapshot) == "A.\nB."
    assert bench.case_data({"name": "x", "topic": "kalendarz"}, snapshot) == "X."


def test_limits_per_case_override_section() -> None:
    spec = {"min_sentences": 2, "max_sentences": 4}
    assert bench.limits({}, spec) == (2, 4)
    assert bench.limits({"max_sentences": 6}, spec) == (2, 6)
    assert bench.limits({}, {}) == (1, 3)


def test_answer_request_own_system_prompt() -> None:
    spec = {"system": "Jesteś asystentem.", "max_sentences": 2}
    messages, tokens = bench.answer_request(
        {"data": "Bank: 5 zł.", "question": "Ile?"}, spec, {}, None, None
    )
    assert messages[0]["content"] == "Jesteś asystentem.\nDane:\nBank: 5 zł."
    assert messages[1] == {"role": "user", "content": "Ile?"}
    assert tokens == 120


def test_answer_request_integration_prompt_with_speaker_and_hint() -> None:
    config = _config()
    now = datetime(2026, 10, 26, 10, 30, tzinfo=UTC)
    snapshot = {
        "zosia_dzis": {
            "topic": "kalendarz",
            "data": "Wydarzenia: 18:15 szarfy.",
            "speaker": "Zosia",
            "hint": "Mów do dziecka.",
        }
    }
    case = {"name": "zosia_dzis", "topic": "kalendarz", "question": "Co mam dziś?"}
    messages, tokens = bench.answer_request(case, {}, snapshot, config, now)
    system = messages[0]["content"]
    assert "Domownicy: Witold" in system
    assert "poniedziałek, 26 października 2026, godzina 10:30" in system
    assert "Pyta: Zosia." in system
    assert "Mów do dziecka." in system
    assert system.endswith("Dane:\nWydarzenia: 18:15 szarfy.")
    assert tokens == 300  # answer_tokens of the topic


def test_answer_request_default_tokens_and_summary() -> None:
    config = _config()
    snapshot = {"auto": {"topic": "samochod", "data": "Zasięg: 90 km."}}
    case = {"name": "auto", "topic": "samochod", "question": "Ile przejadę?"}
    _, tokens = bench.answer_request(case, {}, snapshot, config, datetime.now(UTC))
    assert tokens == bench.ANSWER_TOKENS
    wiki = {"everest": {"text": "Mount Everest ma 8849 m."}}
    messages, tokens = bench.answer_request(
        {"source": "everest", "question": "Jak wysoki?"}, {"prompt": "summary"}, wiki, config, None
    )
    assert messages[0]["content"].endswith("Artykuł:\nMount Everest ma 8849 m.")
    assert tokens == bench.SUMMARY_TOKENS_PER_SENTENCE * config.sentences


def test_answer_request_needs_config_and_time() -> None:
    case = {"name": "a", "topic": "samochod", "question": "?"}
    snapshot = {"a": {"topic": "samochod", "data": "x"}}
    with pytest.raises(ValueError, match="router config"):
        bench.answer_request(case, {}, snapshot, None, None)
    with pytest.raises(ValueError, match="snapshot time"):
        bench.answer_request(case, {}, snapshot, _config(), None)


def test_rescore_uses_case_limits() -> None:
    results = {
        "m": {
            "real": {
                "score": 0,
                "total": 1,
                "details": [{"case": "a", "answer": "Raz. Dwa. Trzy. Cztery.", "problems": []}],
            }
        }
    }
    spec = {"real": {"cases": [{"name": "a", "max_sentences": 5}], "max_sentences": 3}}
    bench.rescore(results, spec)
    assert results["m"]["real"]["score"] == 1


# --- Ollama calls ----------------------------------------------------------------------


def test_chat_retries_dropped_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def fake_call(url, path, body):
        calls.append(body)
        if len(calls) == 1:
            raise ConnectionResetError(54, "Connection reset by peer")
        return {"message": {"content": "ok"}}

    monkeypatch.setattr(bench, "call", fake_call)
    monkeypatch.setattr(bench, "RETRY_PAUSE_S", 0)
    result, _ = bench.chat("http://x", {"model": "m"})
    assert result["message"]["content"] == "ok"
    assert len(calls) == 2


def test_chat_gives_up_after_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_call(url, path, body):
        raise ConnectionResetError(54, "Connection reset by peer")

    monkeypatch.setattr(bench, "call", fake_call)
    monkeypatch.setattr(bench, "RETRY_PAUSE_S", 0)
    with pytest.raises(ConnectionResetError):
        bench.chat("http://x", {"model": "m"})


def test_chat_without_think_option_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    import urllib.error

    bodies = []

    def fake_call(url, path, body):
        bodies.append(body)
        if "think" in body:
            raise urllib.error.HTTPError(url, 400, "bad", {}, None)
        return {"message": {"content": "ok"}}

    monkeypatch.setattr(bench, "call", fake_call)
    bench.chat("http://x", {"model": "m"})
    assert ["think" in body for body in bodies] == [True, False]


# --- model bookkeeping -----------------------------------------------------------------


def test_removable_never_touches_models_installed_before() -> None:
    before = {"gemma4:26b", "qwen2.5vl:7b"}
    assert bench.removable("qwen3.5:2b", before, set())
    assert not bench.removable("gemma4:26b", before, set())
    assert not bench.removable("qwen3.5:2b", before, {"qwen3.5:2b"})


def test_missing_parts_and_wanted_parts() -> None:
    assert bench.missing_parts({"router": {}, "real": {}}, ["router", "control", "real"]) == [
        "control"
    ]
    args = argparse.Namespace(
        router=["a"], answer=["a", "b"], sections=["answers", "real", "wiki_answers", "control"]
    )
    spec = {
        "router": [],
        "control": {"cases": []},
        "answers": {"cases": []},
        "real": {"cases": [{"name": "x", "topic": "samochod"}]},
        "wiki_answers": {"cases": []},
    }
    data = {"home": {}, "live": {}, "wiki": {}}
    assert bench.wanted_parts("a", args, spec, data) == [
        "router", "control", "answers", "real", "wiki_answers",
    ]  # fmt: skip
    # no topic data in the snapshot - the part is not expected
    assert bench.wanted_parts("b", args, spec, {"home": {}}) == ["control", "answers"]


def test_snapshot_part() -> None:
    assert bench.snapshot_part("real", {"cases": [{"topic": "x"}]}, {}) == "live"
    assert bench.snapshot_part("real", {"cases": [{"source": "x"}]}, {}) == "sources"
    assert bench.snapshot_part("answers", {"cases": [{"data": "x"}]}, {}) is None


# --- topic data outside HA -------------------------------------------------------------


def _home(states, ha=None, **kwargs):
    return topic_data.Home(ha=ha, states=states, **kwargs)


def test_entity_lines_like_the_integration() -> None:
    home = _home(
        [
            _state("sensor.volvo_range", "90", "Volvo Zasięg", unit_of_measurement="km"),
            _state("sensor.volvo_lights", "unknown", "Volvo Światła"),
            _state("sensor.volvo_link", "unavailable", "Volvo Połączenie"),
            _state("sensor.other", "1", "Inne"),
        ],
        areas={"sensor.volvo_range": "Garaż"},
        aliases={"sensor.volvo_range": ["zasięg samochodu"]},
    )
    lines = topic_data.entity_lines(home, ("sensor.volvo_*",))
    assert lines == ["Volvo Zasięg (inaczej: zasięg samochodu) [Garaż]: 90 km"]
    # unavailable entities stay when the topic asks for it
    lines = topic_data.entity_lines(home, ("sensor.volvo_*",), unavailable=True)
    assert "Volvo Połączenie: niedostępne" in lines


def test_entity_lines_only_exposed_and_area_in_name() -> None:
    home = _home(
        [_state("light.kuchnia", "on", "Kuchnia lampa"), _state("light.hidden", "on", "Ukryta")],
        areas={"light.kuchnia": "Kuchnia"},
        exposed={"light.kuchnia"},
    )
    assert topic_data.entity_lines(home, ("light.*",), only_exposed=True) == [
        "Kuchnia lampa: włączone"
    ]


def test_todo_lines_replace_item_count_with_items() -> None:
    ha = FakeHA({"todo.get_items": {"todo.zakupy": {"items": [{"summary": "mleko"}]}}})
    home = _home([_state("todo.zakupy", "1", "Zakupy")], ha=ha)
    lines = topic_data.todo_lines(home, ["Zakupy: 1"], ("todo.*",))
    assert lines == ["Zakupy: mleko"]
    assert ha.calls == [
        ("todo.get_items", {"entity_id": ["todo.zakupy"], "status": "needs_action"})
    ]


def test_route_for_speaker_and_names() -> None:
    config = _config()
    route = topic_data.route_for(config, "kalendarz", "Co mam jutro?", "zosia")
    assert route.people == ("zosia",)
    assert route.when == "tomorrow"
    # a name in the question wins over the speaker
    route = topic_data.route_for(config, "kalendarz", "Co ma Zosia?", "witold")
    assert route.people == ("zosia",)
    # a parent without a name: their data and the children's (personal topic)
    route = topic_data.route_for(config, "kalendarz", "Jak wygląda dzień?", "witold")
    assert route.people == ("witold", "zosia")
    with pytest.raises(ValueError, match="unknown topic"):
        topic_data.route_for(config, "brak", "?", None)


def test_topic_data_fetch_filters_other_peoples_calendars() -> None:
    events = {
        "calendar.zosia": {"events": [{"start": "2026-10-27T18:15:00+01:00", "summary": "Szarfy"}]},
    }
    ha = FakeHA({"calendar.get_events": events})
    home = _home(
        [
            _state("calendar.witold", "off", "Kalendarz Witold"),
            _state("calendar.zosia", "off", "Kalendarz Zosia"),
        ],
        ha=ha,
    )
    now = datetime(2026, 10, 26, 10, 0, tzinfo=UTC)
    result = topic_data.topic_data(home, _config(), "kalendarz", "Co mam jutro?", "zosia", now)
    (call,) = ha.calls
    assert call[1]["entity_id"] == ["calendar.zosia"]  # Witold's calendar skipped
    assert call[1]["start_date_time"].startswith("2026-10-27")
    assert "Szarfy" in result["data"]
    assert result["speaker"] == "Zosia"
    assert result["hint"] == "Mów do dziecka."
    assert result["people"] == ["zosia"]
    assert result["when"] == "tomorrow"


def test_topic_data_unknown_speaker_hint_for_personal_topic() -> None:
    ha = FakeHA({"calendar.get_events": {}})
    home = _home([_state("calendar.witold", "off", "Kalendarz Witold")], ha=ha)
    result = topic_data.topic_data(
        home, _config(), "kalendarz", "Co jest jutro?", None, datetime.now(UTC)
    )
    assert result["speaker"] is None
    assert result["hint"].startswith("Nie wiadomo, kto pyta")


def test_topic_data_entities_without_fetch() -> None:
    home = _home([_state("sensor.volvo_range", "90", "Volvo Zasięg", unit_of_measurement="km")])
    result = topic_data.topic_data(
        home, _config(), "samochod", "Ile przejadę?", None, datetime.now(UTC)
    )
    assert result["data"] == "Stany urządzeń:\nVolvo Zasięg: 90 km"
    assert result["hint"] == ""


def test_topic_data_failed_fetch_is_skipped() -> None:
    class BrokenHA:
        def service(self, domain, service, body):
            raise OSError("HTTP Error 500")

    home = _home([_state("calendar.witold", "off", "Kalendarz Witold")], ha=BrokenHA())
    result = topic_data.topic_data(
        home, _config(), "kalendarz", "Co mam jutro?", "witold", datetime.now(UTC)
    )
    assert result["data"] == ""  # like the integration: no calendar data, no crash
