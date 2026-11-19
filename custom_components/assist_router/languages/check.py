"""Checks of a language pack against the reference pack (Polish) - for the tests, for
``tools/check_language.py`` and for the trainer's ``language check``.

Every problem is one line a translator can act on: what is missing, which ``{field}`` was lost,
which example a pattern no longer recognizes, which Home Assistant name was translated by mistake.
"""

from __future__ import annotations

from pathlib import Path
import re
import string
from types import ModuleType
from typing import Any

from . import FOLDER, PATTERNS_FILE, load_pack, pattern_examples, read_yaml

REFERENCE = "pl"
# dictionaries whose keys are Home Assistant names or code words - the same in every language
FIXED_KEYS = (
    "INTENTS",
    "DOMAINS",
    "CONTROL_KEYS",
    "DOMAIN_HINTS",
    "DONE",
    "BINARY_STATES",
    "STATES",
    "PREVIEW_HEADERS",
    "COMMAND_VARIABLE_ALIASES",
    "OPEN_CLOSE_VERBS",
)
DAY_CODES_OF = ("WHEN_PATTERNS",)


def fields(text: str) -> set[str]:
    """The ``{fields}`` of a str.format template."""
    try:
        return {name for _, name, _, _ in string.Formatter().parse(text) if name}
    except ValueError:
        return {"<broken braces>"}


def public_names(pack: ModuleType) -> set[str]:
    """Names a pack defines itself (data and functions, not imports)."""
    out = set()
    for name, value in vars(pack).items():
        if name.startswith("__") or isinstance(value, ModuleType):
            continue
        if callable(value) and getattr(value, "__module__", pack.__name__) not in (
            pack.__name__,
            None,
        ):
            continue
        out.add(name)
    return out


def _texts_of(folder: Path) -> dict[str, Any]:
    return read_yaml(folder / "texts.yaml")


def pattern_problems(specs: dict[str, Any]) -> list[str]:
    problems = []
    for name, spec in specs.items():
        for label, item in pattern_examples(spec):
            where = f"{name}[{label}]" if label else name
            try:
                flags = re.IGNORECASE if "IGNORECASE" in (item.get("flags") or ()) else 0
                pattern = re.compile(item["pattern"], flags)
            except (re.error, KeyError) as err:
                problems.append(f"patterns.yaml {where}: does not compile - {err}")
                continue
            for text in item.get("matches") or ():
                if not pattern.search(text):
                    problems.append(f"patterns.yaml {where}: does not recognize „{text}”")
            for text in item.get("not_matches") or ():
                if pattern.search(text):
                    problems.append(f"patterns.yaml {where}: wrongly recognizes „{text}”")
            if not item.get("matches"):
                problems.append(f"patterns.yaml {where}: no `matches` examples")
    return problems


def problems(folder: Path, reference: Path | None = None) -> list[str]:
    """Everything wrong with the pack in ``folder`` (empty = ready)."""
    reference = reference or FOLDER / REFERENCE
    out: list[str] = []
    try:
        pack = load_pack(folder, f"assist_router_pack_check.{folder.name}")
    except Exception as err:  # the files themselves are broken
        return [f"the pack does not load: {type(err).__name__}: {err}"]
    ref = load_pack(reference, f"assist_router_pack_check.ref_{reference.name}")
    missing = sorted(public_names(ref) - public_names(pack))
    out += [f"missing: {name}" for name in missing]
    own, ref_texts = _texts_of(folder), _texts_of(reference)
    for name, text in ref_texts.items():
        if isinstance(text, str) and isinstance(own.get(name), str):
            lost, extra = fields(text) - fields(own[name]), fields(own[name]) - fields(text)
            if lost or extra:
                out.append(
                    f"texts.yaml {name}: fields {sorted(fields(own[name]))}, "
                    f"expected {sorted(fields(text))}"
                )
    for name in FIXED_KEYS:
        mine, theirs = getattr(pack, name, None), getattr(ref, name, None)
        if isinstance(mine, dict) and isinstance(theirs, dict) and set(mine) != set(theirs):
            changed = sorted(set(mine) ^ set(theirs))
            out.append(f"{name}: keys are Home Assistant names and stay as they are: {changed}")
    ref_days = {code for code, _ in getattr(ref, "WHEN_PATTERNS", ())}
    days = {code for code, _ in getattr(pack, "WHEN_PATTERNS", ())}
    if days - ref_days:
        out.append(f"WHEN_PATTERNS: unknown day codes {sorted(days - ref_days)}")
    unknown = set(getattr(pack, "DAY_ALIASES", {}).values()) - ref_days
    if unknown:
        out.append(f"DAY_ALIASES: unknown day codes {sorted(unknown)}")
    out += _json_key_problems(pack)
    out += pattern_problems(read_yaml(folder / PATTERNS_FILE))
    return out


def _json_key_problems(pack: ModuleType) -> list[str]:
    """JSON keys and answer words must be the ones the prompts ask the model for."""
    out = []
    checks = (
        ("SENTENCES_KEY", "EXAMPLES_PROMPT", lambda: pack.EXAMPLES_PROMPT),
        ("SPLIT_KEY", "split_prompt", lambda: pack.split_prompt("")),
    )
    for key, where, text in checks:
        try:
            if getattr(pack, key) not in text():
                out.append(f"{key} „{getattr(pack, key)}” does not appear in {where}")
        except Exception as err:
            out.append(f"{where}: {type(err).__name__}: {err}")
    try:
        prompt = pack.control_prompt("i", "d", "a", "f", "h", "s")
        for name in ("CHANGE_SET", "CHANGE_MORE", "CHANGE_LESS"):
            if getattr(pack, name) not in prompt:
                out.append(f"{name} „{getattr(pack, name)}” does not appear in control_prompt")
    except Exception as err:
        out.append(f"control_prompt: {type(err).__name__}: {err}")
    return out
