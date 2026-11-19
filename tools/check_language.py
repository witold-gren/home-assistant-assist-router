"""Check a language pack before sending it: every name, every {field}, every pattern example.

    .venv/bin/python tools/check_language.py custom_components/assist_router/languages/cs

Prints one line per problem (what is missing, which {field} was lost, which example a pattern
no longer recognizes, which Home Assistant name was translated by mistake) and exits with 1
when there is any; "ready" and 0 when there is none. The same checks run in the tests
(tests/test_languages.py) for every pack in the integration.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from custom_components.assist_router.languages import check


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("folder", type=Path, help="the pack folder (texts.yaml, words.yaml …)")
    args = parser.parse_args()
    found = check.problems(args.folder.resolve())
    print("\n".join(found) if found else f"{args.folder.name}: ready")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
