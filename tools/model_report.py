"""Model benchmark report (tools/model_benchmark.py): HTML to read and CSV to compare.

    .venv/bin/python tools/model_report.py round1.json round2.json \\
        --label "round 1" --label "round 2" --ollama http://localhost:11434 \\
        --html /config/assist/result.html \\
        --csv /config/assist/model_results.csv --answers-csv /config/assist/model_answers.csv

CSV files are appended to (row = model x test part x date), so later runs, including new
models, can be compared with earlier ones. The HTML shows all CSV rows: the latest result of
every model in every part.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime
import html
import json
from pathlib import Path
import urllib.request

PARTS = {
    "router": "Router (topic)",
    "answers": "Answers: given data",
    "real": "Answers: data from HA",
    "wiki_answers": "Wikipedia summaries",
    "control": "Control (parsing)",
}
SUMMARY_COLUMNS = (
    "date", "run", "model", "part", "score", "total", "percent", "avg_s", "load_s", "size_gb",
)  # fmt: skip
ANSWER_COLUMNS = ("date", "run", "model", "part", "case", "ok", "seconds", "answer", "problems")


def file_sizes(url: str | None) -> dict[str, float]:
    if not url:
        return {}
    with urllib.request.urlopen(f"{url.rstrip('/')}/api/tags", timeout=30) as resp:
        return {m["name"]: round(m["size"] / 1e9, 1) for m in json.load(resp)["models"]}


def append_csv(path: Path, columns: tuple[str, ...], rows: list[dict]) -> None:
    new = not path.exists() or path.stat().st_size == 0
    with path.open("a", encoding="utf-8-sig" if new else "utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, columns, delimiter=";")
        if new:
            writer.writeheader()
        writer.writerows(rows)


def rows_from_results(results: dict, run: str, date: str, sizes: dict[str, float]):
    summary, answers = [], []
    for model, entry in results.items():
        for part in PARTS:
            if not (data := entry.get(part)):
                continue
            summary.append(
                {
                    "date": date,
                    "run": run,
                    "model": model,
                    "part": part,
                    "score": data["score"],
                    "total": data["total"],
                    "percent": round(100 * data["score"] / data["total"]),
                    "avg_s": f"{data['avg_s']:.2f}",
                    "load_s": entry.get("load_s", ""),
                    "size_gb": sizes.get(model, ""),
                }
            )
            for detail in data.get("details", []):
                answers.append(
                    {
                        "date": date,
                        "run": run,
                        "model": model,
                        "part": part,
                        "case": detail["case"],
                        "ok": int(not detail["problems"]),
                        "seconds": detail["s"],
                        "answer": detail["answer"],
                        "problems": " | ".join(detail["problems"]),
                    }
                )
            for error in data.get("errors", []):
                answers.append(
                    {"date": date, "run": run, "model": model, "part": part, "case": "",
                     "ok": 0, "seconds": "", "answer": error, "problems": "wrong topic"}
                )  # fmt: skip
    return summary, answers


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle, delimiter=";"))


def short(model: str) -> str:
    return model.removeprefix("hf.co/").removeprefix("SpeakLeash/").removeprefix("mradermacher/")


def render_html(summary: list[dict], answers: list[dict], notes: str) -> str:
    # latest result of every model in every part (comparable set = same total)
    latest: dict[tuple[str, str], dict] = {}
    for row in summary:
        latest[(row["model"], row["part"])] = row
    totals = {part: max((int(r["total"]) for k, r in latest.items() if k[1] == part), default=0)
              for part in PARTS}  # fmt: skip
    models = sorted({m for m, _ in latest})

    def cell(model: str, part: str) -> str:
        row = latest.get((model, part))
        if not row:
            return '<td class="na">–</td>'
        pct = int(row["percent"])
        cls = "good" if pct >= 95 else "ok" if pct >= 85 else "bad"
        note = ""
        if int(row["total"]) != totals[part]:
            note = f' <span class="small">({row["run"]})</span>'
        return (
            f'<td class="{cls}"><b>{row["score"]}/{row["total"]}</b>{note}'
            f'<br><span class="small">{float(row["avg_s"]):.2f} s</span></td>'
        )

    def overall(model: str) -> tuple[int, float]:
        """Models with the full test first (more parts on the largest set)."""
        rows = [latest[(model, p)] for p in PARTS if (model, p) in latest and p != "router"]
        full = sum(int(r["total"]) == totals[r["part"]] for r in rows)
        return full, sum(int(r["percent"]) for r in rows) / len(rows) if rows else -1

    order = sorted(models, key=overall, reverse=True)
    size = {m: next((r["size_gb"] for r in summary if r["model"] == m and r["size_gb"]), "")
            for m in models}  # fmt: skip
    head = "".join(f"<th>{html.escape(PARTS[p])}</th>" for p in PARTS)
    body = "".join(
        f"<tr><th class='model'>{html.escape(short(m))}"
        f"<br><span class='small'>{size[m]} GB</span></th>"
        + "".join(cell(m, p) for p in PARTS)
        + "</tr>"
        for m in order
    )
    # mistakes from the same run as the result in the table
    mistakes: dict[str, list[dict]] = {}
    for row in answers:
        shown = latest.get((row["model"], row["part"]))
        same_run = shown and (row["run"], row["date"]) == (shown["run"], shown["date"])
        if row["ok"] == "0" and same_run:
            mistakes.setdefault(row["model"], []).append(row)
    errors_html = "".join(
        f"<details><summary>{html.escape(short(m))} – {len(rows)} mistakes</summary><ul>"
        + "".join(
            f"<li><b>{html.escape(PARTS.get(r['part'], r['part']))}"
            f"{' / ' + html.escape(r['case']) if r['case'] else ''}</b>: "
            f"{html.escape(r['answer'])}<br><span class='small'>{html.escape(r['problems'])}"
            "</span></li>"
            for r in rows
        )
        + "</ul></details>"
        for m, rows in sorted(mistakes.items(), key=lambda kv: len(kv[1]))
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Model results</title>
<style>
:root {{ --bg:#fafaf9; --fg:#1c1917; --muted:#78716c; --line:#e7e5e4; --card:#fff;
  --good:#dcfce7; --ok:#fef9c3; --bad:#fee2e2; --na:#f5f5f4; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#1c1917; --fg:#f5f5f4; --muted:#a8a29e;
  --line:#44403c; --card:#292524; --good:#14532d; --ok:#713f12; --bad:#7f1d1d; --na:#292524; }} }}
body {{ background:var(--bg); color:var(--fg); font:15px/1.5 system-ui,sans-serif;
  margin:0 auto; max-width:1100px; padding:24px 16px; }}
h1 {{ margin:0 0 4px; }} .lead {{ color:var(--muted); margin:0 0 20px; }}
.wrap {{ overflow-x:auto; }}
table {{ border-collapse:collapse; width:100%; background:var(--card); }}
th,td {{ border:1px solid var(--line); padding:8px 10px; text-align:center;
  vertical-align:middle; }}
th.model {{ text-align:left; white-space:nowrap; }}
td.good {{ background:var(--good); }} td.ok {{ background:var(--ok); }}
td.bad {{ background:var(--bad); }} td.na {{ background:var(--na); color:var(--muted); }}
.small {{ color:var(--muted); font-size:12px; font-weight:normal; }}
details {{ background:var(--card); border:1px solid var(--line); border-radius:8px;
  padding:8px 12px; margin:8px 0; }} summary {{ cursor:pointer; font-weight:600; }}
li {{ margin:6px 0; }} .notes {{ background:var(--card); border:1px solid var(--line);
  border-radius:8px; padding:4px 16px; margin:20px 0; }}
</style></head><body>
<h1>Model results for Assist Router</h1>
<p class="lead">Generated {datetime.now().strftime("%Y-%m-%d %H:%M")}. Latest result of every
model in every test part; cell: correct / total and the average time of one answer.
Colour: green ≥ 95%, yellow ≥ 85%, red below. A note in brackets = result from a smaller set
(earlier run). Order: models with the full test first, then the average of the answer parts.</p>
<div class="wrap"><table><thead><tr><th>Model<br><span class="small">file size</span></th>
{head}</tr></thead><tbody>{body}</tbody></table></div>
<div class="notes">{notes}</div>
<h2>Mistakes</h2>{errors_html}
</body></html>"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("results", nargs="*", type=Path, help="JSON files from model_benchmark.py")
    parser.add_argument("--label", action="append", default=[], help="run name (in order)")
    parser.add_argument("--ollama", help="Ollama URL - model file sizes")
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--answers-csv", type=Path, required=True)
    parser.add_argument("--html", type=Path, required=True)
    parser.add_argument("--notes", type=Path, help="HTML fragment with conclusions")
    args = parser.parse_args()

    sizes = file_sizes(args.ollama)
    date = datetime.now().strftime("%Y-%m-%d %H:%M")
    for index, path in enumerate(args.results):
        run = args.label[index] if index < len(args.label) else path.stem
        summary, answers = rows_from_results(json.loads(path.read_text()), run, date, sizes)
        append_csv(args.csv, SUMMARY_COLUMNS, summary)
        append_csv(args.answers_csv, ANSWER_COLUMNS, answers)
    notes = args.notes.read_text(encoding="utf-8") if args.notes else ""
    args.html.write_text(
        render_html(read_csv(args.csv), read_csv(args.answers_csv), notes), encoding="utf-8"
    )
    print(f"HTML: {args.html}\nCSV: {args.csv}, {args.answers_csv}")


if __name__ == "__main__":
    main()
