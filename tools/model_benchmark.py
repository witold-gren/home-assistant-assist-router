"""Ollama model comparison for Assist Router: router (topic) and answers from data.

The router gets exactly the same prompt and schema as the integration (router.py), so the
result translates 1:1 to behaviour in HA. Answers are scored automatically (required and
forbidden fragments, length) - the cases live in a YAML file outside the repository.

A section without its own ``system`` prompt uses the integration's prompts: answers from
topic data (``live`` in the snapshot) go through ``answer_messages`` with the speaker, the
hint and the topic's token limit, Wikipedia cases (``prompt: summary``) through
``summary_messages``.

Models are tested one after another: load, measure, free memory - so they do not fight
over the GPU. A missing model is downloaded (--pull), the next one already in the background
while the current one is tested; --delete-after removes downloaded models again (models that
were installed before the start are never removed) and --resume skips models that already
have all parts in --out.

    .venv/bin/python tools/model_benchmark.py \\
        --ollama http://localhost:11434 \\
        --router-config /config/assist/router.yaml --cases /config/assist/model_test.yaml \\
        --data /config/assist/model_test_data.yaml \\
        --router qwen3.5:2b gemma4:e2b --answer qwen3.5:9b gemma4:12b --pull \\
        --delete-after --resume --out results.json
"""

from __future__ import annotations

import argparse
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime
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
    music_intent,
    named_routine,
    normalize_action,
    parse_command,
    prepare_text,
)
from custom_components.assist_router.languages import LANG
from custom_components.assist_router.router import (
    OllamaSettings,
    RouterConfig,
    answer_messages,
    build_request,
    parse_config,
    parse_route,
    summary_messages,
)

# as in conversation.py (not imported: it pulls in the whole conversation component)
ANSWER_TOKENS = 160
SUMMARY_TOKENS_PER_SENTENCE = 70
# a dropped connection (Ollama runner crash or restart) is retried after a pause
CHAT_RETRIES = 2
RETRY_PAUSE_S = 10


def call(
    url: str, path: str, body: dict[str, Any], timeout: float = 600, method: str = "POST"
) -> dict[str, Any]:
    request = urllib.request.Request(
        f"{url}{path}", json.dumps(body).encode(), {"Content-Type": "application/json"},
        method=method,
    )  # fmt: skip
    with urllib.request.urlopen(request, timeout=timeout) as resp:
        return json.loads(resp.read() or b"{}")


def chat(url: str, body: dict[str, Any]) -> tuple[dict[str, Any], float]:
    """Chat without "thinking" (Qwen, Gemma); models lacking that option get a plain request.

    A dropped connection is retried (CHAT_RETRIES), so one failure does not stop a run of
    many hours; only the successful attempt is timed.
    """
    for attempt in range(CHAT_RETRIES + 1):
        started = time.monotonic()
        try:
            try:
                result = call(url, "/api/chat", {**body, "think": False})
            except urllib.error.HTTPError as err:
                if err.code != 400:
                    raise
                result = call(url, "/api/chat", body)
            return result, time.monotonic() - started
        except urllib.error.HTTPError:
            raise
        except (ConnectionError, TimeoutError, urllib.error.URLError) as err:
            if attempt == CHAT_RETRIES:
                raise
            print(f"!! {body.get('model')}: {err} - retry in {RETRY_PAUSE_S} s", flush=True)
            time.sleep(RETRY_PAUSE_S)
    raise AssertionError("unreachable")


def installed(url: str) -> set[str]:
    with urllib.request.urlopen(f"{url}/api/tags", timeout=30) as resp:
        return {m["name"] for m in json.load(resp)["models"]}


def pull_model(url: str, model: str) -> bool:
    """Download a model into Ollama; False when the download failed."""
    print(f".. pulling {model}", flush=True)
    try:
        call(url, "/api/pull", {"model": model, "stream": False}, timeout=7200)
    except (urllib.error.URLError, TimeoutError) as err:
        detail = err.read().decode()[:200] if isinstance(err, urllib.error.HTTPError) else err
        print(f"!! {model}: pull failed ({detail})", flush=True)
        return False
    return True


def delete_model(url: str, model: str) -> None:
    call(url, "/api/delete", {"model": model}, method="DELETE")
    print(f".. deleted {model}", flush=True)


def removable(model: str, before: set[str], keep: set[str]) -> bool:
    """Only models downloaded by this run may be deleted - never ones installed before it."""
    return model not in before and model not in keep


def missing_parts(entry: dict[str, Any], wanted: list[str]) -> list[str]:
    """Parts (router, control, answers...) a model has no result for yet (--resume)."""
    return [part for part in wanted if part not in entry]


def prepare(url: str, model: str, pull: bool) -> float | None:
    """Download (optionally) and load a model; returns the load time or None."""
    if model not in installed(url):
        if not pull:
            print(f"!! {model}: not in Ollama (use --pull)")
            return None
        if not pull_model(url, model):
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


def file_size_gb(url: str, model: str) -> float | None:
    """Size of the model file (stored in the results: --delete-after removes the model)."""
    with urllib.request.urlopen(f"{url}/api/tags", timeout=30) as resp:
        for m in json.load(resp)["models"]:
            if m["name"] == model:
                return round(m["size"] / 1e9, 1)
    return None


def size_gb(url: str, model: str) -> float | None:
    with urllib.request.urlopen(f"{url}/api/ps", timeout=30) as resp:
        for m in json.load(resp)["models"]:
            if m["name"] == model:
                return round(m["size_vram"] / 1e9, 1)
    return None


def topic_ok(got: str, expected: str | list[str]) -> bool:
    """A router case: one topic or a list of equally good ones (an ambiguous question)."""
    return got in expected if isinstance(expected, list) else got == expected


def run_router(
    url: str, model: str, config, cases: list[list[Any]], num_ctx: int = 4096
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
        if topic_ok(got, expected):
            good += 1
        else:
            shown = " / ".join(expected) if isinstance(expected, list) else expected
            errors.append(f"{question} -> {got} (expected {shown})")
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
    """Case data: given directly (data), topic data from the snapshot (topic: ``live`` entry
    of the same name) or snapshot sources (source: key or list)."""
    if "data" in case:
        return case["data"]
    if "topic" in case:
        return snapshot[case["name"]]["data"]
    keys = case["source"] if isinstance(case["source"], list) else [case["source"]]
    return "\n".join(snapshot[key]["text"] for key in keys)


def limits(case: dict[str, Any], spec: dict[str, Any]) -> tuple[int, int]:
    """Allowed answer length in sentences - per case or for the whole section."""
    return (
        case.get("min_sentences", spec.get("min_sentences", 1)),
        case.get("max_sentences", spec.get("max_sentences", 3)),
    )


def answer_request(
    case: dict[str, Any],
    spec: dict[str, Any],
    snapshot: dict[str, Any],
    config: RouterConfig | None,
    now: datetime | None,
) -> tuple[list[dict[str, str]], int]:
    """Messages and token limit: the section's own ``system`` prompt or - without it - the
    integration's prompts, as in HA (topic data or a Wikipedia summary)."""
    data = case_data(case, snapshot)
    if "system" in spec:
        messages = [
            {"role": "system", "content": f"{spec['system']}\n{LANG.DATA_HEADER}\n{data}"},
            {"role": "user", "content": case["question"]},
        ]
        return messages, 60 * limits(case, spec)[1]
    if config is None:
        raise ValueError("integration prompts need the router config")
    if spec.get("prompt") == "summary":
        tokens = SUMMARY_TOKENS_PER_SENTENCE * config.sentences
        return summary_messages(config, data, case["question"]), tokens
    entry = snapshot[case["name"]]
    if now is None:
        raise ValueError("topic data need the snapshot time (now)")
    messages = answer_messages(
        config, now, data, case["question"], entry.get("speaker"), entry.get("hint") or ""
    )
    return messages, config.topics[entry["topic"]].answer_tokens or ANSWER_TOKENS


def run_answers(
    url: str,
    model: str,
    spec: dict[str, Any],
    snapshot: dict[str, Any],
    config: RouterConfig | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    good, times, details = 0, [], []
    for case in spec["cases"]:
        messages, tokens = answer_request(case, spec, snapshot, config, now)
        body = {
            "model": model,
            "stream": False,
            "keep_alive": "10m",
            # same context as the integration - otherwise Ollama reloads the model HA is using
            "options": {"temperature": 0.2, "num_predict": tokens, "num_ctx": ANSWER_NUM_CTX},
            "messages": messages,
        }
        result, elapsed = chat(url, body)
        times.append(elapsed)
        answer = " ".join(result.get("message", {}).get("content", "").split())
        problems = check(answer, case, *limits(case, spec))
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
            good = 0
            for detail in entry[section]["details"]:
                if case := cases.get(detail["case"]):
                    detail["problems"] = check(detail["answer"], case, *limits(case, spec[section]))
                good += not detail["problems"]
            before = entry[section]["score"]
            entry[section]["score"] = good
            print(f"{model} {section}: {before} -> {good}/{entry[section]['total']}")


def expect_ok(expected: Any, value: Any) -> bool:
    """One ``expect`` field of a control case: text = fragment (case-insensitive), number =
    the same number, a list = any of its values."""
    if isinstance(expected, list):
        return any(expect_ok(option, value) for option in expected)
    if isinstance(expected, bool):
        return value is expected  # True == 1 in Python
    if isinstance(expected, str) and isinstance(value, str):
        return expected.lower() in value.lower()
    if isinstance(expected, (int, float)):
        return isinstance(value, (int, float)) and abs(expected - value) < 0.01
    return expected == value


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
                # as plan_command in HA: „wyłącz muzykę” pauses, „włącz muzykę” resumes
                music_intent(command, text)
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
            if not expect_ok(expected, value):
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


def snapshot_part(section: str, spec: dict[str, Any], data: dict[str, Any]) -> str | None:
    """Snapshot part with the section's data: topic cases read ``live``, the rest as in
    SECTIONS; None = the section needs no snapshot."""
    if any("topic" in case for case in spec.get("cases", [])):
        return "live"
    return SECTIONS[section][1]


def wanted_parts(
    model: str, args: argparse.Namespace, spec: dict[str, Any], data: dict[str, Any]
) -> list[str]:
    """Parts this run tests for the model (for --resume)."""
    parts = ["router"] if model in args.router and "router" in spec else []
    if model in args.answer:
        if "control" in args.sections and "control" in spec and "home" in data:
            parts.append("control")
        for section in SECTIONS:
            if section not in args.sections or section not in spec:
                continue
            key = snapshot_part(section, spec[section], data)
            if not key or key in data:
                parts.append(section)
    return parts


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
    parser.add_argument(
        "--delete-after",
        action="store_true",
        help="delete models this run downloaded once they are tested",
    )
    parser.add_argument(
        "--keep", nargs="*", default=[], help="models never deleted (besides those installed)"
    )
    parser.add_argument(
        "--resume", action="store_true", help="skip models that have all parts in --out"
    )
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
    now = datetime.fromisoformat(data["now"]) if data.get("now") else None
    results: dict[str, Any] = {}
    if args.out and args.out.exists():
        results = json.loads(args.out.read_text())

    if args.rescore:
        rescore(results, spec)
        if args.out:
            args.out.write_text(json.dumps(results, ensure_ascii=False, indent=1))
        return

    models = list(dict.fromkeys(args.router + args.answer))
    if args.resume:
        done = [
            m
            for m in models
            if not missing_parts(results.get(m, {}), wanted_parts(m, args, spec, data))
        ]
        for model in done:
            print(f"== {model}: done earlier, skipped (--resume)")
        models = [m for m in models if m not in done]
    before = installed(url)
    keep_models = set(args.keep)
    # the next model downloads in the background while the current one is tested
    downloads = ThreadPoolExecutor(max_workers=1)
    pending: dict[str, Future] = {}

    def prefetch(model: str) -> None:
        if args.pull and model not in before and model not in pending:
            pending[model] = downloads.submit(pull_model, url, model)

    ctx: dict[str, int] = {}
    for index, model in enumerate(models):
        if model in pending and not pending.pop(model).result():
            continue  # download failed (reported)
        if index + 1 < len(models):
            prefetch(models[index + 1])
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
        entry.update(
            load_s=round(load, 1),
            vram_gb=size_gb(url, model),
            size_gb=file_size_gb(url, model),
        )
        print(f"== {model}  (load {load:.1f} s, {entry['vram_gb']} GB)", flush=True)
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
        for section, (label, _) in SECTIONS.items():
            if model not in args.answer or section not in args.sections or section not in spec:
                continue
            snapshot_key = snapshot_part(section, spec[section], data)
            if snapshot_key and snapshot_key not in data:
                print(f"   {label}: skipped (no --data)")
                continue
            snapshot = data.get(snapshot_key, {}) if snapshot_key else {}
            entry[section] = a = run_answers(url, model, spec[section], snapshot, config, now)
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
        if args.delete_after and not keep and removable(model, before, keep_models):
            delete_model(url, model)
        sys.stdout.flush()
    downloads.shutdown()


if __name__ == "__main__":
    main()
