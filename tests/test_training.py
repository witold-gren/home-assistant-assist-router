"""The export for the trainer: every file it needs in one read-only answer, for administrators."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockUser

from custom_components.assist_router.const import DOMAIN
from custom_components.assist_router.training import plain

from .test_editor import call, ok

ROUTER = "household: Tomek i Ania\ntopics:\n  inne:\n    description: wszystko inne\n"


def _write(hass: HomeAssistant, relative: str, text: str) -> Path:
    path = Path(hass.config.path(relative))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


async def _automations(hass: HomeAssistant) -> None:
    # one from automations.yaml (new keys), one as from a package (old keys), one without speech
    assert await async_setup_component(
        hass,
        "automation",
        {
            "automation": [
                {
                    "id": "kawa",
                    "alias": "Zrób kawę",
                    "triggers": [{"trigger": "conversation", "command": ["zrób (mi) kawę"]}],
                    "actions": [{"set_conversation_response": "Robię kawę."}],
                },
                {
                    "id": "lekcje",
                    "alias": "Lekcje",
                    "trigger": {"platform": "conversation", "command": "o której {dziecko} kończy"},
                    "action": [{"set_conversation_response": "O 12:35."}],
                },
                {
                    "id": "rano",
                    "alias": "Rano",
                    "triggers": [{"trigger": "time", "at": "07:00:00"}],
                    "actions": [],
                },
            ]
        },
    )
    await hass.async_block_till_done()


async def test_export_gives_everything_the_trainer_reads(hass, setup, hass_ws_client) -> None:
    _write(hass, "assist/router.yaml", ROUTER)
    _write(hass, "assist/model_test.yaml", "router: []\n")
    _write(hass, "custom_sentences/pl/dom.yaml", "language: pl\nintents: {}\n")
    await _automations(hass)
    await setup.runtime_data.log.async_append(
        {"timestamp": "t", "text": "Ile mam lekcji?", "response": "", "route": "x"}
    )
    client = await hass_ws_client(hass)

    result = await ok(client, type=f"{DOMAIN}/training/export")

    assert result["router_yaml"] == ROUTER and result["language"] == hass.config.language
    assert result["version"]
    assert result["tests"] == {"model_test.yaml": "router: []\n"}  # the data file is missing
    assert [row["text"] for row in result["log"]] == ["Ile mam lekcji?"]
    assert {item["id"] for item in result["automations"]} == {"kawa", "lekcje"}
    lekcje = next(item for item in result["automations"] if item["id"] == "lekcje")
    assert lekcje["trigger"]["command"] == "o której {dziecko} kończy"  # as written
    assert result["custom_sentences"] == [
        {"language": "pl", "name": "dom.yaml", "text": "language: pl\nintents: {}\n"}
    ]


async def test_export_without_files(hass, setup, hass_ws_client) -> None:
    client = await hass_ws_client(hass)
    result = await ok(client, type=f"{DOMAIN}/training/export")
    assert result["router_yaml"] == "" and result["tests"] == {}
    assert result["log"] == [] and result["automations"] == []
    assert result["custom_sentences"] == []


async def test_only_administrators_can_export(hass, setup, hass_ws_client) -> None:
    person = MockUser(name="Ola").add_to_hass(hass)
    refresh = await hass.auth.async_create_refresh_token(person, "client")
    ola = await hass_ws_client(hass, access_token=hass.auth.async_create_access_token(refresh))
    answer = await call(ola, type=f"{DOMAIN}/training/export")
    assert answer["error"]["code"] == "unauthorized"


def test_plain_turns_yaml_values_into_json() -> None:
    assert plain({"at": date(2026, 11, 16), "list": (1, 2)}) == {
        "at": "2026-11-16",
        "list": [1, 2],
    }


# --- the home's voice commands ------------------------------------------------------------------


def _recordings(hass: HomeAssistant, tmp_path: Path) -> Path:
    from homeassistant.components.assist_pipeline.const import DATA_CONFIG

    root = tmp_path / "assist_pipeline"
    for relative, data in (
        ("dev1/Kuchnia/111/00_wake.wav", b"wake"),
        ("dev1/Kuchnia/111/01_stt-stt.whisper.wav", b"a" * 10),
        ("dev1/Salon/222/01_stt-stt.whisper.wav", b"b" * 10),
        ("Salon/333/01_stt.wav", b"c" * 10),
        ("dev1/Salon/222/notes.txt", b"x"),
    ):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    hass.data[DATA_CONFIG] = {"debug_recording_dir": str(root)}
    return root


async def test_recordings_are_listed_and_handed_over_in_parts(
    hass, setup, hass_ws_client, tmp_path, monkeypatch
) -> None:
    import base64

    from custom_components.assist_router import training

    _recordings(hass, tmp_path)
    client = await hass_ws_client(hass)
    listed = await ok(client, type=f"{DOMAIN}/training/recordings")
    assert listed["configured"] is True
    paths = sorted(item["path"] for item in listed["files"])
    assert paths == [
        "Salon/333/01_stt.wav",
        "dev1/Kuchnia/111/01_stt-stt.whisper.wav",
        "dev1/Salon/222/01_stt-stt.whisper.wav",
    ]  # no wake word, no other files
    monkeypatch.setattr(training, "RECORDINGS_PART", 15)
    first = await ok(client, type=f"{DOMAIN}/training/recording_files", paths=paths)
    assert [f["path"] for f in first["files"]] == paths[:1]  # 10 + 10 bytes > 15
    assert base64.b64decode(first["files"][0]["data"]) == b"c" * 10
    rest = await ok(client, type=f"{DOMAIN}/training/recording_files", paths=paths[1:])
    assert [f["path"] for f in rest["files"]] == paths[1:2]


async def test_recordings_never_leave_their_folder(hass, setup, hass_ws_client, tmp_path) -> None:
    root = _recordings(hass, tmp_path)
    (root.parent / "secret.wav").write_bytes(b"s")
    client = await hass_ws_client(hass)
    answer = await ok(
        client,
        type=f"{DOMAIN}/training/recording_files",
        paths=["../secret.wav", "/etc/passwd", "dev1/Salon/222/notes.txt", "missing.wav"],
    )
    assert answer["files"] == []


async def test_without_a_recording_folder(hass, setup, hass_ws_client) -> None:
    from homeassistant.components.assist_pipeline.const import DATA_CONFIG

    hass.data.pop(DATA_CONFIG, None)
    client = await hass_ws_client(hass)
    assert await ok(client, type=f"{DOMAIN}/training/recordings") == {
        "configured": False,
        "files": [],
    }
    answer = await ok(client, type=f"{DOMAIN}/training/recording_files", paths=["a.wav"])
    assert answer["files"] == []


async def test_only_administrators_get_recordings(hass, setup, hass_ws_client) -> None:
    person = MockUser(name="Ola").add_to_hass(hass)
    refresh = await hass.auth.async_create_refresh_token(person, "client")
    ola = await hass_ws_client(hass, access_token=hass.auth.async_create_access_token(refresh))
    for kind in ("recordings", "recording_files"):
        answer = await call(ola, type=f"{DOMAIN}/training/{kind}", paths=[])
        assert answer["error"]["code"] in ("unauthorized", "invalid_format")
