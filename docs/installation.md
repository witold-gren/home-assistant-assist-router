# Installation

## Try it on a Mac {#try-on-a-mac}

- **Needs:** only [Docker Desktop](https://www.docker.com/products/docker-desktop/), running. No Python, no Home
  Assistant, no Ollama, no GPU.
- **Run:** `make demo` (the first build of the small image takes under a minute).
- **Open:** <http://127.0.0.1:8767/dev/editor-demo.html> (English: add `?lang=en`), no login.
- **Made up:** the example `router.example.pl.yaml` in a made-up home, in a container; nothing is saved and nothing
  reaches a real Home Assistant. Ctrl+C stops and removes the container, `make demo-clean` removes the image.
- **Docs and developers:** `make docs` builds this documentation in Docker and opens it. `make test` and
  `make test-browser` need `make setup` (uv, which fetches Python 3.14 itself; Chrome for the browser tests);
  `make demo-local` serves the same page without Docker.

## Requirements and models {#requirements}

- Home Assistant 2026.x (tested on 2026.10) with Assist in a language that has a language pack -
  Polish today (Whisper and Piper, or other STT/TTS).
- An [Ollama](https://ollama.com) server on the local network. It can run on a
  different computer than HA. Choose models that understand and write your language well.
- Optionally a fallback agent, e.g. the Ollama integration with a model for free-form conversation.

!!! tip

    **Proven in daily use:** the whole setup runs every day in the author's home
    on an **NVIDIA Jetson AGX Orin 64 GB**: Ollama (Gemma 4 26B as both router and answer model),
    faster-whisper and Assist Speaker ID. It works very well: the router answers in about 0.7 s and an
    answer from data (router plus answer model) takes about 2 s. 64 GB of unified memory holds the model alongside Whisper.

Example results from an NVIDIA Jetson AGX Orin 64 GB. The test covered 96 router questions, 34
questions about real HA data and 8 Wikipedia summaries:

| Role | Model | Accuracy | Time |
| --- | --- | --- | --- |
| Router | Gemma 4 26B (same model as for answers, loaded in memory once) | 153/153 (incl. actions and gibberish) | 0.7 s |
| Router (smaller) | Gemma 4 E4B | 92/96 | 0.5 s |
| Answer model | Gemma 4 26B (MoE, 4B active) | 34/34 data, 8/8 summaries | 1.2 s / 5.5 s |
| Parsing control commands | Gemma 4 26B (`control_model: answer`) | 67/67 commands (incl. actions) | 2.7 s |
| Guessing the sentence behind gibberish | Gemma 4 26B | out of 10 samples: 6 correct, 3× “don't know” (asks to repeat), 1 bold guess | 1.6 s |
| Lightweight setup | Gemma 4 E4B in all roles | 29/34 data, 8/8 summaries, 26/32 commands | 0.8 s / 3.8 s / 1.7 s |

**[Full comparison of more than a dozen models](models.md)**
(Gemma 4, Bielik, PLLuM, Qwen 3.5, Ministral; the test used Polish questions):
accuracy and time in each role, conclusions, typical errors and fine-tuning results. You can repeat
the test on your own hardware: [Testing and choosing models](good-practice.md#testing).

**Model memory.** Ollama loads a model with the context size given in
the request. The integration uses a fixed context: 4096 for the router and 8192 for the answer model.
If the fallback agent in the Ollama integration uses *the same* model as the answer model,
set its context to 8192 as well. Otherwise Ollama will reload the model on every question.

## Installation {#installation}

1. Copy `custom_components/assist_router` into the
   `/config/custom_components/` directory. Alternatively, add the repository to HACS as a
   custom repository of type “Integration”.
2. Restart Home Assistant.
3. **Settings → Devices & services → Add integration → Assist Router.**
4. **Settings → Voice assistants:** in every pipeline change the conversation agent to
   **“Assist Router”** (entity `conversation.assist_router`) and
   **turn off “Prefer handling commands locally”**. With that option on, HA recognizes
   built-in intents before Assist Router: an announcement (“Announcement, …”) would be spoken by
   text-to-speech, and “Who is speaking?” and recording a voice sample would not take priority. Assist Router passes every sentence to the built-in agent first anyway, so nothing
   is lost.
5. Copy `router.example.yaml` from the repository to
   `/config/assist/router.yaml` and adapt the entities to your home (file description:
   [Example router.yaml](router-yaml.md#example)). For a Polish household start from
   `router.example.pl.yaml` - the same file with Polish descriptions and examples.
6. In the integration options, enter the Ollama address and choose the models ([Integration options](#options)).
7. Optionally: [Speaker
   ID](https://github.com/witold-gren/home-assistant-assist-speaker-id), so the assistant knows who is asking ([Who is asking: recognized speaker (Assist Speaker ID)](data.md#speaker)).
   Assist Router reads the speaker by itself; you only need to change speech-to-text in your pipelines.

## Integration options {#options}

**Settings → Devices & services → Assist Router → Configure** opens a menu:

| Item | What it does |
| --- | --- |
| Settings | Two steps, described below. |
| Router file (router.yaml) | Edit `/config/assist/router.yaml` directly in HA. The file is validated before saving (invalid YAML or a configuration error shows a message and saves nothing), and the previous version is kept as `router.yaml.bak`. The router picks up changes from the next question, without a restart. |
| Example commands | Preview of sentences that work in this home, and generating them (see below). |
| Unrecognized commands | Table of the last 30 log entries (newest first) and a “Clear log” option; the previous content is kept as `unrecognized_commands.csv.bak`. |

### Example commands for your home {#examples}

The `assist_router.generate_examples` action, or the “Example commands” menu item,
works like this:

1. For each topic in `router.yaml`, the answer model composes sentences using real
   names: the topic's entities, devices and rooms (for control), and household members.
2. **Every sentence goes through the real router.** It is kept only if it lands
   in its own topic.
3. Control commands also go through parsing and command planning, **without being
   executed**.

Result:

- the file `/config/assist/router_examples.yaml`: for each topic its
  `description`, `working` (the sentences that work) and `rejected`
  (items with `sentence` and where it ended up: `topic`, or `control`
  with the reason a command would not work), which hints at which topic description or example to
  improve. Files written by older versions with the Polish keys `dzialaja` /
  `odrzucone` are still read;
- the **“Example commands”** sensor: its state is the number of working sentences,
  and the `topics` attribute holds the sentences per topic;
- a preview in the options.

Generation takes a few minutes, because every sentence is a separate router request. Action
options: `per_topic` (sentences per topic, default 5) and `topics` (only
selected topics). Topics with `unclear: true` (gibberish) are skipped. The action response
gives the `working` and `rejected` counts per topic.

The `assist_router.clear_log` action clears the unrecognized log. The
**“Unrecognized commands”** sensor shows the number of entries, and its
`last` attribute holds the last 20, which is handy for a Markdown card on a dashboard.

**Settings**, step one:

| Option | What it does |
| --- | --- |
| Log unrecognized commands | Appends every unrecognized sentence to `/config/assist/unrecognized_commands.csv` and fires the `assist_router_unrecognized` event. |
| Fallback agent | Conversation agent for questions the router provided no data for (a topic without data, e.g. “other”; an error). Empty = the message “You said: …” („Powiedziałeś: …”). |
| Fallback agent timeout | After this time you hear “You said: …”. |
| Ollama address | E.g. `http://localhost:11434`. Empty = router disabled. |

Step two appears once you enter the Ollama address. The model list is fetched from the server:

| Option | What it does |
| --- | --- |
| Router model | Picks the topic. A small, fast model is enough. |
| Answer model | Optional, but required for answers from data. It writes the answer from the topic data and summarizes Wikipedia. Without it, data questions go to the fallback agent, and for Wikipedia the beginning of the article is read out. |
| Router / model timeout | Default 8 s and 15 s. The router limit also applies to the Wikipedia search. |
| Keep model in memory | Minutes since the last question. `-1` = always in memory, fastest response. Both models are loaded when the integration starts. |
