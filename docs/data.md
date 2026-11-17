# Where the router gets its data

## Where the router gets its data {#data}

The router needs no special automations or Assist sentences. It takes data directly from Home
Assistant, and in `router.yaml` you only describe **which** entities and
services belong to a topic. The code does the rest: it picks out what was asked about, removes
noise and gives the answer model a concise list of facts.

<div class="flow">
<svg aria-label="Diagram: question, topic and person with day, data sources (entities, details, fetch), trimming, data, answer model" role="img" viewbox="0 0 900 470">
<defs><marker id="arrow2" markerheight="7" markerwidth="7" orient="auto-start-reverse" refx="9" refy="5" viewbox="0 0 10 10"><path d="M0,0 L10,5 L0,10 z"></path></marker></defs>
<rect class="box" height="66" rx="8" width="210" x="10" y="30"></rect>
<text text-anchor="middle" x="115" y="56">Question</text>
<text class="small" text-anchor="middle" x="115" y="76">“What time does Olivia go</text>
<text class="small" text-anchor="middle" x="115" y="89">to school tomorrow?”</text>
<rect class="box hot" height="52" rx="8" width="220" x="270" y="10"></rect>
<text text-anchor="middle" x="380" y="32">Router (model)</text>
<text class="small" text-anchor="middle" x="380" y="50">topic only: school</text>
<rect class="box" height="52" rx="8" width="220" x="270" y="72"></rect>
<text text-anchor="middle" x="380" y="94">Code</text>
<text class="small" text-anchor="middle" x="380" y="112">person: olivia · day: tomorrow</text>
<rect class="box" height="62" rx="8" width="330" x="560" y="36"></rect>
<text text-anchor="middle" x="725" y="60">Topic in router.yaml</text>
<text class="small" text-anchor="middle" x="725" y="80">school: details, fetch, entities, days, drop</text>
<rect class="box" height="70" rx="8" width="270" x="10" y="160"></rect>
<text text-anchor="middle" x="145" y="184">entities</text>
<text class="small" text-anchor="middle" x="145" y="203">entity states in plain words</text>
<text class="small" text-anchor="middle" x="145" y="218">“Living room window: open (12 min)”</text>
<rect class="box" height="70" rx="8" width="270" x="315" y="160"></rect>
<text text-anchor="middle" x="450" y="184">details</text>
<text class="small" text-anchor="middle" x="450" y="203">entity attributes</text>
<text class="small" text-anchor="middle" x="450" y="218">timetable, balance, departures, address</text>
<rect class="box" height="70" rx="8" width="270" x="620" y="160"></rect>
<text text-anchor="middle" x="755" y="184">fetch</text>
<text class="small" text-anchor="middle" x="755" y="203">services that return data</text>
<text class="small" text-anchor="middle" x="755" y="218">calendar.get_events, weather.get_forecasts</text>
<rect class="box hot" height="78" rx="8" width="880" x="10" y="275"></rect>
<text text-anchor="middle" x="450" y="299">Trimming (code, no model)</text>
<text class="small" text-anchor="middle" x="450" y="320">person: only items whose child/person matches “Olivia” · day: only date/datetime from tomorrow</text>
<text class="small" text-anchor="middle" x="450" y="338">no noise (html, avatars, colors, false) · local time and weekday · length limits</text>
<rect class="box" height="62" rx="8" width="400" x="10" y="395"></rect>
<text text-anchor="middle" x="210" y="419">Data for the model (concise YAML)</text>
<text class="small" text-anchor="middle" x="210" y="439">usually a few hundred to a few thousand characters</text>
<rect class="box hot" height="62" rx="8" width="420" x="470" y="395"></rect>
<text text-anchor="middle" x="680" y="419">Answer model</text>
<text class="small" text-anchor="middle" x="680" y="439">“Olivia goes in at 8:00 tomorrow, maths is first.”</text>
<path class="arrow" d="M220,52 L268,38" style="marker-end:url(#arrow2)"></path>
<path class="arrow" d="M220,74 L268,96" style="marker-end:url(#arrow2)"></path>
<path class="arrow" d="M490,36 L558,58" style="marker-end:url(#arrow2)"></path>
<path class="arrow" d="M490,98 L558,80" style="marker-end:url(#arrow2)"></path>
<path class="arrow" d="M640,98 C560,130 250,120 160,158" style="marker-end:url(#arrow2)"></path>
<path class="arrow" d="M700,98 C640,130 470,130 455,158" style="marker-end:url(#arrow2)"></path>
<path class="arrow" d="M760,98 L758,158" style="marker-end:url(#arrow2)"></path>
<path class="arrow" d="M145,230 L145,273" style="marker-end:url(#arrow2)"></path>
<path class="arrow" d="M450,230 L450,273" style="marker-end:url(#arrow2)"></path>
<path class="arrow" d="M755,230 L755,273" style="marker-end:url(#arrow2)"></path>
<path class="arrow" d="M210,353 L210,393" style="marker-end:url(#arrow2)"></path>
<path class="arrow" d="M410,426 L468,426" style="marker-end:url(#arrow2)"></path>
</svg>
</div>

### Three data sources {#three-data-sources}

| Topic field | What goes to the model | Typical examples |
| --- | --- | --- |
| `entities` | The state of every matching entity, in words, with the most important attributes: light brightness, blind position, thermostat temperature, what is playing, how long a sensor has been open. | windows and doors, lights, room sensors, car, people (`person.*`), motion, alarm, washing machine |
| `details` | Entity attributes, i.e. data you cannot see in the state itself: lists, timetables, balances, addresses. | school timetable from the e-gradebook, departures from a stop, phone address (`*_geocoded_location`), pocket-money accounts |
| `fetch` | The response of an HA service that returns data. The day range comes from the question. | calendars (`calendar.get_events`), forecast (`weather.get_forecasts`) |

You can combine all three in a single topic. The weather topic in the example takes the current
reading from sensors (`entities`) and the forecast from a service (`fetch`).

### How the code trims data {#how-the-code-trims-data}

- **Person.** A list item with a `child` or `person` key is
  kept only if it matches the person in the question (the `match` pattern from
  `people`, so “Olivia” also matches “Liv”). If the person from the question does
  not appear in the data at all (dad asking about the children's accounts), nothing is removed.
  A question about “the kids” or without a name gives everyone's data.
- **Day.** An item with a `date` or `datetime` key is kept
  only if it falls on the day from the question. If the question gives no day, the topic's
  `days` applies. Without `days`, data is not filtered by day. When there is
  nothing on that day (lessons on a Saturday), the model gets “none” (Polish pack: „brak”) instead
  of an empty list. The filter does not apply to the attribute root itself, because there `date` is
  usually the reading date.
- **Noise.** Skipped: html, avatars, colors, identifiers,
  `friendly_name`, `false` values (“cancelled: no”) and
  empty values, plus the keys listed in `drop`.
- **Time.** Times with a time zone (forecasts are in UTC) are converted to local
  time, and the weekday is added next to the date: `2026-10-24 12:00 (Saturday)` (the
  weekday name comes from the language pack - `sobota` in Polish). The model does not have
  to work out which day is Saturday.
- **Limits.** At most 80 entities in `entities` (in pattern order,
  so put the most important first), 40 list items (`limit` in `fetch`
  changes this per service) and 6000 characters per source.

### Day from the question {#day-from-the-question}

The language pack recognizes the day words in the question and turns them into a **day
code**. The codes are the same in every language and are what you write in `days:`
and what the `when` variable holds. The Polish words of the bundled pack are given in
brackets; in `days:` the Polish pack also accepts its own names (`dzis`,
`jutro`, `tydzien` …).

| In the question | Day code | Day range |
| --- | --- | --- |
| “today”, “now” („dziś”, „dzisiaj”, „teraz”) | `today` | today |
| “tomorrow”, “the day after tomorrow” („jutro”, „pojutrze”) | `tomorrow`, `day_after_tomorrow` | that single day |
| “on Monday” … “on Sunday” („w poniedziałek” … „w niedzielę”) | `monday` … `sunday` | the nearest such day (today, if it is today) |
| “at the weekend” („w weekend”) | `weekend` | the nearest Saturday and Sunday |
| “this week” („w tym tygodniu”) | `week` | today and the next 6 days |
| nothing | the topic's `days` | e.g. `today` or `"30"` (today and the next 29 days) |

### Step-by-step example: school timetable {#step-by-step-example-school}

Question: *“What time does Olivia go to school tomorrow?”*. The router picks the topic
`school`, and the code extracts the person `olivia` and the day `tomorrow`. The topic has `details: [sensor.gradebook_timetable]`. This entity's attributes contain
the whole week for both children, well over ten thousand characters:

```
{"friendly_name": "Timetable", "week_start": "2026-10-19",
 "children": [
   {"child": "Olivia", "avatar": "https://…", "color": "#f5ec00",
    "days": [
      {"date": "2026-10-22", "lessons": [{"start": "08:00", "subject": "Maths", "canceled": false}, …]},
      {"date": "2026-10-23", "lessons": [{"start": "08:00", "subject": "Maths", "canceled": false},
                                         {"start": "08:55", "subject": "Science", "canceled": true}, …]},
      …]},
   {"child": "Jack", "days": […]}]}
```

After trimming, the model gets only Olivia's tomorrow, without avatars, colors and
`canceled: false` (the state label and weekday names come from the language pack; English
shown here):

```
Timetable (state: 2026-10-22):
week_start: 2026-10-19 (Monday)
children:
- child: Olivia
  days:
  - date: 2026-10-23 (Friday)
    lessons:
    - start: 08:00
      subject: Maths
    - start: 08:55
      subject: Science
      canceled: true
```

The model's answer: *“Olivia goes in at 8:00 tomorrow, maths is first. Science at 8:55 is
cancelled.”* The model noticed the cancelled lesson on its own, because the `true` flag
stayed in the data.

### Example: several calendars at once {#example-several-calendars-at-once}

<div class="flow">
<svg aria-label="Diagram: four calendars, the calendar.get_events service with a day range, merge into one list sorted by time" role="img" viewbox="0 0 900 210">
<defs><marker id="arrow3" markerheight="7" markerwidth="7" orient="auto-start-reverse" refx="9" refy="5" viewbox="0 0 10 10"><path d="M0,0 L10,5 L0,10 z"></path></marker></defs>
<rect class="box" height="40" rx="8" width="190" x="10" y="10"></rect>
<text text-anchor="middle" x="105" y="35">calendar.family</text>
<rect class="box" height="40" rx="8" width="190" x="10" y="60"></rect>
<text text-anchor="middle" x="105" y="85">calendar.tom_work</text>
<rect class="box" height="40" rx="8" width="190" x="10" y="110"></rect>
<text text-anchor="middle" x="105" y="135">calendar.birthdays</text>
<rect class="box" height="40" rx="8" width="190" x="10" y="160"></rect>
<text text-anchor="middle" x="105" y="185">calendar.holidays</text>
<rect class="box" height="70" rx="8" width="250" x="260" y="70"></rect>
<text text-anchor="middle" x="385" y="94">calendar.get_events</text>
<text class="small" text-anchor="middle" x="385" y="113">“on Friday” → start: Friday 00:00</text>
<text class="small" text-anchor="middle" x="385" y="128">end: Saturday 00:00</text>
<rect class="box hot" height="110" rx="8" width="320" x="570" y="50"></rect>
<text text-anchor="middle" x="730" y="74">merge: events</text>
<text class="small" text-anchor="middle" x="730" y="96">08:00 (Friday) Family: parents' evening</text>
<text class="small" text-anchor="middle" x="730" y="113">11:45 (Friday) Work: client meeting</text>
<text class="small" text-anchor="middle" x="730" y="130">16:30 (Friday) Family: Sam's birthday</text>
<text class="small" text-anchor="middle" x="730" y="147">one list sorted by time, with source</text>
<path class="arrow" d="M200,30 C230,30 240,80 258,92" style="marker-end:url(#arrow3)"></path>
<path class="arrow" d="M200,80 L258,98" style="marker-end:url(#arrow3)"></path>
<path class="arrow" d="M200,130 L258,114" style="marker-end:url(#arrow3)"></path>
<path class="arrow" d="M200,180 C230,180 240,130 258,122" style="marker-end:url(#arrow3)"></path>
<path class="arrow" d="M510,105 L568,105" style="marker-end:url(#arrow3)"></path>
</svg>
</div>

Without `merge`, each calendar would be a separate source and the model would have to
put the events in order itself. With `merge`, the question “What do we have on Friday?”
gets a ready-made plan for the day, and “When is grandma's birthday?” searches 30 days
(`days: "30"`).

**`fetch` safety.** The integration only calls services
that *only return data* (in HA: `SupportsResponse.ONLY`, e.g.
`calendar.get_events`, `weather.get_forecasts`,
`todo.get_items`). An entry with a service that does something (`lock.unlock`,
a script) is skipped with a warning in the log. A question never switches anything.

### What about automations with sentences? {#what-about-automations-with-sentences}

They are not needed. If you already have them, they can stay: HA checks them *before* the
router, so a sentence that exactly matches an automation gets an answer in a fraction of a second,
without a model. Any other phrasing goes to the router and the model answers it from the data. The
legacy `command` field (a template question for an automation) still works, but new
topics are better described with `entities`, `details` and `fetch`.

## Who is asking: recognized speaker (Assist Speaker ID) {#speaker}

With the [Assist Speaker
ID](https://github.com/witold-gren/home-assistant-assist-speaker-id) integration (speech-to-text that also recognizes the voice), the router knows who asked the
question. You only need to set its STT (“Speech-to-text with speaker”) in your pipelines. The agent
stays Assist Router, which reads the speaker by itself from the same pipeline run. First-person words,
family terms and the phrases below are recognized by the language pack (Polish words in brackets).

- **A first-person question without a name** (“What classes do *I* have
  today?”, “Show *my* grades”) is about the speaker. `details` are trimmed to their
  data, as if their name had been said.
- **A name in the question wins** (“What classes does Jack have?” from Olivia gives
  Jack's timetable). A question without the first person (“What is the timetable?”) stays for
  everyone. “We have” (Polish „mamy”) is not first person singular.
- **The answer model gets the line “Asking: Olivia.”** (Polish pack: „Pyta: …”), so it
  understands “I” and “my” as that person. The name comes from `people`, not from
  Assist Speaker ID.
- **Mapping a voice to a person:** the `speaker` field on the person.
  It defaults to the person key, so it is enough to save voice samples under the same identifiers
  (`olivia`, `jack`…).
- **Probable speaker** (Assist Speaker ID 0.2.0+): the voice did not reach the
  person's threshold, but the most similar person is close enough (option “Probable speaker
  from”). Where the answer depends on who asks (first person, `personal` topics, family
  terms, “my room”) the router uses that person and says so first: “I think it is Olivia asking.
  Today you have…” (Polish pack: „Wydaje mi się, że pyta Ola.”, `probable_speaker`).
  A recognized speaker is not named; a guess that changes nothing (“What's the weather?”, a
  name in the question) is not said. The fallback agent never gets a probable name.
- **Unknown speaker** (unfamiliar voice, utterance too short, text typed by hand)
  means everything works as without Assist Speaker ID.

**A person's entities and room (`owns`, `labels`, `room`):**

- **`owns`** are patterns of entities that belong to the person, e.g.
  their calendar or their phone's location. When a question is about a specific person (by name,
  or “I”, “my” from a recognized speaker), *other* people's entities are skipped in
  `details`, `fetch` and `entities`. Entities that belong to no
  one, e.g. the family calendar, are always included. So “What do I have tomorrow?” from Olivia
  gives the family calendar and her own, without dad's work calendar. This is needed because
  calendar events have no person field to trim by.
- **`labels`** do the same with Home Assistant labels: give the
  person `labels: [olivia]` and put the label “Olivia” on her entities in
  *Settings → Entities* (select the entity → labels). Handy for calendars from CalDAV or
  Google Calendar, which Home Assistant does not link to a person – a new calendar is assigned in
  the UI, without editing `router.yaml`. `owns` and `labels` can
  be combined. Set `personal: true` on the calendar topic, so a recognized speaker gets
  their own and the shared calendars even without “my” (a parent also gets the children's).
  When the person asked about has no calendar of their own while others do, the answer model is
  told so and says it, instead of “there are no events”.
- **`room`** is the person's room. “Turn off the light in my room” from
  that person means this area.
- **Family terms relative to the speaker** (the `family` section:
  `parents`, `children`, `men`). “My brother”, “my sister”, “my
  siblings” from a child, and “my son”, “my daughter”, “my kids” from a parent point to the right
  people, e.g. “my daughter” from dad means all daughters. They are added to the names in the
  question (“Are mom and my brother at home?”). “Mom”, “dad”, “wife” and “husband” remain fixed
  names in `match`.
- **The fallback agent** also gets the line “Asking: Olivia.” in its system prompt.
- **Automation sentences** are handled by HA before Assist Router, so they do not get
  the speaker directly. They can read it from the Assist Speaker ID “Last speaker” sensor, which
  stays fresh for a few seconds after recognition, e.g. with a macro in
  `custom_templates` (see the Assist Speaker ID README).

**Daily summary and “good night” for a person:** topics with
`personal: true` collect the speaker's data. “Good morning”, “What does my day look like?”,
“What's ahead of me today?” from a child give their lessons, tests, chores and calendar. From a parent
they give the parent's calendar and the weather, plus a short summary about the kids. How to structure
the answer is set by the topic's `answer_hint`. Example: the `daily_summary` and
`good_night` topics in `router.example.yaml`. Scenes with these names are only
run when asked explicitly (“Run the Good morning scene”). A plain “Good morning” is a greeting.

**Announcements (intercom):** a sentence starting with an announcement keyword (Polish
pack: „ogłoszenie”, „komunikat”, „do wszystkich”, „intercom”), e.g. “Announcement, kids, please come
to dinner”, goes neither to HA nor to the models. Assist Speaker ID plays the **speaker's
recording**, uncut and unchanged, on the other speakers, and the speaker that recorded it only
says “Announcement sent.” Additional players, e.g. HomePods, are set in `router.yaml` as
`announce_players: [media_player.…]`; with Assist Speaker ID 0.1.1+ one speaker plays per
room: an available player (e.g. a HomePod) instead of the satellite, and the announcing room gets
nothing. Without a recording (text typed by hand or no Assist Speaker ID) the sentence continues along
the normal path: HA reads it out with text-to-speech. The keyword must be at the start of the
sentence, so “What are the announcements in the school app?” is an ordinary question.

**Checking recognition:** “Who is speaking?”, “Who am I?”, “How do you recognize me?”,
“Whose voice is this?” (Polish pack: „Kto to mówi?”, „Kim jestem?”…). The assistant answers
immediately, without HA or models, from the result of that same utterance, e.g. “Olivia is speaking,
82 percent similarity. Next person: Jack, 35 percent.” The answer may also be “I'm not sure”, with the two most
similar voices, or “I don't recognize this voice” with the closest person, the similarity that
person needs (their threshold) and the next person - e.g. “Closest: Jack, 53 percent, recognition
needs 78 percent. Next person: Olivia, 50 percent.” A high threshold usually means somebody else in
the household has a similar voice. A short question (under 1 s of speech)
gets a request for a longer sentence, e.g. “Tell me who is talking to you now”.

## The assistant's character per pipeline (personas) {#personas}

Each Assist pipeline can have its own voice and wake word: „Hey Jarvis” with Jarvis's voice, Elsa in
the daughters' room, Optimus Prime for the son. The `personas` section tells the models who
the assistant is in a pipeline. Without it, and in pipelines it does not name, everything works as
before.

```
personas:
  jarvis:
    pipelines: [Hey Jarvis]          # a fragment of the pipeline name, or its id
    gender: male
    prompt: >-
      You are Jarvis, Tony Stark's super-intelligent system from Iron Man. You speak as a man,
      politely and with a touch of irony.
  elsa:
    voices: [pl_PL-elsa-medium]      # the pipeline's TTS voice - the character goes with the voice
    gender: female
    prompt: You are Elsa, the queen from Frozen. You speak as a girl, warmly and calmly.
```

- `prompt` - 1-2 sentences: who the character is and how it speaks. It is added at the
  end of the prompt of the answer model (HA data), the Wikipedia summaries and the fallback agent,
  with a note to speak in the character's style and grammatical gender but take facts only from the
  data. The topic router and the command parser do not get it, so understanding commands does not
  change.
- `gender` (`male` / `female`, optional) - the assistant's fixed
  replies in the character's form (in Polish: „źle zrozumiałam”, „nie znalazłam”, „nie jestem
  pewna”).
- `voices` and `pipelines` - how to find the pipeline (one is enough). The
  pipeline's TTS voice comes first, then a fragment of the pipeline name or its id (case does not
  matter). The first matching persona wins.

The pipeline is found from the run that handed over the sentence (satellites and the Assist dialog
in the browser). The `conversation.process` action has no pipeline, so the plain assistant
answers. Changes work as soon as the file is saved.
