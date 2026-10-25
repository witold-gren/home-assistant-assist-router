"""Snapshot of real data for the model benchmark (tools/model_benchmark.py).

For every source in the cases file it asks Home Assistant the reference question
(built-in agent, like the router does) and stores the automation's answer; for Wikipedia
phrases it stores the article text (trimmed the same way as in the integration). The result
is frozen in a file, so the expected facts in the test cases do not change along with
the calendar.

    .venv/bin/python tools/snapshot_data.py --ha http://homeassistant.local:8123 \\
        --token-file ~/.ha_token --cases /config/assist/model_test.yaml \\
        --out /config/assist/model_test_data.yaml

In the cases file:

    sources:            # key: reference question to HA (questions ONLY)
      kalendarz_jutro: jakie są jutro wydarzenia
    wiki:               # key: phrase
      everest: Mount Everest
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
import urllib.parse
import urllib.request

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from custom_components.assist_router.languages import LANG
from custom_components.assist_router.router import (
    USER_AGENT,
    WIKIPEDIA_CHARS,
    clean_article,
)


def ask_ha(url: str, token: str, text: str) -> str:
    request = urllib.request.Request(
        f"{url}/api/conversation/process",
        json.dumps(
            {"text": text, "language": "pl", "agent_id": "conversation.home_assistant"}
        ).encode(),
        {"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=60) as resp:
        response = json.load(resp)["response"]
    if response["response_type"] == "error":
        raise RuntimeError(f"HA did not recognize: {text!r}")
    return " ".join(response["speech"]["plain"]["speech"].split())


async def _ws(url: str, token: str, commands: list[dict]) -> list:
    import aiohttp

    ws_url = url.replace("http", "ws", 1) + "/api/websocket"
    async with aiohttp.ClientSession() as session, session.ws_connect(ws_url, max_msg_size=0) as ws:
        await ws.receive_json()
        await ws.send_json({"type": "auth", "access_token": token})
        await ws.receive_json()
        out = []
        for number, command in enumerate(commands, 1):
            await ws.send_json({"id": number, **command})
            while (reply := await ws.receive_json()).get("id") != number:
                pass
            out.append(reply["result"])
        return out


def home(url: str, token: str) -> dict:
    """Home snapshot for the control test: exposed entities with aliases, areas, floors."""
    import asyncio

    areas, floors, devices, entities, exposed, states, services = asyncio.run(
        _ws(
            url,
            token,
            [
                {"type": "config/area_registry/list"},
                {"type": "config/floor_registry/list"},
                {"type": "config/device_registry/list"},
                {"type": "config/entity_registry/list_for_display"},
                {"type": "homeassistant/expose_entity/list"},
                {"type": "get_states"},
                {"type": "get_services"},
            ],
        )
    )
    area_names = {a["area_id"]: a["name"] for a in areas}
    device_area = {d["id"]: d.get("area_id") for d in devices}
    registry = {e["ei"]: e for e in entities["entities"]}
    shown = {e for e, a in exposed["exposed_entities"].items() if a.get("conversation")}
    # full entries (with aliases) of exposed entities only
    (full,) = asyncio.run(
        _ws(
            url,
            token,
            [{"type": "config/entity_registry/get_entries", "entity_ids": sorted(shown)}],
        )
    )
    aliases = {
        entity_id: [a for a in (entry or {}).get("aliases", []) if isinstance(a, str)]
        for entity_id, entry in full.items()
    }
    targets = []
    for state in states:
        entity_id = state["entity_id"]
        if entity_id not in shown:
            continue
        entry = registry.get(entity_id, {})
        area_id = entry.get("ai") or device_area.get(entry.get("di"))
        name = state["attributes"].get("friendly_name", entity_id)
        targets.append(
            {
                "entity_id": entity_id,
                "name": name,
                "domain": entity_id.split(".")[0],
                "device_class": state["attributes"].get("device_class"),
                "area": area_names.get(area_id),
                "names": [name, *aliases.get(entity_id, [])],
            }
        )
    # actions as in the integration: scripts with descriptions, scenes with what they set
    # (the scene description comes from the language pack)
    names = {s["entity_id"]: s["attributes"].get("friendly_name", s["entity_id"]) for s in states}
    actions = {}
    for target in targets:
        if target["domain"] == "script":
            info = services.get("script", {}).get(target["entity_id"].split(".", 1)[1], {})
            actions[target["name"]] = str(info.get("description") or "")
        elif target["domain"] == "scene":
            state = next(s for s in states if s["entity_id"] == target["entity_id"])
            members = [names.get(e, e) for e in state["attributes"].get("entity_id") or []]
            actions[target["name"]] = LANG.scene_description(members)
    return {
        "actions": actions,
        "targets": targets,
        "areas": {
            alias: a["name"]
            for a in areas
            for alias in [a["name"], *(x for x in a.get("aliases", []) if isinstance(x, str))]
        },
        "floors": {
            alias: f["name"]
            for f in floors
            for alias in [f["name"], *(x for x in f.get("aliases", []) if isinstance(x, str))]
        },
        "domains": sorted({t["domain"] for t in targets} & set(LANG.DOMAINS)),
    }


def wikipedia(phrase: str, language: str = LANG.WIKIPEDIA_LANGUAGE) -> tuple[str, str]:
    params = {
        "action": "query",
        "format": "json",
        "generator": "search",
        "gsrsearch": phrase,
        "gsrlimit": "1",
        "prop": "extracts",
        "explaintext": "1",
        "redirects": "1",
    }
    request = urllib.request.Request(
        f"https://{language}.wikipedia.org/w/api.php?{urllib.parse.urlencode(params)}",
        headers={"User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(request, timeout=30) as resp:
        pages = json.load(resp)["query"]["pages"]
    page = next(iter(pages.values()))
    return page["title"], clean_article(page["extract"], WIKIPEDIA_CHARS)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--ha", required=True)
    parser.add_argument("--token-file", type=Path, required=True)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--only-home",
        action="store_true",
        help="refresh only the home snapshot (control) in the existing file - the answer test "
        "data is kept, because its expected facts come from the snapshot day",
    )
    args = parser.parse_args()
    if args.only_home:
        token = args.token_file.expanduser().read_text().strip()
        out = yaml.safe_load(args.out.read_text(encoding="utf-8"))
        out["home"] = home(args.ha.rstrip("/"), token)
        out["home_taken"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        args.out.write_text(
            yaml.safe_dump(out, allow_unicode=True, sort_keys=False, width=100), encoding="utf-8"
        )
        print(
            f"home: {len(out['home']['targets'])} entities, {len(out['home']['actions'])} actions"
        )
        return

    token = args.token_file.expanduser().read_text().strip()
    spec = yaml.safe_load(args.cases.read_text(encoding="utf-8"))
    out: dict = {"taken": datetime.now().strftime("%Y-%m-%d %H:%M"), "sources": {}, "wiki": {}}
    for key, command in (spec.get("sources") or {}).items():
        text = ask_ha(args.ha.rstrip("/"), token, command)
        out["sources"][key] = {"command": command, "text": text}
        print(f"{key}: {out['sources'][key]['text'][:100]}")
    if spec.get("control"):
        out["home"] = home(args.ha.rstrip("/"), token)
        print(f"home: {len(out['home']['targets'])} exposed entities")
    for key, phrase in (spec.get("wiki") or {}).items():
        title, text = wikipedia(phrase)
        out["wiki"][key] = {"phrase": phrase, "title": title, "text": text}
        print(f"{key}: {title} ({len(text)} chars)")
    args.out.write_text(
        yaml.safe_dump(out, allow_unicode=True, sort_keys=False, width=100), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
