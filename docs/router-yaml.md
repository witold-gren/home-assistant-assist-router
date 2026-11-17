# The router.yaml file

## The router.yaml file {#router}

`/config/assist/router.yaml` describes your home. The integration code is the same for
all users. Changes to the file take effect immediately, without restarting HA. Without the file the
router is disabled. Below is a skeleton with the most important fields; a full example home with
more than a dozen topics is in [Example router.yaml](#example), and how the code collects and
trims data is described in [Where the router gets its data](data.md#data).

```
# language: pl            # language pack (default: HA's language if there is a pack, otherwise pl)

# Who lives in the home - goes into the router and answer model prompts
household: "Household: Tom (dad), Anna (mom), kids: Olivia, Jack."

# People in questions: match = word beginnings (regex), so inflected forms match too
people:
  olivia: {name: Olivia, match: "oliv|liv\\b"}
  jack:   {name: Jack,   match: "jack"}
  tom:    {name: Tom,    match: "tom|dad"}
  # family: {parents: [tom, anna], children: [olivia, jack], men: [tom, jack]}
  # speaker: voice identifier in Assist Speaker ID (defaults to the person key, here "olivia", "jack")
  # owns: [calendar.olivia] - this person's entities; room: Olivia's room - their room

sentences: 4              # number of sentences in a Wikipedia summary
only_exposed: false       # true = topic entities only from those exposed to Assist
control_model: answer     # which model parses control commands: router or answer
confirm_entities:         # always ask for confirmation (entity_id patterns or names)
  - switch.kitchen_fridge
  - switch.*_enabled
music_players:            # "play …": room -> players, first available wins
  Living room: [media_player.living_room_homepod, media_player.living_room_voice]
# personas:               # who the assistant is in a pipeline - personas
#   jarvis: {pipelines: [Hey Jarvis], gender: male, prompt: "You are Jarvis from Iron Man."}

topics:
  school:
    description: school, timetable, extra classes, when lessons end
    examples: ["What time does Olivia go to school tomorrow?"]
    details: [sensor.school_timetable]  # entity attributes, trimmed to the person and day in the question
    days: today                         # day code: no day in the question - today
    drop: [teacher, classroom]          # keys to skip

  calendar:
    description: plans, events, meetings, birthdays
    examples: ["What do we have at the weekend?"]
    days: "14"                          # no day in the question - 14 days from today
    fetch:                              # service with a response
      - action: calendar.get_events
        entities: [calendar.family, calendar.work]
        data: {start_date_time: "{start}", end_date_time: "{end}"}
        merge: events                   # one list from all calendars, in order
        title: Calendar events

  car:
    description: car - fuel, range, mileage, is it locked, where is it parked
    examples: ["How much fuel is in the car?", "Did I lock the car?"]
    entities: [sensor.my_car_*, binary_sensor.my_car_*, lock.my_car_*]

  lights:
    description: which lights are on
    entities: [light.*, "!light.ipad_*"]   # "!" = exclusion
    skip_states: ["off"]

  control:
    description: commands - turn on, turn off, set, dim, blinds, warmer, louder
    examples: ["Make it brighter in the living room.", "Lower the blinds halfway."]
    control: true

  knowledge:
    description: a general knowledge question - who was, what is, history, geography
    examples: ["Who was Nicolaus Copernicus?"]
    search: wikipedia

  other:
    description: everything else - chit-chat, jokes, requests
    examples: ["Tell me something interesting."]
```

!!! note

    Topic keys (`school`, `calendar`…) are your own names. Write
    `description` and `examples` in the language your household speaks - the router
    compares them with the question. With the bundled Polish pack that means Polish (see
    `router.example.pl.yaml`).

### Topic fields {#topic-fields}

| Field | Meaning |
| --- | --- |
| `description` | A short description for the router: what questions in this topic are about. Topic descriptions should not overlap. |
| `examples` | 2–4 example questions. They help most with phrasings on the border between two topics. |
| `entities` | `entity_id` patterns (`*` = any string, `|class1,class2` = only these sensor device classes, `!pattern` = exclusion). Their states go into the data in words of the language pack: a window is “open” (Polish „otwarte”), a lock is “locked” („zamknięty”). `unknown`/`unavailable` are skipped; at most 80 entities, in pattern order (most important first). |
| `details` | Patterns of entities whose **attributes** are sent to the model (e.g. school timetable, account balances, tram departures). Lists are trimmed to the person in the question (key `child` or `person`) and to the day (key `date` or `datetime`); noise (html, avatars, colors, `false` values) is skipped, and times are local and include the weekday. |
| `fetch` | Services with a response: `action`, `entities`, `data` (`{start}` and `{end}` = the day range from the question), optionally `merge` (a list to combine across all entities), `past` (items whose time is already over: `drop` leaves them out, so a daily summary at 4 pm skips the noon meeting; `mark` keeps them marked `już_było: true`, so “how many meetings did I have today” still adds up), `title` and `limit` (maximum number of items, default 40). E.g. calendars (`calendar.get_events`) or the forecast (`weather.get_forecasts`). |
| `frigate` | Who the **Frigate** cameras saw, where and when: `url` (Frigate address, port 5000 without login), optionally `cameras` (camera → spoken name, e.g. `salon: Living room`; only these are asked), `labels` (default `person`), `days` (days back when the question gives no day, default 7), `limit` (most visits, 30), `summaries` (most GenAI review summaries, 10; 0 = none) and `gap` (seconds that still join events into one visit, 120). The people in the question are Frigate face names (`sub_label`), so name faces in Frigate's Face Library exactly like `people`. Days look back: a weekday is the last one, and "yesterday" is read from the question. No tool calling - nothing in Frigate can be switched by voice. |
| `days` | The day used when the question does not give one, as a day code: `today`, `tomorrow`, `day_after_tomorrow`, `weekend`, `week` (this week), `monday` … `sunday` or a number of days (`"14"` = today and the next 13 days). The codes are keywords and stay the same in every language; the language pack maps spoken words to them. The pack may also accept its own names here - the Polish one takes `dzis`, `jutro`, `pojutrze`, `tydzien`, `poniedzialek` … `niedziela`, so older Polish files keep working. An unknown value disables the router with an error in the log. Without this field, data is not filtered by day. |
| `drop` | Attribute keys skipped in this topic. |
| `personal` | `true`: the topic is for the person asking, even without “I have” or “my” (“Good morning”). A parent (`family.parents`) gets their own data and the children's data, a child only their own. An unknown speaker means everyone's data. A name in the question always wins. |
| `answer_hint` | An extra instruction for the answer model in this topic, e.g. how to structure a daily summary and what to say to a parent versus a child. |
| `verbatim` | `true`: HA's answer to the template sentence in `command` is read out word for word, without the answer model. Several sentences separated by `;` give all the answers in turn. Useful when an automation has a fixed answer layout, e.g. the daily news: “Today's news: First item…”. |
| `answer_hints` | Instructions that depend on who is asking. Keys, in order: person (e.g. `olivia`), `girl`/`boy` (children), `child`/`parent`, `unknown` (speaker not recognized). If no key matches, `answer_hint` is used. A simple instruction for one person works more reliably than one long instruction with conditions. |
| `answer_tokens` | A longer answer than the default 160 tokens, e.g. 360 for a daily summary. |
| `command` | (legacy) An HA (Jinja) template with a template question for your HA, e.g. an automation sentence. Separate several questions with `;`. It is better to use `details` and `fetch` instead - no separate Assist automations needed. |
| `search: wikipedia` | Knowledge topic: the search term is taken from the question and the article is summarized. |
| `control: true` | Control commands topic ([Home control](control.md)). |
| `unclear: true` | Speech recognition gibberish topic: the model guesses what was said and the assistant asks “Did you mean…?”; without a guess it asks you to repeat ([Home control](control.md)). |
| *no data and no search* | The question goes to the fallback agent. |

### Variables in the `command` template (legacy field) {#variables-in-the-command-template}

| Variable | Polish alias | Value |
| --- | --- | --- |
| `person` | `osoba` | the first name in the question (the form from `people.name`) or none |
| `people` | `osoby` | all names in the question, in order: “Olivia and Jack” → `['Olivia', 'Jack']` |
| `who` | `kto` | the key of the first person from `people` (e.g. `olivia`) |
| `when` | `kiedy` | a day code: `today`, `tomorrow`, `day_after_tomorrow`, `weekend`, `week`, a weekday (`monday` … `sunday`), a number of days or none. `kiedy` gets the Polish day name instead (`jutro`, `tydzien` …), so old templates like `{{ 'jutro' if kiedy == 'jutro' else 'dzisiaj' }}` still work |
| `text` | `tekst` | the full question, e.g. to extract a tram line number |

The Polish names keep older `router.yaml` files working; they come from the language pack
(`COMMAND_VARIABLE_ALIASES`). Example:
`command: "{{ 'What does ' ~ person ~ ' have ' ~ when ~ '?' if person else text }}"`.

### Answer model prompts {#answer-model-prompts}

The default prompts are built into the integration. You can override them in `router.yaml`
with the fields `answer_prompt` (answer from data) and `summary_prompt`
(summary). In the text you can use the fields `{household}`, `{now}` (date and
time in the pack's language) and `{sentences}`. The defaults come from the language
pack.

## How to add a new topic (step by step) {#new-topic}

Example: questions about the washing machine and dryer, e.g. “How much longer will the wash
take?” or “Can I take the laundry out?”.

1. **Find the entities.** *Developer tools → States*, search e.g. for
   `washing_machine`. Check whether the information you need is in the *state* (e.g.
   “time remaining: 25 min”) - then `entities` is enough - or in the
   *attributes* (lists, timetables) - then use `details`.
2. **If the data comes from a service** (calendar, forecast), try it in
   *Developer tools → Actions* with “Return response” checked. The same action with the same
   data goes into `fetch`; use `{start}` and `{end}` instead of
   dates.
3. **Add the topic:**

   ```
     laundry:
       description: washing machine, dryer, is the laundry done, how much longer
       examples: ["Is the dryer done?", "How much longer will the wash take?"]
       entities: [sensor.washing_machine_*, sensor.dryer_*]
   ```
4. **Save and ask** freely. In the CSV file, in the `route` column, you will
   see e.g. `laundry + 12 encji + odpowiedź` (12 entities + answer; the labels come from
   the language pack), and for `details` and `fetch`
   `school + 1 źródeł + odpowiedź` (1 source + answer).
5. **If the router picks the wrong topic**, improve the `description` and add
   the question from the log to `examples`.
6. **If the answer is wrong but the topic is right**, look at what the model received:
   the data is too long (add `drop`, `days`, `limit`), the answer is
   missing from it (add an entity), or it contains similar, confusing entities (exclude them with
   `!pattern`). `tools/compare_sources.py` helps ([Testing and choosing models](good-practice.md#testing)).

**Good practices**

- Fewer, clearly distinct topics work better than many similar ones. One “car” topic with all the
  car's sensors is better than three separate ones.
- Give the model complete data, e.g. a timetable with the time of every lesson. Then it will also
  answer questions you did not anticipate (“How many hours is Olivia at school?”).
- For data with dates, set `days` so that a question without a day does not pull in the
  whole week.
- Put the most important patterns first: the 80-entity limit cuts from the end.

Ready examples of questions and commands step by step (gaming, cameras, private mode, heating, podcasts) are in
[Recipes](recipes.md#recipes).

## Example router.yaml {#example}

The `router.example.yaml` file in the repository describes a made-up home: Tom, Anna
and two kids, Olivia and Jack. Entities are named the way popular integrations usually name them:
the HA mobile app (phone location), Frigate (cameras), Met.no (weather), calendars, a car, a robot
vacuum, a washing machine and shopping lists. Just replace the entity names with your own
(*Developer tools → States*). The same home with Polish descriptions, examples and
`match` patterns - ready for the bundled Polish pack - is
`router.example.pl.yaml`.

| Topic | Data source | What it shows |
| --- | --- | --- |
| `daily_summary`, `good_night` | `personal`, `details` + `fetch` | a summary for the speaker; `answer_hint` / `answer_hints` |
| `calendar` | `fetch`: `calendar.get_events`, `merge` | several calendars in one list, day from the question, 30 days if no day given |
| `school` | `details` or `fetch` | timetable trimmed to the child and day; two e-gradebook variants |
| `weather` | `entities` + 2 × `fetch` | sensor reading plus daily and hourly forecast (`limit: 24`) |
| `sensors` | `entities` with `|class` | sensors by `device_class`, exposed only |
| `windows_doors` | `entities` | windows, doors, garage and blinds with the “since when” time |
| `people` | `entities` + `details` | household members, Frigate cameras, motion, address from the phone; pattern order |
| `car` | `entities` | all car sensors - the model picks |
| `lights` | `entities`, `skip_states`, `!` | only lights that are on, excluding the tablet screen |
| `media` | `entities`, `skip_states` | only players that are playing something |
| `lists` | `entities: [todo.*]` | list items (the integration calls `todo.get_items` itself) |
| `transport` | `details` | departures from stops, from attributes |
| `devices` | `entities`, `unavailable: true` | sockets and switches, unavailable ones included |
| `unclear` | `unclear: true` | speech recognition gibberish: a “Did you mean…?” suggestion or a request to repeat |
| `control`, `knowledge`, `other` | - | commands, Wikipedia, fallback agent |

```
# Example router.yaml for Assist Router - copy it to /config/assist/router.yaml
# and adapt the entities to your home (Developer tools → States).
#
# LANGUAGE: the assistant understands and answers in the language of the active language
# pack. The bundled pack is Polish, so a working setup today uses Polish descriptions,
# examples and `match` patterns - see router.example.pl.yaml for the same file in Polish.
# This English file is the reference for the structure; write the texts in the language
# your household speaks (a pack for it has to exist - see "Adding a language" in the docs).
#
# The example home: Tom (dad), Anna (mom), and the kids Olivia and Jack. Entities are named
# the way popular integrations usually name them: the HA mobile app (phone location),
# Frigate (cameras), Met.no (weather), Google/CalDAV calendars, a car, robot vacuum and
# washing machine integration. All entity names are examples.
#
# How the router uses this file:
#   1. The router model picks ONE topic from `topics` (based on description and examples).
#   2. The code extracts the people (`people`) and the day ("tomorrow", "on Friday") from
#      the question.
#   3. The topic collects data: entity states (entities), entity attributes (details) and
#      service responses (fetch) - trimmed to the person and day in the question.
#   4. The answer model answers the question using only this data.
# Changes to the file take effect immediately, without restarting HA.

# --- General settings ----------------------------------------------------------------

# language: pl              # language pack; default: HA's language if there is a pack for it,
#                           # otherwise pl. An unknown code disables the router (error in the log).

# Who lives in the home - goes into the prompts (the model knows that "mom" is Anna and
# "the kids" are Olivia and Jack).
household: >-
  Household: Tom (dad, asks most often), Anna (mom), kids: Olivia (Liv, 10 years old)
  and Jack (7 years old).

# People in questions. `match` is word beginnings (regex), so inflected forms match too
# (in Polish: "Oli", "Olą" for "Ola"). A person from the question trims data that has a
# `child` or `person` key (e.g. only Olivia's timetable). A question without a name
# ("the kids") - everyone's data.
# With speaker recognition (the Assist Speaker ID integration) a first-person question
# ("What do I have tomorrow?") is about whoever is speaking. Extra person fields:
#   speaker - their voice identifier in Assist Speaker ID (defaults to the person key, e.g. "olivia"),
#   owns    - their entities (e.g. work calendar, phone): skipped when asking about another person;
#             entities owned by no one (family calendar) - always included,
#   labels  - the same with Home Assistant labels (Settings -> Entities): entities with one of
#             these labels belong to the person (e.g. a CalDAV / Google calendar),
#   room    - their room: "turn off the light in my room" from this person = this area.
people:
  tom:
    name: Tom
    match: "tom|dad"
    owns: [calendar.tom_work, sensor.tom_phone_*]
    labels: [tom]
  anna:
    name: Anna
    match: "ann|mom|mum"
    owns: [sensor.anna_phone_*]
  olivia:
    name: Olivia
    match: "oliv|liv\\b"
    room: Olivia's room
  jack:
    name: Jack
    match: "jack"
    room: Jack's room

# Family terms relative to the speaker: "my brother" from Olivia = Jack, "my daughter" from
# Tom = Olivia, "my kids" from Anna = Olivia and Jack. "mom"/"dad" are fixed names (match above).
family:
  parents: [tom, anna]
  children: [olivia, jack]
  men: [tom, jack]

sentences: 4                # number of sentences in a Wikipedia summary
# wikipedia_language: pl    # Wikipedia edition; default: the language pack's language
only_exposed: false         # true = topic entities only from those exposed to Assist
control_model: answer       # parsing control commands: router or answer (the larger model)

# Control: for these devices the assistant always asks "Turn off …?" - also when they are
# part of a group command ("turn off all switches").
confirm_entities:
  - switch.fridge
  - switch.server_*
  - switch.*_camera_enabled     # camera switches (Frigate)
  - Wi-Fi router                # you can also give a device name

# "Play …": room -> players in order (first available). Music Assistant players often have
# no room - hence this list. With no room in the command: the room of the speaker you are
# talking to. An empty list or unavailable players = a reply that there is nothing to play on
# in that room (the assistant does not pick another speaker then).
music_players:
  Living room: [media_player.living_room_speaker, media_player.living_room_tv]
  Bedroom: [media_player.bedroom_speaker]
  Kitchen: [media_player.kitchen_speaker]

# Announcements (intercom) also play on these players (optional):
# announce_players: [media_player.living_room_homepod]

# --- Topics ---------------------------------------------------------------------------
#
# Topic keys (calendar, school…) are your own names; they only have to be unique.
#
# Topic data sources (can be combined):
#   entities  - entity_id patterns; the state goes to the model in the pack's language
#               ("open", "home"). `*` = any string, `|class1,class2` = only these
#               device_class values, `!pattern` = exclusion. Order matters (limit of 80 entities).
#   details   - patterns of entities whose ATTRIBUTES go to the model (lists, timetables, balances).
#   fetch     - services that return data (calendar.get_events, weather.get_forecasts…).
#               `{start}` and `{end}` = the day range from the question.
#   days      - the day when the question gives none. Day codes, the same in every language:
#               today, tomorrow, day_after_tomorrow, weekend, week (this week),
#               monday … sunday, or a number of days ("14" = today and the next 13 days).
#               The language pack's names work too (Polish: dzis, jutro, tydzien …).
#   drop      - attribute keys to skip (noise the model does not need).
#   skip_states - states to skip (e.g. lights that are off - only lights that are on remain).
#   unavailable - true = unavailable entities go to the model as "unavailable" instead of
#               being skipped (so the model does not answer "I have no information").

topics:
  # Summaries for the person asking (requires Assist Speaker ID; without it - for the whole family).
  # personal: with no name in the question, the speaker's data, and for a parent also the kids'.
  daily_summary:
    description: good morning, daily summary, what does my day look like, what's ahead of me today, plan for the rest of the day
    examples: ["Good morning", "What does my day look like?", "What's ahead of me today?"]
    personal: true
    days: today
    answer_tokens: 360
    answer_hint: >-
      This is a spoken daily summary. Talk to the person from "Asking:", by name, in plain
      sentences. Weather first, then their plan (lessons, events, chores). For a parent add
      one or two sentences about the kids' most important matters. Up to 6 sentences.
    details: [sensor.school_timetable, sensor.chores]
    fetch:
      - action: calendar.get_events
        entities: [calendar.family, calendar.tom_work]
        data: {start_date_time: "{start}", end_date_time: "{end}"}
        merge: events
      - action: weather.get_forecasts
        entities: [weather.home]
        data: {type: daily}

  good_night:
    description: good night, I'm going to bed, what's ahead of me tomorrow
    examples: ["Good night", "I'm going to bed", "What's ahead of me tomorrow?"]
    personal: true
    days: tomorrow
    # speaker-dependent instructions: person key, girl/boy, child/parent, unknown
    answer_hints:
      girl: >-
        In one or two sentences say what awaits her tomorrow (no house, no weather), then
        wish her good night by name, tenderly, like in a fairy tale, as to a princess.
      boy: >-
        In one or two sentences say what awaits him tomorrow (no house, no weather), then
        wish him a cheerful good night by name (e.g. recharging a superhero's batteries).
      parent: >-
        What awaits them tomorrow and the morning weather, what was left open or on at
        home, one sentence about the kids' tomorrow. End with "Good night". Up to 5 sentences.
      unknown: >-
        Briefly for the whole family, no names: what's tomorrow and what is open or on at home.
    details: [sensor.school_timetable]
    fetch:
      - action: calendar.get_events
        entities: [calendar.family, calendar.tom_work]
        data: {start_date_time: "{start}", end_date_time: "{end}"}
        merge: events
    entities: [binary_sensor.*_window, light.*]

  # Calendars: events from all calendars in one list, in order.
  # "What do we have on Friday?" -> Friday only; "When is grandma's birthday?" -> 30 days from today.
  calendar:
    description: plans, events, meetings, birthdays, name days, holidays, what we have planned, dates
    examples:
      - What do we have at the weekend?
      - How many work meetings do I have tomorrow?
      - When is grandma's birthday?
      - Is anything happening on Thursday?
    days: "30"
    drop: [description]           # meeting descriptions (video call links) just take up space
    fetch:
      - action: calendar.get_events
        entities: [calendar.family, calendar.tom_work, calendar.birthdays, calendar.holidays]
        data: {start_date_time: "{start}", end_date_time: "{end}"}
        merge: events             # one list from all calendars, sorted by time
        title: Calendar events (in order)
        limit: 60

  # School from the e-gradebook. Two typical variants - pick the one that fits:
  #  a) the integration provides an entity with attributes (children -> days -> lessons): `details`;
  #  b) the integration provides a lesson calendar for each child: `fetch` as for the calendar.
  school:
    description: school, timetable, when lessons start or end, when they get back from school, substitutions, cancelled lessons
    examples:
      - What time does Olivia go to school tomorrow?
      - Does Jack have PE tomorrow?
      - When do the kids finish school today?
    details: [sensor.gradebook_timetable]       # variant a)
    days: today                                 # no day in the question - today
    drop: [teacher_id, classroom_id]
    # fetch:                                    # variant b)
    #   - action: calendar.get_events
    #     entities: [calendar.lessons_olivia, calendar.lessons_jack]
    #     data: {start_date_time: "{start}", end_date_time: "{end}"}
    #     merge: events

  # Weather: current conditions from the balcony sensors, forecast from a service (daily and hourly).
  weather:
    description: outdoor weather now and the forecast, rain, wind, should I take an umbrella, what to wear, outside temperature
    examples:
      - Will it rain tomorrow?
      - Should I take an umbrella?
      - What should I wear at the weekend?
      - How many degrees is it outside?
    entities:
      - sensor.balcony_temperature
      - sensor.balcony_humidity
      - sensor.rain_gauge_*
    drop: [wind_bearing, uv_index, cloud_coverage, dew_point, pressure]
    fetch:
      - action: weather.get_forecasts
        entities: [weather.home]
        data: {type: daily}
        title: Forecast for the coming days
      - action: weather.get_forecasts
        entities: [weather.home]
        data: {type: hourly}
        title: Hourly forecast
        limit: 24                 # one day at most - more only slows the answer down

  # Room climate: sensors by type (device_class) and thermostats.
  sensors:
    description: temperature, humidity, CO2, indoor air quality, heating, thermostats, is it stuffy
    examples:
      - How warm is it in Olivia's room?
      - Where is the CO2 highest?
      - What is the heating in the living room set to?
    only_exposed: true            # only sensors exposed to Assist (no technical ones)
    entities:
      - sensor.*|temperature,humidity,carbon_dioxide,pm25,volatile_organic_compounds
      - climate.*

  # Windows, doors and blinds: opening sensors and blind position.
  windows_doors:
    description: which windows or doors are open, is everything closed, front door, balcony, garage, blinds
    examples:
      - Which windows are open?
      - Did I close the balcony door?
      - Since when has the bedroom window been open?
    entities:
      - binary_sensor.*|door,window,opening,garage_door
      - cover.*

  # Who is home and where: household members (person), address from the phone (HA mobile app),
  # Frigate cameras (number of people), motion sensors. Order: most important first.
  people:
    description: who is home, where someone is, is anyone in a room, where was there motion, how many people the cameras see
    examples:
      - Where is mom?
      - Is Jack home yet?
      - Is anyone in the living room?
      - How many people does the garden camera see?
    entities:
      - person.*
      - sensor.*_person_count                    # Frigate: number of people in frame
      - binary_sensor.*|motion,occupancy,presence
    details: [sensor.*_phone_geocoded_location]  # phone address (attributes: street, city)
    drop: [Location, Country, ISO Country Code, Postal Code, Time Zone, Areas Of Interest,
           Administrative Area, Sub Administrative Area, Ocean, Inland Water]

  # Car: all car sensors - the model picks what was asked about.
  car:
    description: car - fuel, range, mileage, consumption, service, is it locked, windows, tyres, where is it parked
    examples:
      - Do I need to fill up?
      - Did I lock the car?
      - Where did I park?
      - When is the car inspection?
    entities:
      - sensor.my_car_*
      - binary_sensor.my_car_*
      - lock.my_car_*
      - device_tracker.my_car_*

  # Lights: only those that are on (skip_states), excluding the tablet screen and speaker LED rings.
  lights:
    description: which lights are on, where is a light on, was a light left on, lamp brightness
    examples:
      - Did I leave a light on anywhere?
      - Which lamps are on in the kitchen?
    only_exposed: true
    entities:
      - light.*
      - "!light.*_screen"
      - "!light.*_led_ring"
    skip_states: ["off"]

  # What's playing: only players that are doing something.
  media:
    description: what's playing now, music, TV, speakers, what volume, is the TV on
    examples:
      - What's playing in the living room?
      - Is the TV on?
    only_exposed: true
    entities:
      - media_player.*
    skip_states: ["off", "idle", "standby"]

  # Robot vacuum, washing machine - state and time remaining.
  vacuum:
    description: vacuum, cleaning robot, has it finished, battery, filter, brushes
    examples: ["Has the vacuum finished?", "How much battery does the robot have?"]
    entities: [vacuum.*, sensor.vacuum_*]

  laundry:
    description: washing machine, dryer, is the laundry done, how long is left
    examples: ["Is the washing machine done?", "How much longer will the dryer run?"]
    entities: [sensor.washing_machine_*, sensor.dryer_*]

  # Lists (todo): list contents, not just the number of items (todo.get_items).
  lists:
    description: shopping list, what we need to buy, reminders, things to do
    examples: ["What's on the shopping list?", "Is milk on the list?"]
    entities: [todo.*]

  # Alarm and safety - read-only (leave arming the alarm to automations).
  alarm:
    description: alarm, is the alarm armed, protection mode, flooding, smoke, gas, is water leaking anywhere
    examples: ["Is the alarm armed?", "Has the smoke detector detected anything?"]
    entities:
      - alarm_control_panel.*
      - binary_sensor.*|moisture,smoke,gas,carbon_monoxide

  # Public transport: departures from stops (transit integrations keep a list of departures
  # in attributes). Without a day - everything in the data.
  transport:
    description: tram, bus, departures from a stop, when is the next tram
    examples: ["When is my number 8 tram?", "When does the bus leave from Park Street?"]
    details: [sensor.stop_*]
    drop: [html, original_departure]

  # State of other devices (sockets, switches).
  devices:
    description: is a device on - sockets, switches, chargers, aquarium
    examples: ["Is the aquarium on?", "Is the charger in the garage working?"]
    only_exposed: true
    unavailable: true             # unavailable ones too - "The mirror is unavailable"
    entities: [switch.*]

  # Commands HA did not recognize: parsed into an HA intent and executed
  # (with a confirmation question when in doubt). Details: documentation, "Home control".
  control:
    description: commands - turn on, turn off, switch on, switch off, set, dim, light color, blinds, warmer, louder, play music, vacuum, add to a list
    examples:
      - Make the bedroom light warm.
      - Lower the blinds halfway.
      - Play jazz in the kitchen.
      - Add milk to the shopping list.
    control: true

  # General knowledge: a summary of a Wikipedia article (3–4 sentences).
  knowledge:
    description: a general knowledge question - who was, what is, history, geography, science
    examples: ["Who was Nicolaus Copernicus?", "What is photosynthesis?"]
    search: wikipedia

  # Speech recognition gibberish: the words do not fit together. The assistant guesses what was
  # said ("Did you mean: turn on the mood scene in the living room?") or asks you to repeat.
  # State explicitly in the description what does NOT belong here - otherwise the router will
  # also put strange but meaningful questions here.
  unclear:
    description: a nonsensical sentence - the words do not fit together and neither a question nor a command can be understood; it looks garbled by speech recognition. NOT for questions and commands with one garbled word when the meaning is clear, nor for knowledge questions, chit-chat and jokes
    examples:
      - Glue mood in the lilac groom.
      - Drawer evening newspaper kitchen.
    unclear: true

  # Everything else - the fallback agent (chit-chat, jokes).
  other:
    description: everything else - chit-chat, jokes, requests, questions without data from the home
    examples: ["Tell me something interesting.", "How are you?"]
```
