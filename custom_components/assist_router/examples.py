"""Example commands from router.yaml and home entities, checked on the real router.

For each topic the answer model writes sentences with the names of your entities, people
and actions. Each sentence then goes through the router (topic), and control sentences
also through parsing and the command plan - without execution. The file keeps the
working sentences and, separately, the rejected ones (with the topic they landed in),
which shows where to improve the router.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
import json
import logging
from pathlib import Path
import random
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
import yaml

from .control import Home
from .languages import LANG
from .router import (
    OllamaSettings,
    RouterConfig,
    Topic,
    async_chat,
    async_classify,
    by_pattern,
)

_LOGGER = logging.getLogger(__name__)

EXAMPLES_FILE = "router_examples.yaml"
MAX_NAMES = 40  # entity names in the model prompt per topic
# keys of router_examples.yaml (and of the generate_examples response)
KEY_DESCRIPTION = "description"
KEY_WORKING = "working"
KEY_REJECTED = "rejected"
KEY_SENTENCE = "sentence"
KEY_TOPIC = "topic"
KEY_CONTROL = "control"
# the same keys in files written by versions before 0.1.0
_LEGACY_KEYS = {KEY_WORKING: "dzialaja", KEY_REJECTED: "odrzucone"}


def working(topic: dict[str, Any]) -> list[str]:
    """Working sentences of a topic from router_examples.yaml (also the old key)."""
    return topic.get(KEY_WORKING) or topic.get(_LEGACY_KEYS[KEY_WORKING]) or []


def rejected(topic: dict[str, Any]) -> list[dict[str, str]]:
    """Rejected sentences of a topic from router_examples.yaml (also the old key)."""
    return topic.get(KEY_REJECTED) or topic.get(_LEGACY_KEYS[KEY_REJECTED]) or []


def _schema() -> dict[str, Any]:
    key = LANG.SENTENCES_KEY
    return {
        "type": "object",
        "properties": {key: {"type": "array", "items": {"type": "string"}}},
        "required": [key],
    }


# checking a control command without executing it: None = works, text = why not
ControlCheck = Callable[[str], Awaitable[str | None]]


@dataclass
class TopicExamples:
    description: str
    working: list[str] = field(default_factory=list)
    rejected: list[dict[str, str]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {KEY_DESCRIPTION: self.description, KEY_WORKING: self.working}
        if self.rejected:
            data[KEY_REJECTED] = self.rejected
        return data


def topic_names(hass: HomeAssistant, topic: Topic, home: Home) -> list[str]:
    """Names from the topic data: entities (`entities`, `details`, `fetch`) or home devices."""
    if topic.control:
        names = [f"{t.name} ({t.area})" if t.area else t.name for t in home.targets]
        random.shuffle(names)
        return names[:MAX_NAMES]
    patterns = (*topic.entities, *topic.details, *(e for f in topic.fetch for e in f.entities))
    states = by_pattern(hass.states.async_all(), patterns) if patterns else []
    return [s.name for s in states][:MAX_NAMES]


def topic_request(
    config: RouterConfig, topic: Topic, names: list[str], count: int, settings: OllamaSettings
) -> dict[str, Any]:
    content = LANG.examples_request(
        topic=topic.description,
        examples="; ".join(topic.examples),
        names="; ".join(names),
        people=", ".join(p.name for p in config.people.values()),
        household=config.household,
        count=count,
    )
    return {
        "model": settings.model,
        "stream": False,
        "keep_alive": f"{settings.keep_alive}m" if settings.keep_alive >= 0 else -1,
        "format": _schema(),
        "options": {"temperature": 0.7, "num_predict": 600, "num_ctx": settings.num_ctx},
        "messages": [
            {"role": "system", "content": LANG.EXAMPLES_PROMPT},
            {"role": "user", "content": content},
        ],
    }


def parse_sentences(content: str | None) -> list[str]:
    try:
        data = json.loads(content or "")
    except ValueError:
        return []
    sentences = data.get(LANG.SENTENCES_KEY) if isinstance(data, dict) else None
    if not isinstance(sentences, list):
        return []
    seen: dict[str, str] = {}
    for item in sentences:
        text = " ".join(str(item).split()).strip(" -•")
        if 2 <= len(text.split()) <= 20:
            seen.setdefault(text.lower(), text)
    return list(seen.values())


async def async_generate(
    hass: HomeAssistant,
    config: RouterConfig,
    home: Home,
    writer: OllamaSettings,
    router: OllamaSettings,
    check_control: ControlCheck,
    per_topic: int = 5,
    only: set[str] | None = None,
) -> dict[str, TopicExamples]:
    """Sentences for every topic (except `unclear`), checked by the router and the plan."""
    result: dict[str, TopicExamples] = {}
    for topic in config.topics.values():
        if topic.unclear or (only and topic.name not in only):
            continue
        examples = result[topic.name] = TopicExamples(topic.description)
        names = topic_names(hass, topic, home)
        request = topic_request(config, topic, names, per_topic * 2, writer)
        candidates = parse_sentences(await async_chat(hass, writer, request))
        for text in candidates:
            if len(examples.working) >= per_topic:
                break
            route = await async_classify(hass, router, config, text)
            if route is None or route.topic != topic.name:
                got = route.topic if route else LANG.NO_ROUTER_ANSWER
                examples.rejected.append({KEY_SENTENCE: text, KEY_TOPIC: got})
                continue
            if topic.control and (reason := await check_control(text)) is not None:
                examples.rejected.append({KEY_SENTENCE: text, KEY_CONTROL: reason})
                continue
            examples.working.append(text)
        _LOGGER.info(
            "Examples for %s: %d working, %d rejected",
            topic.name,
            len(examples.working),
            len(examples.rejected),
        )
    return result


def render(result: dict[str, TopicExamples], writer: str, router: str) -> str:
    when = dt_util.now().strftime("%Y-%m-%d %H:%M")
    header = LANG.EXAMPLES_HEADER.format(when=when, writer=writer, router=router)
    body = {name: examples.as_dict() for name, examples in result.items()}
    return header + yaml.safe_dump(body, allow_unicode=True, sort_keys=False, width=100)


def load(path: Path) -> dict[str, Any]:
    """Saved examples (for the sensor) or {}."""
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return {}
    return data if isinstance(data, dict) else {}
