"""The "who is speaking?" check of voice recognition (Assist Speaker ID integration).

The answer comes from the recognition result of the same utterance: who, with what
similarity and who is next - so a few sentences show how reliably a voice is recognized.
The phrases and replies come from the active language pack.
"""

from __future__ import annotations

import re
from typing import Any

from .languages import LANG

# replies of the language pack available as voice.ANNOUNCED etc.
_PACK_NAMES = frozenset({"ANNOUNCED", "NO_VOICE", "TOO_SHORT", "NO_PRINTS"})

# threshold the best voice missed, from the Assist Speaker ID reason "<id> below threshold 0.78"
_THRESHOLD = re.compile(r"below threshold (\d+(?:\.\d+)?)")


def __getattr__(name: str) -> Any:
    if name in _PACK_NAMES:
        return getattr(LANG, name)
    raise AttributeError(name)


def is_announcement(text: str) -> bool:
    return bool(LANG.ANNOUNCEMENT.search(text))


def is_who_speaks(text: str) -> bool:
    return bool(LANG.WHO_SPEAKS.search(text))


def answer(result: Any, names: dict[str, str]) -> str:
    """Reply from an Assist Speaker ID result (SpeakerResult; None = no recognition).

    ``names`` - voice id -> name to say (from router.yaml or Assist Speaker ID).
    """
    if result is None:
        return LANG.NO_VOICE
    reason = result.reason or ""
    if reason.startswith("too short"):
        return LANG.TOO_SHORT
    if not result.scores:
        return LANG.NO_PRINTS

    def name(speaker_id: str) -> str:
        return names.get(speaker_id) or speaker_id.title()

    ranked = sorted(result.scores.items(), key=lambda item: -item[1])
    best_id, best = ranked[0]
    second = LANG.next_speaker(name(ranked[1][0]), ranked[1][1]) if len(ranked) > 1 else ""
    if result.speaker:
        return LANG.speaker_recognized(name(result.speaker), result.score, second)
    if "too close" in reason:
        return LANG.speaker_uncertain(name(best_id), best, name(ranked[1][0]), ranked[1][1])
    found = _THRESHOLD.search(reason)
    threshold = float(found.group(1)) if found else None
    return LANG.speaker_unknown(name(best_id), best, threshold, second)
