# Assist Router

**English** · [Polski](README.pl.md)

<img src="custom_components/assist_router/brand/icon.png" width="96" align="right" alt="">

A conversation agent for Home Assistant (domain `assist_router`, entity
`conversation.assist_router`) that makes Assist understand ordinary questions and commands,
not just memorized sentences.

> **Language:** everything language-dependent (keywords, built-in phrases, prompts, spoken
> replies) lives in a language pack. The bundled pack is **Polish**, so the assistant
> understands and answers Polish today; more packs can be added - see
> [Adding a language](#adding-a-language). The example sentences below are in English for
> readability; with the Polish pack you say them in Polish.

**Building a new voice setup from scratch** (satellites, Whisper, Piper, Ollama, speaker
recognition)? Start with **[GUIDE.md](GUIDE.md)** (Polish version:
[PRZEWODNIK.md](PRZEWODNIK.md)).

## What it does

Every sentence goes to the built-in HA agent first. Intents, `custom_sentences`
and sentence-triggered automations keep working unchanged. When HA does not recognize a sentence:

| What | How |
|---|---|
| **Question router** | A model in Ollama picks a topic from `/config/assist/router.yaml` (calendar, school lessons, weather, sensors…). The code collects the topic's data from entities, attributes and services, trimmed to the person and day from the question. The answer model replies briefly from that data. |
| **Control** | Turns “Turn off the lamp in the walk-in closet”, “make it warmer”, “play jazz in the living room” into HA intents. When unsure, or for sensitive devices, it asks “Do I understand correctly…?”. |
| **Knowledge** | General questions (“Who was Copernicus?”) are answered with a Wikipedia summary. |
| **Who is asking** | With the [Assist Speaker ID](https://github.com/witold-gren/home-assistant-assist-speaker-id) integration, a first-person question (“What do I have tomorrow?”) is about the speaker. Family terms (“my brother”), the speaker's room (“in my room”) and the question “Who is speaking?” work too. |
| **Announcements (intercom)** | “Announcement, kids, please come to dinner” plays **your recording** on the other speakers instead of synthesized speech (Assist Speaker ID). |
| **Gibberish** | A misrecognized sentence ends with the question “Did you mean …?”. After two misunderstandings in a row Assist apologizes and ends the conversation. |
| **Fallback agent** | When the router has no data, the chosen LLM agent takes over the question. |
| **Log** | Unrecognized sentences go to `/config/assist/unrecognized_commands.csv`, with a preview in the options, a sensor and a clear action. |
| **Example commands** | The `assist_router.generate_examples` action writes sentences from your entities and checks them with the real router. The result lands in `assist/router_examples.yaml`. |
| **Editing router.yaml in HA** | Integration options → “Router file”, with validation before saving and a `.bak` copy. |

**Proven in practice:** the author runs everything daily on an **NVIDIA Jetson AGX Orin 64 GB**
(Ollama with Gemma 4 26B, faster-whisper, Assist Speaker ID) and it works very well: the router
answers in about 0.7 s, an answer from data (router plus answer model) takes about 2 s.

## Installation

1. Copy `custom_components/assist_router` to `/config/custom_components/` (or HACS:
   custom repository, type “Integration”) and restart HA.
2. **Settings → Devices & services → Add integration → Assist Router.**
3. Copy [router.example.yaml](router.example.yaml) to `/config/assist/router.yaml`
   and adjust the entities and people. For a Polish household (the bundled language pack)
   start from [router.example.pl.yaml](router.example.pl.yaml): the same file with Polish
   descriptions and examples.
4. In the integration options, enter the Ollama URL and choose the models.
5. **Settings → Voice assistants:** in every pipeline set the conversation agent to
   **“Assist Router”** and **turn off “Prefer handling commands locally”**. Otherwise
   the built-in HA intents get ahead of announcements, “Who is speaking?” and voiceprint enrollment.

## Services in docker compose (without HA add-ons)

Assist Router is an HA integration. The services it uses (Whisper, Piper, Ollama
and optionally [Assist Speaker ID](https://github.com/witold-gren/home-assistant-assist-speaker-id))
do not have to be add-ons. They can run as containers on another computer, e.g. one with a
graphics card. That is how the author runs them, on a Jetson AGX Orin 64 GB. An example
`docker-compose.yaml`:

```yaml
services:
  whisper:                      # speech to text (Wyoming, port 10300)
    image: rhasspy/wyoming-whisper
    command: --model medium-int8 --language pl      # the language of your household
    ports: ["10300:10300"]
    volumes: ["./whisper:/data"]
    restart: unless-stopped

  piper:                        # text to speech (Wyoming, port 10200)
    image: rhasspy/wyoming-piper
    command: --voice pl_PL-gosia-medium             # a voice in your language
    ports: ["10200:10200"]
    volumes: ["./piper:/data"]
    restart: unless-stopped

  ollama:                       # language models for the router and answers (port 11434)
    image: ollama/ollama
    ports: ["11434:11434"]
    volumes: ["./ollama:/root/.ollama"]
    environment:
      OLLAMA_FLASH_ATTENTION: "1"
      OLLAMA_MAX_LOADED_MODELS: "2"
    restart: unless-stopped
    deploy:                     # NVIDIA card (requires NVIDIA Container Toolkit)
      resources:
        reservations:
          devices: [{ driver: nvidia, count: all, capabilities: [gpu] }]

  speaker-id:                   # optional: who is speaking (in front of Whisper, ports 10350/10351)
    build: ./home-assistant-assist-speaker-id/speaker_id   # git clone next to this file
    depends_on: [whisper]
    ports: ["10350:10350", "10351:10351"]
    volumes: ["./speaker-id:/data"]
    environment:
      SPEAKER_ID_UPSTREAM: tcp://whisper:10300
      SPEAKER_ID_API_TOKEN: ${SPEAKER_ID_API_TOKEN}       # from the .env file next to it
    restart: unless-stopped
```

1. Start it: `docker compose up -d`, then pull a model:
   `docker compose exec ollama ollama pull gemma4:26b` (or a smaller one, e.g. `gemma4:e4b`).
2. In HA: Settings → Devices & services → Add → **Wyoming Protocol** for Piper
   (`192.168.1.10`, port 10200) and Whisper (port 10300). With Assist Speaker ID, add the
   **Assist Speaker ID** integration instead of Whisper (ports 10350 and 10351, token from `.env`).
3. In the Assist Router options, set the Ollama URL: `http://192.168.1.10:11434`.
4. In the voice assistant: speech to text Whisper (or “Speech to text with speaker”),
   agent **Assist Router**, text to speech Piper.

**Notes:**
- **Whisper:** the `rhasspy/wyoming-whisper` image computes on the CPU. On a graphics card
  (e.g. `large-v3`) use an image with CUDA, e.g. `lscr.io/linuxserver/faster-whisper:gpu`
  (variables `WHISPER_MODEL`, `WHISPER_LANG`).
- **Jetson:** use `runtime: nvidia` instead of the `deploy` section. The official
  `ollama/ollama` image detects the Orin GPU on its own. Whisper and Piper on the Jetson GPU
  need images built for JetPack (e.g. from the `dusty-nv/jetson-containers` project).
- **Without a GPU:** Ollama also runs on the CPU, but then choose a small model (e.g.
  `gemma4:e4b`) and expect slower answers.
- **Service address:** `192.168.1.10` is an example address of the computer running the
  containers. Expose the ports only on your home network.

### Ollama alone in docker compose

When Whisper and Piper already run as HA add-ons, Ollama alone on a computer with a
graphics card is enough:

```yaml
services:
  ollama:
    image: ollama/ollama
    container_name: ollama
    command: serve
    ports: ["11434:11434"]
    volumes: ["./ollama:/root/.ollama"]   # downloaded models (a dozen or more GB)
    environment:
      OLLAMA_HOST: 0.0.0.0
      OLLAMA_KEEP_ALIVE: "72h"            # the model stays in memory, no loading on a question
      OLLAMA_NUM_PARALLEL: "1"
      OLLAMA_MAX_LOADED_MODELS: "2"       # router and answer model at once, if they differ
      OLLAMA_FLASH_ATTENTION: "1"
      OLLAMA_KV_CACHE_TYPE: "q8_0"        # less context memory
    restart: unless-stopped
    deploy:                               # NVIDIA card (NVIDIA Container Toolkit)
      resources:
        reservations:
          devices: [{ driver: nvidia, count: all, capabilities: [gpu] }]
```

- **Jetson (JetPack 6):** remove `deploy` and add `runtime: nvidia`. The official
  `ollama/ollama` image has an arm64 build and detects the Orin GPU on its own; that is how
  the author runs it on an AGX Orin 64 GB.
- **Without a GPU:** remove `deploy` and choose a small model, e.g. `gemma4:e4b`.
- **AMD card:** the `ollama/ollama:rocm` image with the `/dev/kfd` and `/dev/dri` devices.

Start-up and models:

```sh
docker compose up -d ollama
docker compose exec ollama ollama pull gemma4:26b   # router and answers (18 GB, 24 GB card)
docker compose exec ollama ollama pull gemma4:e4b   # smaller (about 8 GB): router or a lighter setup
curl http://192.168.1.10:11434/api/tags              # from the HA computer: list of models
```

In the Assist Router options, enter `http://192.168.1.10:11434` and choose the models from
the list. The “Keep model in memory” option (`-1` = always) means only the first question
after Ollama starts waits for the model to load.

## Documentation

- [GUIDE.md](GUIDE.md): the whole setup step by step, for beginners (Polish version:
  [PRZEWODNIK.md](PRZEWODNIK.md));
- **full documentation with diagrams:** how the router works, `router.yaml` fields, data sources,
  control, speaker, log, model tests, privacy.
  In English: [docs/en](https://witold-gren.github.io/home-assistant-assist-router/en/),
  in Polish: [docs/pl](https://witold-gren.github.io/home-assistant-assist-router/pl/)
  (source files: [docs/](docs/));
- [LLM model comparison](https://witold-gren.github.io/home-assistant-assist-router/en/models.html)
  (the test used Polish questions): Gemma 4, Bielik, PLLuM, Qwen 3.5, Ministral
  on a Jetson AGX Orin 64 GB, accuracy and time in each role;
- [router.example.yaml](router.example.yaml): an example configuration with comments
  (a fictional household: Tom, Anna, Olivia, Jack); the Polish version:
  [router.example.pl.yaml](router.example.pl.yaml);
- [CHANGELOG.md](CHANGELOG.md): changes in each version.

## Development

```bash
python3.13 -m venv .venv && .venv/bin/pip install -r requirements_test.txt
.venv/bin/pytest -q && .venv/bin/ruff check . && .venv/bin/ruff format --check .
scripts/deploy.sh            # copies the integration to HA's config share (custom_components)
```

The version lives in `manifest.json`, `CHANGELOG.md` describes the changes, and a release is a
`vX.Y.Z` tag. Tools for testing models and sentences are in `tools/` (`model_benchmark.py`,
`check_sentences.py`, `compare_sources.py`, `snapshot_data.py`; description: documentation,
chapter 12).

## Adding a language

The integration ships the Polish language pack. Everything language-dependent lives in
`custom_components/assist_router/languages/<code>.py`: spoken replies, words and patterns
(days, yes/no answers, verbs, colors…), LLM prompts and the JSON keys they ask for, log
labels and the functions that build sentences. To add e.g. Czech:

1. Copy `languages/pl.py` to `languages/cs.py`.
2. Translate all phrases, patterns, prompts and replies, and optionally the JSON key names.
   Keep the same names of constants and functions - the code reads them through `LANG`.
3. The pack is used when HA's language is `cs`, or when `router.yaml` has `language: cs`
   (an unknown code disables the router with an error in the log).
4. Day codes (`today`, `tomorrow`, `day_after_tomorrow`, `weekend`, `week`, `monday` …
   `sunday`, a number of days) stay the same in every language: they are what `days:` takes and
   what the `when` variable holds. The pack maps its spoken words to them (`WHEN_PATTERNS`) and
   may add its own names for `days:` (`DAY_ALIASES`, e.g. Polish `dzis`, `jutro`).
5. Choose an Ollama model that understands the language, write the `router.yaml`
   descriptions and examples in it, and test with `tools/model_benchmark.py`.

Details: [documentation, chapter 15](https://witold-gren.github.io/home-assistant-assist-router/en/#adding-a-language).
Contributions are welcome as a pull request.
