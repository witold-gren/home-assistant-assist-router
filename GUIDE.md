# A local voice assistant in Home Assistant: a guide from scratch

**English** · [Polski](PRZEWODNIK.md)

This guide takes you step by step from Home Assistant without an assistant to a home where
you can ask in an ordinary sentence:

- “What time does Olivia go to school tomorrow?”
- “Turn off the lamp in the walk-in closet.”
- “What's in my calendar tomorrow?” (the assistant knows **who** is asking)
- “Who was Nicolaus Copernicus?”

> **Language:** Assist Router keeps everything language-dependent in a language pack. The
> bundled pack is **Polish**, so today you talk to it in Polish: choose Polish in HA, Whisper
> and Piper. The example sentences here are in English for readability. Other languages can
> be added: see [Adding a language](README.md#adding-a-language).

Each step says **what** to do and **why**, and leaves the details to the documentation of
the individual parts (links in the “More” columns and notes). The examples use a fictional
household: Tom (dad), Anna (mom), and the kids Olivia and Jack, as in
[router.example.yaml](router.example.yaml) (Polish version:
[router.example.pl.yaml](router.example.pl.yaml)).

> You don't have to do everything at once. Steps 1–5 give you a working assistant; step 6
> (speaker recognition) and step 7 (your own automations) are extras.

---

## 0. How it works in one picture

```
 You: "What do I have tomorrow?"
   │
   ▼
 satellite (speaker with a microphone, e.g. Home Assistant Voice)
   │ audio
   ▼
 Home Assistant: Assist pipeline
   ├─ 1. speech → text       Whisper              (step 2)
   │      └─ (optional) who is speaking?  Assist Speaker ID   (step 6)
   ├─ 2. text → answer       Assist Router        (step 4)
   │      ├─ HA sentences and automations          (step 7)
   │      └─ question router + models in Ollama    (step 3)
   └─ 3. answer → speech     Piper                (step 2)
   │
   ▼
 satellite: "Tomorrow at 16:00 you have swimming."
```

| Part | What it does | Where it runs | More |
|---|---|---|---|
| **Satellite** | microphone and speaker in a room, wake word (“Okay Nabu”, “Hey Jarvis”) | ESPHome, e.g. Home Assistant Voice PE | [HA documentation: Voice](https://www.home-assistant.io/voice_control/) |
| **Whisper** | turns speech into text | HA add-on or container (Wyoming, port 10300) | [Wyoming](https://www.home-assistant.io/integrations/wyoming/) |
| **Piper** | reads answers aloud | HA add-on or container (Wyoming, port 10200) | as above |
| **Ollama** | runs language models locally | the same or another computer (port 11434) | [ollama.com](https://ollama.com) |
| **Assist Router** | understands ordinary sentences: question router, control, Wikipedia | HA integration (this repository) | [documentation](https://witold-gren.github.io/home-assistant-assist-router/en/) |
| **Assist Speaker ID** | recognizes who is speaking | HA add-on or container + HA integration | [home-assistant-assist-speaker-id](https://github.com/witold-gren/home-assistant-assist-speaker-id) |

**Hardware.** Whisper and the language models work best on a computer with a graphics card
or on a device like an NVIDIA Jetson. They also run on the CPU alone, but more slowly;
choose smaller models then. A Raspberry Pi is enough for Home Assistant itself, but too weak
for Whisper and language models. Which models to choose and how to compare them:
[documentation, chapter 3 (Requirements and models)](https://witold-gren.github.io/home-assistant-assist-router/en/#requirements).

---

## 1. Home Assistant and a satellite

1. Install Home Assistant (Home Assistant OS is the simplest) and set the language to one
   that has a language pack - **Polish** for the bundled one (Settings → System → General).
2. Create **areas** for your rooms: Settings → Areas. Area names later become part of
   sentences (“in the kitchen”, “in the living room”), so name them the way you speak.
3. Connect a satellite: Home Assistant Voice PE shows up on its own as an ESPHome device.
   Assign it to an area. That way “turn on the light” without a room works in the room where
   the speaker stands.
4. Expose to Assist the devices you want to control by voice: Settings →
   Voice assistants → Expose.

---

## 2. Speech to text and text to speech: Whisper and Piper

Both services speak the **Wyoming** protocol, which Home Assistant supports with the
built-in Wyoming integration.

**Option A: HA add-ons** (everything on one computer). Settings → Add-ons → Add-on store:
install **Whisper** and **Piper**.
- Whisper: your language (`pl` for the Polish pack), the largest model your hardware
  allows. Smaller models mangle words more often.
- Piper: a voice in your language, e.g. `pl_PL-gosia-medium` or `pl_PL-darkman-medium` for Polish.

**Option B: containers on a more powerful computer** (e.g. with a graphics card). An example
`docker-compose.yaml`:

```yaml
services:
  whisper:
    image: rhasspy/wyoming-whisper
    command: --model small-int8 --language pl
    ports: ["10300:10300"]
    volumes: ["./whisper:/data"]
    restart: unless-stopped
  piper:
    image: rhasspy/wyoming-piper
    command: --voice pl_PL-gosia-medium
    ports: ["10200:10200"]
    volumes: ["./piper:/data"]
    restart: unless-stopped
```

Then in HA: Settings → Devices & services → Add → **Wyoming Protocol**, separately for
Whisper (host, port 10300) and Piper (host, port 10200).

**Check:** Settings → Voice assistants → (any assistant) → microphone button
in the Assist dialog. The sentence you say should appear as text.

---

## 3. Language models: Ollama

Assist Router uses models in two roles. They can be the same model or two different ones:

| Role | Task | Requirements |
|---|---|---|
| **router** | picks the **topic** of the question from a list (returns only the topic name) | fast; a small model is enough, a bigger one makes fewer mistakes |
| **answer model** | writes a short answer from HA data, parses control commands, summarizes Wikipedia | bigger, writes your language well |

1. Install [Ollama](https://ollama.com) on a computer with a graphics card (or on the same
   one as HA, if it is powerful enough) and pull a model: `ollama pull <model>`.
2. Check that HA can see it: `curl http://<host>:11434/api/tags` from the HA network.

Which model to choose: [documentation, chapter 3](https://witold-gren.github.io/home-assistant-assist-router/en/#requirements). How to compare models
on questions from your own home: [chapter 12 (Testing and choosing models)](https://witold-gren.github.io/home-assistant-assist-router/en/#testing).
The author uses the same model for the router and the answers, on a Jetson AGX Orin 64 GB.

---

## 4. Assist Router

1. **Installation:** copy `custom_components/assist_router` to
   `/config/custom_components/` (or HACS → custom repository, type
   “Integration”), restart HA and add the **Assist Router** integration (Settings →
   Devices & services → Add).
2. **Options** (Configure → Settings):
   - the Ollama URL (`http://<host>:11434`);
   - in the second step: the router model and the answer model;
   - optionally a fallback agent: any LLM agent for questions the router has no
     data for.

   Description of all fields: [documentation, chapter 5](https://witold-gren.github.io/home-assistant-assist-router/en/#options).
3. **router.yaml:** copy [router.example.yaml](router.example.yaml) to
   `/config/assist/router.yaml` (for Polish: [router.example.pl.yaml](router.example.pl.yaml)).
   The most important parts:
   - `household`: who lives in the home (the model knows that “mom” is Anna);
   - `people`: people and the beginnings of their names as they inflect (`match`); optionally
     `owns` (their entities, e.g. a work calendar), `labels` (HA labels marking their entities),
     `room` (their room) and `speaker` (voice,
     step 6);
   - `family`: parents, children, who is male (for “my brother”, “my daughter”);
   - `topics`: question topics. Each has a description and examples (for the router, in the
     language you speak) and a data source: `entities` (entity states), `details` (entity
     attributes), `fetch` (services, e.g. `calendar.get_events`).
   - optionally `language`: the language pack (default: HA's language if there is a pack for
     it, otherwise `pl`).

   You can also edit the file in HA itself: integration options → **Router file**. The file
   is validated before saving, and the previous version is kept as `.bak`. Changes take
   effect immediately, without a restart.
   Field descriptions and examples: [documentation, chapters 6–9](https://witold-gren.github.io/home-assistant-assist-router/en/#router).
4. **Checking what works in your home:** integration options → **Example commands** →
   “Generate” (a few minutes). The model writes sentences with the names of your entities,
   and the real router checks each one (control commands only as a dry run, nothing is
   executed). Result: `/config/assist/router_examples.yaml` (per topic: `description`,
   `working` and `rejected` sentences) and the “Example commands” sensor. The `rejected`
   sentences show which topic description is worth improving.

---

## 5. Assist pipelines: putting it all together

Settings → Voice assistants → **Add assistant** (preferably one per room, e.g.
“Kitchen”):

| Field | Value |
|---|---|
| Language | the language of your pack (Polish) |
| Conversation agent | **Assist Router** |
| Speech-to-text | Whisper (from step 2), and after step 6 **“Speech to text with speaker”** |
| Text-to-speech | Piper, a voice in that language |
| **Prefer handling commands locally** | **off** |

The last field matters. When it is on, HA recognizes built-in intents **before**
Assist Router. “Announcement, …” then broadcasts the text with synthesized speech instead of
your recording, and “Who is speaking?” and voiceprint enrollment don't get priority. You lose nothing: Assist Router passes every sentence to the
built-in HA agent first anyway.

Then, in the satellite's settings (ESPHome device → “Assistant”), choose that room's pipeline.

**Check:** say “What will the weather be tomorrow?” and “Turn off the light in the
kitchen” to the satellite (in Polish with the Polish pack). The details
of each request are shown in Settings → Voice assistants → ⋮ → **Debug**. You can see the
heard text, the chosen topic and the answer there. Sentences the assistant did not understand
go to the log: Assist Router options → **Unrecognized commands**
([documentation, chapter 11](https://witold-gren.github.io/home-assistant-assist-router/en/#log)).

---

## 6. (Optional) Who is speaking: Assist Speaker ID

With this, “What do I have tomorrow?” from Olivia is about her calendar, and “Where is my
phone?” rings the right phone. Documentation:
[home-assistant-assist-speaker-id](https://github.com/witold-gren/home-assistant-assist-speaker-id).

**How it works.** The service sits between HA and Whisper: it passes the audio through
unchanged, and meanwhile turns the voice into a “fingerprint” (a vector of numbers) and
compares it with the stored voiceprints of the household. It adds no delay and stores no
recordings.

1. **Service:**
   - as an HA add-on: add the add-on repository
     `https://github.com/witold-gren/home-assistant-assist-speaker-id`, install **Speaker
     ID** and set the speech-to-text server (e.g. `tcp://core-whisper:10300`); see
     [Service as an HA add-on](https://github.com/witold-gren/home-assistant-assist-speaker-id#service-as-an-ha-add-on);
   - or as a container next to Whisper: see the repository README, section
     [Service as a container](https://github.com/witold-gren/home-assistant-assist-speaker-id#service-as-a-container)
     (or [Service in docker compose (without the add-on)](https://github.com/witold-gren/home-assistant-assist-speaker-id#service-in-docker-compose-without-the-add-on)).
2. **The Assist Speaker ID integration** (HACS, custom repository, type “Integration”; see
   [Integration](https://github.com/witold-gren/home-assistant-assist-speaker-id#integration)).
   The HA add-on is discovered automatically; for a container, enter the host and ports 10350
   and 10351.
3. **Pipelines:** in each one, change speech-to-text to **“Speech to text with speaker”**.
   The text is the same as from Whisper, so it doesn't break anything.
4. **Voiceprints**, separately for each person. Developer tools → Actions:

   ```yaml
   action: speaker_id.start_enrollment
   data:
     speaker: olivia       # the same key as in people in router.yaml
     name: Olivia
     count: 10
     satellite: assist_satellite.kitchen_assist_satellite
   ```

   The speaker asks for the next sentences by itself (“Recorded 3 of 10. Next sentence.”),
   without a wake word. Commands are not executed in the
   meantime. Say ordinary sentences of a few words each, from your usual distance.
5. **Calibration** after all people are recorded: the `speaker_id.calibrate` action with
   `apply: true`. Each person then gets their own threshold. You can also set thresholds by
   hand: Assist Speaker ID integration options → **Recognition thresholds**. What the numbers
   mean and how to calibrate similar voices (siblings): the Assist Speaker ID README, section
   [How to read scores and thresholds](https://github.com/witold-gren/home-assistant-assist-speaker-id#how-to-read-scores-and-thresholds).
6. **Announcements:** “Announcement, kids, please come to dinner” (in the Polish pack the
   sentence starts with „ogłoszenie”, „komunikat”, „do wszystkich” or „intercom”) plays your
   recording on the other speakers instead of synthesized speech.
   Additional players: `announce_players` in `router.yaml` (with Assist Speaker ID 0.1.1+ one
   speaker per room: an available player, e.g. a HomePod, instead of the satellite there).
7. **Check:** ask “Tell me who is talking to you now”. The assistant gives the name, the similarity in percent and the runner-up.

What Assist Router does with the speaker (first person, `owns`, `room`, `family`, fallback
agent): [documentation, chapter 7, “Who is asking”](https://witold-gren.github.io/home-assistant-assist-router/en/#speaker).

---

## 7. Your own sentence automations

Automations with a “Sentence” (conversation) trigger work as before and take priority over
the router: HA checks them before it asks Assist Router. Two rules:

- **Questions that should be answered from data are better described as a topic in
  router.yaml than as an automation.** A topic understands any phrasing, person, day and
  speaker. An automation sentence has to match exactly.
- **Speaker in an automation:** automation sentences don't receive the speaker directly.
  However, the “Last speaker” sensor changes within the same command. The `speaker()` macro
  from the Assist Speaker ID README ([Usage](https://github.com/witold-gren/home-assistant-assist-speaker-id#usage), point 3) returns the speaker of the
  current sentence, e.g. so that “where is my phone” rings that person's phone.

---

## 8. When something doesn't work

| Symptom | Where to look |
|---|---|
| The assistant misheard the sentence | Pipeline debug → text from Whisper; a bigger Whisper model, speak more clearly, closer to the microphone |
| “I don't understand” or a wrong answer to a question | the Unrecognized commands log (the `route` column: which topic the router chose); improve the topic's `description` and `examples`; “Example commands” shows what lands elsewhere |
| A question about data, and the answer is “I don't know” | do the topic's entities exist (Developer tools → States); `only_exposed`; the device is unavailable (add `unavailable: true` to the topic); a different name - add an alias to the entity; [documentation, chapter 7](https://witold-gren.github.io/home-assistant-assist-router/en/#data) |
| A control command doesn't work | is the device exposed to Assist; [documentation, chapter 10](https://witold-gren.github.io/home-assistant-assist-router/en/#control) |
| Speaker “unknown” | does the pipeline use “Speech to text with speaker”; sentence longer than 1 s; calibration and thresholds (Assist Speaker ID README) |
| Siblings get mixed up | more samples, a bigger margin (Assist Speaker ID README, [How to calibrate similar voices](https://github.com/witold-gren/home-assistant-assist-speaker-id#how-to-calibrate-similar-voices-eg-siblings)) |

---

## 9. Privacy

Everything runs locally: speech, models, voice recognition. A voiceprint is biometric data:
Assist Speaker ID stores only vectors, no recordings, and `speaker_id.delete_speaker`
deletes a person's voiceprint. Household members should know about voice recognition.

The `debug_recording_dir` option in the `assist_pipeline` section of `configuration.yaml`
saves the audio of **every** command to disk. Turn it on only while diagnosing a problem.

More: [documentation, chapter 14](https://witold-gren.github.io/home-assistant-assist-router/en/#privacy) and the Assist Speaker ID README,
section [Privacy](https://github.com/witold-gren/home-assistant-assist-speaker-id#privacy).

---

## Documentation map

| Topic | Document |
|---|---|
| Assist Router: how it works, router.yaml, data sources, control, speaker, log, models | [documentation](https://witold-gren.github.io/home-assistant-assist-router/en/) |
| LLM model comparison | [models](https://witold-gren.github.io/home-assistant-assist-router/en/models.html) |
| Example router configuration with comments | [router.example.yaml](router.example.yaml) (Polish: [router.example.pl.yaml](router.example.pl.yaml)) |
| Adding a language | [README: Adding a language](README.md#adding-a-language) |
| Assist Router changes | [CHANGELOG.md](CHANGELOG.md) |
| Assist Speaker ID: installation, usage, voiceprints, thresholds and calibration, privacy | [Assist Speaker ID README](https://github.com/witold-gren/home-assistant-assist-speaker-id#readme) |
| Assist Speaker ID add-on (add-on options) | [speaker_id/DOCS.md](https://github.com/witold-gren/home-assistant-assist-speaker-id/blob/main/speaker_id/DOCS.md) |
| Voice assistant in Home Assistant (official) | [home-assistant.io/voice_control](https://www.home-assistant.io/voice_control/) |
