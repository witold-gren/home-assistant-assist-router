"""Appending unrecognized commands to a CSV file."""

from __future__ import annotations

import asyncio
import csv
from pathlib import Path
import shutil

from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import COLUMNS, SIGNAL_LOG
from .languages import LANG

# Spreadsheets treat a cell starting with these characters as a formula.
_FORMULA_PREFIXES = ("=", "+", "-", "@")


def _safe_cell(value: str) -> str:
    value = " ".join(str(value).split())
    return "'" + value if value.startswith(_FORMULA_PREFIXES) else value


class CsvLog:
    """CSV file (UTF-8 with BOM, separator ";") that opens directly in Numbers and Excel.

    Writes run in a worker thread under a lock, so two commands at once
    do not mix up rows.
    """

    def __init__(self, hass: HomeAssistant, path: Path) -> None:
        self._hass = hass
        self.path = path
        self._lock = asyncio.Lock()

    async def async_append(self, row: dict[str, str]) -> None:
        async with self._lock:
            await self._hass.async_add_executor_job(self._append, row)
        async_dispatcher_send(self._hass, SIGNAL_LOG)

    async def async_rows(self) -> list[dict[str, str]]:
        """All entries, oldest first (for the preview and the sensor)."""
        async with self._lock:
            return await self._hass.async_add_executor_job(self._rows)

    async def async_clear(self) -> int:
        """Empty the log (header only); old content kept as .bak. Returns the old entry count."""
        async with self._lock:
            count = await self._hass.async_add_executor_job(self._clear)
        async_dispatcher_send(self._hass, SIGNAL_LOG)
        return count

    def _rows(self) -> list[dict[str, str]]:
        try:
            with self.path.open(encoding="utf-8-sig", newline="") as handle:
                return list(csv.DictReader(handle, delimiter=";"))
        except FileNotFoundError:
            return []

    def _clear(self) -> int:
        count = len(self._rows())
        if self.path.exists():
            shutil.copy2(self.path, self.path.with_name(self.path.name + ".bak"))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8-sig", newline="") as handle:
            csv.writer(handle, delimiter=";").writerow(COLUMNS)
        return count

    def _append(self, row: dict[str, str]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        is_new = not self.path.exists() or self.path.stat().st_size == 0
        if not is_new:
            self._upgrade_header()
        # utf-8-sig writes the BOM only at the start of a new file.
        encoding = "utf-8-sig" if is_new else "utf-8"
        with self.path.open("a", encoding=encoding, newline="") as handle:
            writer = csv.writer(handle, delimiter=";")
            if is_new:
                writer.writerow(COLUMNS)
            writer.writerow([_safe_cell(row.get(column, "")) for column in COLUMNS])

    def _upgrade_header(self) -> None:
        """A file from an older version (fewer columns) gets the new header; rows are kept."""
        with self.path.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.reader(handle, delimiter=";"))
        if not rows or tuple(rows[0]) == COLUMNS or rows[0] != list(COLUMNS[: len(rows[0])]):
            return
        with self.path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle, delimiter=";")
            writer.writerow(COLUMNS)
            writer.writerows(rows[1:])


# preview columns (CSV keys); the headers come from the language pack
PREVIEW_COLUMNS = ("timestamp", "area", "speaker", "text", "response")


def markdown_table(rows: list[dict[str, str]], limit: int, cell_chars: int = 80) -> str:
    """Latest entries (newest on top) as a markdown table."""
    if not rows:
        return "-"

    def cell(value: str | None) -> str:
        text = " ".join((value or "").split()).replace("|", "/")
        return text if len(text) <= cell_chars else text[: cell_chars - 1] + "…"

    lines = [
        "| " + " | ".join(LANG.PREVIEW_HEADERS[key] for key in PREVIEW_COLUMNS) + " |",
        "|" + "---|" * len(PREVIEW_COLUMNS),
    ]
    for row in reversed(rows[-limit:]):
        lines.append("| " + " | ".join(cell(row.get(key)) for key in PREVIEW_COLUMNS) + " |")
    return "\n".join(lines)
