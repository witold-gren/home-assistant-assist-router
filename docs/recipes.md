# Recipes: from a question to an answer {#recipes}

This page shows with ready examples how to add your own question or command. Every recipe has the same parts:
**what you say**, **what must be in Home Assistant**, **what to enter in the editor** and **what you hear**.
The examples are about the home of this documentation (Tom, Anna, Ola, Kuba); replace the entity names with yours
(*Developer tools → States*). The spoken sentences are in English here; with the Polish language pack you say them
in Polish.

## Two roads {#two-roads}

Every request to the assistant goes one of two roads:

| Road | Example | What the assistant does | What you add |
| --- | --- | --- | --- |
| **Question → answer** | "How long did Kuba play today?" | reads data from HA and answers; changes nothing | a topic with data in `router.yaml` (<b class="ui">Kind of topic</b>: <b class="ui">Answer</b>) |
| **Question → action → answer** | "Turn on the private mode" | does something in the home and says what it did | a script or a device exposed to Assist; `router.yaml` usually unchanged |

How to choose:

| You want to… | Do… | Recipe |
| --- | --- | --- |
| ask about something HA already knows (a state, a time, a count) | a topic with <b class="ui">Entities</b> | [Gaming](#gaming) |
| ask about something HA does not count yet | first an HA helper (history stats, template), then a topic | [Gaming](#gaming) |
| ask about camera events | a topic with the Frigate source | [Motion on the cameras](#motion) |
| run several steps with one sentence | a script with a description | [Private mode](#private-mode) |
| turn one device on or off | nothing, a name and an area in HA are enough | [Heating](#heating) |
| hear your own sentence after an action | an automation with a sentence and a response | [Your own answer after an action](#own-answer) |
| first do something (refresh), then answer from the result | an automation + a topic with a command | [New podcasts](#podcasts) |

## How to check every recipe {#check}

Always the same, before you save anything:

1. Type the sentence in the right column, in <b class="ui">Tester</b>, and click <b class="ui">Test</b>. The tester does
   nothing in the home.
2. See where the sentence went:
    - <b class="ui">1. Home Assistant</b> – HA understood it itself (built-in sentences or your automation);
    - <b class="ui">2. Router</b> – the chosen topic; a wrong topic is fixed in <b class="ui">What it answers (for the router model)</b>
      or by adding the question to <b class="ui">Example questions</b>;
    - <b class="ui">4. Control (plan)</b> – what would be turned on or run;
    - <b class="ui">5. Answer</b> – what you will hear.
3. Works? <b class="ui">Add to the tests</b>, then <b class="ui">Save…</b>. The router reads the file at once, without a restart.

## Question → answer {#question-answer}

The assistant answers **only from the data the topic points it to**. So the most important question is: *does HA
already have this information in some entity?* If yes – a topic is enough. If not – first a helper in HA that
computes it, and the model only reads it. The model counts poorly; HA counts exactly.

### Gaming: how long today and how much is left this week {#gaming}

**What you say:** "How long did Kuba play today?", "How much longer can Kuba play this week?"

Both questions are about the same thing, so it is **one topic** with two questions. Fewer but clear topics work
better than many similar ones.

**1. What must be in HA.** The playing time is counted by the **History stats** helper (*Settings → Devices &
services → Helpers → Create helper → History stats*): how long the console's entity was on. Two are needed – for
today and for this week – plus a weekly limit and what is left of it. The same in YAML (e.g. in `packages/`):

```yaml
input_number:
  kuba_gaming_limit:               # the limit for a week, changed in HA
    name: Kuba gaming limit
    min: 0
    max: 40
    step: 0.5
    unit_of_measurement: h

sensor:
  - platform: history_stats
    name: Kuba gaming today
    entity_id: switch.kuba_console # an entity that is "on" while the console runs
    state: "on"
    type: time
    start: "{{ today_at() }}"
    end: "{{ now() }}"
  - platform: history_stats
    name: Kuba gaming this week
    entity_id: switch.kuba_console
    state: "on"
    type: time
    start: "{{ today_at() - timedelta(days=now().weekday()) }}"   # from Monday
    end: "{{ now() }}"

template:
  - sensor:
      - name: Kuba gaming left this week
        unit_of_measurement: h
        state: >
          {{ [states('input_number.kuba_gaming_limit') | float(0)
              - states('sensor.kuba_gaming_this_week') | float(0), 0] | max | round(2) }}
```

Check in *Developer tools → States* that `sensor.kuba_gaming_today` has a sensible value, e.g. `1.75` (hours).

**2. What to enter in the editor.** <b class="ui">Topics of questions</b> → <b class="ui">+</b>:

- <b class="ui">Name of the topic</b>: `gaming`;
- <b class="ui">What it answers (for the router model)</b>: "gaming, console, games, computer, how long he played, how much
  he can play, gaming limit, screen time";
- <b class="ui">Example questions</b>: both sentences above and e.g. "Did Kuba play a lot today?";
- <b class="ui">Entities</b> → <b class="ui">Entity patterns</b>: `sensor.kuba_gaming_*` and `input_number.kuba_gaming_limit`
  – the green number next to each pattern should be above zero;
- <b class="ui">Hint for the answer model</b>: "Give times in hours and minutes: 1.75 h is 1 hour 45 minutes. A week
  starts on Monday."

In the file it looks like this:

```yaml
topics:
  gaming:
    description: gaming, console, games, computer, how long he played, how much he can play, gaming limit, screen time
    examples:
      - How long did Kuba play today?
      - How much longer can Kuba play this week?
    entities: [sensor.kuba_gaming_*, input_number.kuba_gaming_limit]
    answer_hint: >-
      Give times in hours and minutes: 1.75 h is 1 hour 45 minutes.
      A week starts on Monday.
```

**3. What you hear:** "Kuba played for 1 hour 45 minutes today." / "This week Kuba can still play for 3 hours and
30 minutes."

!!! tip "When more children play"
    Add the same helpers for Ola and the pattern `sensor.*_gaming_*`. So that a question about Kuba does not get
    Ola's data, give the entities to their people with `owns` in `people` (e.g. `owns: [sensor.kuba_gaming_*]`) –
    then a question with a name, and with speaker recognition also "how much longer can I play?", sees only that
    person's data.

### Motion on the cameras in the last 24 hours {#motion}

**What you say:** "Was any motion detected on a camera in the last 24 hours?", "Who was in front of the house
yesterday?"

**1. What must be in HA.** Cameras in **Frigate** (with person detection). The router asks Frigate for the events
directly, so no helpers are needed.

**2. What to enter in the editor.** A new topic as above (`cameras`, description: "cameras, motion, was anyone
there, who walked by, what the cameras saw, in front of the house, in the garden", examples). The Frigate source is
entered in the topic's <b class="ui">YAML</b> tab:

```yaml
topics:
  cameras:
    description: cameras, motion, was anyone there, who walked by, what the cameras saw, in front of the house, in the garden
    examples:
      - Was any motion detected on a camera in the last 24 hours?
      - Who was in front of the house yesterday?
    frigate:
      url: http://192.168.1.20:5000          # Frigate's address, port 5000 without a login
      cameras: {entrance: Entrance, garden: Garden}   # camera → name to speak
      labels: [person, car, dog, cat]        # what counts as motion (by default only person)
      days: 2                                # a question without a day: yesterday and today
    answer_hint: >-
      "The last 24 hours" is from this hour yesterday until now – do not count earlier events.
      When there was nothing, say so plainly.
```

`days: 2` takes yesterday and today – that covers the whole 24 hours, and the hint tells the model where to cut.

**3. What you hear:** "Yes, in the last 24 hours the Entrance camera saw a person twice: yesterday at 18:40 and
today at 7:55."

!!! note "Without Frigate"
    A motion sensor in HA only knows its state now. To answer about the last day, count the events with a
    **History stats** helper with `type: count`, `start: "{{ now() - timedelta(hours=24) }}"`, `end: "{{ now() }}"`
    and give that counter to the topic's <b class="ui">Entities</b>.

## Question → action → answer {#question-action-answer}

Commands are done by the topic with <b class="ui">Kind of topic</b> <b class="ui">Control</b> (in the example `router.yaml`
it is `control`). If you have it, **you add nothing to `router.yaml`** – the router finds the device or the action
by its name, area and description. Your work is in Home Assistant. Details: [Home control](control.md#control).

### Private mode: several steps with one sentence {#private-mode}

**What you say:** "Start the private mode", "Turn on privacy", "I want some privacy".

**1. What must be in HA.** A **script** that does all the steps, with a **description** – the model chooses an
action by its description, so any wording works, not only the words written down:

```yaml
script:
  private_mode:
    alias: Private mode
    description: >-
      Turns on the private mode (privacy): turns off the cameras in the home and their recording.
    sequence:
      - action: switch.turn_off
        target: {entity_id: [switch.camera_living_room, switch.camera_kitchen]}
      - action: input_boolean.turn_on
        target: {entity_id: input_boolean.private_mode}
```

Then:

- expose the script to Assist (*Settings → Voice assistants → Expose*);
- give it the alias "Privacy" (in the same window) – "turn on privacy" then hits the name directly;
- let the first sentence of the description say what it does – the model sees the first 160 characters.

**2. What to enter in the editor:** nothing. Only check in <b class="ui">Tester</b>: <b class="ui">4. Control (plan)</b> should
show running `script.private_mode`. If the assistant should always ask before running it, add the script in
<b class="ui">Settings</b> → <b class="ui">Ask before</b> → <b class="ui">Entities and devices</b>.

**3. What you hear:** "Started: Private mode." (the words come from the language pack; the Polish one says
"Uruchomiono: Tryb prywatny.")

!!! warning "Turning the mode off is another script"
    The router always **runs** an action – "turn off the private mode" would run the same script again. Make a
    second script, e.g. "Private mode – off", with the description "Turns off the private mode: turns the cameras
    back on…".

### Heating in the bathroom: one device {#heating}

**What you say:** "Turn off the heating in the bathroom", "Make it warmer in the bathroom".

**1. What must be in HA.**

- a thermostat (e.g. `climate.bathroom`) in the **Bathroom** area;
- exposed to Assist;
- if its name differs from what you say ("Bathroom radiator"), the alias "heating".

Floor heating on a switch (`switch.*`) needs the same.

**2. What to enter in the editor:** nothing. In <b class="ui">Tester</b> you usually see <b class="ui">1. Home Assistant</b>: HA
understood the command itself (the built-in sentence "turn off {name} in {area}"). When you say it differently, the
control topic does it – "warmer" raises the temperature by 1°.

**3. What you hear:** HA's answer, e.g. "Turned off the heating.", or the router's: "Turned off: Bathroom heating."

### Your own answer after an action {#own-answer}

After a script the router speaks briefly: "Started: Private mode." If you want to hear more – e.g. which cameras
were turned off – make an **automation with a sentence** that runs the action and sets the answer:

```yaml
automation:
  - alias: Assistant – private mode
    triggers:
      - trigger: conversation
        command:
          - "(start|turn on) [the] (private mode|privacy)"
    actions:
      - action: script.private_mode
      - set_conversation_response: >-
          Private mode is on. The cameras in the living room and the kitchen are not recording.
```

HA checks automations **before** the router, so these sentences get this answer at once, without a model.
`(a|b)` is one of the words, `[a]` an optional word. Another wording ("I want some privacy") still goes to the
router and runs the script – only with the short answer.

### New podcasts: an action first, then an answer from its result {#podcasts}

**What you say:** "Are there any new podcasts?", "What's new in the podcasts?"

Here the assistant must **do something first** (refresh the feeds) and **then answer from the result**. This is
what a topic with a **command** is for: the router recognises the topic by any wording, sends the command's sentence
to HA, and the automation does the action and returns the data the model makes the answer from.

**1. What must be in HA.** The podcast feeds as sensors, e.g. from the **Feedparser** integration (HACS):
`sensor.podcast_*`, with the episodes in the `entries` attribute. The automation refreshes them and returns the
newest episode of each feed:

```yaml
automation:
  - alias: Assistant – new podcasts
    triggers:
      - trigger: conversation
        command: "check new podcasts"
    actions:
      - action: homeassistant.update_entity
        target: {entity_id: [sensor.podcast_coffee_and_science, sensor.podcast_history]}
      - delay: 3
      - set_conversation_response: >-
          {% for s in ['sensor.podcast_coffee_and_science', 'sensor.podcast_history'] %}
          {%- set e = (state_attr(s, 'entries') or [{}])[0] %}
          {{ state_attr(s, 'friendly_name') }}: {{ e.title | default('no episodes') }}, {{ e.published | default('') }}.
          {% endfor %}
```

**2. What to enter in the editor.** The topic `podcasts` (description: "podcasts, new episodes, what's new in the
podcasts, shows", examples) and in the <b class="ui">YAML</b> tab the command – the automation's sentence:

```yaml
topics:
  podcasts:
    description: podcasts, new episodes, what's new in the podcasts, shows
    examples:
      - Are there any new podcasts?
      - What's new in the podcasts?
    command: "check new podcasts"
    answer_hint: >-
      A new episode is one from the last 7 days (compare its date with today). Name the new ones: the podcast
      and the title. When there is none, say so briefly.
```

Leave <b class="ui">Read HA's answer as it is</b> off: then the model gets the automation's list as data and decides
itself what is new. Turn it on when the automation already returns a finished sentence to read.

**3. What you hear:** "Yes, there are two new episodes: in Coffee and Science 'How dolphins sleep' from yesterday,
and in History 'The Battle of Grunwald' from Monday."

!!! tip "When a command, when data"
    If the feeds refresh by themselves (e.g. every hour), no command is needed: a topic with
    <b class="ui">Attributes</b> → <b class="ui">Entities whose attributes go to the model</b>: `sensor.podcast_*` and the same
    hint is enough. A command is for questions that need something **done** first.

## When a recipe does not work {#troubleshooting}

| What you see in the tester | What to do |
| --- | --- |
| <b class="ui">2. Router</b> chose another topic | add the words of the question to <b class="ui">What it answers (for the router model)</b> and the question itself to <b class="ui">Example questions</b> |
| the topic is right, but the answer is "I have no information" | open the model's data in <b class="ui">4. Data</b>: an entity is missing (a pattern with 0) or the value is `unknown` |
| the answer counts wrong (times, differences) | count it in HA with a helper (template, history stats), give the model the finished number |
| <b class="ui">4. Control (plan)</b> picks the wrong device | fix the name or alias in HA, check the area; give a script a clearer description |
| the command does nothing | the entity or the script is not exposed to Assist |
| the automation does not run | the sentence must match exactly; check it in <b class="ui">Commands of Home Assistant</b> → <b class="ui">What Home Assistant recognizes</b> |

More about the topic's fields: [The router.yaml file](router-yaml.md#topic-fields), about data:
[Where the router gets data](data.md#data), about commands: [Home control](control.md#control).
