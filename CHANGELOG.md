# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), versions: [SemVer](https://semver.org/).

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
