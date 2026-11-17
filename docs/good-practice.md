# Doing it well

This page collects good practice and every setting with its default value from the integration's code. Each
field is described in [The router.yaml file](router-yaml.md#router), and the way of working step by step in
[The editor step by step](editor.md).

## Rules {#rules}

- **Start from what the household already asked.** Build new topics from the [log of unrecognized commands](#log)
  (in the editor <b class="ui">Learning</b> → <b class="ui">Unrecognized sentences</b>), not from made-up questions.
- **Topic descriptions must not overlap.** `description` holds the words and phrases the router picks a topic by.
  Two topics with similar descriptions are the most common reason for a wrong choice.
- **2–4 real examples per topic**, especially phrasings on the border between two topics.
- **Point at data narrowly.** Entity patterns in order of importance (at most 80 entities go to the model),
  `!pattern` excludes what is not needed, `drop` skips attribute keys. Less data means a faster, surer answer.
- **`details` and `fetch` instead of `command`.** The legacy `command` field needs a separate Assist automation;
  data from entities and services needs nothing more.
- **Check every change with the tester and the test set** before saving (<b class="ui">Tester</b>,
  <b class="ui">Test set</b>). A sentence that once went wrong belongs in the tests.
- **After changing a model, repeat the [model test](#testing).** The results in the
  [Language model comparison](models.md) are from the test home; in yours, your own test set counts.

## Integration options: defaults {#integration-defaults}

Settings → Devices & services → Assist Router → Configure (field names as in Home Assistant).

| Option | Default | What it changes |
| --- | --- | --- |
| <b class="ui">Ollama URL (question router)</b> | none | Without it the router is off; the HA agent and the fallback agent remain. |
| <b class="ui">Router model</b> | none | The small model that picks the topic; it has to answer quickly (about 0.5 s). |
| <b class="ui">Router timeout</b> | 8 s | How long to wait for the topic. Too short: a slow model does not make it. |
| <b class="ui">Keep model in memory</b> | -1 (always) | Minutes Ollama keeps the model. Less frees memory, but the first question after that waits for the model to load. |
| <b class="ui">Answer model</b> | none | Writes answers from the home's data and Wikipedia summaries. Without it questions about data go to the fallback agent, and from Wikipedia the beginning of the article is read. |
| <b class="ui">Answer timeout</b> | 15 s | How long to wait for the answer model (also for Wikipedia). |
| <b class="ui">Fallback conversation agent</b> | none | The conversation agent for questions without data (chit-chat, jokes). |
| <b class="ui">Fallback answer timeout</b> | 30 s | After this the assistant stops waiting for the fallback agent. |
| <b class="ui">Log unrecognized commands</b> | on | Writes `/config/assist/unrecognized_commands.csv` and fires `assist_router_unrecognized`. |
| <b class="ui">Show the editor in the sidebar</b> | on | Off hides the panel; the editor still opens at `/assist-router-editor`. |

The context of the models in Ollama is fixed: the router 4096, the answer model 8192 tokens. An Ollama
conversation agent in HA with the same model as the answer model should have the same context, otherwise Ollama
loads the model again.

## router.yaml: top-level fields {#file-defaults}

| Field | Default | What it changes |
| --- | --- | --- |
| `language` | HA's language if there is a pack for it, otherwise `pl` | The language pack: words, prompts, day names. |
| `household` | empty | Who lives in the home; goes into the prompts of the router and the answer model. |
| `people` | no people | People in questions. `name` = the key, `match` = the first 4 letters of the name, `speaker` = the key. |
| `family` | none | Parents and children: who sees whose data in `personal` topics. |
| `sentences` | 4 | Sentences in a Wikipedia summary. |
| `wikipedia_language` | from the pack (`pl`) | The Wikipedia the articles come from. |
| `answer_prompt`, `summary_prompt` | the pack's prompts | Your own prompt for answers and summaries. |
| `only_exposed` | `false` | `true`: topic entities only from those exposed to Assist. |
| `control_model` | `router` | Which model parses control commands: `router` or `answer`. |
| `confirm_entities` | none | Devices the assistant always asks about (locks, gates and garage doors it always asks about anyway). |
| `music_players` | none | "Play …": room → players, the first available one. |
| `announce_players` | none | Speakers for announcements instead of the satellite. |
| `personas` | none | The assistant's character per pipeline (prompt, gender, pipelines or voices). |

## Topic fields: defaults {#topic-defaults}

| Field | Default | What it changes |
| --- | --- | --- |
| `entities` | none | Entity states; at most 80, in pattern order. |
| `unavailable` | `false` | `true`: unavailable entities go into the data as "unavailable" instead of being skipped. |
| `only_exposed` | the top-level field | Overrides `only_exposed` for this topic. |
| `details` | none | Entity attributes, trimmed to the person and the day in the question. |
| `fetch` → `limit` | 40 | Most items from one service; one source is at most 6000 characters, a service gets 10 s. |
| `frigate` | `labels: person`, `days: 7`, `limit: 30`, `summaries: 10`, `gap: 120` | How many days back, how many visits and summaries, how many seconds still join events into one visit. |
| `days` | none | The day when the question gives none. |
| `answer_tokens` | 0 = 160 tokens | A longer answer, e.g. 360 for a daily summary. |
| `personal`, `verbatim`, `control`, `unclear` | `false` | See [Topic fields](router-yaml.md#topic-fields). |

Control: a command for 8 or more devices at once without "all" or "whole" is confirmed first; "brighter" and
"higher" change by 25%, "warmer" by 1°; a confirmation question waits 30 s.

## Log of unrecognized commands {#log}

`/config/assist/unrecognized_commands.csv` (UTF-8, separator `;`)
opens in Numbers and Excel. Columns:

| Column | Content |
| --- | --- |
| `timestamp`, `area`, `device` | when and on which speaker |
| `kind` | `no_intent_match` (HA recognized nothing) or `no_valid_targets` (it recognized a command for a non-existent area or device, e.g. “…at school”) |
| `text` | what Whisper heard |
| `response` | what the assistant answered |
| `route` | the router's path: topic, number of entities and sources (`details`, `fetch`), “+ answer” / “+ summary”, and for control the intent and parameters (labels from the language pack, e.g. Polish „+ odpowiedź”) |
| `speaker` | recognized speaker (Assist Speaker ID), empty = unknown |

Review it from time to time. Questions with an empty `route` or a wrong answer show
which topic to improve. Frequent sentences are worth adding as regular HA sentences, because those
work instantly.

- **Preview in HA:** integration options → “Unrecognized commands” shows a table of
  the last 30 entries, newest first.
- **Sensor** `sensor.assist_router_unrecognized_commands` (the same id in every HA language;
  ids built from a translated name by earlier versions are renamed automatically) gives the number
  of entries, and its `last` attribute holds the last 20. Handy for a Markdown card on a
  dashboard.
- **Clearing:** the `assist_router.clear_log` action or “Clear log” in the
  options. The header stays, and the previous content goes to
  `unrecognized_commands.csv.bak`.
- The `speaker` column contains the recognized speaker (Assist Speaker ID).

## Testing and choosing models {#testing}

The `tools/` directory contains five tools (Python, run from any computer with access
to Ollama):

- `snapshot_data.py` saves a snapshot of real data: Wikipedia articles and, for cases
  with a topic (`topic`, question, speaker), the topic data exactly as the integration
  builds it: entities, `details` and `fetch`, with the person and day from the
  question (needs `--router-config`). It also stores the snapshot time, which the model
  gets as "now", so the expected facts in the test do not change.
- `model_benchmark.py` tests models in turn:
  - router, with the same prompt as the integration;
  - answers from data;
  - summaries.

  Scoring is automatic: required and forbidden fragments, and length. The
  `control` section checks command parsing against the home snapshot, without executing
  anything. It replays the integration's whole decision: the alarm safeguard, a plain “yes/no” reply,
  the script name without the model, and parsing with the list of actions (scripts with descriptions,
  scenes). It checks the intent, the area, the matched device or action, and whether the assistant
  would ask for confirmation.
  `snapshot_data.py --only-home` refreshes just the home snapshot, e.g. after changing
  descriptions or aliases. The code tests alone (`pytest`) check control from sentence to
  the called service on a fake home (`tests/test_actions.py`). The
  `--rescore` option re-scores saved answers after test fixes.
  A section without its own `system` prompt uses the integration's prompts: answers get
  the topic data with the speaker and the hint, summaries (`prompt: summary`) the summary
  prompt. In the router part an ambiguous question may list several equally good topics.
  For a long run over many models: `--pull` downloads missing models (the next one
  already in the background), `--delete-after` removes them after their test (never models
  installed before the start; `--keep` protects more), and `--resume` skips models
  that already have all results, so an interrupted run can be resumed.
- `model_report.py` creates an HTML report and appends history to a CSV, so new models
  can be compared with old ones.
- `compare_sources.py` is a consistency test for changing a topic's data source.
  For each question in a list it computes the data the old way and the new way (two router.yaml
  files), e.g. automation sentences versus `details`/`fetch`, on live HA data.
  It saves the model's answers side by side. Read-only.
- `check_sentences.py` checks your automations with sentences. From each
  `conversation` trigger template it generates a few sentences and asks HA (debug mode,
  nothing is executed) what would handle them. It reports sentences that hit a different automation
  or HA intent, sentences that match nothing, and disabled automations. Run it after every change to
  your sentences.

```
.venv/bin/python tools/model_benchmark.py --ollama http://localhost:11434 \
  --router-config /config/assist/router.yaml --cases model_test.yaml \
  --data model_test_data.yaml --router gemma4:e4b --answer gemma4:26b --pull --out results.json
.venv/bin/python tools/model_report.py results.json --label "test" \
  --html result.html --csv model_results.csv --answers-csv model_answers.csv
.venv/bin/python tools/compare_sources.py --ha http://homeassistant.local:8123 \
  --token-file ~/.ha_token --ollama http://localhost:11434 \
  --old router.yaml --new router.new.yaml --questions questions.txt --out comparison.json
.venv/bin/python tools/check_sentences.py --ha http://homeassistant.local:8123 \
  --token-file ~/.ha_token --config /config --per-template 5
```

The test case file (YAML) contains questions with the expected topic, and data with a question and
the expected facts. The format is described at the top of `tools/model_benchmark.py`. Keep
it outside the repository, because it contains your home's data. The test questions are in the
language of your pack (Polish for the bundled one); a new language pack is checked the same way.

## Fine-tuning the router (optional) {#fine-tuning}

A general small model recognizes topics well, but it can be fine-tuned on your own home's data.
This is done with a separate set of scripts that will move to a separate repository in the future.
Training requires a graphics card (e.g. an RTX 4090), and after fine-tuning the model runs in Ollama
like any other. Steps:

1. fetching areas, entities with aliases, people and sentence files from HA;
2. the dataset:
   - sentences from your hassil templates, with the topic assigned via the template questions in
     `router.yaml`;
   - built-in HA intents with your names;
   - knowledge questions;
   - Whisper-style noise.
3. LoRA (Unsloth) with exactly the same prompt the integration uses;
4. export to Ollama;
5. a test on questions that were not in the training data.

After the topic list changes, the fine-tuned model has to be fine-tuned again.

**Lessons from the first attempt:** Gemma 4 E2B fine-tuned on template sentences alone
recognized them 99% of the time, but on free-form questions from the log it did worse than plain
Gemma 4 E4B (88/96 versus 93/96). It learned the style of the templates, not the language.
That is why the second run combines templates with paraphrases written by a large model (Gemma 4 26B):
natural questions with names, rooms and Whisper errors. The base is E4B.
