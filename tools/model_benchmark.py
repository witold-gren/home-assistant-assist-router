"""Ollama model comparison for Assist Router: router (topic) and answers from data.

The router gets exactly the same prompt and schema as the integration (router.py), so the
result translates 1:1 to behaviour in HA. Answers are scored automatically (required and
forbidden fragments, length) - the cases live in a YAML file outside the repository.

Models are tested one after another: load, measure, free memory - so they do not fight
over the GPU. A missing model is downloaded (--pull).

    .venv/bin/python tools/model_benchmark.py \\
        --ollama http://localhost:11434 \\
        --router-config /config/assist/router.yaml --cases /config/assist/model_test.yaml \\
        --data /config/assist/model_test_data.yaml \\
        --router qwen3.5:2b gemma4:e2b --answer qwen3.5:9b gemma4:12b --pull \\
        --out results.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
import time
from typing import Any
import urllib.error
import urllib.request

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from custom_components.assist_router.const import ANSWER_NUM_CTX
from custom_components.assist_router.control import (
    CERTAIN,
    build_control_prompt,
    build_control_schema,
    find_target,
    home_from_dict,
    is_bare_answer,
    kind_guessed,
    named_routine,
    normalize_action,
    parse_command,
    prepare_text,
)
from custom_components.assist_router.languages import LANG
from custom_components.assist_router.router import (
    OllamaSettings,
    build_request,
    parse_config,
    parse_route,
)


def call(url: str, path: str, body: dict[str, Any], timeout: float = 600) -> dict[str, Any]:
    request = urllib.request.Request(
        f"{url}{path}", json.dumps(body).encode(), {"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=timeout) as resp:
        return json.loads(resp.read() or b"{}")


def chat(url: str, body: dict[str, Any]) -> tuple[dict[str, Any], float]:
    """Chat without "thinking" (Qwen, Gemma); models lacking that option get a plain request."""
    started = time.monotonic()
    try:
        result = call(url, "/api/chat", {**body, "think": False})
    except urllib.error.HTTPError as err:
        if err.code != 400:
            raise
        result = call(url, "/api/chat", body)
    return result, time.monotonic() - started


def installed(url: str) -> set[str]:
    with urllib.request.urlopen(f"{url}/api/tags", timeout=30) as resp:
        return {m["name"] for m in json.load(resp)["models"]}


def prepare(url: str, model: str, pull: bool) -> float | None:
    """Download (optionally) and load a model; returns the load time or None."""
    if model not in installed(url):
        if not pull:
            print(f"!! {model}: not in Ollama (use --pull)")
            return None
        print(f".. pulling {model}")
        try:
            call(url, "/api/pull", {"model": model, "stream": False}, timeout=7200)
        except urllib.error.HTTPError as err:
            print(f"!! {model}: pull failed ({err.code} {err.read().decode()[:200]})")
            return None
    started = time.monotonic()
    call(url, "/api/generate", {"model": model, "keep_alive": "10m", "options": {"num_ctx": 4096}})
    return time.monotonic() - started


def unload(url: str, model: str) -> None:
    call(url, "/api/generate", {"model": model, "keep_alive": 0})


def loaded(url: str) -> set[str]:
    with urllib.request.urlopen(f"{url}/api/ps", timeout=30) as resp:
        return {m["name"] for m in json.load(resp)["models"]}


def loaded_context(url: str, model: str) -> int:
    with urllib.request.urlopen(f"{url}/api/ps", timeout=30) as resp:
        for m in json.load(resp)["models"]:
            if m["name"] == model:
                return int(m.get("context_length") or 4096)
    return 4096


def size_gb(url: str, model: str) -> float | None:
    with urllib.request.urlopen(f"{url}/api/ps", timeout=30) as resp:
        for m in json.load(resp)["models"]:
            if m["name"] == model:
                return round(m["size_vram"] / 1e9, 1)
    return None


def run_router(
    url: str, model: str, config, cases: list[list[str]], num_ctx: int = 4096
) -> dict[str, Any]:
    # context of a model already loaded (e.g. by HA) - no reload in Ollama
    ollama = OllamaSettings(url=url, model=model, timeout=60, keep_alive=10, num_ctx=num_ctx)
    good, times, errors = 0, [], []
    for question, expected in cases:
        body = build_request(ollama, config, question)
        body["keep_alive"] = "10m"
        result, elapsed = chat(url, body)
        times.append(elapsed)
        route = parse_route(config, result.get("message", {}).get("content", ""), question)
        got = route.topic if route else "(bad JSON)"
        if got == expected:
            good += 1
        else:
            errors.append(f"{question} -> {got} (expected {expected})")
    return {"score": good, "total": len(cases), "avg_s": sum(times) / len(times), "errors": errors}


def sentences(text: str) -> int:
    return len([s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s])


def check(answer: str, case: dict[str, Any], min_sentences: int, max_sentences: int) -> list[str]:
    """List of problems with the answer (empty = good)."""
    problems = []
    low = answer.lower()
    for item in case.get("must", []):
        options = item if isinstance(item, list) else [item]
        if not any(re.search(o, low) for o in options):
            problems.append(f"missing: {' / '.join(options)}")
    for item in case.get("never", []):
        if re.search(item, low):
            problems.append(f"forbidden: {item}")
    count = sentences(answer)
    if count > max_sentences:
        problems.append(f"too long: {count} sentences")
    elif count < min_sentences:
        problems.append(f"too short: {count} sentences")
    return problems


def case_data(case: dict[str, Any], snapshot: dict[str, Any]) -> str:
    """Case data: given directly (data) or from the snapshot (source: key or list)."""
    if "data" in case:
        return case["data"]
    keys = case["source"] if isinstance(case["source"], list) else [case["source"]]
    return "\n".join(snapshot[key]["text"] for key in keys)


def run_answers(
    url: str, model: str, spec: dict[str, Any], snapshot: dict[str, Any]
) -> dict[str, Any]:
    good, times, details = 0, [], []
    max_sentences = spec.get("max_sentences", 3)
    for case in spec["cases"]:
        body = {
            "model": model,
            "stream": False,
            "keep_alive": "10m",
            # same context as the integration - otherwise Ollama reloads the model HA is using
            "options": {
                "temperature": 0.2,
                "num_predict": 60 * max_sentences,
                "num_ctx": ANSWER_NUM_CTX,
            },
            "messages": [
                {
                    "role": "system",
                    "content": f"{spec['system']}\nDane:\n{case_data(case, snapshot)}",
                },
                {"role": "user", "content": case["question"]},
            ],
        }
        result, elapsed = chat(url, body)
        times.append(elapsed)
        answer = " ".join(result.get("message", {}).get("content", "").split())
        problems = check(answer, case, spec.get("min_sentences", 1), max_sentences)
        good += not problems
        details.append(
            {"case": case["name"], "s": round(elapsed, 1), "answer": answer, "problems": problems}
        )
    return {
        "score": good,
        "total": len(spec["cases"]),
        "avg_s": sum(times) / len(times),
        "details": details,
    }


def rescore(results: dict[str, Any], spec: dict[str, Any]) -> None:
    """Re-score saved answers against the current cases (matched by name)."""
    for model, entry in results.items():
        for section in SECTIONS:
            if section not in entry or section not in spec:
                continue
            cases = {case["name"]: case for case in spec[section]["cases"]}
            limits = (spec[section].get("min_sentences", 1), spec[section].get("max_sentences", 3))
            good = 0
            for detail in entry[section]["details"]:
                if case := cases.get(detail["case"]):
                    detail["problems"] = check(detail["answer"], case, *limits)
                good += not detail["problems"]
            before = entry[section]["score"]
            entry[section]["score"] = good
            print(f"{model} {section}: {before} -> {good}/{entry[section]['total']}")


def run_control(
    url: str, model: str, spec: dict[str, Any], home_data: dict, num_ctx: int = 4096
) -> dict[str, Any]:
    """Control decision as in the integration (nothing is executed): alarm guard, bare yes/no
    answer, script name without the model, and only then parsing by the model with the action
    list (scripts with descriptions, scenes) - intent, domain, area, device, whether to ask.

    ``expect`` in the cases file uses the keys of ``got`` (intent, domain, area, device...);
    the Polish keys of older cases files are accepted too (``LEGACY_EXPECT_KEYS``)."""
    home = home_from_dict(home_data)
    system = build_control_prompt(home, spec.get("household", ""), home_data.get("actions"))
    schema = build_control_schema(home)
    good, times, details = 0, [], []
    for case in spec["cases"]:
        text, doubts = prepare_text(case["text"])
        got: dict[str, Any] = {}
        elapsed = 0.0
        routine = named_routine(home, text)
        if LANG.ALARM_WORDS.search(text):
            got = {"alarm": True}
        elif is_bare_answer(text):
            got = {"answer": True}
        elif routine is not None:
            got = {"intent": "HassTurnOn", "domain": routine.domain,
                   "device": routine.name, "without_model": True, "confirm": False}  # fmt: skip
        else:
            body = {
                "model": model,
                "stream": False,
                "keep_alive": "10m",
                "format": schema,
                "options": {"temperature": 0, "num_predict": 160, "num_ctx": num_ctx},
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": text},
                ],
            }
            result, elapsed = chat(url, body)
            command = parse_command(home, result.get("message", {}).get("content", ""))
            if command:
                match = find_target(home, command, text)
                normalize_action(command, match)
                got = {
                    "intent": command.intent,
                    "domain": command.domain,
                    "area": command.area,
                    "floor": command.floor,
                    "device": match.target.name if match and match.target else None,
                    "all": command.all,
                    "value": command.value,
                    "change": command.change,
                    "item": command.item,
                    "color": command.color,
                    "white": command.white,
                    "query": command.query,
                    "media_class": command.media_class,
                    "artist": command.artist,
                    "radio": command.radio,
                    "confirm": bool(
                        doubts
                        or (match and (match.ambiguous or match.score < CERTAIN))
                        or kind_guessed(command, match, text)
                    ),
                }
        times.append(elapsed)
        problems = []
        for key, expected in case["expect"].items():
            value = got.get(LEGACY_EXPECT_KEYS.get(key, key))
            if isinstance(expected, str) and isinstance(value, str):
                ok = expected.lower() in value.lower()
            elif isinstance(expected, (int, float)) and isinstance(value, (int, float)):
                ok = abs(expected - value) < 0.01
            else:
                ok = expected == value
            if not ok:
                problems.append(f"{key}: {value!r} (expected {expected!r})")
        good += not problems
        details.append(
            {
                "case": case["text"],
                "s": round(elapsed, 1),
                "answer": json.dumps(got, ensure_ascii=False),
                "problems": problems,
            }
        )
    return {
        "score": good,
        "total": len(spec["cases"]),
        "avg_s": sum(times) / len(times),
        "details": details,
    }


# Polish keys of `expect` in cases files written before 0.1.0 -> keys of the results
LEGACY_EXPECT_KEYS = {
    "intencja": "intent", "domena": "domain", "obszar": "area", "pietro": "floor",
    "urzadzenie": "device", "wszystkie": "all", "wartosc": "value", "zmiana": "change",
    "element": "item", "kolor": "color", "barwa": "white", "szukaj": "query",
    "rodzaj": "media_class", "wykonawca": "artist", "pytanie": "confirm",
    "odpowiedz": "answer", "bez_modelu": "without_model",
}  # fmt: skip

# cases file section -> (label in the output, snapshot part with the data)
SECTIONS = {
    "answers": ("answers (given data)", None),
    "real": ("answers (data from HA)", "sources"),
    "wiki_answers": ("Wikipedia summaries", "wiki"),
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--ollama", default="http://localhost:11434")
    parser.add_argument("--router-config", type=Path, required=True)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--data", type=Path, help="snapshot from tools/snapshot_data.py")
    parser.add_argument(
        "--sections",
        nargs="*",
        default=[*SECTIONS, "control"],
        help="which parts to test: " + ", ".join([*SECTIONS, "control"]),
    )
    parser.add_argument("--router", nargs="*", default=[], help="models for the router test")
    parser.add_argument("--answer", nargs="*", default=[], help="models for the answer test")
    parser.add_argument("--pull", action="store_true", help="pull missing models")
    parser.add_argument("--out", type=Path, help="JSON results (appended)")
    parser.add_argument(
        "--rescore",
        action="store_true",
        help="no models: re-score the answers saved in --out (after fixing the cases)",
    )
    args = parser.parse_args()

    url = args.ollama.rstrip("/")
    config = parse_config(yaml.safe_load(args.router_config.read_text(encoding="utf-8")))
    spec = yaml.safe_load(args.cases.read_text(encoding="utf-8"))
    data = yaml.safe_load(args.data.read_text(encoding="utf-8")) if args.data else {}
    results: dict[str, Any] = {}
    if args.out and args.out.exists():
        results = json.loads(args.out.read_text())

    if args.rescore:
        rescore(results, spec)
        if args.out:
            args.out.write_text(json.dumps(results, ensure_ascii=False, indent=1))
        return

    ctx: dict[str, int] = {}
    for model in dict.fromkeys(args.router + args.answer):
        # a model that was already in memory (e.g. the HA agent with keep_alive -1) stays there
        keep = model in loaded(url)
        if keep:
            # already in memory (e.g. for HA) - no reload with a different context
            ctx[model] = loaded_context(url, model)
            load = 0.0
        else:
            load = prepare(url, model, args.pull)
        if load is None:
            continue
        entry = results.setdefault(model, {})
        entry.update(load_s=round(load, 1), vram_gb=size_gb(url, model))
        print(f"== {model}  (load {load:.1f} s, {entry['vram_gb']} GB)")
        if model in args.router:
            entry["router"] = r = run_router(
                url, model, config, spec["router"], ctx.get(model, 4096)
            )
            print(f"   router: {r['score']}/{r['total']}  avg {r['avg_s']:.2f} s")
            for error in r["errors"]:
                print(f"     - {error}")
        if model in args.answer and "control" in args.sections and "control" in spec:
            if "home" not in data:
                print("   control: skipped (no home snapshot in --data)")
            else:
                # context as in the integration for the answer model (no reload in Ollama)
                entry["control"] = c = run_control(
                    url, model, spec["control"], data["home"], spec["control"].get("num_ctx", 4096)
                )
                print(f"   control: {c['score']}/{c['total']}  avg {c['avg_s']:.2f} s")
                for d in c["details"]:
                    if d["problems"]:
                        print(f"     -- {d['case']}: {'; '.join(d['problems'])}")
        for section, (label, snapshot_key) in SECTIONS.items():
            if model not in args.answer or section not in args.sections or section not in spec:
                continue
            if snapshot_key and snapshot_key not in data:
                print(f"   {label}: skipped (no --data)")
                continue
            snapshot = data.get(snapshot_key, {}) if snapshot_key else {}
            entry[section] = a = run_answers(url, model, spec[section], snapshot)
            print(f"   {label}: {a['score']}/{a['total']}  avg {a['avg_s']:.2f} s")
            for d in a["details"]:
                mark = "OK" if not d["problems"] else "--"
                print(f"     {mark} [{d['s']:4.1f}s] {d['case']}: {d['answer']}")
                for problem in d["problems"]:
                    print(f"          ! {problem}")
        if not keep:
            unload(url, model)
        else:
            # a model in everyday use (e.g. by HA): back in memory permanently,
            # with the same context it was loaded with before the test
            call(
                url,
                "/api/generate",
                {"model": model, "keep_alive": -1, "options": {"num_ctx": ctx[model]}},
            )
        if args.out:
            args.out.write_text(json.dumps(results, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
