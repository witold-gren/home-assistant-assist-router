# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), versions: [SemVer](https://semver.org/).

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
  them. Questions („co mają jutro Zosia i Adam”) are not split.
- Probable speaker (Assist Speaker ID 0.2.0+): when a voice is not recognized for sure but the
  most similar person is close enough, the router uses that person where the answer depends on
  who asks (1st person, personal topics, family terms, „w moim pokoju”) and starts the answer
  with „Wydaje mi się, że pyta Zosia.”; a recognized speaker is not named, an unused guess is not
  said. The fallback agent never gets a probable name. Log: speaker `Zosia?`, route
  `(prawdopodobnie Zosia)`. Language pack: `probable_speaker(name)`, `LOG_PROBABLE`.

### Changed
- „Kto to mówi?” for an unrecognized voice says why: the closest person, the similarity that
  person's threshold needs and the next person - „Nie rozpoznaję tego głosu. Najbliżej: Adam,
  53 procent, a do rozpoznania potrzeba 78 procent. Następna osoba: Zosia, 50 procent.”
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
