# FAQ

## The editor and the router {#editor-faq}

| Message or symptom | Cause and what to do |
| --- | --- |
| No “Assist Router editor” in the sidebar | The panel appears after restarting HA once the integration is installed or updated, and only for administrators. After the restart reload the page (Ctrl+Shift+R). |
| “The router will not read this text: …” | The draft has an error that would turn the router off; the window says why (e.g. a persona without a prompt). Fix it in the form or in YAML; saving waits. |
| `expected ',' or ']', but got '?'` | A text with `?` or `:` in a list in brackets without quotes: `[Will it rain?]`. Write `["Will it rain?"]`. The form does it itself. |
| “router.yaml was changed outside the editor meanwhile” | Someone changed the file (another editor, File editor, Samba) since the draft began. The window of saving shows the differences; *Save anyway* overwrites that change, and *Discard draft* reads the file again. |
| “The preview waits until the router reads the text: …” | The preview of sources is made on a text the router can read. Fix the error after the colon. |
| “This change was not made: Nothing can be added here…” | The part the form adds to is a text or a list (e.g. `people: none`). Make it a mapping in the YAML tab (`people:` with people under it). |
| “This service may change something: the router never calls it from a topic” | Only services that just return data (e.g. `calendar.get_events`) work in `fetch`. Pick one of the suggested. |
| “The service returned nothing (or failed…)” | The service answered with an empty list or an error; the details are in the HA log (`Router fetch … failed`). Check its entities and data. |
| “the router cannot fill {who}” | A prompt of the settings has a word in braces the router does not know. `{household}`, `{now}` and `{sentences}` are allowed; write a plain brace twice: `{{`, `}}`. |
| “Error: The Assist Router agent is not running” | The tester, the unrecognized sentences and the tests need the integration running. Check that Assist Router is loaded (Settings → Devices & services). |
| “The router has no model set” | The integration's options have no Ollama URL or router model. |
| “No topic (the model did not answer or answered wrong)” | Ollama is off, the model did not fit in memory, or it answered out of format. Try again; the details are in the HA log. |
| “Home Assistant has no handler of …” | The sentence goes to an intent HA cannot carry out. Choose a known intent (e.g. `HassTurnOn`) or add an `intent_script` of that name in `configuration.yaml`. |
| “Unable to find end of group”, “Unable to find end of optional” | A sentence misses its closing `)` or `]`. The file is not saved while the sentence is wrong. |
| “router_tests.yaml is not a test set: …” | The test file has another layout. Expected: `tests:` with a list, each item with `sentence` and `topic` or `intent`. Fix the file or delete it; the editor makes a new one. |

## Trying it and developing {#make-faq}

| Message or symptom | Cause and what to do |
| --- | --- |
| “Docker is not running - start Docker Desktop and try again” / “Docker not found” | `make demo`, `make docs` and `make docs-serve` run in Docker only. Install and start Docker Desktop, wait until it runs, run the command again; `make doctor` shows what is missing. |
| “uv not found - install it: …” | The developer's environment (`make setup`, `make test`, `make lint`) is made by uv, which fetches Python 3.14 itself. Install uv with the command in the message and open a new terminal. Trying the editor needs no uv. |
| `make: *** No rule to make target 'ui'` | `make ui` was the old name of the demo and is gone. Use `make demo`. |

## While building a topic {#problems}

| What you see | Why | What to do |
| --- | --- | --- |
| **0** beside an entity pattern | The pattern fits no entity. | Check the entity id in Home Assistant; <b class="ui">Entities whose attributes go to the model</b> takes patterns of entities, not names of attributes. |
| <b class="ui">Kind of topic</b>: <b class="ui">No data (conversation)</b> | The topic has no source of data. | Add <b class="ui">Entity patterns</b> or a service under <b class="ui">Data</b>. |
| The tester chooses another topic | The description or examples are close to another topic. | Add words to <b class="ui">What it answers (for the router model)</b> and real questions to <b class="ui">Example questions</b>. |
| <b class="ui">Check</b>: "The router will not read this text:" | The text in the YAML tab is not valid YAML. | Fix the line of the message or undo (<kbd>Ctrl</kbd>+<kbd>Z</kbd>). |
| "router.yaml was changed outside the editor meanwhile." | The file was changed elsewhere after the draft began. | <b class="ui">Save anyway</b> overwrites those changes; the save window shows the differences. |
| "Home Assistant has no handler of …" | The intent is not built in and has no `intent_script`. | Choose a known intent or add an `intent_script`. |
| The browser warns that the tab uses a lot of energy or memory | Up to 0.1.6 the editor read `router.yaml` again on every change of a state in the home. | Update to 0.1.7 or later and load the tab again. |
| No panel in the sidebar | The account is not an administrator, or the panel is hidden. | Open `/assist-router-editor` or turn on <b class="ui">Show the editor in the sidebar</b>. |

Every field and option is described in [The editor on a computer](editor.md#editor).
