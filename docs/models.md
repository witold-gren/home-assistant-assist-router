# Language model comparison

Which Ollama models work best in Assist Router with Polish: accuracy and time in each role. Test of 26.10.2026 (round 3) on an NVIDIA Jetson AGX Orin 64 GB.

!!! note

    The test was run only with Polish questions and Polish data (the bundled language
    pack is Polish), so these results apply to Polish. In another language the results may look
    different; you can repeat the test for your language ([see below](#repeat)).

## What was tested {#tested}

Each of the 16 models went through the same set of 669 cases, in the five roles a model plays
in Assist Router. The cases come from a real home configuration (28 topics, areas, devices,
scripts and scenes) and from questions that Home Assistant did not understand on its own:

| Test part | What it checks | Number of cases |
| --- | --- | --- |
| Router (topic) | whether the model picks the right topic from `router.yaml` for a free-form question, also with speech recognition errors and gibberish; for questions that fit two topics, either one is correct | 379 |
| Control (parsing) | whether a command becomes the right HA intent, area, device, value and “ask first” decision: lights, color and white temperature, covers, climate, music (Music Assistant, artist, radio), volume, vacuum, lists, scripts and scenes | 155 |
| Answers: given data | an answer from ready-made data: counting hours and amounts, “in how many minutes”, “the day after tomorrow”, no data, a request to control a device | 34 |
| Answers: HA data | an answer from a snapshot of the home's data, built exactly as the integration builds it (entities, `details`, `fetch`, the person and day from the question, the same prompt and token limit): school timetable, tests, calendars, chores, medicines, car, sensors, windows, unavailable devices, lists, vacuum, daily summary | 86 |
| Wikipedia summaries | an article summary with the integration's prompt: 2–5 sentences, with the key fact | 15 |

An answer counts as correct when it contains the expected facts (e.g. a time or an amount) and
does not contain forbidden ones (e.g. an event from another day). Time is the average time of one
answer; models were loaded and unloaded one after another, so they did not compete for memory.
The data snapshot freezes the state of the home, so every model got the same facts.

Colors: ≥ 95%≥ 85%below 85%
Order: average accuracy over all five parts.

## Results {#results}

| Model file size | Router (topic) | Control (parsing) | Answers: given data | Answers: HA data | Wikipedia summaries |
| --- | --- | --- | --- | --- | --- |
| gemma4:26b 18.7 GB | **376/379** 0.85 s | **152/155** 3.27 s | **33/34** 0.95 s | **83/86** 2.28 s | **14/15** 4.75 s |
| gemma4:12b 8.0 GB | **369/379** 1.01 s | **148/155** 4.53 s | **34/34** 1.20 s | **77/86** 3.93 s | **15/15** 7.71 s |
| gemma4:e4b 6.6 GB | **359/379** 0.54 s | **139/155** 2.43 s | **34/34** 0.68 s | **72/86** 1.71 s | **14/15** 3.64 s |
| qwen3.5:9b 6.6 GB | **357/379** 1.72 s | **130/155** 8.93 s | **29/34** 2.04 s | **71/86** 4.58 s | **14/15** 9.19 s |
| qwen3.5:4b 3.3 GB | **348/379** 1.33 s | **135/155** 5.92 s | **26/34** 1.60 s | **68/86** 3.04 s | **14/15** 7.10 s |
| gemma4:e2b 4.6 GB | **336/379** 0.49 s | **128/155** 2.47 s | **28/34** 0.51 s | **67/86** 1.11 s | **14/15** 2.13 s |
| ministral-3:8b 6.0 GB | **338/379** 0.72 s | **136/155** 6.04 s | **31/34** 1.11 s | **75/86** 3.42 s | **8/15** 11.39 s |
| bielik-minitron-7B-v3.0-instruct:Q4_K_M 4.5 GB | **280/379** 1.02 s | **128/155** 5.88 s | **29/34** 2.19 s | **70/86** 6.56 s | **9/15** 14.65 s |
| bielik-11b-v3.0-instruct:Q6_K 9.2 GB | **293/379** 1.66 s | **134/155** 10.35 s | **31/34** 4.08 s | **63/86** 15.12 s | **7/15** 31.47 s |
| Llama-PLLuM-8B-instruct-2512-GGUF:Q4_K_M 4.9 GB | **312/379** 0.86 s | **124/155** 5.02 s | **26/34** 0.77 s | **64/86** 2.18 s | **9/15** 5.51 s |
| PLLuM-12B-chat-2512-GGUF:Q4_K_M 7.5 GB | **332/379** 1.10 s | **134/155** 8.02 s | **25/34** 1.12 s | **69/86** 4.90 s | **6/15** 13.47 s |
| bielik-11b-v3.0-instruct:Q4_K_M 6.7 GB | **296/379** 1.43 s | **131/155** 8.83 s | **31/34** 3.32 s | **63/86** 11.47 s | **6/15** 25.08 s |
| ministral-3:3b 3.0 GB | **324/379** 0.61 s | **120/155** 3.64 s | **23/34** 0.62 s | **70/86** 1.77 s | **6/15** 5.78 s |
| qwen3.5:2b 2.7 GB | **314/379** 0.74 s | **114/155** 4.37 s | **18/34** 0.99 s | **59/86** 2.80 s | **8/15** 13.73 s |
| PLLuM-4B-instruct-2512-GGUF:Q4_K_M 2.5 GB | **299/379** 0.77 s | **115/155** 4.40 s | **14/34** 0.82 s | **56/86** 2.06 s | **1/15** 3.23 s |
| qwen3.5:0.8b 1.3 GB | **259/379** 1.06 s | **40/155** 6.99 s | **14/34** 1.16 s | **42/86** 2.28 s | **9/15** 6.61 s |
| Gemma 4 E4B fine-tuned router, QLoRA 8.0 GB | **100/101** (before re-training) 0.62 s | – | – | – | – |
| Gemma 4 E2B fine-tuned router, LoRA 5.0 GB | **88/96** (before re-training) 0.41 s | – | – | – | – |

Size is the size of the model file; on the Jetson, memory is shared by the CPU and GPU.
The fine-tuned Gemmas show results from an earlier, smaller set (96 and 101 questions): they will
be fine-tuned again on the current 28 topics and checked with the same set. The PLLuM models ran
with the chat template that Hugging Face picks for `ollama pull` (Granite style) – with
their native template they may do better.

## Conclusions {#conclusions}

- **Best in every role: Gemma 4 26B** (MoE, about 4B parameters active at a
  time): router 376/379 in 0.85 s, control 152/155, HA data 83/86 in 2.3 s – the best result for
  the router, control and HA data, and faster than the dense Gemma 4 12B and Qwen 3.5 9B. One
  model in both roles keeps only one model in memory; this is how the author runs it.
- **Gemma 4 12B** is close behind (369/379, 15/15 summaries, 34/34 on given
  data), but 1.2–1.7× slower and weaker on HA data (77/86).
- **Lightweight setup: Gemma 4 E4B** (6.6 GB) – the fastest good router
  (359/379 in 0.54 s), 34/34 on given data, but weaker at control (139/155) and on HA data
  (72/86). Gemma 4 E2B is even faster (0.49 s), but clearly less accurate.
- **Qwen 3.5 9B and 4B** recognize topics well (357 and 348/379) and summarize
  well (14/15), but parse commands more slowly (6–9 s) and calculate worse with data.
- **Ministral 3 8B** answers well from HA data (75/86), but its summaries are
  too long (8/15) and answers often contain markdown.
- **Polish models** (Bielik, PLLuM) did worse than the earlier, smaller rounds
  suggested: Bielik recognizes 74–78% of topics, summarizes too long and is slow (Bielik 11B Q6:
  15 s per answer from HA data); PLLuM 12B scores 332/379 as a router, but only 6/15 summaries.
  They do well with given data (Bielik 31/34).
- **Small models** (Qwen 3.5 0.8B–2B, PLLuM 4B, Ministral 3 3B) are not suitable
  for control or answers; Qwen 3.5 0.8B parses only 40/155 commands correctly.

## Typical model errors {#errors}

- **Arithmetic:** sums of amounts, number of hours („5 i pół godziny”, “5 and a half
  hours”), “in how many minutes” until the next meeting – the most common slips, even for large models.
- **Days of the week:** „pojutrze” (“the day after tomorrow”), „w przyszłym
  tygodniu” (“next week”) – events from the wrong day, or left out.
- **Confused topics:** most often a control command read as a question about
  music, the alarm or lights (e.g. „włącz serial”, “play the series”), gibberish taken for an
  ordinary question, and a question about devices taken for one about sensors.
- **Control:** most errors are the choice of device (e.g. „ledy w korytarzu”,
  “hallway LEDs”, “colored lamps”, the inner blind instead of the outer one) and of the intent
  (calibrating and positioning covers, scene-like commands such as “set the mood”, “turn on the TV”).
- **Making things up:** adding events that are not in the data, or “I don't know”
  although the data contained the answer.
- **Summaries:** 6–11 sentences instead of at most 5 (Bielik, Ministral, PLLuM),
  or the key fact missing.
- **Form:** markdown (`**`) and end-of-text markers in an answer
  that is meant to be read aloud – mostly Ministral 3 (over 50 answers) and PLLuM 12B.

## Fine-tuning the router {#fine-tuning}

- **First run:** Gemma 4 E2B fine-tuned (LoRA) on 15 thousand sentences
  generated from hassil templates, 80 minutes on an RTX 4090. 298/300 on template sentences, but
  88/96 on free-form questions – the model learned the templates instead of generalizing.
- **Second run:** Gemma 4 E4B (QLoRA), 14 thousand examples, including 7.7 thousand
  paraphrases written by Gemma 4 26B. On 101 questions outside the training data 100/101 in 0.62 s
  (base Gemma 4 E4B: 97/101 in 0.55 s); validation 290/300 versus 272/300.
- **Conclusion:** paraphrases written by a larger model are key. How to fine-tune
  the router on your own topics: [Fine-tuning the router (optional)](good-practice.md#fine-tuning).

## How to repeat the test yourself {#repeat}

The tools are in the repository's `tools/` directory: `snapshot_data.py`
(data snapshot), `model_benchmark.py` (model test) and `model_report.py`
(a table like this one as HTML and CSV). Description: [Testing and choosing models](good-practice.md#testing).
