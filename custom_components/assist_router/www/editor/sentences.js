// Sentences of Home Assistant's own agent: one file of custom_sentences/<language>/*.yaml in a form (intents, their
// sentences and the answer) or as YAML. A file is saved by itself, with a .bak, and Home Assistant reloads the
// sentences at once; the test asks Home Assistant what it recognizes now, without running anything.

import { LitElement, css, html, nothing } from "../vendor/lit-all.min.js";
import { renameKey, setField } from "./fields.js";
import { translate } from "./i18n.js";
import { keysAt, readDocument, valueAt } from "./source.js";
import { callWS } from "./ws.js";

const SENTENCES_TAG = "assist-router-sentences";
export const FILE_NAME = /^[\w-]+\.yaml$/;

const asList = (value) => (Array.isArray(value) ? value : value == null ? [] : [value]);

/** A new file of sentences in a language, with no intents yet. */
export function newSentencesFile(language) {
  return `language: ${language}\nintents: {}\n`;
}

/** A file name the editor may write: letters, digits, _ and -, ending in .yaml (added when missing). */
export function sentencesFileName(name) {
  const text = String(name ?? "").trim();
  const full = text.endsWith(".yaml") ? text : `${text}.yaml`;
  return FILE_NAME.test(full) ? full : null;
}

/**
 * What a file of sentences holds, as the form shows it: its intents with their groups of sentences (and the keys
 * of a group the form leaves to the YAML) and the answer of each; `error` when it is not YAML.
 */
export function readSentences(text) {
  const { doc, error } = readDocument(text);
  if (error) return { error, intents: [] };
  const intents = keysAt(doc, ["intents"]).map((name) => {
    const data = asList(valueAt(doc, ["intents", name, "data"]));
    return {
      name,
      groups: data.map((group) => ({
        sentences: asList(group?.sentences).map(String),
        other: Object.keys(group ?? {}).filter((key) => key !== "sentences"),
      })),
      response: valueAt(doc, ["responses", "intents", name, "default"]) ?? "",
    };
  });
  return { error: null, intents };
}

/** The text with the sentences of one group of an intent set (other keys of the group kept). */
export function setGroupSentences(text, intent, index, sentences) {
  const path = ["intents", intent, "data"];
  const data = asList(valueAt(readDocument(text).doc, path)).map((group) => ({ ...(group ?? {}) }));
  while (data.length <= index) data.push({ sentences: [] });
  data[index] = { ...data[index], sentences };
  return setField(text, path, data);
}

/** The text with an intent renamed, and its answer with it. */
export function renameIntent(text, from, to) {
  let next = renameKey(text, ["intents", from], to).text;
  if (valueAt(readDocument(next).doc, ["responses", "intents", from]) !== undefined) {
    next = renameKey(next, ["responses", "intents", from], to).text;
  }
  return next;
}

/** The text without an intent and its answer. */
export function removeIntent(text, name) {
  let next = setField(text, ["intents", name], undefined);
  if (valueAt(readDocument(next).doc, ["responses", "intents", name]) !== undefined) {
    next = setField(next, ["responses", "intents", name], undefined);
    for (const path of [["responses", "intents"], ["responses"]]) {
      const left = valueAt(readDocument(next).doc, path);
      const empty = left === null || (typeof left === "object" && left !== undefined && !Object.keys(left).length);
      if (empty) next = setField(next, path, undefined);
    }
  }
  if (valueAt(readDocument(next).doc, ["intents"]) == null) next = setField(next, ["intents"], {});
  return next;
}

class AssistRouterSentences extends LitElement {
  static properties = {
    hass: { attribute: false },
    // { language, name, text, hash, check } of the file; `hash` is "" for a file not saved yet.
    file: { attribute: false },
    // The text being edited, when it differs from the file.
    edited: { attribute: false },
    intents: { attribute: false },
    _view: { state: true },
    _busy: { state: true },
    _error: { state: true },
    _conflict: { state: true },
    _sample: { state: true },
    _results: { state: true },
    _newIntent: { state: true },
  };

  constructor() {
    super();
    this._view = "form";
    this._sample = "";
    this._newIntent = "";
  }

  _t(key, values, fallback) {
    return translate(this.hass?.language, key, values, fallback);
  }

  willUpdate(changed) {
    if (changed.has("file") && changed.get("file")?.name !== this.file?.name) {
      this._error = null;
      this._conflict = false;
      this._results = null;
    }
  }

  get _text() {
    return this.edited ?? this.file?.text ?? "";
  }

  _change(text) {
    this._error = null;
    this.dispatchEvent(new CustomEvent("change", { detail: { text: text === this.file.text ? null : text } }));
  }

  _apply(change) {
    try {
      this._change(change(this._text));
    } catch (err) {
      this._error = err.message === "key_taken" ? this._t("key_taken") : (err.message ?? String(err));
    }
  }

  async _save(force = false) {
    this._busy = true;
    this._error = null;
    try {
      const saved = await callWS(this.hass, {
        type: "assist_router/editor/sentences_save",
        language: this.file.language,
        name: this.file.name,
        text: this._text,
        base: this.file.hash,
        force,
      });
      this._conflict = false;
      this.dispatchEvent(new CustomEvent("saved", { detail: { text: this._text, ...saved } }));
      if (this._sample.trim()) this._test();
    } catch (err) {
      this._conflict = err.code === "conflict";
      this._error = this._conflict ? this._t("sentences_conflict") : (err.message ?? String(err));
    } finally {
      this._busy = false;
    }
  }

  async _delete() {
    if (!window.confirm(this._t("sentences_delete_confirm", { name: this.file.name }))) return;
    if (!this.file.hash) {
      this.dispatchEvent(new CustomEvent("deleted"));
      return;
    }
    try {
      await callWS(this.hass, { type: "assist_router/editor/sentences_delete", language: this.file.language, name: this.file.name });
      this.dispatchEvent(new CustomEvent("deleted"));
    } catch (err) {
      this._error = err.message ?? String(err);
    }
  }

  async _test() {
    const sentences = this._sample
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean);
    if (!sentences.length) return;
    try {
      this._results = await callWS(this.hass, {
        type: "assist_router/editor/sentences_test",
        sentences,
        language: this.file.language,
      });
    } catch (err) {
      this._error = err.message ?? String(err);
    }
  }

  render() {
    if (!this.hass || !this.file) return nothing;
    const dirty = this.edited != null;
    const parsed = readSentences(this._text);
    return html`<div class="sentences" data-sentences-file=${`${this.file.language}/${this.file.name}`}>
      <section>
        <div class="head">
          <h2>${this.file.language}/${this.file.name}</h2>
          <span class="state ${dirty || !this.file.hash ? "dirty" : ""}" data-sentences-state>
            ${!this.file.hash ? this._t("sentences_new") : dirty ? this._t("sentences_unsaved") : this._t("sentences_saved")}
          </span>
          <span class="grow"></span>
          <div class="seg">
            <button class=${this._view === "form" ? "on" : ""} data-sentences-view="form" @click=${() => (this._view = "form")}>
              ${this._t("tab_form")}
            </button>
            <button class=${this._view === "yaml" ? "on" : ""} data-sentences-view="yaml" @click=${() => (this._view = "yaml")}>YAML</button>
          </div>
        </div>
        <p class="hint">${this._t("sentences_hint")}</p>
        ${this._view === "yaml" ? this._renderYaml(parsed) : this._renderForm(parsed)}
        ${this._error ? html`<p class="bad" data-sentences-error>${this._error}</p>` : nothing}
        <div class="row">
          ${dirty && this.file.hash
            ? html`<button data-sentences-discard @click=${() => this._change(this.file.text)}>${this._t("sentences_discard")}</button>`
            : nothing}
          <button class="ghost danger" data-sentences-delete @click=${this._delete}>${this._t("sentences_delete")}</button>
          <span class="grow"></span>
          ${this._conflict
            ? html`<button class="danger" data-sentences-force ?disabled=${this._busy} @click=${() => this._save(true)}>
                ${this._t("save_force")}
              </button>`
            : html`<button
                class="primary"
                data-sentences-save
                ?disabled=${this._busy || parsed.error || (!dirty && this.file.hash)}
                @click=${() => this._save()}
              >
                ${this._busy ? this._t("sentences_saving") : this._t("sentences_save")}
              </button>`}
        </div>
      </section>
      ${this._renderTest(dirty)}
    </div>`;
  }

  _renderYaml(parsed) {
    return html`<textarea
        class="code"
        data-sentences-yaml
        spellcheck="false"
        .value=${this._text}
        @input=${(event) => this._change(event.target.value)}
      ></textarea>
      ${parsed.error ? html`<p class="bad" data-sentences-yaml-error>${parsed.error}</p>` : nothing}`;
  }

  _renderForm(parsed) {
    if (parsed.error) return html`<p class="bad" data-sentences-yaml-error>${this._t("sentences_fix_yaml", { error: parsed.error })}</p>`;
    const known = this.intents ?? [];
    return html`<datalist id="intents">${known.map((name) => html`<option value=${name}></option>`)}</datalist>
      ${parsed.intents.length ? nothing : html`<p class="muted">${this._t("sentences_no_intents")}</p>`}
      ${parsed.intents.map((item) => this._renderIntent(item, known))}
      <form
        class="row add"
        data-add-intent
        @submit=${(event) => {
          event.preventDefault();
          const name = this._newIntent.trim();
          if (!name) return;
          this._apply((text) => setGroupSentences(text, name, 0, []));
          this._newIntent = "";
        }}
      >
        <input
          list="intents"
          data-new-intent
          placeholder=${this._t("sentences_intent_placeholder")}
          .value=${this._newIntent}
          @input=${(event) => (this._newIntent = event.target.value)}
        />
        <button type="submit">${this._t("sentences_add_intent")}</button>
      </form>`;
  }

  _renderIntent(item, known) {
    const handled = known.includes(item.name);
    return html`<div class="intent" data-intent=${item.name}>
      <div class="row">
        <input
          class="mono"
          list="intents"
          data-intent-name
          .value=${item.name}
          @change=${(event) => {
            const name = event.target.value.trim();
            if (name && name !== item.name) this._apply((text) => renameIntent(text, item.name, name));
          }}
        />
        <button class="ghost danger" data-remove-intent @click=${() => this._apply((text) => removeIntent(text, item.name))}>
          ${this._t("form_remove")}
        </button>
      </div>
      ${handled ? nothing : html`<p class="warn" data-intent-unhandled>${this._t("sentences_unhandled", { intent: item.name })}</p>`}
      ${item.groups.map(
        (group, index) => html`<div class="group" data-sentence-group=${index}>
          <span class="label">${this._t("sentences_group", { number: index + 1 })}</span>
          ${group.sentences.map(
            (sentence, at) => html`<div class="row">
              <input
                class="mono"
                data-sentence-input
                .value=${sentence}
                @change=${(event) =>
                  this._apply((text) =>
                    setGroupSentences(
                      text,
                      item.name,
                      index,
                      group.sentences.map((old, i) => (i === at ? event.target.value.trim() : old)).filter(Boolean),
                    ),
                  )}
              />
              <button
                class="ghost"
                data-remove-sentence
                @click=${() => this._apply((text) => setGroupSentences(text, item.name, index, group.sentences.filter((_, i) => i !== at)))}
              >
                ×
              </button>
            </div>`,
          )}
          <input
            class="mono"
            data-add-sentence
            placeholder=${this._t("sentences_add_sentence")}
            @change=${(event) => {
              const value = event.target.value.trim();
              event.target.value = "";
              if (value) this._apply((text) => setGroupSentences(text, item.name, index, [...group.sentences, value]));
            }}
          />
          ${group.other.length ? html`<span class="hint">${this._t("sentences_other_keys", { keys: group.other.join(", ") })}</span>` : nothing}
        </div>`,
      )}
      <button class="small" data-add-group @click=${() => this._apply((text) => setGroupSentences(text, item.name, item.groups.length, []))}>
        ${this._t("sentences_add_group")}
      </button>
      <label class="field">
        <span class="label">${this._t("sentences_response")}</span>
        <input
          data-response
          .value=${String(item.response)}
          placeholder=${this._t("sentences_response_placeholder")}
          @change=${(event) =>
            this._apply((text) => setField(text, ["responses", "intents", item.name, "default"], event.target.value.trim() || undefined))}
        />
      </label>
    </div>`;
  }

  _renderTest(dirty) {
    return html`<section data-sentences-test>
      <h2>${this._t("sentences_test_title")}</h2>
      <p class="hint">${dirty || !this.file.hash ? this._t("sentences_test_unsaved") : this._t("sentences_test_hint")}</p>
      <textarea
        rows="3"
        data-sentences-sample
        placeholder=${this._t("sentences_sample")}
        .value=${this._sample}
        @input=${(event) => (this._sample = event.target.value)}
      ></textarea>
      <div class="row">
        <button class="primary" data-sentences-run ?disabled=${!this._sample.trim()} @click=${this._test}>${this._t("tester_run")}</button>
      </div>
      ${this._results
        ? html`<ul class="results">
            ${this._results.map(
              (result) => html`<li data-sentence-result=${result.match === true ? "match" : result.match === false ? "partial" : "none"}>
                <strong>${this._t("quoted", { text: result.sentence })}</strong>
                ${result.match === true
                  ? html`<span class="ok">${this._t("ha_match", { intent: result.intent ?? result.template })}</span>
                      <span class="muted">${this._t(`ha_source_${result.source}`, null, result.source ?? "")}${result.file ? ` · ${result.file}` : ""}</span>
                      ${Object.keys(result.slots ?? {}).length ? html`<code>${JSON.stringify(result.slots)}</code>` : nothing}`
                  : result.match === false
                    ? html`<span class="warn">${this._t("ha_partial", { intent: result.intent })}</span>`
                    : html`<span class="muted">${this._t("sentences_not_recognized")}</span>`}
              </li>`,
            )}
          </ul>`
        : nothing}
    </section>`;
  }

  static styles = css`
    :host {
      display: block;
      min-height: 0;
      overflow: auto;
    }
    .sentences {
      display: flex;
      flex-direction: column;
      gap: 12px;
      max-width: 820px;
      padding-bottom: 24px;
    }
    section {
      display: flex;
      flex-direction: column;
      gap: 10px;
      padding: 14px 16px;
      border-radius: 12px;
      background: var(--panel, #1b1e24);
    }
    h2 {
      margin: 0;
      font: 600 13px ui-monospace, SFMono-Regular, Menlo, monospace;
    }
    p {
      margin: 0;
    }
    .head,
    .row {
      display: flex;
      gap: 8px;
      align-items: center;
    }
    .grow {
      flex: 1;
    }
    .hint,
    .muted {
      font-size: 12px;
      color: var(--muted, #9aa0a6);
    }
    .label {
      font-weight: 600;
    }
    .ok {
      color: var(--green, #30d158);
    }
    .warn {
      font-size: 12px;
      color: var(--amber, #ffb340);
    }
    .bad {
      color: var(--red, #ff453a);
    }
    .state {
      padding: 2px 9px;
      border-radius: 999px;
      font-size: 12px;
      color: var(--muted, #9aa0a6);
      background: var(--panel2, #23272e);
    }
    .state.dirty {
      color: var(--amber, #ffb340);
      background: rgba(255, 179, 64, 0.15);
    }
    input,
    textarea {
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
    .mono,
    textarea.code {
      font: 13px/1.5 ui-monospace, SFMono-Regular, Menlo, monospace;
    }
    textarea.code {
      min-height: 320px;
      resize: vertical;
      white-space: pre;
    }
    button {
      flex: none;
      font: inherit;
      color: inherit;
      border: 0;
      cursor: pointer;
      padding: 7px 12px;
      border-radius: 9px;
      background: var(--panel2, #23272e);
    }
    button:disabled {
      opacity: 0.4;
      cursor: default;
    }
    button.primary {
      background: var(--accent, #4f8cff);
      color: #fff;
      font-weight: 600;
    }
    button.danger:not(.ghost) {
      background: var(--red, #ff453a);
      color: #fff;
    }
    button.ghost {
      background: transparent;
      color: var(--muted, #9aa0a6);
    }
    button.ghost.danger {
      color: var(--red, #ff453a);
    }
    button.small {
      align-self: flex-start;
      padding: 4px 10px;
      font-size: 12px;
    }
    .seg {
      display: flex;
      gap: 2px;
      padding: 3px;
      border-radius: 9px;
      background: var(--panel2, #23272e);
    }
    .seg button {
      padding: 4px 10px;
      background: transparent;
      color: var(--muted, #9aa0a6);
    }
    .seg button.on {
      background: var(--on);
      color: var(--text, #e8eaed);
    }
    .intent {
      display: flex;
      flex-direction: column;
      gap: 8px;
      padding: 12px;
      border: 1px solid var(--line, #2f343c);
      border-radius: 10px;
    }
    .group {
      display: flex;
      flex-direction: column;
      gap: 6px;
    }
    .field {
      display: flex;
      flex-direction: column;
      gap: 4px;
    }
    ul.results {
      display: flex;
      flex-direction: column;
      gap: 6px;
      margin: 0;
      padding: 0;
      list-style: none;
    }
    ul.results li {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: baseline;
    }
    code {
      font: 12px ui-monospace, SFMono-Regular, Menlo, monospace;
    }
  `;
}

if (!customElements.get(SENTENCES_TAG)) customElements.define(SENTENCES_TAG, AssistRouterSentences);
