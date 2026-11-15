"""Sentences of Home Assistant's own agent for the editor: the files of
<config>/custom_sentences/<language>/*.yaml, checked as Home Assistant reads them (every sentence
template parsed by hassil), written with a .bak and reloaded at once (conversation.reload), so new
voice commands work without a restart."""

from __future__ import annotations

import hashlib
from pathlib import Path
import re
from typing import Any

from hassil.parse_expression import parse_sentence
from homeassistant.core import HomeAssistant
from homeassistant.helpers import intent
import yaml

SENTENCES_DIR = "custom_sentences"
LANGUAGE = re.compile(r"^[a-z]{2,3}([-_][A-Za-z0-9]+)?$")
FILE_NAME = re.compile(r"^[\w\-]+\.yaml$")


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def sentences_root(hass: HomeAssistant) -> Path:
    return Path(hass.config.path(SENTENCES_DIR))


def file_path(root: Path, language: str, name: str) -> Path | None:
    """The file of a language and a name, or None when either is not a plain name."""
    if not LANGUAGE.match(language) or not FILE_NAME.match(name):
        return None
    path = (root / language / name).resolve()
    return path if path.is_relative_to(root.resolve()) else None


def check_sentences(text: str) -> dict[str, Any]:
    """Whether Home Assistant can use a file of sentences: `ok`, the first `error` (with the intent
    and the sentence it is in) and a summary of its intents."""
    try:
        data = yaml.safe_load(text) if text.strip() else None
    except yaml.YAMLError as err:
        return {"ok": False, "error": str(err).split("\n")[0], "intents": []}
    if not isinstance(data, dict):
        return {
            "ok": False,
            "error": "the file must be a mapping (language:, intents:)",
            "intents": [],
        }
    intents = data.get("intents") or {}
    if not isinstance(intents, dict):
        return {"ok": False, "error": "intents: must be a mapping of intent names", "intents": []}
    summary = []
    for name, spec in intents.items():
        groups = spec.get("data") if isinstance(spec, dict) else None
        if not isinstance(groups, list):
            return {"ok": False, "error": f"{name}: needs data: with a list", "intents": summary}
        count = 0
        for group in groups:
            sentences = group.get("sentences") if isinstance(group, dict) else None
            if not isinstance(sentences, list) or not all(isinstance(s, str) for s in sentences):
                return {
                    "ok": False,
                    "error": f"{name}: data needs sentences: with texts",
                    "intents": summary,
                }
            for sentence in sentences:
                try:
                    parse_sentence(sentence)
                except Exception as err:
                    return {
                        "ok": False,
                        "error": f"{name}: „{sentence}”: {err}",
                        "intents": summary,
                    }
                count += 1
        summary.append({"name": str(name), "sentences": count})
    responses = data.get("responses")
    if responses is not None and not isinstance(responses, dict):
        return {"ok": False, "error": "responses: must be a mapping", "intents": summary}
    return {"ok": True, "error": None, "intents": summary}


def list_files(root: Path) -> list[dict[str, Any]]:
    """Every file of sentences, by language and name, with its text and what is in it."""
    out = []
    if not root.is_dir():
        return out
    for path in sorted(root.glob("*/*.yaml")):
        text = path.read_text(encoding="utf-8")
        out.append(
            {
                "language": path.parent.name,
                "name": path.name,
                "text": text,
                "hash": text_hash(text),
                "check": check_sentences(text),
            }
        )
    return out


def known_intents(hass: HomeAssistant) -> list[str]:
    """The intents Home Assistant can carry out (built in, intent_script, integrations)."""
    return sorted({handler.intent_type for handler in intent.async_get(hass)})


def write_file(path: Path, text: str) -> None:
    if path.exists():
        path.with_name(path.name + ".bak").write_text(
            path.read_text(encoding="utf-8"), encoding="utf-8"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def remove_file(path: Path) -> None:
    """The file out of the way as .bak (Home Assistant reads only *.yaml)."""
    path.replace(path.with_name(path.name + ".bak"))
