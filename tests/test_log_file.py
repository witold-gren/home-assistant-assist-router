"""Writing to the CSV file."""

from __future__ import annotations

import asyncio
import csv
from pathlib import Path

from homeassistant.core import HomeAssistant

from custom_components.assist_router.const import COLUMNS
from custom_components.assist_router.log_file import CsvLog


def _row(**kwargs: str) -> dict[str, str]:
    row = dict.fromkeys(COLUMNS, "")
    row.update(kwargs)
    return row


def _read(path: Path) -> list[list[str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.reader(handle, delimiter=";"))


async def test_header_bom_and_polish_text(hass: HomeAssistant, tmp_path: Path) -> None:
    log = CsvLog(hass, tmp_path / "assist" / "unrecognized_commands.csv")
    await log.async_append(_row(text="zapal światło nad blatem; proszę", area="Kuchnia"))
    await log.async_append(_row(text='powiedz "dzień dobry"'))
    raw = log.path.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    assert raw.count(b"\xef\xbb\xbf") == 1
    rows = _read(log.path)
    assert rows[0] == list(COLUMNS)
    assert rows[1][COLUMNS.index("text")] == "zapal światło nad blatem; proszę"
    assert rows[1][COLUMNS.index("area")] == "Kuchnia"
    assert rows[2][COLUMNS.index("text")] == 'powiedz "dzień dobry"'


async def test_formula_like_text_is_escaped(hass: HomeAssistant, tmp_path: Path) -> None:
    log = CsvLog(hass, tmp_path / "x.csv")
    await log.async_append(_row(text="=HYPERLINK(1)"))
    assert _read(log.path)[1][COLUMNS.index("text")] == "'=HYPERLINK(1)"


async def test_parallel_writes_keep_rows_whole(hass: HomeAssistant, tmp_path: Path) -> None:
    log = CsvLog(hass, tmp_path / "x.csv")
    await asyncio.gather(*(log.async_append(_row(text=f"komenda {i}")) for i in range(30)))
    rows = _read(log.path)
    assert len(rows) == 31
    assert sorted(r[COLUMNS.index("text")] for r in rows[1:]) == sorted(
        f"komenda {i}" for i in range(30)
    )
