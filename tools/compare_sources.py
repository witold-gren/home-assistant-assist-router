"""Consistency test: topic data from automation sentences (old router.yaml) vs. from entities
and services (``details``/``fetch``, new router.yaml) - the same real questions, model answers
side by side. Live data from HA (REST); nothing is executed apart from reads.

    .venv/bin/python tools/compare_sources.py --ha http://homeassistant.local:8123 \\
        --token-file ~/.ha_token --ollama http://192.168.1.10:11434 \\
        --old /config/assist/router.yaml --new router.new.yaml \\
        --questions questions.txt --out comparison.json
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace
from typing import Any
import urllib.request
from zoneinfo import ZoneInfo

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from custom_components.assist_router.languages import LANG
from custom_components.assist_router.router import (
    ENTITY_LIMIT,
    OllamaSettings,
    _extras,
    _match,
    answer_messages,
    build_request,
    by_pattern,
    day_range,
    fetch_sources,
    parse_config,
    parse_route,
    template_variables,
)
from custom_components.assist_router.sources import (
    WEEK,
    compact,
    fill,
    range_bounds,
    render,
)


class HA:
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


def states(ha: HA) -> list[SimpleNamespace]:
    out = []
    for s in ha.call("/api/states"):
        out.append(
            SimpleNamespace(
                entity_id=s["entity_id"],
                domain=s["entity_id"].split(".")[0],
                state=s["state"],
                attributes=s["attributes"],
                name=s["attributes"].get("friendly_name") or s["entity_id"],
                last_changed=datetime.fromisoformat(s["last_changed"]),
            )
        )
    return sorted(out, key=lambda s: s.entity_id)


def entity_lines(all_states, topic, exposed: set[str], only_exposed: bool) -> list[str]:
    """Like router.entity_lines, without areas (approximation over REST)."""
    lines = []
    for state in by_pattern(all_states, topic.entities):
        if only_exposed and state.entity_id not in exposed:
            continue
        if state.state in ("unknown", "unavailable", "") or state.state in topic.skip_states:
            continue
        value = state.state
        if state.domain == "binary_sensor" and value in ("on", "off"):
            pair = LANG.BINARY_STATES.get(state.attributes.get("device_class") or "")
            value = (pair[0] if value == "on" else pair[1]) if pair else LANG.STATES[value]
        else:
            value = LANG.STATES.get(value, value)
        unit = state.attributes.get("unit_of_measurement") or ""
        lines.append(f"{state.name}: {value}{' ' + unit if unit else ''}{_extras(state)}")
        if len(lines) >= ENTITY_LIMIT:
            break
    if not lines and topic.skip_states:
        lines = [LANG.NOTHING_ACTIVE]
    return lines


def new_sources(ha: HA, all_states, config, topic, route, now: datetime) -> list[str]:
    """Like router.async_topic_sources, over REST."""
    people = [config.people[key].pattern for key in route.people] or None
    days = day_range(route.when or topic.days, now.date())
    out = []
    for state in all_states:
        if topic.details and _match(state, topic.details):
            value = compact(dict(state.attributes), people, days, topic.drop, now.tzinfo)
            out.append(render(f"{state.name} (stan: {state.state})", value))
    by_id = {s.entity_id: s for s in all_states}
    for item in topic.fetch:
        domain, service = item.action.split(".", 1)
        targets = [s.entity_id for s in all_states if _match(s, item.entities)]
        if not targets:
            continue
        start, end = range_bounds(days or day_range(WEEK, now.date()))
        body = {"entity_id": targets, **fill(item.data, start, end)}
        response = ha.call(f"/api/services/{domain}/{service}?return_response", body)
        data = response.get("service_response") or {}
        names = {e: by_id[e].name if e in by_id else e for e in data}
        out.extend(fetch_sources(item, data, names, people, days, topic.drop, now))
    return out


def old_command(ha: HA, config, topic, route, text: str) -> str:
    if not topic.command:
        return ""
    variables = template_variables(config, route, text)
    rendered = ha.call("/api/template", {"template": topic.command, "variables": variables})
    texts = []
    for question in (q.strip() for q in " ".join(str(rendered).split()).split(";")):
        if not question:
            continue
        result = ha.call(
            "/api/conversation/process",
            {"text": question, "language": LANG.CODE, "agent_id": "conversation.home_assistant"},
        )
        speech = result["response"]["speech"].get("plain", {}).get("speech", "").strip()
        if result["response"]["response_type"] != "error" and speech:
            texts.append(speech)
    return "\n".join(texts)


def ollama(url: str, body: dict) -> tuple[str, float]:
    body = {**body, "think": False, "keep_alive": -1}
    request = urllib.request.Request(f"{url}/api/chat", json.dumps(body).encode())
    started = time.monotonic()
    with urllib.request.urlopen(request, timeout=180) as response:
        content = json.load(response).get("message", {}).get("content", "")
    return content.strip(), time.monotonic() - started


def answer(url: str, model: str, config, data: str, question: str, now) -> tuple[str, float]:
    if not data:
        return "(no data)", 0.0
    return ollama(
        url,
        {
            "model": model,
            "stream": False,
            "options": {"temperature": 0, "num_predict": 160, "num_ctx": 8192},
            "messages": answer_messages(config, now, data, question),
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--ha", required=True)
    parser.add_argument("--token-file", type=Path, required=True)
    parser.add_argument("--ollama", required=True)
    parser.add_argument("--model", default="gemma4:26b")
    parser.add_argument("--old", type=Path, required=True)
    parser.add_argument("--new", type=Path, required=True)
    parser.add_argument("--questions", type=Path, required=True, help="one question per line")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--time-zone", default="Europe/Warsaw", help="HA time zone (DST changes)")
    args = parser.parse_args()

    ha = HA(args.ha, args.token_file.expanduser().read_text().strip())
    old = parse_config(yaml.safe_load(args.old.read_text(encoding="utf-8")))
    new = parse_config(yaml.safe_load(args.new.read_text(encoding="utf-8")))
    url = args.ollama.rstrip("/")
    settings = OllamaSettings(url=url, model=args.model, timeout=60, keep_alive=-1, num_ctx=8192)
    all_states = states(ha)
    exposed = {entity_id for entity_id, flags in _exposed(ha).items() if flags.get("conversation")}
    now = datetime.now(ZoneInfo(args.time_zone))
    rows = []
    for question in [q.strip() for q in args.questions.read_text().splitlines() if q.strip()]:
        content, _ = ollama(url, build_request(settings, new, question))
        route = parse_route(new, content, question)
        if route is None:
            rows.append({"question": question, "topic": None})
            continue
        topic_new = new.topics[route.topic]
        topic_old = old.topics.get(route.topic, topic_new)
        lines = entity_lines(
            all_states,
            topic_new,
            exposed,
            new.only_exposed if topic_new.only_exposed is None else topic_new.only_exposed,
        )
        state_part = "Stany urządzeń:\n" + "\n".join(lines) if lines else ""
        old_data = "\n".join(
            p for p in (old_command(ha, old, topic_old, route, question), state_part) if p
        )
        new_data = "\n".join(
            p for p in (state_part, *new_sources(ha, all_states, new, topic_new, route, now)) if p
        )
        old_answer, old_s = answer(url, args.model, old, old_data, question, now)
        new_answer, new_s = answer(url, args.model, new, new_data, question, now)
        row = {
            "question": question, "topic": route.topic, "people": route.people,
            "when": route.when, "old": old_answer, "new": new_answer,
            "old_chars": len(old_data), "new_chars": len(new_data),
            "old_s": round(old_s, 2), "new_s": round(new_s, 2), "new_data": new_data,
        }  # fmt: skip
        rows.append(row)
        print(
            f"\n[{route.topic}] {question}\n  old ({len(old_data)} chars, {old_s:.1f} s): "
            f"{old_answer}\n  new ({len(new_data)} chars, {new_s:.1f} s): {new_answer}",
            flush=True,
        )
    args.out.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")


def _exposed(ha: HA) -> dict[str, dict]:
    """Entity exposure (WebSocket) - not available over REST, so via snapshot_data."""
    import asyncio

    from snapshot_data import _ws

    (result,) = asyncio.run(_ws(ha.url, ha.token, [{"type": "homeassistant/expose_entity/list"}]))
    return result["exposed_entities"]


if __name__ == "__main__":
    main()
