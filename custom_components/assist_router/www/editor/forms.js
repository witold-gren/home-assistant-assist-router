// The forms of the editor: a topic (what it answers, its kind, how to answer and from which data), the people,
// the family, the personas, music in rooms, announcements, devices to ask about first and the settings. Every
// change writes one value of the text through fields.js, so the rest of the file stays as it was.

import { LitElement, css, html, nothing } from "../vendor/lit-all.min.js";
import { fieldLines, renameKey, setField, setListItem } from "./fields.js";
import { translate } from "./i18n.js";
import { KIND_ICONS, SETTINGS_KEYS, SETTINGS_PATH, SOURCE_KEYS, nodeKey, topicKind } from "./outline.js";
import { freeKey, keysAt, pairAt, readDocument, valueAt } from "./source.js";
import { callWS } from "./ws.js";

const FORM_TAG = "assist-router-form";
// Answer hints for kinds of speakers; hints for single people are keyed by the person.
export const HINT_KEYS = ["parent", "child", "girl", "boy", "unknown"];
export const DAY_CODES = [
  "today",
  "tomorrow",
  "day_after_tomorrow",
  "weekend",
  "week",
  "monday",
  "tuesday",
  "wednesday",
  "thursday",
  "friday",
  "saturday",
  "sunday",
];
// The kinds a topic can be made: "answer" answers from data of the home, or without it when there is none.
export const TOPIC_KINDS = ["answer", "control", "knowledge", "unclear"];
// What the prompts of the settings may hold in braces.
export const PROMPT_VALUES = ["household", "now", "sentences"];
// The preview of a topic's data waits this long after typing.
export const PREVIEW_MS = 500;
export const PAST_MODES = ["drop", "mark"];
// A service added to a topic starts as this, with no entities yet (so nothing is called).
export const NEW_FETCH = { action: "calendar.get_events", entities: [] };
// Keys the router and the family refer to by name: plain words only.
const PLAIN_KEY = /^[a-z0-9_]+$/;

/** Which form a node of the tree has, or null when it has none (its YAML is edited instead). */
export function formFor(path) {
  if (!path?.length) return null;
  const [first] = path;
  if (path.length === 1) {
    if (first === SETTINGS_PATH[0] || SETTINGS_KEYS.includes(first)) return "settings";
    if (first === "@unrecognized") return "unrecognized";
    if (first === "@tests") return "tests";
    const forms = {
      household: "household",
      people: "people",
      family: "family",
      personas: "personas",
      music_players: "music",
      announce_players: "announce",
      confirm_entities: "confirm",
    };
    return forms[first] ?? null;
  }
  if (path.length === 2) return { topics: "topic", people: "person", personas: "persona", music_players: "room" }[first] ?? null;
  if (path.length === 3 && first === "@sentences") return "sentences";
  return null;
}

/** The text with a topic made one kind: its flag set and the flags of the other kinds taken out. */
export function setTopicKind(text, path, kind) {
  const flags = { control: ["control", true], unclear: ["unclear", true], knowledge: ["search", "wikipedia"] };
  let next = text;
  for (const [name, [key, value]] of Object.entries(flags)) {
    next = setField(next, [...path, key], name === kind ? value : undefined);
  }
  return next;
}

/** A key made of a name: small letters, digits and `_` ("Pokój Oli" → "pokoj_oli"). */
export function keyFromName(name, fallback = "item") {
  const key = String(name ?? "")
    .replace(/ł/g, "l")
    .replace(/Ł/g, "L")
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
  return key || fallback;
}

/**
 * Where the `match` of a person finds something in a text, as the router looks (start of a word, any case,
 * `\b` around letters with Polish marks too): `{ found }` with the matching words, or `{ error }`.
 */
export function matchSample(match, name, sample) {
  const pattern = match || String(name ?? "").toLowerCase().slice(0, 4).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const word = "[\\p{L}\\p{N}_]";
  const edge = `(?:(?<=${word})(?!${word})|(?<!${word})(?=${word}))`;
  try {
    const regex = new RegExp(`${edge}(?:${pattern.replace(/(?<!\\)\\b/g, edge)})`, "giu");
    return { found: [...String(sample ?? "").matchAll(regex)].map((found) => found[0]).filter(Boolean) };
  } catch (err) {
    return { error: err.message };
  }
}

/** Words in braces of a prompt that the router does not fill (it would fail on them). */
export function unknownPromptValues(prompt) {
  return [...String(prompt ?? "").matchAll(/\{([^{}]*)\}/g)].map((found) => found[1]).filter((name) => !PROMPT_VALUES.includes(name));
}

const asList = (value) => (Array.isArray(value) ? value.map(String) : value == null || value === "" ? [] : [String(value)]);

class AssistRouterForm extends LitElement {
  static properties = {
    text: { attribute: false },
    path: { attribute: false },
    hass: { attribute: false },
    languages: { attribute: false },
    _typing: { state: true },
    _error: { state: true },
    _renameError: { state: true },
    _pipelines: { state: true },
    _sample: { state: true },
    _hintKeys: { state: true },
    _preview: { state: true },
    _fetched: { state: true },
    _services: { state: true },
  };

  constructor() {
    super();
    this._typing = {};
    this._hintKeys = [];
    this._sample = "";
  }

  _t(key, values, fallback) {
    return translate(this.hass?.language, key, values, fallback);
  }

  willUpdate(changed) {
    if (changed.has("path") && nodeKey(changed.get("path") ?? []) !== nodeKey(this.path ?? [])) {
      this._typing = {};
      this._error = null;
      this._renameError = null;
      this._hintKeys = [];
      this._dataError = null;
    } else if (changed.has("text") && this.text !== this._emitted) {
      // The text changed elsewhere (undo, the YAML): the fields show it again.
      this._typing = {};
    }
    if (changed.has("text") || !this._doc) this._doc = readDocument(this.text ?? "").doc;
  }

  updated(changed) {
    if (formFor(this.path) === "topic" && (changed.has("text") || changed.has("path"))) this._schedulePreview();
    if (formFor(this.path) === "topic" && !this._services) this._loadServices();
    // A setting chosen in the tree is shown in the form of all the settings.
    if (changed.has("path") && this.path?.length === 1 && SETTINGS_KEYS.includes(this.path[0])) {
      this.renderRoot.querySelector(`[data-field="${this.path[0]}"]`)?.scrollIntoView?.({ block: "center" });
    }
    if (!this._pipelines && ["persona", "personas"].includes(formFor(this.path))) this._loadPipelines();
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    clearTimeout(this._previewTimer);
  }

  // The preview of the data sources --------------------------------------------------------------------

  _schedulePreview() {
    const key = `${this.path[1]}\n${this.text}`;
    if (this._preview?.key === key) return;
    if (this._fetched && this._fetched.topic !== this.path[1]) this._fetched = null;
    clearTimeout(this._previewTimer);
    this._previewTimer = setTimeout(() => this._runPreview(key), PREVIEW_MS);
  }

  async _runPreview(key) {
    const topic = this.path?.[1];
    const text = this.text;
    try {
      const data = await callWS(this.hass, { type: "assist_router/editor/sources", text, topic });
      if (text === this.text) this._preview = { key, data };
    } catch (err) {
      if (text === this.text) this._preview = { key, error: err.message ?? String(err) };
    }
  }

  /** The answers of the topic's services, asked for with the button (they may take a few seconds). */
  async _fetch() {
    const topic = this.path[1];
    this._fetched = { topic, loading: true };
    try {
      const data = await callWS(this.hass, { type: "assist_router/editor/sources", text: this.text, topic, fetch: true });
      this._fetched = { topic, data, at: new Date() };
    } catch (err) {
      this._fetched = { topic, error: err.message ?? String(err) };
    }
  }

  async _loadServices() {
    this._services = [];
    try {
      this._services = (await callWS(this.hass, { type: "assist_router/editor/services" })) ?? [];
    } catch {
      this._services = [];
    }
  }

  async _loadPipelines() {
    this._pipelines = [];
    try {
      const result = await callWS(this.hass, { type: "assist_pipeline/pipeline/list" });
      this._pipelines = result?.pipelines ?? [];
    } catch {
      this._pipelines = [];
    }
  }

  // Writing --------------------------------------------------------------------------------------------

  _emit(text, coalesce, path = null) {
    if (text === this.text && !path) return;
    this._emitted = text;
    this.dispatchEvent(new CustomEvent("edit", { detail: { text, coalesce, path } }));
  }

  _errorText(err) {
    const own = ["one_key", "lost", "not_a_map", "key_taken", "key_empty", "key_format"];
    return own.includes(err.message) ? this._t(err.message) : (err.message ?? String(err));
  }

  _apply(change, coalesce = null) {
    try {
      const next = change(this.text);
      this._error = null;
      if (typeof next === "string") this._emit(next, coalesce);
      else this._emit(next.text, coalesce, next.path);
    } catch (err) {
      this._error = this._errorText(err);
    }
  }

  _get(path) {
    const value = valueAt(this._doc, path);
    // A person written as a name only (`ola: Ola`).
    if (value === undefined && path.at(-1) === "name") {
      const owner = valueAt(this._doc, path.slice(0, -1));
      if (typeof owner === "string") return owner;
    }
    return value;
  }

  /**
   * A value written to the text: an empty text or list takes the key out, and mappings left empty go too. While
   * a field is typed in (`live`), an empty one keeps its key, so the line does not move; leaving it takes it out.
   */
  _set(path, value, { keepEmpty = false, live = false } = {}) {
    let clean = value;
    if (typeof value === "string") clean = value.trim() || undefined;
    if (Array.isArray(value)) clean = value.length || keepEmpty ? value : undefined;
    if (live && clean === undefined) {
      if (!pairAt(this._doc, path)) return;
      clean = Array.isArray(value) ? [] : "";
    }
    this._apply((text) => {
      const owner = path.slice(0, -1);
      const ownerValue = valueAt(readDocument(text).doc, owner);
      if (owner[0] === "people" && owner.length === 2 && typeof ownerValue === "string") {
        // A person written as a name only gets the other fields on lines of its own.
        const whole = { name: ownerValue, [path.at(-1)]: clean };
        if (clean === undefined) delete whole[path.at(-1)];
        return setField(text, owner, whole);
      }
      let next = setField(text, path, clean);
      for (let up = owner; clean === undefined && up.length > 2; up = up.slice(0, -1)) {
        const left = valueAt(readDocument(next).doc, up);
        if (left == null || (typeof left === "object" && !Object.keys(left).length)) next = setField(next, up, undefined);
        else break;
      }
      return next;
    }, `form:${nodeKey(path)}`);
  }

  _shown(path, value) {
    const key = nodeKey(path);
    return key in this._typing ? this._typing[key] : value;
  }

  _type(path, raw) {
    this._typing = { ...this._typing, [nodeKey(path)]: raw };
  }

  // Leaving a field shows its value again as the file holds it; a field left empty takes its key out.
  _leave(path, { keepEmpty = false, put = null } = {}) {
    return (event) => {
      if (event.currentTarget.contains(event.relatedTarget)) return;
      const key = nodeKey(path);
      if (!(key in this._typing)) return;
      const { [key]: typed, ...rest } = this._typing;
      this._typing = rest;
      const empty = Array.isArray(typed) ? !typed.some((item) => item.trim()) : !String(typed).trim();
      if (empty && !keepEmpty) {
        if (put) put(undefined);
        else this._set(path, undefined);
      }
    };
  }

  _rename(value, { plain = true } = {}) {
    const key = value.trim();
    try {
      if (plain && key && !PLAIN_KEY.test(key)) throw Object.assign(new Error("key_format"), { yaml: true });
      const result = renameKey(this.text, this.path, key);
      this._renameError = null;
      if (result.text !== this.text) this._emit(result.text, null, result.path);
    } catch (err) {
      this._renameError = this._errorText(err);
    }
  }

  _add(parent, key, value) {
    this._apply((text) => ({ text: setField(text, [...parent, key], value), path: [...parent, key] }));
  }

  _open(path) {
    this.dispatchEvent(new CustomEvent("select", { detail: { path } }));
  }

  // Fields ---------------------------------------------------------------------------------------------

  _text(path, label, { hint, warn, list, placeholder, rows, mono, get, put } = {}) {
    const stored = get ? get() : this._get(path);
    const value = this._shown(path, stored == null || typeof stored === "object" ? "" : String(stored));
    const input = (event) => {
      this._type(path, event.target.value);
      if (put) put(event.target.value, { live: true });
      else this._set(path, event.target.value, { live: true });
    };
    const control = rows
      ? html`<textarea rows=${rows} .value=${value} placeholder=${placeholder ?? ""} @input=${input}></textarea>`
      : html`<input
          class=${mono ? "mono" : ""}
          list=${list ?? nothing}
          .value=${value}
          placeholder=${placeholder ?? ""}
          @input=${input}
        />`;
    return html`<label class="field" data-field=${nodeKey(path)} @focusout=${this._leave(path, { put })}>
      <span class="label">${label}</span>${control}
      ${warn ? html`<span class="warn" data-warn>${warn}</span>` : nothing}
      ${hint ? html`<span class="hint">${hint}</span>` : nothing}
    </label>`;
  }

  _number(path, label, { hint, min = 0, placeholder } = {}) {
    const stored = this._get(path);
    const value = this._shown(path, stored == null ? "" : String(stored));
    return html`<label class="field" data-field=${nodeKey(path)} @focusout=${this._leave(path)}>
      <span class="label">${label}</span>
      <input
        type="number"
        class="short"
        min=${min}
        .value=${value}
        placeholder=${placeholder ?? ""}
        @input=${(event) => {
          this._type(path, event.target.value);
          // An empty number waits for the field to be left, so the line does not move while typing.
          if (event.target.value !== "" && Number.isFinite(Number(event.target.value))) this._set(path, Number(event.target.value));
        }}
      />
      ${hint ? html`<span class="hint">${hint}</span>` : nothing}
    </label>`;
  }

  _bool(path, label, { hint } = {}) {
    return html`<label class="check-field" data-field=${nodeKey(path)}>
      <input
        type="checkbox"
        .checked=${Boolean(this._get(path))}
        @change=${(event) => this._set(path, event.target.checked ? true : undefined)}
      />
      <span><span class="label">${label}</span>${hint ? html`<span class="hint">${hint}</span>` : nothing}</span>
    </label>`;
  }

  _choice(path, label, options, { hint, empty } = {}) {
    const stored = this._get(path);
    const value = stored == null ? "" : String(stored);
    const known = options.some((option) => option.value === value) || (value === "" && empty);
    return html`<label class="field" data-field=${nodeKey(path)}>
      <span class="label">${label}</span>
      <select
        @change=${(event) => {
          const chosen = options.find((option) => option.value === event.target.value);
          this._set(path, chosen ? chosen.raw ?? chosen.value : event.target.value || undefined);
        }}
      >
        ${empty ? html`<option value="" ?selected=${value === ""}>${empty}</option>` : nothing}
        ${options.map((option) => html`<option value=${option.value} ?selected=${option.value === value}>${option.label}</option>`)}
        ${known ? nothing : html`<option value=${value} selected>${value}</option>`}
      </select>
      ${hint ? html`<span class="hint">${hint}</span>` : nothing}
    </label>`;
  }

  /** A list of texts, one field each; the last, empty field adds one (Enter, or leaving it). */
  _list(path, label, { hint, warn, list, placeholder, keepEmpty = false, mono = false, get, put, badge } = {}) {
    const shown = this._shown(path, asList(get ? get() : this._get(path)));
    const write = (next) => {
      this._type(path, next);
      const clean = next.map((item) => item.trim()).filter(Boolean);
      if (put) put(clean, { live: true });
      else this._set(path, clean, { keepEmpty, live: true });
    };
    return html`<div class="field" data-list=${nodeKey(path)} @focusout=${this._leave(path, { keepEmpty, put })}>
      <span class="label">${label}</span>
      ${shown.map(
        (item, index) => html`<div class="row">
          <input
            class=${mono ? "mono" : ""}
            list=${list ?? nothing}
            .value=${item}
            @input=${(event) => write(shown.map((old, at) => (at === index ? event.target.value : old)))}
          />
          ${badge ? badge(item) : nothing}
          <button
            class="ghost icon"
            title=${this._t("form_remove")}
            data-remove=${index}
            @click=${() => write(shown.filter((old, at) => at !== index))}
          >
            <ha-icon icon="mdi:close"></ha-icon>
          </button>
        </div>`,
      )}
      <div class="row">
        <input
          data-add
          class=${mono ? "mono" : ""}
          list=${list ?? nothing}
          placeholder=${placeholder ?? this._t("form_add_item")}
          @change=${(event) => {
            const value = event.target.value;
            if (!value.trim()) return;
            event.target.value = "";
            write([...shown, value]);
          }}
        />
      </div>
      ${warn ? html`<span class="warn" data-warn>${warn}</span>` : nothing}
      ${hint ? html`<span class="hint">${hint}</span>` : nothing}
    </div>`;
  }

  /** People of the file to tick; keys not among them stay listed, so they can be unticked. */
  _people(path, label, hint) {
    const chosen = asList(this._get(path));
    const people = keysAt(this._doc, ["people"]);
    const all = [...people, ...chosen.filter((key) => !people.includes(key))];
    return html`<div class="field" data-people=${nodeKey(path)}>
      <span class="label">${label}</span>
      <div class="checks">
        ${all.length
          ? all.map(
              (key) => html`<label class="check ${people.includes(key) ? "" : "unknown"}" title=${people.includes(key) ? "" : this._t("form_unknown_person")}>
                <input
                  type="checkbox"
                  data-person=${key}
                  .checked=${chosen.includes(key)}
                  @change=${(event) => this._set(path, event.target.checked ? [...chosen, key] : chosen.filter((other) => other !== key))}
                />${this._personName(key)}
              </label>`,
            )
          : html`<span class="hint">${this._t("form_no_people")}</span>`}
      </div>
      ${hint ? html`<span class="hint">${hint}</span>` : nothing}
    </div>`;
  }

  _personName(key) {
    const person = valueAt(this._doc, ["people", key]);
    const name = typeof person === "string" ? person : person?.name;
    return name && name !== key ? `${name} (${key})` : key;
  }

  _keyField(label, hint, { plain = true, list } = {}) {
    return html`<label class="field" data-field="@key">
      <span class="label">${label}</span>
      <input
        class="mono"
        data-key
        list=${list ?? nothing}
        .value=${this.path.at(-1)}
        @change=${(event) => this._rename(event.target.value, { plain })}
        @keydown=${(event) => event.key === "Enter" && event.target.blur()}
      />
      ${this._renameError ? html`<span class="error" data-rename-error>${this._renameError}</span>` : html`<span class="hint">${hint}</span>`}
    </label>`;
  }

  /** A list of the entries of a part (people, personas, rooms) to open, and a field to add one by its name. */
  _entries(parent, rows, { addLabel, addPlaceholder, list, add }) {
    return html`<div class="entries" data-entries=${parent.join("/")}>
        ${rows.length
          ? rows.map(
              (row) => html`<button class="entry" data-entry=${row.key} @click=${() => this._open([...parent, row.key])}>
                <span class="name">${row.title}</span><span class="hint">${row.detail}</span>
                <ha-icon icon="mdi:chevron-right"></ha-icon>
              </button>`,
            )
          : html`<p class="hint">${this._t("form_none_yet")}</p>`}
      </div>
      <form
        class="add-entry"
        @submit=${(event) => {
          event.preventDefault();
          const input = event.currentTarget.querySelector("input");
          if (!input.value.trim()) return;
          add(input.value.trim());
          input.value = "";
        }}
      >
        <input data-new-entry list=${list ?? nothing} placeholder=${addPlaceholder} />
        <button class="primary" type="submit"><ha-icon icon="mdi:plus"></ha-icon>${addLabel}</button>
      </form>`;
  }

  _datalists() {
    const states = Object.keys(this.hass?.states ?? {}).sort();
    const areas = Object.values(this.hass?.areas ?? {}).map((area) => area.name).filter(Boolean).sort();
    const pipelines = this._pipelines ?? [];
    const voices = [...new Set(pipelines.map((pipeline) => pipeline.tts_voice).filter(Boolean))];
    const options = (items) => items.map((item) => html`<option value=${item}></option>`);
    return html`<datalist id="entities">${options(states)}</datalist>
      <datalist id="players">${options(states.filter((id) => id.startsWith("media_player.")))}</datalist>
      <datalist id="areas">${options(areas)}</datalist>
      <datalist id="pipelines">${options(pipelines.map((pipeline) => pipeline.name))}</datalist>
      <datalist id="voices">${options(voices)}</datalist>
      <datalist id="services">${options(this._services ?? [])}</datalist>`;
  }

  // Forms ----------------------------------------------------------------------------------------------

  render() {
    if (!this.path || !this.hass) return nothing;
    const form = formFor(this.path);
    const render = {
      topic: this._renderTopic,
      household: this._renderHousehold,
      people: this._renderPeople,
      person: this._renderPerson,
      family: this._renderFamily,
      personas: this._renderPersonas,
      persona: this._renderPersona,
      music: this._renderMusic,
      room: this._renderRoom,
      announce: this._renderAnnounce,
      confirm: this._renderConfirm,
      settings: this._renderSettings,
    }[form];
    if (!render) return nothing;
    return html`<div class="form" data-form=${form}>
      ${this._error ? html`<p class="error" data-form-error>${this._t("form_error", { error: this._error })}</p>` : nothing}
      ${render.call(this)} ${this._datalists()}
    </div>`;
  }

  _renderTopic() {
    const path = this.path;
    const stored = this._get(path);
    const topic = stored && typeof stored === "object" ? stored : {};
    const kind = topicKind(topic);
    const choice = TOPIC_KINDS.includes(kind) ? kind : "answer";
    const description = typeof topic.description === "string" ? topic.description.trim() : "";
    return html`
      <section>
        <h2>${this._t("form_topic")}</h2>
        ${this._keyField(this._t("form_topic_key"), this._t("form_topic_key_hint"))}
        ${this._text([...path, "description"], this._t("form_description"), {
          rows: 3,
          hint: this._t("form_description_hint"),
          warn: description ? null : this._t("warn_no_description"),
        })}
        ${this._list([...path, "examples"], this._t("form_examples"), {
          hint: this._t("form_examples_hint"),
          placeholder: this._t("form_examples_add"),
          warn: asList(topic.examples).length ? null : this._t("warn_no_examples"),
        })}
      </section>
      <section>
        <h2>${this._t("kind_title")}</h2>
        <div class="seg" data-kind-choice>
          ${TOPIC_KINDS.map(
            (option) => html`<button
              class=${option === choice ? "on" : ""}
              data-kind-option=${option}
              @click=${() => this._apply((text) => setTopicKind(text, path, option))}
            >
              <ha-icon .icon=${KIND_ICONS[option === "answer" ? (kind === "other" ? "other" : "data") : option]}></ha-icon>
              ${this._t(`kind_choice_${option}`)}
            </button>`,
          )}
        </div>
        <p class="hint" data-kind-hint>${this._t(`kind_hint_${kind}`)}</p>
      </section>
      ${choice === "answer" ? html`${this._renderAnswer(path, topic)} ${this._renderData(path, topic, kind)}` : nothing}
    `;
  }

  _renderAnswer(path, topic) {
    const hints = topic.answer_hints && typeof topic.answer_hints === "object" ? topic.answer_hints : {};
    const people = keysAt(this._doc, ["people"]);
    const own = [...new Set([...Object.keys(hints).filter((key) => !HINT_KEYS.includes(key)), ...this._hintKeys])];
    const free = people.filter((key) => !own.includes(key));
    return html`<section>
      <h2>${this._t("form_answer")}</h2>
      ${this._text([...path, "answer_hint"], this._t("form_answer_hint"), { rows: 2, hint: this._t("form_answer_hint_hint") })}
      <details class="more" ?open=${Object.keys(hints).length > 0 || this._hintKeys.length > 0} data-hints>
        <summary>${this._t("form_answer_hints", { count: Object.keys(hints).length })}</summary>
        <p class="hint">${this._t("form_answer_hints_hint")}</p>
        ${[...own, ...HINT_KEYS].map((key) =>
          this._text([...path, "answer_hints", key], HINT_KEYS.includes(key) ? this._t(`hint_${key}`) : this._personName(key), { rows: 2 }),
        )}
        ${free.length
          ? html`<label class="field">
              <span class="label">${this._t("form_hint_person")}</span>
              <select
                data-add-hint
                @change=${(event) => {
                  const key = event.target.value;
                  event.target.value = "";
                  if (key) this._hintKeys = [...this._hintKeys, key];
                }}
              >
                <option value="">${this._t("form_hint_person_pick")}</option>
                ${free.map((key) => html`<option value=${key}>${this._personName(key)}</option>`)}
              </select>
            </label>`
          : nothing}
      </details>
      ${this._number([...path, "answer_tokens"], this._t("form_answer_tokens"), { hint: this._t("form_answer_tokens_hint"), placeholder: "0" })}
      ${this._bool([...path, "personal"], this._t("form_personal"), { hint: this._t("form_personal_hint") })}
      ${topic.command ? this._bool([...path, "verbatim"], this._t("form_verbatim"), { hint: this._t("form_verbatim_hint") }) : nothing}
    </section>`;
  }

  _renderData(path, topic, kind) {
    const preview = this._preview?.key === `${path[1]}\n${this.text}` ? this._preview : null;
    const data = preview?.data;
    const others = ["frigate", "command"].filter((key) => topic[key] != null && topic[key] !== "");
    return html`<section data-sources>
      <h2>${this._t("form_data")}</h2>
      ${preview?.error ? html`<p class="warn" data-preview-error>${this._t("preview_waits", { error: preview.error })}</p>` : nothing}
      ${kind === "other" ? html`<p class="hint">${this._t("form_no_sources")}</p>` : nothing}
      <h3>${this._t("source_entities")}</h3>
      ${this._list([...path, "entities"], this._t("form_entities"), {
        list: "entities",
        mono: true,
        hint: this._t("form_entities_hint"),
        badge: (pattern) => this._badge(data?.entities.patterns, pattern),
      })}
      ${data && asList(topic.entities).length ? this._renderLines(data.entities) : nothing}
      ${this._list([...path, "skip_states"], this._t("form_skip_states"), { hint: this._t("form_skip_states_hint"), mono: true })}
      ${this._bool([...path, "unavailable"], this._t("form_unavailable"), { hint: this._t("form_unavailable_hint") })}
      ${this._choice(
        [...path, "only_exposed"],
        this._t("form_only_exposed"),
        [
          { value: "true", raw: true, label: this._t("yes") },
          { value: "false", raw: false, label: this._t("no") },
        ],
        { empty: this._t("form_only_exposed_default"), hint: this._t("form_only_exposed_hint") },
      )}
      <h3>${this._t("source_details")}</h3>
      ${this._list([...path, "details"], this._t("form_details"), {
        list: "entities",
        mono: true,
        hint: this._t("form_details_hint"),
        badge: (pattern) => this._badge(data?.details.patterns, pattern),
      })}
      ${this._list([...path, "drop"], this._t("form_drop"), { hint: this._t("form_drop_hint"), mono: true })}
      ${data?.details.sources.length
        ? html`<details class="preview" data-details-preview>
            <summary>${this._t("preview_details", { count: data.details.sources.length })}</summary>
            <pre>${data.details.sources.join("\n\n")}</pre>
          </details>`
        : nothing}
      <h3>${this._t("source_fetch")}</h3>
      ${this._renderFetch(path, topic, data)}
      ${this._renderDays(path, topic)}
      ${others.length
        ? html`<h3>${this._t("form_other_sources")}</h3>
            ${others.map(
              (key) => html`<div class="source">
                <span class="label">${this._t(`source_${key}`)}</span>
                <code>${this._sourceSummary(key, topic[key])}</code>
              </div>`,
            )}
            <p class="hint">${this._t("form_sources_hint")}</p>`
        : nothing}
    </section>`;
  }

  /** How many entities a pattern finds (how many it leaves out, for `!…`), with the first of them. */
  _badge(patterns, pattern) {
    const found = patterns?.find((item) => item.pattern === pattern.trim());
    if (!found) return nothing;
    const exclude = pattern.trim().startsWith("!");
    return html`<span
      class="badge ${found.count ? "" : "zero"}"
      data-count=${found.pattern}
      title=${found.sample.join("\n") || this._t("preview_none")}
      >${exclude ? `−${found.count}` : found.count}</span
    >`;
  }

  _renderLines(entities) {
    const { lines, matched, limit } = entities;
    return html`<p class="hint" data-matched>
        ${this._t("preview_matched", { matched, lines: lines.length })}
        ${entities.only_exposed ? this._t("preview_only_exposed") : ""}
      </p>
      ${matched > limit ? html`<p class="warn" data-limit>${this._t("preview_limit", { limit })}</p>` : nothing}
      ${entities.nothing_active ? html`<p class="hint">${this._t("preview_nothing_active")}</p>` : nothing}
      ${lines.length
        ? html`<details class="preview" data-lines>
            <summary>${this._t("preview_lines", { count: lines.length })}</summary>
            <pre>${lines.join("\n")}</pre>
          </details>`
        : nothing}`;
  }

  _renderDays(path, topic) {
    const days = topic.days == null ? "" : String(topic.days);
    const count = /^\d+$/.test(days);
    return html`<label class="field" data-field=${nodeKey([...path, "days"])}>
      <span class="label">${this._t("form_days")}</span>
      <div class="row">
        <select
          data-days
          @change=${(event) => {
            const value = event.target.value;
            this._set([...path, "days"], value === "#" ? 7 : value || undefined);
          }}
        >
          <option value="" ?selected=${!days}>${this._t("days_none")}</option>
          ${DAY_CODES.map((code) => html`<option value=${code} ?selected=${code === days}>${this._t(`day_${code}`)}</option>`)}
          <option value="#" ?selected=${count}>${this._t("days_count")}</option>
          ${days && !count && !DAY_CODES.includes(days) ? html`<option value=${days} selected>${days}</option>` : nothing}
        </select>
        ${count
          ? html`<input
              type="number"
              class="short"
              min="1"
              data-days-count
              .value=${days}
              @change=${(event) => this._set([...path, "days"], Math.max(1, Number(event.target.value) || 1))}
            />`
          : nothing}
      </div>
      <span class="hint">${this._t("form_days_hint")}</span>
    </label>`;
  }

  /** The services of a topic, one card each, written item by item so the comments between them stay. */
  _renderFetch(path, topic, data) {
    const listPath = [...path, "fetch"];
    const items = Array.isArray(topic.fetch) ? topic.fetch : [];
    const fetched = this._fetched?.topic === path[1] ? this._fetched : null;
    const put = (index, key, value, { live = false } = {}) => {
      this._apply((text) => {
        const current = valueAt(readDocument(text).doc, listPath)?.[index] ?? {};
        const next = { ...current };
        let clean = typeof value === "string" ? value.trim() : value;
        if (Array.isArray(clean) && key === "entities") clean = clean.length ? clean : live ? [] : undefined;
        if (clean === "" || clean === undefined) {
          if (live && key in next) next[key] = Array.isArray(next[key]) ? [] : "";
          else delete next[key];
        } else {
          next[key] = clean;
        }
        return setListItem(text, listPath, index, next);
      }, `form:${nodeKey([...listPath, index, key])}`);
    };
    return html`<div class="fetch-list" data-fetch>
      ${items.map((item, index) => this._renderFetchItem(listPath, item ?? {}, index, data?.fetch?.[index], fetched, put))}
      <div class="row">
        <button
          data-add-fetch
          @click=${() => this._apply((text) => setListItem(text, listPath, items.length, { ...NEW_FETCH }))}
        >
          <ha-icon icon="mdi:plus"></ha-icon>${this._t("fetch_add")}
        </button>
        ${items.length
          ? html`<button class="primary" data-run-fetch ?disabled=${fetched?.loading} @click=${this._fetch}>
              <ha-icon icon="mdi:download"></ha-icon>${fetched?.loading ? this._t("fetch_running") : this._t("fetch_run")}
            </button>`
          : nothing}
      </div>
      ${items.length ? html`<p class="hint">${this._t("fetch_hint")}</p>` : nothing}
      ${fetched?.error ? html`<p class="error" data-fetch-error>${this._t("form_error", { error: fetched.error })}</p>` : nothing}
    </div>`;
  }

  _renderFetchItem(listPath, item, index, info, fetched, put) {
    const base = [...listPath, index];
    const status = info?.service;
    const result = fetched?.data?.fetch?.[index];
    const dataPath = [...base, "data"];
    const dataText = this._shown(dataPath, item.data && Object.keys(item.data).length ? fieldLines("x", item.data, { flow: false }).slice(1).map((line) => line.slice(2)).join("\n") : "");
    return html`<div class="fetch-item" data-fetch-item=${index}>
      <div class="row head">
        <span class="label">${this._t("fetch_item", { number: index + 1 })}</span>
        <span class="grow"></span>
        <button class="ghost icon" title=${this._t("form_remove")} data-remove-fetch=${index} @click=${() => this._apply((text) => setListItem(text, listPath, index, undefined))}>
          <ha-icon icon="mdi:delete-outline"></ha-icon>
        </button>
      </div>
      ${this._text([...base, "action"], this._t("fetch_action"), {
        mono: true,
        list: "services",
        get: () => item.action,
        put: (value, options) => put(index, "action", value, options),
        warn: status && status !== "read_only" ? this._t(`fetch_${status}`) : null,
        hint: this._t("fetch_action_hint"),
      })}
      ${this._list([...base, "entities"], this._t("fetch_entities"), {
        list: "entities",
        mono: true,
        get: () => item.entities,
        put: (value, options) => put(index, "entities", value, options),
        badge: (pattern) => this._badge(info?.patterns, pattern),
        warn: info && !info.targets.length ? this._t("fetch_no_targets") : null,
      })}
      <div class="row wrap">
        ${this._text([...base, "title"], this._t("fetch_title"), {
          get: () => item.title,
          put: (value, options) => put(index, "title", value, options),
          hint: this._t("fetch_title_hint"),
        })}
        ${this._text([...base, "merge"], this._t("fetch_merge"), {
          mono: true,
          get: () => item.merge,
          put: (value, options) => put(index, "merge", value, options),
          hint: this._t("fetch_merge_hint"),
        })}
      </div>
      <div class="row wrap">
        <label class="field" data-field=${nodeKey([...base, "limit"])}>
          <span class="label">${this._t("fetch_limit")}</span>
          <input
            type="number"
            class="short"
            min="1"
            .value=${item.limit == null ? "" : String(item.limit)}
            placeholder="40"
            @change=${(event) => put(index, "limit", event.target.value === "" ? undefined : Math.max(1, Number(event.target.value) || 1))}
          />
        </label>
        <label class="field" data-field=${nodeKey([...base, "past"])}>
          <span class="label">${this._t("fetch_past")}</span>
          <select @change=${(event) => put(index, "past", event.target.value || undefined)}>
            <option value="" ?selected=${!item.past}>${this._t("fetch_past_keep")}</option>
            ${PAST_MODES.map((mode) => html`<option value=${mode} ?selected=${item.past === mode}>${this._t(`fetch_past_${mode}`)}</option>`)}
          </select>
        </label>
      </div>
      <label class="field" data-field=${nodeKey(dataPath)} @focusout=${() => {
        const { [nodeKey(dataPath)]: left, ...rest } = this._typing;
        this._typing = rest;
      }}>
        <span class="label">${this._t("fetch_data")}</span>
        <textarea
          class="mono"
          rows="2"
          .value=${dataText}
          placeholder="start_date_time: '{start}'"
          @input=${(event) => {
            const raw = event.target.value;
            this._type(dataPath, raw);
            const { doc, error } = readDocument(raw);
            const value = doc.toJSON();
            if (error || (raw.trim() && (value === null || typeof value !== "object" || Array.isArray(value)))) {
              this._dataError = { index, error: error ?? this._t("fetch_data_map") };
              this.requestUpdate();
              return;
            }
            this._dataError = null;
            put(index, "data", raw.trim() ? value : undefined, { live: false });
          }}
        ></textarea>
        ${this._dataError?.index === index
          ? html`<span class="warn" data-warn>${this._dataError.error}</span>`
          : html`<span class="hint">${this._t("fetch_data_hint")}</span>`}
      </label>
      ${result
        ? html`<div class="fetched" data-fetched=${index}>
            ${result.service !== "read_only"
              ? html`<p class="warn">${this._t("fetch_not_run")}</p>`
              : result.sources?.length
                ? html`<pre>${result.sources.join("\n\n")}</pre>`
                : html`<p class="hint">${this._t("fetch_empty")}</p>`}
          </div>`
        : nothing}
    </div>`;
  }

  _sourceSummary(key, value) {
    if (key === "fetch") return asList((Array.isArray(value) ? value : [value]).map((item) => item?.action ?? "?")).join(", ");
    if (key === "frigate") return value?.url ?? "frigate";
    if (key === "command") return String(value).trim().split("\n")[0];
    return asList(value).join(", ");
  }

  _renderHousehold() {
    return html`<section>
      <h2>${this._t("key_household")}</h2>
      ${this._text(["household"], this._t("form_household"), { rows: 5, hint: this._t("form_household_hint") })}
    </section>`;
  }

  _renderPeople() {
    const rows = keysAt(this._doc, ["people"]).map((key) => {
      const person = valueAt(this._doc, ["people", key]);
      const name = typeof person === "string" ? person : (person?.name ?? key);
      return { key, title: name, detail: key };
    });
    return html`<section>
      <h2>${this._t("key_people")}</h2>
      <p class="hint">${this._t("form_people_hint")}</p>
      ${this._entries(["people"], rows, {
        addLabel: this._t("form_add_person"),
        addPlaceholder: this._t("form_person_name"),
        add: (name) => this._add(["people"], freeKey(this._doc, ["people"], keyFromName(name, "person")), { name }),
      })}
    </section>`;
  }

  _renderPerson() {
    const path = this.path;
    const stored = this._get(path);
    const person = stored && typeof stored === "object" ? stored : { name: stored };
    const sample = matchSample(person.match, person.name ?? path.at(-1), this._sample);
    return html`<section>
      <h2>${this._t("form_person")}</h2>
      ${this._keyField(this._t("form_person_key"), this._t("form_person_key_hint"))}
      ${this._text([...path, "name"], this._t("form_person_name"))}
      ${this._text([...path, "match"], this._t("form_match"), {
        mono: true,
        hint: this._t("form_match_hint"),
        warn: sample.error ? this._t("form_match_error", { error: sample.error }) : null,
      })}
      <label class="field sample">
        <span class="label">${this._t("form_match_try")}</span>
        <input data-sample .value=${this._sample} placeholder=${this._t("form_match_sample")} @input=${(event) => (this._sample = event.target.value)} />
        ${this._sample.trim() && !sample.error
          ? sample.found.length
            ? html`<span class="ok" data-sample-result="yes">${this._t("form_match_found", { words: sample.found.join(", ") })}</span>`
            : html`<span class="warn" data-sample-result="no">${this._t("form_match_none")}</span>`
          : nothing}
      </label>
      ${this._text([...path, "speaker"], this._t("form_speaker"), { mono: true, placeholder: path.at(-1), hint: this._t("form_speaker_hint") })}
      ${this._text([...path, "room"], this._t("form_room"), { list: "areas", hint: this._t("form_room_hint") })}
      ${this._list([...path, "owns"], this._t("form_owns"), { list: "entities", mono: true, hint: this._t("form_owns_hint") })}
      ${this._list([...path, "labels"], this._t("form_labels"), { mono: true, hint: this._t("form_labels_hint") })}
    </section>`;
  }

  _renderFamily() {
    return html`<section>
      <h2>${this._t("key_family")}</h2>
      <p class="hint">${this._t("form_family_hint")}</p>
      ${this._people(["family", "parents"], this._t("form_parents"))}
      ${this._people(["family", "children"], this._t("form_children"))}
      ${this._people(["family", "men"], this._t("form_men"), this._t("form_men_hint"))}
    </section>`;
  }

  _renderPersonas() {
    const rows = keysAt(this._doc, ["personas"]).map((key) => {
      const persona = valueAt(this._doc, ["personas", key]) ?? {};
      return { key, title: key, detail: [...asList(persona.pipelines), ...asList(persona.voices)].join(", ") };
    });
    return html`<section>
      <h2>${this._t("key_personas")}</h2>
      <p class="hint">${this._t("form_personas_hint")}</p>
      ${this._entries(["personas"], rows, {
        addLabel: this._t("form_add_persona"),
        addPlaceholder: this._t("form_persona_name"),
        add: (name) =>
          this._add(["personas"], freeKey(this._doc, ["personas"], keyFromName(name, "persona")), {
            pipelines: [name],
            prompt: this._t("form_persona_prompt_new", { name }),
          }),
      })}
    </section>`;
  }

  _renderPersona() {
    const path = this.path;
    const persona = this._get(path) ?? {};
    const prompt = typeof persona.prompt === "string" ? persona.prompt.trim() : "";
    const matched = asList(persona.pipelines).length || asList(persona.voices).length;
    return html`<section>
      <h2>${this._t("form_persona")}</h2>
      ${this._keyField(this._t("form_persona_key"), this._t("form_persona_key_hint"))}
      ${this._text([...path, "prompt"], this._t("form_persona_prompt"), {
        rows: 4,
        hint: this._t("form_persona_prompt_hint"),
        warn: prompt ? null : this._t("form_persona_no_prompt"),
      })}
      ${this._choice(
        [...path, "gender"],
        this._t("form_gender"),
        [
          { value: "male", label: this._t("gender_male") },
          { value: "female", label: this._t("gender_female") },
        ],
        { empty: this._t("gender_none"), hint: this._t("form_gender_hint") },
      )}
      ${this._list([...path, "pipelines"], this._t("form_pipelines"), {
        list: "pipelines",
        hint: this._t("form_pipelines_hint"),
        warn: matched ? null : this._t("form_persona_unmatched"),
      })}
      ${this._list([...path, "voices"], this._t("form_voices"), { list: "voices", mono: true, hint: this._t("form_voices_hint") })}
    </section>`;
  }

  _renderMusic() {
    const rows = keysAt(this._doc, ["music_players"]).map((key) => ({
      key,
      title: key,
      detail: asList(valueAt(this._doc, ["music_players", key])).join(", ") || this._t("form_no_players"),
    }));
    return html`<section>
      <h2>${this._t("key_music_players")}</h2>
      <p class="hint">${this._t("form_music_hint")}</p>
      ${this._entries(["music_players"], rows, {
        addLabel: this._t("form_add_room"),
        addPlaceholder: this._t("form_room_name"),
        list: "areas",
        add: (name) => this._add(["music_players"], freeKey(this._doc, ["music_players"], name), []),
      })}
    </section>`;
  }

  _renderRoom() {
    return html`<section>
      <h2>${this._t("form_room_title")}</h2>
      ${this._keyField(this._t("form_room_name"), this._t("form_room_name_hint"), { plain: false, list: "areas" })}
      ${this._list([...this.path], this._t("form_players"), {
        list: "players",
        mono: true,
        keepEmpty: true,
        hint: this._t("form_players_hint"),
      })}
    </section>`;
  }

  _renderAnnounce() {
    return html`<section>
      <h2>${this._t("key_announce_players")}</h2>
      ${this._list(["announce_players"], this._t("form_players"), { list: "players", mono: true, hint: this._t("form_announce_hint") })}
    </section>`;
  }

  _renderConfirm() {
    return html`<section>
      <h2>${this._t("key_confirm_entities")}</h2>
      ${this._list(["confirm_entities"], this._t("form_confirm"), { list: "entities", mono: true, hint: this._t("form_confirm_hint") })}
    </section>`;
  }

  _renderSettings() {
    const languages = (this.languages ?? []).map((code) => ({ value: code, label: code }));
    const promptWarn = (key) => {
      const unknown = unknownPromptValues(this._get([key]));
      return unknown.length ? this._t("form_prompt_unknown", { names: unknown.map((name) => `{${name}}`).join(", ") }) : null;
    };
    return html`<section>
        <h2>${this._t("key_settings")}</h2>
        ${this._choice(["language"], this._t("key_language"), languages, { empty: this._t("language_auto"), hint: this._t("form_language_hint") })}
        ${this._number(["sentences"], this._t("key_sentences"), { min: 1, placeholder: "4", hint: this._t("form_sentences_hint") })}
        ${this._text(["wikipedia_language"], this._t("key_wikipedia_language"), { mono: true, placeholder: "pl", hint: this._t("form_wikipedia_hint") })}
        ${this._bool(["only_exposed"], this._t("key_only_exposed"), { hint: this._t("form_only_exposed_all_hint") })}
        ${this._choice(
          ["control_model"],
          this._t("key_control_model"),
          [
            { value: "router", label: this._t("control_model_router") },
            { value: "answer", label: this._t("control_model_answer") },
          ],
          { empty: this._t("control_model_default"), hint: this._t("form_control_model_hint") },
        )}
      </section>
      <section>
        <h2>${this._t("form_prompts")}</h2>
        <p class="hint">${this._t("form_prompts_hint")}</p>
        ${this._text(["answer_prompt"], this._t("key_answer_prompt"), { rows: 6, placeholder: this._t("form_prompt_default"), warn: promptWarn("answer_prompt") })}
        ${this._text(["summary_prompt"], this._t("key_summary_prompt"), { rows: 6, placeholder: this._t("form_prompt_default"), warn: promptWarn("summary_prompt") })}
      </section>`;
  }

  static styles = css`
    :host {
      display: block;
      min-height: 0;
      overflow: auto;
    }
    .form {
      display: flex;
      flex-direction: column;
      gap: 12px;
      max-width: 760px;
      padding-bottom: 24px;
    }
    section {
      display: flex;
      flex-direction: column;
      gap: 12px;
      padding: 14px 16px;
      border-radius: 12px;
      background: var(--panel, #1b1e24);
    }
    p {
      margin: 0;
    }
    h2 {
      margin: 0;
      font-size: 11px;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      color: var(--muted, #9aa0a6);
    }
    .field {
      display: flex;
      flex-direction: column;
      gap: 4px;
    }
    .label {
      font-weight: 600;
    }
    .hint {
      font-size: 12px;
      color: var(--muted, #9aa0a6);
    }
    .warn {
      font-size: 12px;
      color: var(--amber, #ffb340);
    }
    .error {
      margin: 0;
      font-size: 12px;
      color: var(--red, #ff453a);
    }
    .ok {
      font-size: 12px;
      color: var(--green, #30d158);
    }
    input,
    textarea,
    select {
      box-sizing: border-box;
      width: 100%;
      padding: 7px 10px;
      border: 1px solid var(--line, #2f343c);
      border-radius: 8px;
      outline: none;
      color: var(--text, #e8eaed);
      background: var(--field);
      font: inherit;
    }
    input:focus,
    textarea:focus,
    select:focus {
      border-color: rgba(79, 140, 255, 0.6);
    }
    textarea {
      resize: vertical;
      line-height: 1.45;
    }
    .mono {
      font: 13px ui-monospace, SFMono-Regular, Menlo, monospace;
    }
    input.short {
      width: 120px;
    }
    input[type="checkbox"] {
      width: auto;
      margin: 3px 0 0;
    }
    .row {
      display: flex;
      gap: 6px;
      align-items: center;
    }
    .row select {
      width: auto;
    }
    button {
      font: inherit;
      color: inherit;
      border: 0;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 7px 12px;
      border-radius: 9px;
      background: var(--panel2, #23272e);
    }
    button.ghost {
      background: transparent;
      color: var(--muted, #9aa0a6);
    }
    button.icon {
      padding: 6px;
    }
    button.primary {
      flex: none;
      background: var(--accent, #4f8cff);
      color: #fff;
      font-weight: 600;
    }
    .check-field {
      display: flex;
      gap: 10px;
      align-items: flex-start;
    }
    .check-field > span {
      display: flex;
      flex-direction: column;
      gap: 2px;
    }
    .checks {
      display: flex;
      flex-wrap: wrap;
      gap: 6px 14px;
    }
    .check {
      display: inline-flex;
      gap: 6px;
      align-items: center;
    }
    .check.unknown {
      color: var(--amber, #ffb340);
    }
    .seg {
      display: flex;
      flex-wrap: wrap;
      gap: 2px;
      padding: 3px;
      border-radius: 9px;
      background: var(--panel2, #23272e);
      align-self: flex-start;
    }
    .seg button {
      padding: 5px 10px;
      background: transparent;
      color: var(--muted, #9aa0a6);
    }
    .seg button.on {
      background: var(--on);
      color: var(--text, #e8eaed);
    }
    details.more {
      display: flex;
      flex-direction: column;
      gap: 10px;
    }
    details.more > summary {
      cursor: pointer;
      font-weight: 600;
    }
    details.more[open] > summary {
      margin-bottom: 8px;
    }
    details.more > .field {
      margin-bottom: 10px;
    }
    h3 {
      margin: 6px 0 0;
      font-size: 13px;
      color: var(--text, #e8eaed);
    }
    .badge {
      flex: none;
      min-width: 28px;
      padding: 2px 8px;
      border-radius: 999px;
      text-align: center;
      font-size: 12px;
      color: var(--green, #30d158);
      background: rgba(48, 209, 88, 0.15);
    }
    .badge.zero {
      color: var(--amber, #ffb340);
      background: rgba(255, 179, 64, 0.15);
    }
    details.preview > summary {
      cursor: pointer;
      font-size: 12px;
      color: var(--muted, #9aa0a6);
    }
    pre {
      margin: 6px 0 0;
      max-height: 280px;
      overflow: auto;
      padding: 10px 12px;
      border-radius: 8px;
      background: var(--field);
      font: 12px/1.5 ui-monospace, SFMono-Regular, Menlo, monospace;
      white-space: pre-wrap;
    }
    .fetch-list {
      display: flex;
      flex-direction: column;
      gap: 10px;
    }
    .fetch-item {
      display: flex;
      flex-direction: column;
      gap: 10px;
      padding: 12px;
      border: 1px solid var(--line, #2f343c);
      border-radius: 10px;
    }
    .row.wrap {
      flex-wrap: wrap;
      align-items: flex-start;
      gap: 12px;
    }
    .row.wrap > .field {
      flex: 1;
      min-width: 160px;
    }
    .grow {
      flex: 1;
    }
    .source {
      display: flex;
      gap: 10px;
      align-items: baseline;
    }
    .source code {
      overflow: hidden;
      color: var(--muted, #9aa0a6);
      font: 12px ui-monospace, SFMono-Regular, Menlo, monospace;
      white-space: nowrap;
      text-overflow: ellipsis;
    }
    .entries {
      display: flex;
      flex-direction: column;
      gap: 4px;
    }
    .entry {
      justify-content: flex-start;
      width: 100%;
      text-align: left;
    }
    .entry .name {
      font-weight: 600;
    }
    .entry .hint {
      flex: 1;
      overflow: hidden;
      white-space: nowrap;
      text-overflow: ellipsis;
    }
    .add-entry {
      display: flex;
      gap: 8px;
    }
  `;
}

if (!customElements.get(FORM_TAG)) customElements.define(FORM_TAG, AssistRouterForm);
