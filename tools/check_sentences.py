"""Assist automation sentence test: do sample sentences from `conversation` triggers
hit their own automation - and is that automation enabled.

Sentences are generated from the templates (hassil) and HA only reports what would handle
them (``conversation/agent/homeassistant/debug``) - nothing is executed.

    .venv/bin/python tools/check_sentences.py --ha http://homeassistant.local:8123 \\
        --token-file ~/.ha_token --config /config --per-template 5 --out sentences.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import random
import re
import sys
from typing import Any

from hassil.parse_expression import parse_sentence
from hassil.sample import sample_sentence
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from snapshot_data import _ws

WILDCARD = "test"  # value substituted for the trigger {wildcards}


class _Loader(yaml.SafeLoader):
    """HA configuration YAML: tags (!include, !secret) are not expanded."""


_Loader.add_multi_constructor("!", lambda loader, suffix, node: None)


def automations(config: Path) -> list[dict[str, Any]]:
    """Automations from automations.yaml and packages (packages/*.yaml)."""
    found = []
    path = config / "automations.yaml"
    if path.exists():
        found += yaml.load(path.read_text(encoding="utf-8"), _Loader) or []
    for package in sorted((config / "packages").glob("*.yaml")):
        data = yaml.load(package.read_text(encoding="utf-8"), _Loader) or {}
        if isinstance(data, dict) and isinstance(data.get("automation"), list):
            found += data["automation"]
    return [a for a in found if isinstance(a, dict)]


def commands(automation: dict[str, Any]) -> list[str]:
    triggers = automation.get("triggers") or automation.get("trigger") or []
    triggers = triggers if isinstance(triggers, list) else [triggers]
    out = []
    for trigger in triggers:
        if isinstance(trigger, dict) and (trigger.get("trigger") or trigger.get("platform")) == (
            "conversation"
        ):
            command = trigger.get("command")
            out += command if isinstance(command, list) else [command]
    return [str(c) for c in out if c]


def normalize(template: str) -> str:
    return " ".join(str(template).split()).lower()


def samples(template: str, count: int, rng: random.Random) -> list[str]:
    """Up to ``count`` random sentences from a template (always incl. shortest and longest)."""
    expression = re.sub(r"\{[^}]+\}", WILDCARD, template)
    try:
        sentences = []
        for sentence in sample_sentence(parse_sentence(expression), language="pl"):
            sentences.append(" ".join(sentence.split()))
            if len(sentences) >= 5000:
                break
    except Exception as err:  # a template hassil cannot expand is an error too
        return [f"!! template error: {err}"]
    sentences = sorted(set(s for s in sentences if s))
    if len(sentences) <= count:
        return sentences
    picked = {min(sentences, key=len), max(sentences, key=len)}
    picked |= set(rng.sample(sentences, count - len(picked)))
    return sorted(picked)


async def check(args: argparse.Namespace) -> dict[str, Any]:
    token = args.token_file.expanduser().read_text().strip()
    url = args.ha.rstrip("/")
    entries, states = await _ws_all(url, token)
    by_unique = {e["unique_id"]: e["entity_id"] for e in entries if e["platform"] == "automation"}
    state = {s["entity_id"]: s["state"] for s in states}
    rng = random.Random(args.seed)

    owners: dict[str, str] = {}  # template -> automation alias
    cases = []
    for automation in automations(args.config):
        alias = str(automation.get("alias") or automation.get("id"))
        templates = commands(automation)
        if not templates:
            continue
        entity_id = by_unique.get(str(automation.get("id")))
        for template in templates:
            owners[normalize(template)] = alias
            for sentence in samples(template, args.per_template, rng):
                cases.append({"alias": alias, "entity_id": entity_id,
                              "state": state.get(entity_id or "", "no entity"),
                              "template": template, "sentence": sentence})  # fmt: skip

    valid = [c for c in cases if not c["sentence"].startswith("!!")]
    for start in range(0, len(valid), 200):
        batch = valid[start : start + 200]
        (result,) = await _ws(url, token, [{
            "type": "conversation/agent/homeassistant/debug",
            "sentences": [c["sentence"] for c in batch], "language": "pl",
        }])  # fmt: skip
        for case, match in zip(batch, result["results"], strict=True):
            if not match or not match.get("match"):
                case["got"] = "no match"
            elif match.get("source") == "trigger":
                owner = owners.get(normalize(match.get("sentence_template", "")), "?")
                case["got"] = "ok" if owner == case["alias"] else f"other automation: {owner}"
            else:
                case["got"] = f"HA intent: {match['intent']['name']}"
    for case in cases:
        if case["sentence"].startswith("!!"):
            case["got"] = case["sentence"][3:]
        if case["got"] == "ok" and case["state"] != "on":
            case["got"] = f"matches, but the automation is {case['state']}"
    return {"cases": cases}


async def _ws_all(url: str, token: str) -> tuple[list, list]:
    entries, states = await _ws(
        url, token, [{"type": "config/entity_registry/list"}, {"type": "get_states"}]
    )
    return entries, states


def report(cases: list[dict[str, Any]]) -> int:
    per: dict[str, list[dict[str, Any]]] = {}
    for case in cases:
        per.setdefault(case["alias"], []).append(case)
    bad_total = 0
    for alias, items in per.items():
        bad = [c for c in items if c["got"] != "ok"]
        bad_total += len(bad)
        mark = "OK  " if not bad else "FAIL"
        print(f"{mark} {len(items) - len(bad):3}/{len(items):<3} {alias}  [{items[0]['state']}]")
        for case in bad[:6]:
            print(f'        "{case["sentence"]}" -> {case["got"]}')
    print(f"\n{len(per)} automations, {len(cases)} sentences, failures: {bad_total}")
    return bad_total


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--ha", required=True)
    parser.add_argument("--token-file", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True, help="HA configuration directory")
    parser.add_argument("--per-template", type=int, default=5, help="sentences per template")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--out", type=Path, help="JSON results")
    args = parser.parse_args()
    result = asyncio.run(check(args))
    if args.out:
        args.out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    sys.exit(1 if report(result["cases"]) else 0)


if __name__ == "__main__":
    main()
