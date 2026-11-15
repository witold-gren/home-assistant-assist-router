"""Learning from what was said, for the editor: the unrecognized commands of the log grouped by
sentence, and the test set (assist/router_tests.yaml) - sentences with the topic the router should
choose or the intent Home Assistant should recognize - run on the draft and on the saved file.
Like the tester, nothing is done: Home Assistant only recognizes, the router model only chooses."""

from __future__ import annotations

import time
from typing import Any

from homeassistant.core import HomeAssistant
import yaml

from .router import RouterConfig, async_classify

TESTS_FILE = "router_tests.yaml"
GROUP_LIMIT = 300  # sentences of the log shown, newest first
CLASSIFY_LIMIT = 50  # sentences the router model chooses a topic for at once
TESTS_LIMIT = 500
TESTS_HEADER = (
    "# Test set of the Assist Router editor: a sentence and the topic the router should choose\n"
    "# (topic) or the intent Home Assistant should recognize itself (intent).\n"
)


def sentence_key(text: str) -> str:
    """One key for the ways a sentence was written: case, spaces and the final mark aside."""
    return " ".join(str(text).casefold().strip().rstrip(".!?…").split())


def unrecognized_groups(rows: list[dict[str, str]], hidden: set[str]) -> list[dict[str, Any]]:
    """The log grouped by sentence, newest first: how often, when first and last, how it went."""
    groups: dict[str, dict[str, Any]] = {}
    for row in rows:
        text = " ".join(str(row.get("text") or "").split())
        key = sentence_key(text)
        if not key:
            continue
        group = groups.get(key)
        if group is None:
            group = groups[key] = {
                "key": key,
                "text": text,
                "count": 0,
                "first": row.get("timestamp") or "",
                "kinds": [],
                "speakers": [],
                "areas": [],
            }
        group["count"] += 1
        group["text"] = text
        group["last"] = row.get("timestamp") or ""
        group["route"] = row.get("route") or ""
        group["response"] = row.get("response") or ""
        for field, name in (("kinds", "kind"), ("speakers", "speaker"), ("areas", "area")):
            value = row.get(name) or ""
            if value and value not in group[field]:
                group[field].append(value)
    out = sorted(groups.values(), key=lambda group: group["last"], reverse=True)
    for group in out:
        group["hidden"] = group["key"] in hidden
    return out[:GROUP_LIMIT]


def read_tests(text: str) -> list[dict[str, str]]:
    """The tests of the file; ValueError with the reason when it is not a test set."""
    data = yaml.safe_load(text) if text.strip() else None
    if data is None:
        return []
    items = data.get("tests") if isinstance(data, dict) else data
    if not isinstance(items, list):
        raise ValueError(f"{TESTS_FILE}: expected `tests:` with a list")
    return [clean_test(item, index) for index, item in enumerate(items)]


def clean_test(item: Any, index: int = 0) -> dict[str, str]:
    """A test as the file keeps it: `sentence`, and `topic` or `intent`, and a `note`."""
    if not isinstance(item, dict) or not str(item.get("sentence") or "").strip():
        raise ValueError(f"{TESTS_FILE}: test {index + 1} needs a sentence")
    test = {"sentence": " ".join(str(item["sentence"]).split())}
    for key in ("topic", "intent", "note"):
        if item.get(key):
            test[key] = str(item[key]).strip()
    return test


def dump_tests(tests: list[dict[str, str]]) -> str:
    body = yaml.safe_dump(
        {"tests": tests}, allow_unicode=True, sort_keys=False, width=100, default_flow_style=False
    )
    return TESTS_HEADER + body


async def async_outcome(
    hass: HomeAssistant,
    ollama: Any,
    config: RouterConfig | None,
    sentence: str,
    ha: dict[str, Any] | None,
) -> dict[str, Any]:
    """Where a sentence goes: Home Assistant's intent, or the router's topic (None: no topic)."""
    if ha is not None and ha.get("match"):
        return {"intent": (ha.get("intent") or {}).get("name") or "trigger"}
    if config is None or ollama is None:
        return {"topic": None}
    route = await async_classify(hass, ollama, config, sentence)
    return {"topic": route.topic if route else None}


def passes(test: dict[str, str], outcome: dict[str, Any]) -> bool:
    if test.get("intent"):
        return outcome.get("intent") == test["intent"]
    if test.get("topic"):
        return "intent" not in outcome and outcome.get("topic") == test["topic"]
    return False


async def async_run_tests(
    hass: HomeAssistant,
    agent: Any,
    tests: list[dict[str, str]],
    config: RouterConfig,
    saved: RouterConfig | None = None,
) -> dict[str, Any]:
    """Each test on the draft (and on the saved file): passed, failed, fixed, broken."""
    from .tester import async_ha_debug

    ollama = agent._ollama()
    start = time.monotonic()
    results = []
    for test in tests[:TESTS_LIMIT]:
        ha = await async_ha_debug(hass, test["sentence"])
        draft = await async_outcome(hass, ollama, config, test["sentence"], ha)
        result = {**test, "draft": draft, "ok": passes(test, draft)}
        if saved is not None:
            before = await async_outcome(hass, ollama, saved, test["sentence"], ha)
            result["saved"] = before
            result["ok_saved"] = passes(test, before)
        results.append(result)
    summary = {
        "total": len(results),
        "passed": sum(1 for r in results if r["ok"]),
        "failed": sum(1 for r in results if not r["ok"]),
    }
    if saved is not None:
        summary["fixed"] = sum(1 for r in results if r["ok"] and not r["ok_saved"])
        summary["broken"] = sum(1 for r in results if not r["ok"] and r["ok_saved"])
    return {
        "results": results,
        "summary": summary,
        "model": ollama.model if ollama else None,
        "ms": round((time.monotonic() - start) * 1000),
    }


async def async_classify_sentences(
    hass: HomeAssistant, agent: Any, config: RouterConfig, sentences: list[str]
) -> list[dict[str, Any]]:
    """Where each sentence would go on the draft (Home Assistant's intent or the router's topic)."""
    from .tester import async_ha_debug

    ollama = agent._ollama()
    out = []
    for sentence in sentences[:CLASSIFY_LIMIT]:
        ha = await async_ha_debug(hass, sentence)
        out.append(
            {"sentence": sentence, **await async_outcome(hass, ollama, config, sentence, ha)}
        )
    return out
