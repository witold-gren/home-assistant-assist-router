"""What the data sources of a topic give, for the editor: how many entities each pattern finds, the
lines of states and attributes the answer model would get, and - only when asked - the answers of
the services. It uses the router's own functions, so the preview is what a question would see.
Nothing is switched: a service is called only when it solely returns data (SupportsResponse.ONLY),
and a topic's `command` sentence is never sent to Home Assistant."""

from __future__ import annotations

from dataclasses import replace
import fnmatch
import string
from typing import Any

from homeassistant.core import HomeAssistant, SupportsResponse
from homeassistant.util import dt as dt_util

from .router import (
    ENTITY_LIMIT,
    Fetch,
    Route,
    RouterConfig,
    Topic,
    _pattern_index,
    async_todo_lines,
    async_topic_sources,
    entity_lines,
)

SAMPLE = 8  # entity ids shown under a pattern


def pattern_counts(hass: HomeAssistant, patterns: tuple[str, ...]) -> list[dict[str, Any]]:
    """For each pattern: how many entities it finds (an exclusion `!…`: how many it leaves out),
    and the first of them."""
    states = sorted(hass.states.async_all(), key=lambda state: state.entity_id)
    out = []
    for pattern in patterns:
        if pattern.startswith("!"):
            found = [s.entity_id for s in states if fnmatch.fnmatchcase(s.entity_id, pattern[1:])]
        else:
            found = [s.entity_id for s in states if _pattern_index(s, (pattern,)) is not None]
        out.append({"pattern": pattern, "count": len(found), "sample": found[:SAMPLE]})
    return out


def read_only(hass: HomeAssistant, action: str) -> str:
    """`read_only` when the service only returns data, `missing` when there is no such service,
    else `changes` (it may switch something, so the router never calls it from `fetch`)."""
    domain, _, service = action.partition(".")
    if not hass.services.has_service(domain, service):
        return "missing"
    support = hass.services.supports_response(domain, service)
    return "read_only" if support is SupportsResponse.ONLY else "changes"


def read_only_services(hass: HomeAssistant) -> list[str]:
    """Every service that only returns data, e.g. calendar.get_events."""
    return sorted(
        f"{domain}.{service}"
        for domain, services in hass.services.async_services().items()
        for service in services
        if hass.services.supports_response(domain, service) is SupportsResponse.ONLY
    )


async def async_sources_preview(
    hass: HomeAssistant, config: RouterConfig, topic: Topic, run_fetch: bool = False
) -> dict[str, Any]:
    """The data of a topic for a question without a person or a day."""
    route = Route(topic=topic.name, person=None, when=None, phrase=None)
    now = dt_util.now()
    exposed = config.only_exposed if topic.only_exposed is None else topic.only_exposed
    lines: list[str] = []
    if topic.entities:
        lines = entity_lines(
            hass, topic.entities, exposed, topic.skip_states, unavailable=topic.unavailable
        )
        lines = await async_todo_lines(hass, lines, topic.entities)
    matched = sum(
        1 for state in hass.states.async_all() if _pattern_index(state, topic.entities) is not None
    )
    details: list[str] = []
    if topic.details:
        only_details = replace(topic, fetch=(), frigate=None)
        details = await async_topic_sources(hass, config, only_details, route, now)
    fetch = []
    for item in topic.fetch:
        fetch.append(await _fetch_preview(hass, config, topic, route, item, run_fetch, now))
    return {
        "entities": {
            "patterns": pattern_counts(hass, topic.entities),
            "matched": matched,
            "lines": lines,
            "limit": ENTITY_LIMIT,
            "only_exposed": exposed,
            "nothing_active": not lines and bool(topic.skip_states) and matched > 0,
        },
        "details": {"patterns": pattern_counts(hass, topic.details), "sources": details},
        "fetch": fetch,
    }


async def _fetch_preview(
    hass: HomeAssistant,
    config: RouterConfig,
    topic: Topic,
    route: Route,
    item: Fetch,
    run: bool,
    now,
) -> dict[str, Any]:
    kind = read_only(hass, item.action)
    found = pattern_counts(hass, item.entities)
    targets = sorted(
        state.entity_id
        for state in hass.states.async_all()
        if _pattern_index(state, item.entities) is not None
    )
    result: dict[str, Any] = {
        "action": item.action,
        "service": kind,
        "patterns": found,
        "targets": targets,
        "sources": None,
    }
    if run and kind == "read_only" and targets:
        one = replace(topic, details=(), frigate=None, fetch=(item,))
        result["sources"] = await async_topic_sources(hass, config, one, route, now)
    return result


PROMPT_VALUES = ("household", "now", "sentences")


def prompt_problem(prompt: str) -> str | None:
    """Why the router could not fill a prompt of the settings ({who}, a lone brace), or None."""
    try:
        names = [name for _, name, _, _ in string.Formatter().parse(prompt) if name is not None]
    except ValueError as err:
        return str(err)
    unknown = sorted({name for name in names if name not in PROMPT_VALUES})
    return ", ".join(f"{{{name}}}" for name in unknown) or None


def config_checks(hass: HomeAssistant, config: RouterConfig) -> list[dict[str, Any]]:
    """What is worth a look before saving: `error` breaks answers, `warn` is likely a mistake."""
    out: list[dict[str, Any]] = []

    def add(level: str, code: str, **values: Any) -> None:
        out.append({"level": level, "code": code, **values})

    for key in ("answer_prompt", "summary_prompt"):
        if problem := prompt_problem(getattr(config, key)):
            add("error", "prompt", key=key, problem=problem)
    for name, topic in config.topics.items():
        if not topic.description.strip():
            add("warn", "no_description", topic=name)
        if not topic.examples and not (topic.control or topic.unclear):
            add("warn", "no_examples", topic=name)
        for field, patterns in (("entities", topic.entities), ("details", topic.details)):
            for found in pattern_counts(hass, patterns):
                if not found["count"] and not found["pattern"].startswith("!"):
                    add("warn", "pattern_empty", topic=name, field=field, pattern=found["pattern"])
        for item in topic.fetch:
            kind = read_only(hass, item.action)
            if kind != "read_only":
                add(
                    "error" if kind == "changes" else "warn",
                    f"fetch_{kind}",
                    topic=name,
                    action=item.action,
                )
            for found in pattern_counts(hass, item.entities):
                if not found["count"] and not found["pattern"].startswith("!"):
                    add(
                        "warn", "pattern_empty", topic=name, field="fetch", pattern=found["pattern"]
                    )
    return out
