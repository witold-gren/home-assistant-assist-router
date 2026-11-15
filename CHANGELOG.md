# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), versions: [SemVer](https://semver.org/).

## [0.1.6] - 2026-11-15

### Added
- A guide to the editor step by step, with pictures, in English and Polish
  (`docs/en/editor-guide.html`, `docs/pl/przewodnik-edytora.html`): from an unrecognized sentence
  to a new topic with data, the tester, the test set, saving, the history and a command of Home
  Assistant. The pictures are taken on the demo by `make screenshots` (`dev/screenshots.py`), so
  the names in the guide are the names on the screen.
- The demo of the editor (`make ui`) draws the icons, and its made-up Home Assistant recognizes the
  sentences of the files of commands (`{name}`, `(a|b)`, `[a]`).
- The editor on a computer: a panel for administrators, **Assist Router editor** („Edytor Assist
  Routera”), that edits `router.yaml` in three columns. The tree of the file (the home, the topics
  of questions, the special topics: control, knowledge, unclear, no data), the YAML of the chosen
  item with the comments right above its key or the whole file, and the router's own check of the
  text. A change replaces only the lines of one item, so every other line, the comments and the
  layout stay as they were. Changes go to a draft kept in `.storage/assist_router.editor`, which
  changes nothing until it is saved; undo and redo; saving lists what changes, refuses a text the
  router cannot read, stops when the file was changed elsewhere meanwhile (unless saved anyway),
  keeps `router.yaml.bak` and a history of the last 30 saves, any of them restored as a draft.
  Adding, duplicating and deleting topics; a search and folding of the tree; resizable columns
  that are remembered; the Home Assistant menu button. WebSocket commands
  `assist_router/editor/*` (administrators only). The option *Show the editor in the sidebar*
  takes the panel out of the sidebar; it still opens at `/assist-router-editor`. The editor has a
  light look besides the dark one: as Home Assistant by default, or chosen with a button in the top
  bar (Auto, Light, Dark), remembered by the browser. The groups of the tree (Home, Topics of
  questions, Special, Learning, Commands of Home Assistant) fold by an arrow, and a button of each
  folds or unfolds everything inside it.
- Forms in the editor, next to the YAML of an item: a topic (name, description, examples, kind,
  answer hints for everyone, for kinds of speakers and for single people, answer length,
  `personal`, `verbatim`, `days`, `skip_states`, `drop`, `unavailable`, `only_exposed`; the data
  sources are shown and edited as YAML), people (with a try of `match` on a sentence), family,
  personas, music in rooms, announcements, devices to ask about first and the settings (with a
  warning for words in braces the router cannot fill in a prompt). A form rewrites the lines of
  one value only, in the style of the file, with the comments around it kept; values are written
  as YAML 1.1, as the router reads them. Entities, players, areas, pipelines and voices are
  suggested from Home Assistant. The parts of the home the file has none of yet are in the tree to
  fill in, and the settings are one node. `assist_router/editor/load` also gives the language packs.
- The data sources of a topic in the editor's form, with a live preview: how many entities each
  pattern finds, the lines and attributes the answer model would get (made by the router's own
  code), and cards for the services with a response, written item by item so the comments between
  them stay. Services are called only with the "Fetch the data now" button and only when they just
  return data; a topic's `command` is never sent. WebSocket commands
  `assist_router/editor/sources` and `assist_router/editor/services` (administrators only).
- The tester in the editor: a typed sentence goes the way of a spoken one on the draft, step by
  step: Home Assistant's own recognition (built-in sentences and `custom_sentences`, without
  running the intent), the router's topic (and the topic of the saved file, to compare), the
  person and the day, the data or the plan of a control command, and the answer with its prompt;
  several commands of one sentence each on their way. Options: speaker, persona, room, skipping
  HA, no answer model. Nothing is done: control is only planned, a topic's `command` is only
  recognized, the fallback agent is not asked, nothing is said, announced or logged. WebSocket
  command `assist_router/editor/test` (administrators only).
- Learning in the editor. The unrecognized commands of the log grouped by sentence (count, last
  time, speakers, rooms, the route then), checked on the draft, and turned into an example of a
  topic or a new topic, tested, added to the tests or hidden (in the editor only; the log is not
  changed). The test set `assist/router_tests.yaml` (a sentence and the topic or the intent of
  Home Assistant it should go to), saved at once with a `.bak`, added to from the tester, and run
  on the draft against the saved file: passed, failed, fixed and broken. WebSocket commands
  `assist_router/editor/unrecognized`, `unrecognized_hide`, `classify`, `tests_load`,
  `tests_save` and `tests_run` (administrators only).
- The window of saving in the editor says what is worth a look before the file is saved
  (patterns that find no entity, services that may change something or do not exist, topics
  without a description or examples, words in braces of a prompt the router cannot fill) and runs
  the test set on the draft against the saved file, saying how many tests the change breaks and
  which tests expect a topic the draft has no more; none of it stops saving. WebSocket command
  `assist_router/editor/checks`. The docs have a section on what to do when the editor says
  something is wrong (Polish and English).
- Commands of Home Assistant in the editor: the files `custom_sentences/<language>/*.yaml` in a
  form (intents, their sentences, the answer; other keys of a group kept) or as YAML, with the
  comments of the file kept. Saving checks every sentence template as Home Assistant does
  (hassil), writes the file with a `.bak` and reloads the sentences (`conversation.reload`), so a
  new command works without a restart; a file changed elsewhere is saved only when asked. An
  intent Home Assistant cannot carry out is marked. Typed sentences are checked against what Home
  Assistant recognizes now, without running anything. New files and deleting (as `.bak`).
  WebSocket commands `assist_router/editor/sentences_load`, `sentences_save`, `sentences_delete`
  and `sentences_test` (administrators only).

### Development
- `Makefile` with `make help` in English and Polish (`setup`, `doctor`, `ui`, `test`,
  `test-browser`, `test-all`, `lint`, `deploy`, `docs`, `clean`); `make ui` opens the editor on
  `router.example.pl.yaml` with a server kept in memory.
- Tests of the editor in Google Chrome (Playwright, `tests/browser`), run by CI too.

## [0.1.5] - 2026-11-12

### Added
- Announcements through the [Intercom](https://github.com/witold-gren/home-assistant-intercom)
  integration when it is added: „Komunikat do kuchni, obiad gotowy” plays only in the rooms named
  (inflected names and area aliases), otherwise in every room but the one spoken in; the speaker's
  own recording (Assist Speaker ID 0.2.1+), or the message read by text to speech for typed text;
  HomePods get a whole file. Reply when no speaker answered: `NOBODY_HEARD` in the language pack.
- Personas: who the assistant is in an Assist pipeline - a character with its own voice and wake
  word (e.g. Jarvis, a fairy-tale princess, a robot). `personas:` in `router.yaml` gives each one
  1-2 sentences (`prompt`) for the answer model, the Wikipedia summaries and the fallback agent,
  and optionally `gender: female`, which turns the fixed replies to female forms („Przepraszam,
  źle zrozumiałam”). A pipeline is matched by its TTS voice (`voices`), else by a fragment of its
  name or its id (`pipelines`); the pipeline is found from the run that handed over the sentence.
  Without the section nothing changes. Language pack: `PERSONA`, `FEMININE_FORMS`, `gendered()`.
- Frigate as topic data (`frigate:` in a topic): who the cameras saw, where and when, from
  Frigate's face recognition („Czy Kasia była wczoraj w salonie?”, „Kto był dziś w kuchni?”).
  The people from the question filter the Frigate API by face name (`sub_label`), the day is read
  backwards (a weekday is the last one, „wczoraj” from the question, otherwise `days` back);
  consecutive events of one person on one camera become one visit with local times, and GenAI
  review summaries of the same people are added. No tool calling - a small model answers
  reliably and nothing in Frigate can be switched by voice. Language pack: `FRIGATE_*`,
  `PAST_DAYS`.

- `past:` of a `fetch` source: items whose time is already over (the `end`, else the `start`;
  all-day items never) are left out (`drop`) or kept marked `już_było: true` (`mark`). A daily
  summary at 4 pm no longer mentions the noon meeting or the morning appointment, while „how
  many meetings did I have today” still counts them. Language pack: `PAST_KEY`.

### Fixed
- Speech recognition fix: „ruchom” (Whisper's cut „uruchom”) is read as „uruchom”, so
  „Ruchom podcast …” is a command. Language pack: `WHISPER_FIXES`.

## [0.1.4] - 2026-10-26

### Added
- A device that does not respond (state `unavailable`) is reported instead of a vague error:
  a command for it (or for a room where nothing responds) says „Urządzenie … nie odpowiada
  (jest niedostępne), więc nic nie zmieniłem.” and changes nothing - also when it stopped
  responding while the assistant was asking „czy dobrze rozumiem?”. A state question answered
  by the HA agent no longer says „Nie, … jest unavailable”, but that the device does not
  respond, so its state is unknown; when only some devices of the answer do not respond, the
  state word is translated. Language pack: `unavailable_command`, `unavailable_state`.

### Changed
- Music without a title - „włącz muzykę”, „puść coś w kuchni”, „wznów muzykę w salonie” -
  resumes the queue of the room's music player (`music_players`, or the satellite's room)
  instead of asking „Co mam puścić?” or offering to resume every speaker in the house.
  Language pack: `GENERIC_MUSIC`, `describe_resume`, `resumed`.
- With `music_players` set, music plays only on those players: a speaker named by the model
  (e.g. a satellite's own speaker) that is not on the list is ignored and the room's player
  from the list plays.
- Benchmark tools (`tools/`): answers from HA data now use the integration's own topic data
  and prompts - `snapshot_data.py` stores, per case (`topic`, question, speaker), the data
  the integration builds (entities, `details`, `fetch`, the person and day from the question;
  new shared module `tools/topic_data.py`), and `model_benchmark.py` sends it through
  `answer_messages` (speaker, hint, the topic's token limit) and summaries through
  `summary_messages`. Router cases may list several equally good topics, control `expect`
  values may list alternatives and replay the music intent mapping. New options for long runs:
  `--delete-after`, `--keep`, `--resume`, and the next model downloads in the background. The
  model file size is stored in the results (the report needs it after `--delete-after`). A
  dropped Ollama connection is retried twice instead of stopping the run.
- Model comparison page (`docs/pl/modele.html`, `docs/en/models.html`): round 3 of 26.10.2026 -
  16 models, each on the same 669 cases in all five parts (router 379, control 155, given data
  34, HA data 86, Wikipedia 15); conclusions and typical errors updated.

### Fixed
- „Wyłącz muzykę w łazience” said the music was off while the HomePod kept playing: the
  command turned off the HomePod (Apple TV) and the satellites' speakers, but the Music
  Assistant player that plays cannot be turned off. Turning off music now pauses the players
  that are playing in that room (`HassMediaPause`); other speakers are left alone and
  „wyłącz telewizor” still turns the TV off. Language pack: `MUSIC_WORDS`.

## [0.1.3] - 2026-10-25

### Added
- Correcting a question: to any question from the assistant („Czy dobrze rozumiem…?”, „Czy
  chodziło o…?”, also after „Powtórz, proszę”) a reply that starts with "no" and goes on with a
  command - „nie, wyłącz światło w łazience”, „nie, pytałem czy możesz…” - is handled from the
  start as a new command (HA agent, router, models). It can be corrected again and again; a plain
  „nie” and the cancel phrases work as before. Language pack: `REPHRASE_LEADS` (lead-ins such as
  „pytałem czy”, „chodziło mi o”), log label `(poprawione: …)`.
- People's entities by Home Assistant labels: `labels: [olivia]` at a person in `router.yaml`
  - entities with one of these labels belong to that person, like `owns` (e.g. CalDAV or Google
  calendars, assigned in Settings -> Entities). When the person asked about has no calendar (or
  other source) of their own while others have, the answer model is told so and says it, instead
  of "there are no events".
- Several commands in one sentence: „wyłącz światło w kuchni oraz łazience”, „zamknij rolety w
  salonie i włącz ekspres do kawy”. When the HA agent does not understand a command with a
  conjunction, the control model splits it into complete commands (`split_prompt`,
  `CONJUNCTIONS` in the language pack); each takes the whole usual path and the replies are
  joined. A command that needs a question waits; the rest run after the answer, „anuluj” drops
  them. Questions („co mają jutro Kasia i Jan”) are not split.
- Probable speaker (Assist Speaker ID 0.2.0+): when a voice is not recognized for sure but the
  most similar person is close enough, the router uses that person where the answer depends on
  who asks (1st person, personal topics, family terms, „w moim pokoju”) and starts the answer
  with „Wydaje mi się, że pyta Kasia.”; a recognized speaker is not named, an unused guess is not
  said. The fallback agent never gets a probable name. Log: speaker `Kasia?`, route
  `(prawdopodobnie Kasia)`. Language pack: `probable_speaker(name)`, `LOG_PROBABLE`.

### Changed
- „Kto to mówi?” for an unrecognized voice says why: the closest person, the similarity that
  person's threshold needs and the next person - „Nie rozpoznaję tego głosu. Najbliżej: Jan,
  53 procent, a do rozpoznania potrzeba 78 procent. Następna osoba: Kasia, 50 procent.”
  Language pack: `speaker_unknown(name, score, threshold, second)`.
- Sensor ids no longer depend on the HA language: `sensor.assist_router_unrecognized_commands`,
  `sensor.assist_router_example_commands`; Polish default ids of earlier versions are renamed on
  setup, ids changed by hand stay.

## [0.1.2] - 2026-10-25

### Added
- Logo images (`logo`, `dark_logo`) next to the icons in `brand/`.

### Fixed
- Control no longer runs a script or scene on a weak match: when the model picks an action but
  the words of the command that point to it also name a device, the assistant asks first.
  „Uruchom ekspres do kawy” (start the coffee machine; heard as „… do kabli”) made coffee with
  the script „Ekspres - zrób kawę”, because „ekspres” was the only shared word - it now asks
  „Czy dobrze rozumiem, że mam uruchomić …?”. „Zrób mi kawę” still runs the script at once.

## [0.1.1] - 2026-10-25

### Fixed
- Questions answered from entity states (e.g. „Które urządzenia są wyłączone?”) failed with
  `TypeError` when an entity had a non-text alias: newer Home Assistant keeps markers
  (`ComputedNameType`, "use the entity name") among entity aliases. Only text aliases are
  used now - for entity lines, device matching in control, and area and floor aliases.

## [0.1.0] - 2026-10-25

First public release. A conversation agent for Assist (domain `assist_router`, entity
`conversation.assist_router`) that understands ordinary questions and commands. It ships a
Polish language pack; other languages can be added as packs (see "Adding a language").

### Added
- Language packs (`custom_components/assist_router/languages/`): replies, vocabulary,
  patterns and LLM prompts in one module per language; the pack follows the HA language or
  `language:` in `router.yaml`. Bundled: Polish (`pl`).
- `command` templates get `who`, `person`, `people`, `when` (a day code, e.g. `tomorrow`),
  `text`; the Polish aliases from the pack keep working (`kto`, `osoba`, `osoby`, `tekst`, and
  `kiedy` with the Polish day name, e.g. `jutro`).
- Day codes are English: `today`, `tomorrow`, `day_after_tomorrow`, `weekend`, `week`,
  `monday` … `sunday` or a number of days. `days:` in `router.yaml` also accepts the language
  pack's names (Polish `dzis`, `jutro`, `tydzien`, …); an unknown value disables the router with
  an error in the log.
- Music Assistant players: „puść …” (play) uses `music_assistant.play_media` with the media
  type, the artist of a track or album and radio mode („puść coś w stylu …”); other players or
  genres use `search_media`. A room without an available player says so.
- Announcements: one speaker per room - an available player from `announce_players` (e.g. a
  HomePod) plays instead of the satellite (Assist Speaker ID 0.1.0+).
- Topic option `unavailable: true` (unavailable entities are reported, not skipped) and entity
  aliases next to names.
- `router_examples.yaml` and the `generate_examples` response use English keys (`working`,
  `rejected`); files with the older Polish keys are still read.
- A layer on top of the built-in HA agent: sentences, intents and automations work unchanged;
  Assist Router only takes over what HA did not recognize.
- Question router (Ollama): topics in `/config/assist/router.yaml`; data from entities (`entities`),
  attributes (`details`) and services (`fetch`), trimmed to the person and day from the question;
  the answer model writes a short reply. Topic fields: `personal`, `answer_hint`, `answer_hints`
  (speaker-dependent), `answer_tokens`, `verbatim`.
- Control with ordinary sentences (HA intents), asking „Czy dobrze rozumiem…?” (“Do I understand
  correctly…?”) when unsure and for sensitive devices; scripts and scenes; music („puść …”, “play …”).
- Wikipedia for knowledge questions; speech-recognition gibberish - „Czy chodziło o …?” (“Did you
  mean …?”).
- Recognized speaker (Assist Speaker ID integration): first-person questions, people's entities
  (`owns`), room (`room`), family terms (`family`), „Kto to mówi?” (“Who is speaking?”), short
  replies during voiceprint enrollment, announcements (intercom) with the speaker's recording.
- Integration options as a menu: settings, editing `router.yaml`, example commands
  (generated and checked with the router), unrecognized commands log (preview, clearing).
- Fallback agent (any LLM agent), CSV log, sensors, `generate_examples` and `clear_log`
  actions.
