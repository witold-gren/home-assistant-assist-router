"""Topic data for the answer model as the integration builds it, read over REST/WebSocket.

Used by the tools (snapshot_data.py, compare_sources.py) outside Home Assistant: the same
functions as ``router.entity_lines``, ``async_todo_lines`` and ``async_topic_sources``, but on
a copy of the states and registries taken from HA. Only reads; ``fetch`` calls only the
read-only services from router.yaml (e.g. ``calendar.get_events``).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
import json
import sys
from types import SimpleNamespace
from typing import Any
import urllib.request

from custom_components.assist_router.control import text_aliases
from custom_components.assist_router.languages import LANG
from custom_components.assist_router.router import (
    ENTITY_LIMIT,
    Route,
    RouterConfig,
    Topic,
    _extras,
    _match,
    _no_own_source,
    apply_personal,
    apply_relatives,
    apply_speaker,
    by_pattern,
    day_range,
    fetch_sources,
    hint_for,
    owned_by_others,
    parse_route,
)
from custom_components.assist_router.sources import WEEK, compact, fill, range_bounds, render


class HA:
    """Minimal REST client of Home Assistant."""

    def __init__(self, url: str, token: str) -> None:
        self.url, self.token = url.rstrip("/"), token

    def call(self, path: str, body: dict | None = None) -> Any:
        request = urllib.request.Request(
            f"{self.url}{path}",
            json.dumps(body).encode() if body is not None else None,
            {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read().decode()
        return json.loads(raw) if raw.strip().startswith(("{", "[")) else raw

    def service(self, domain: str, service: str, body: dict) -> dict:
        """Response of a service that returns data (``return_response``)."""
        result = self.call(f"/api/services/{domain}/{service}?return_response", body)
        return result.get("service_response") or {}


async def ws_commands(url: str, token: str, commands: list[dict]) -> list:
    """Results of WebSocket commands, in order."""
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


@dataclass
class Home:
    """States and registries of Home Assistant, the way the integration sees them."""

    ha: HA
    states: list[SimpleNamespace]
    areas: dict[str, str] = field(default_factory=dict)  # entity_id -> area name
    aliases: dict[str, list[str]] = field(default_factory=dict)
    labels: dict[str, frozenset[str]] = field(default_factory=dict)
    exposed: set[str] = field(default_factory=set)

    def state(self, entity_id: str) -> SimpleNamespace | None:
        return next((s for s in self.states if s.entity_id == entity_id), None)


def load_home(ha: HA) -> Home:
    """States over REST, areas, aliases, labels and exposure over WebSocket."""
    states = []
    for s in ha.call("/api/states"):
        states.append(
            SimpleNamespace(
                entity_id=s["entity_id"],
                domain=s["entity_id"].split(".")[0],
                state=s["state"],
                attributes=s["attributes"],
                name=s["attributes"].get("friendly_name") or s["entity_id"],
                last_changed=datetime.fromisoformat(s["last_changed"]),
            )
        )
    areas, devices, entities, label_list, exposed = asyncio.run(
        ws_commands(
            ha.url,
            ha.token,
            [
                {"type": "config/area_registry/list"},
                {"type": "config/device_registry/list"},
                {"type": "config/entity_registry/list"},
                {"type": "config/label_registry/list"},
                {"type": "homeassistant/expose_entity/list"},
            ],
        )
    )
    area_names = {a["area_id"]: a["name"] for a in areas}
    device_area = {d["id"]: d.get("area_id") for d in devices}
    label_names = {lb["label_id"]: lb["name"] for lb in label_list}
    home = Home(ha=ha, states=sorted(states, key=lambda s: s.entity_id))
    shown = {e for e, flags in exposed["exposed_entities"].items() if flags.get("conversation")}
    home.exposed = shown
    # aliases are only in the full entries - fetched for the exposed entities
    (full,) = asyncio.run(
        ws_commands(
            ha.url,
            ha.token,
            [{"type": "config/entity_registry/get_entries", "entity_ids": sorted(shown)}],
        )
    )
    for entry in entities:
        entity_id = entry["entity_id"]
        area_id = entry.get("area_id") or device_area.get(entry.get("device_id"))
        if area_id in area_names:
            home.areas[entity_id] = area_names[area_id]
        if entry.get("labels"):
            ids = entry["labels"]
            names = [label_names[i] for i in ids if i in label_names]
            home.labels[entity_id] = frozenset(x.casefold() for x in (*ids, *names))
    for entity_id, entry in full.items():
        home.aliases[entity_id] = sorted(text_aliases((entry or {}).get("aliases") or []))
    return home


def entity_lines(
    home: Home,
    patterns: tuple[str, ...],
    only_exposed: bool = False,
    skip_states: tuple[str, ...] = (),
    skip=None,
    unavailable: bool = False,
) -> list[str]:
    """Like ``router.entity_lines``: „Nazwa (inaczej: alias) [pokój]: stan”."""
    lines = []
    for state in by_pattern(home.states, patterns):
        if only_exposed and state.entity_id not in home.exposed:
            continue
        if skip is not None and skip(state.entity_id):
            continue
        missing = state.state == "unavailable" and unavailable
        if (
            state.state in ("unknown", "", *(() if missing else ("unavailable",)))
            or state.state in skip_states
        ):
            continue
        value = state.state
        if missing:
            value = LANG.UNAVAILABLE
        elif state.domain == "binary_sensor" and value in ("on", "off"):
            pair = LANG.BINARY_STATES.get(state.attributes.get("device_class") or "")
            value = (pair[0] if value == "on" else pair[1]) if pair else LANG.STATES[value]
        else:
            value = LANG.STATES.get(value, value)
        unit = "" if missing else state.attributes.get("unit_of_measurement") or ""
        area = home.areas.get(state.entity_id)
        where = f" [{area}]" if area and area.lower() not in state.name.lower() else ""
        aliases = home.aliases.get(state.entity_id) or []
        name = f"{state.name}{f' ({LANG.ALIASES}: ' + ', '.join(aliases) + ')' if aliases else ''}"
        extras = "" if missing else _extras(state)
        lines.append(f"{name}{where}: {value}{' ' + unit if unit else ''}{extras}")
        if len(lines) >= ENTITY_LIMIT:
            break
    return lines


def todo_lines(home: Home, lines: list[str], patterns: tuple[str, ...]) -> list[str]:
    """Like ``router.async_todo_lines``: list items instead of the item count."""
    todo = [s.entity_id for s in home.states if s.domain == "todo" and _match(s, patterns)]
    if not todo:
        return lines
    try:
        response = home.ha.service(
            "todo", "get_items", {"entity_id": todo, "status": "needs_action"}
        )
    except Exception:  # list unavailable - the item count stays
        return lines
    extra = []
    for entity_id, data in response.items():
        state = home.state(entity_id)
        items = [i.get("summary", "") for i in (data or {}).get("items", []) if i.get("summary")]
        name = state.name if state else entity_id
        extra.append(f"{name}: {', '.join(items) if items else LANG.EMPTY_LIST}")
    names = {s.name for e in todo if (s := home.state(e))}
    return [line for line in lines if _line_name(line) not in names] + extra


def _line_name(line: str) -> str:
    return line.split(":")[0].split(" [")[0].split(f" ({LANG.ALIASES}")[0]


def topic_sources(
    home: Home, config: RouterConfig, topic: Topic, route: Route, now: datetime
) -> list[str]:
    """Like ``router.async_topic_sources``: ``details`` and ``fetch`` for the person and day."""
    people = [config.people[key].pattern for key in route.people] or None
    days = day_range(route.when or topic.days, now.date())
    out = []
    for state in home.states:
        if owned_by_others(config, route.people, state.entity_id, _labels(home, state.entity_id)):
            continue
        if topic.details and _match(state, topic.details):
            value = compact(dict(state.attributes), people, days, topic.drop, now.tzinfo)
            out.append(render(f"{state.name} (stan: {state.state})", value))
    for item in topic.fetch:
        domain, service = item.action.split(".", 1)
        matched = {
            s.entity_id: _labels(home, s.entity_id) for s in home.states if _match(s, item.entities)
        }
        targets = [
            entity_id
            for entity_id, labels in matched.items()
            if not owned_by_others(config, route.people, entity_id, labels)
        ]
        if note := _no_own_source(config, route, item, matched):
            out.append(note)
        if not targets:
            continue
        start, end = range_bounds(days or day_range(WEEK, now.date()))
        try:
            response = home.ha.service(
                domain, service, {"entity_id": targets, **fill(item.data, start, end)}
            )
        except Exception as err:  # as in HA: the topic answers from the remaining data
            print(f"!! fetch {item.action} failed: {err}", file=sys.stderr)
            continue
        names = {e: (s.name if (s := home.state(e)) else e) for e in response}
        out.extend(fetch_sources(item, response, names, people, days, topic.drop, now))
    return out


def _labels(home: Home, entity_id: str) -> frozenset[str]:
    return home.labels.get(entity_id, frozenset())


def route_for(config: RouterConfig, topic: str, question: str, speaker: str | None) -> Route:
    """The route the integration builds for a question already classified as ``topic``:
    person and day from the text, family terms and 1st person relative to the speaker."""
    route = parse_route(config, json.dumps({LANG.TOPIC_KEY: topic}), question)
    if route is None:
        raise ValueError(f"unknown topic {topic!r}")
    route = apply_relatives(config, route, question, speaker)
    route = apply_speaker(config, route, question, speaker)
    if config.topics[topic].personal:
        route = apply_personal(config, route, speaker)
    return route


def topic_data(
    home: Home,
    config: RouterConfig,
    topic_name: str,
    question: str,
    speaker: str | None,
    now: datetime,
) -> dict[str, Any]:
    """Data block, hint and token limit for the answer model - as in ``_answer_topic``.

    ``speaker`` - voice identifier from Assist Speaker ID (``people.<key>.speaker``)."""
    topic = config.topics[topic_name]
    route = route_for(config, topic_name, question, speaker)
    parts = []
    if topic.entities:
        exposed = config.only_exposed if topic.only_exposed is None else topic.only_exposed
        lines = entity_lines(
            home,
            topic.entities,
            exposed,
            topic.skip_states,
            skip=lambda entity_id: owned_by_others(
                config, route.people, entity_id, _labels(home, entity_id)
            ),
            unavailable=topic.unavailable,
        )
        lines = todo_lines(home, lines, topic.entities)
        if not lines and topic.skip_states:
            lines = [LANG.NOTHING_ACTIVE]
        if lines:
            parts.append(f"{LANG.DEVICE_STATES}\n" + "\n".join(lines))
    if topic.details or topic.fetch:
        parts.extend(topic_sources(home, config, topic, route, now))
    key = next((k for k, p in config.people.items() if p.speaker == speaker), None)
    hint = hint_for(config, topic, speaker)
    if topic.personal and key is None:
        hint = f"{LANG.UNKNOWN_SPEAKER_HINT} {hint}"
    return {
        "data": "\n".join(parts),
        "hint": hint.strip(),
        "speaker": config.people[key].name if key else None,
        "people": list(route.people),
        "when": route.when,
    }
