// Learning from what was said: the unrecognized commands of the log (grouped by sentence, with the topic the draft
// would choose, and ways to make the router understand them) and the test set run on the draft and on the saved
// file. A sentence becomes an example of a topic or a new topic in the draft; the test set is a file of its own,
// written at once.

import { LitElement, css, html, nothing } from "../vendor/lit-all.min.js";
import { setField } from "./fields.js";
import { keyFromName } from "./forms.js";
import { translate } from "./i18n.js";
import { freeKey, keysAt, readDocument, valueAt } from "./source.js";

const LEARN_TAG = "assist-router-learn";
export const KEY_LENGTH = 30;

const asList = (value) => (Array.isArray(value) ? value.map(String) : value == null || value === "" ? [] : [String(value)]);

/** The text with a sentence added as the last example of a topic (once). */
export function addExample(text, topic, sentence) {
  const path = ["topics", topic, "examples"];
  const examples = asList(valueAt(readDocument(text).doc, path));
  if (examples.some((example) => example.trim().toLowerCase() === sentence.trim().toLowerCase())) return text;
  return setField(text, path, [...examples, sentence.trim()]);
}

/** The text with a new topic made of a sentence (its description and first example), and its path. */
export function topicFromSentence(text, sentence) {
  const { doc } = readDocument(text);
  const key = freeKey(doc, ["topics"], keyFromName(sentence, "topic").slice(0, KEY_LENGTH).replace(/_+$/, ""));
  const value = { description: sentence.trim(), examples: [sentence.trim()] };
  return { text: setField(text, ["topics", key], value), path: ["topics", key] };
}

/** A test of a sentence that goes where it went on the draft; null when it went nowhere. */
export function testFrom(sentence, outcome) {
  if (outcome?.intent) return { sentence, intent: outcome.intent };
  if (outcome?.topic) return { sentence, topic: outcome.topic };
  return null;
}

class AssistRouterLearn extends LitElement {
  static properties = {
    hass: { attribute: false },
    text: { attribute: false },
    mode: { attribute: false },
    tests: { attribute: false },
    _groups: { state: true },
    _rows: { state: true },
    _error: { state: true },
    _search: { state: true },
    _showHidden: { state: true },
    _outcomes: { state: true },
    _busy: { state: true },
    _run: { state: true },
    _new: { state: true },
  };

  constructor() {
    super();
    this._search = "";
    this._showHidden = false;
    this._outcomes = {};
    this._new = { sentence: "", topic: "" };
  }

  _t(key, values, fallback) {
    return translate(this.hass?.language, key, values, fallback);
  }

  _ws(message) {
    return this.hass.callWS({ ...message, type: `assist_router/editor/${message.type}` });
  }

  updated(changed) {
    if (changed.has("mode") && this.mode === "unrecognized" && !this._groups) this._loadLog();
  }

  async _loadLog() {
    try {
      const loaded = await this._ws({ type: "unrecognized" });
      this._groups = loaded.groups;
      this._rows = loaded.rows;
      this._error = null;
    } catch (err) {
      this._groups = [];
      this._error = err.message ?? String(err);
    }
  }

  _edit(change) {
    try {
      const result = change(this.text);
      const detail = typeof result === "string" ? { text: result } : result;
      this.dispatchEvent(new CustomEvent("edit", { detail: { coalesce: null, ...detail } }));
    } catch (err) {
      this._error = err.message ?? String(err);
    }
  }

  _changeTests(tests) {
    this.dispatchEvent(new CustomEvent("tests-changed", { detail: { tests } }));
  }

  _addTest(test) {
    if (!test) return;
    const tests = this.tests ?? [];
    if (tests.some((item) => item.sentence.toLowerCase() === test.sentence.toLowerCase())) return;
    this._changeTests([...tests, test]);
  }

  async _hide(group, hidden) {
    try {
      await this._ws({ type: "unrecognized_hide", key: group.key, hidden });
      this._groups = this._groups.map((item) => (item.key === group.key ? { ...item, hidden } : item));
    } catch (err) {
      this._error = err.message ?? String(err);
    }
  }

  _visible() {
    const words = this._search.trim().toLowerCase().split(/\s+/).filter(Boolean);
    return (this._groups ?? []).filter(
      (group) => (this._showHidden || !group.hidden) && words.every((word) => group.text.toLowerCase().includes(word)),
    );
  }

  async _classify() {
    const sentences = this._visible()
      .map((group) => group.text)
      .slice(0, 50);
    if (!sentences.length) return;
    this._busy = true;
    try {
      const found = await this._ws({ type: "classify", text: this.text, sentences });
      this._outcomes = { ...this._outcomes, ...Object.fromEntries(found.map((item) => [item.sentence, item])) };
      this._error = null;
    } catch (err) {
      this._error = err.message ?? String(err);
    } finally {
      this._busy = false;
    }
  }

  async _runTests() {
    this._busy = true;
    try {
      this._run = await this._ws({ type: "tests_run", text: this.text, compare: true });
      this._error = null;
    } catch (err) {
      this._error = err.message ?? String(err);
    } finally {
      this._busy = false;
    }
  }

  _try(sentence) {
    this.dispatchEvent(new CustomEvent("try", { detail: { sentence } }));
  }

  _open(path) {
    this.dispatchEvent(new CustomEvent("select", { detail: { path } }));
  }

  render() {
    if (!this.hass) return nothing;
    return html`<div class="learn" data-learn=${this.mode}>
      ${this._error ? html`<p class="bad" data-learn-error>${this._t("error", { message: this._error })}</p>` : nothing}
      ${this.mode === "tests" ? this._renderTests() : this._renderLog()}
    </div>`;
  }

  _outcomeText(outcome) {
    if (!outcome) return nothing;
    if (outcome.intent) return html`<span class="ok" data-outcome-of>${this._t("learn_goes_ha", { intent: outcome.intent })}</span>`;
    if (outcome.topic)
      return html`<span data-outcome-of>${this._t("learn_goes_topic")}
        <button class="link" data-open-topic=${outcome.topic} @click=${() => this._open(["topics", outcome.topic])}>${outcome.topic}</button></span>`;
    return html`<span class="warn" data-outcome-of>${this._t("learn_goes_nowhere")}</span>`;
  }

  _renderLog() {
    if (!this._groups) return html`<p class="muted">${this._t("loading")}</p>`;
    const topics = keysAt(readDocument(this.text ?? "").doc, ["topics"]);
    const groups = this._visible();
    const hidden = this._groups.filter((group) => group.hidden).length;
    return html`<section>
      <h2>${this._t("key_unrecognized")}</h2>
      <p class="hint">${this._t("learn_log_hint", { rows: this._rows ?? 0, sentences: this._groups.length })}</p>
      <div class="bar">
        <input data-log-search placeholder=${this._t("search")} .value=${this._search} @input=${(event) => (this._search = event.target.value)} />
        <label class="check"
          ><input type="checkbox" data-show-hidden .checked=${this._showHidden} @change=${(event) => (this._showHidden = event.target.checked)} />
          ${this._t("learn_show_hidden", { count: hidden })}</label
        >
        <button class="primary" data-classify ?disabled=${this._busy || !groups.length} @click=${this._classify}>
          ${this._busy ? this._t("learn_classifying") : this._t("learn_classify")}
        </button>
        <button data-reload @click=${this._loadLog}>${this._t("learn_reload")}</button>
      </div>
      ${groups.length
        ? html`<div class="rows">
            ${groups.map((group) => this._renderGroup(group, topics))}
          </div>`
        : html`<p class="muted" data-log-empty>${this._t("learn_log_empty")}</p>`}
    </section>`;
  }

  _renderGroup(group, topics) {
    const outcome = this._outcomes[group.text];
    const test = testFrom(group.text, outcome);
    return html`<div class="row ${group.hidden ? "hidden" : ""}" data-log-sentence=${group.key}>
      <div class="sentence">
        <strong>${group.text}</strong>
        <span class="muted"
          >${this._t("learn_meta", { count: group.count, last: group.last })}${group.speakers.length ? ` · ${group.speakers.join(", ")}` : ""}${group.areas.length
            ? ` · ${group.areas.join(", ")}`
            : ""}</span
        >
        <span class="muted">${group.route ? this._t("learn_was", { route: group.route }) : this._t(`learn_kind_${group.kinds[0]}`, null, group.kinds[0] ?? "")}</span>
        ${this._outcomeText(outcome)}
      </div>
      <div class="actions">
        <select
          data-add-example
          @change=${(event) => {
            const topic = event.target.value;
            event.target.value = "";
            if (topic) this._edit((text) => addExample(text, topic, group.text));
          }}
        >
          <option value="">${this._t("learn_as_example")}</option>
          ${topics.map((topic) => html`<option value=${topic}>${topic}</option>`)}
        </select>
        <button data-new-topic @click=${() => this._edit((text) => topicFromSentence(text, group.text))}>${this._t("learn_new_topic")}</button>
        <button data-try @click=${() => this._try(group.text)}>${this._t("learn_try")}</button>
        <button data-to-tests ?disabled=${!test} title=${test ? "" : this._t("learn_to_tests_first")} @click=${() => this._addTest(test)}>
          ${this._t("learn_to_tests")}
        </button>
        <button class="ghost" data-hide @click=${() => this._hide(group, !group.hidden)}>
          ${group.hidden ? this._t("learn_unhide") : this._t("learn_hide")}
        </button>
      </div>
    </div>`;
  }

  _renderTests() {
    const tests = this.tests ?? [];
    const topics = keysAt(readDocument(this.text ?? "").doc, ["topics"]);
    const results = this._run?.results ?? [];
    const summary = this._run?.summary;
    const update = (index, change) => this._changeTests(tests.map((test, at) => (at === index ? change(test) : test)));
    const expectation = (test, value) => {
      const { topic, intent, ...rest } = test;
      if (value === "@intent") return { ...rest, intent: intent || "HassTurnOn" };
      return value ? { ...rest, topic: value } : rest;
    };
    return html`<section>
      <h2>${this._t("key_tests")}</h2>
      <p class="hint">${this._t("learn_tests_hint")}</p>
      <div class="bar">
        <button class="primary" data-run-tests ?disabled=${this._busy || !tests.length} @click=${this._runTests}>
          ${this._busy ? this._t("learn_running") : this._t("learn_run_tests")}
        </button>
        ${summary
          ? html`<span class="summary" data-summary>
              <span class="ok">${this._t("learn_passed", { count: summary.passed, total: summary.total })}</span>
              ${summary.failed ? html`<span class="bad">${this._t("learn_failed", { count: summary.failed })}</span>` : nothing}
              ${summary.fixed ? html`<span class="ok" data-fixed>${this._t("learn_fixed", { count: summary.fixed })}</span>` : nothing}
              ${summary.broken ? html`<span class="bad" data-broken>${this._t("learn_broken", { count: summary.broken })}</span>` : nothing}
            </span>`
          : nothing}
      </div>
      <div class="rows">
        ${tests.map((test, index) => {
          const result = results.find((item) => item.sentence === test.sentence);
          const expected = test.intent ? "@intent" : (test.topic ?? "");
          return html`<div class="row test" data-test=${index}>
            <div class="sentence">
              <input
                data-test-sentence
                .value=${test.sentence}
                @change=${(event) => event.target.value.trim() && update(index, (item) => ({ ...item, sentence: event.target.value.trim() }))}
              />
              ${result ? this._renderResult(result) : nothing}
            </div>
            <div class="actions">
              <select data-test-expect @change=${(event) => update(index, (item) => expectation(item, event.target.value))}>
                <option value="" ?selected=${!expected}>${this._t("learn_expect_none")}</option>
                ${topics.map((topic) => html`<option value=${topic} ?selected=${expected === topic}>${topic}</option>`)}
                ${test.topic && !topics.includes(test.topic)
                  ? html`<option value=${test.topic} selected>${this._t("learn_missing_topic", { topic: test.topic })}</option>`
                  : nothing}
                <option value="@intent" ?selected=${expected === "@intent"}>${this._t("learn_expect_intent")}</option>
              </select>
              ${test.intent
                ? html`<input
                    class="mono short"
                    data-test-intent
                    .value=${test.intent}
                    @change=${(event) => update(index, (item) => ({ ...item, intent: event.target.value.trim() || "HassTurnOn" }))}
                  />`
                : nothing}
              <button data-try @click=${() => this._try(test.sentence)}>${this._t("learn_try")}</button>
              <button class="ghost" data-remove-test @click=${() => this._changeTests(tests.filter((_, at) => at !== index))}>
                ${this._t("form_remove")}
              </button>
            </div>
          </div>`;
        })}
      </div>
      <form
        class="bar"
        data-new-test
        @submit=${(event) => {
          event.preventDefault();
          const sentence = this._new.sentence.trim();
          if (!sentence) return;
          this._addTest(this._new.topic ? { sentence, topic: this._new.topic } : { sentence });
          this._new = { sentence: "", topic: "" };
        }}
      >
        <input
          data-new-sentence
          placeholder=${this._t("learn_new_sentence")}
          .value=${this._new.sentence}
          @input=${(event) => (this._new = { ...this._new, sentence: event.target.value })}
        />
        <select data-new-topic-select @change=${(event) => (this._new = { ...this._new, topic: event.target.value })}>
          <option value="">${this._t("learn_expect_none")}</option>
          ${topics.map((topic) => html`<option value=${topic} ?selected=${this._new.topic === topic}>${topic}</option>`)}
        </select>
        <button class="primary" type="submit">${this._t("learn_add_test")}</button>
      </form>
    </section>`;
  }

  _renderResult(result) {
    const where = (outcome) =>
      outcome?.intent ? `HA: ${outcome.intent}` : outcome?.topic ? outcome.topic : this._t("learn_no_topic");
    const change = result.ok && result.ok_saved === false ? "fixed" : !result.ok && result.ok_saved ? "broken" : null;
    return html`<span class="result ${result.ok ? "ok" : "bad"}" data-result=${result.ok ? "ok" : "failed"}>
      ${result.ok ? "✓" : "✗"} ${this._t("learn_draft_gives", { where: where(result.draft) })}
      ${"saved" in result ? html`<span class="muted"> · ${this._t("learn_saved_gives", { where: where(result.saved) })}</span>` : nothing}
      ${change ? html`<span class="badge ${change}" data-change=${change}>${this._t(`learn_${change}_one`)}</span>` : nothing}
    </span>`;
  }

  static styles = css`
    :host {
      display: block;
      min-height: 0;
      overflow: auto;
    }
    section {
      display: flex;
      flex-direction: column;
      gap: 12px;
      padding: 14px 16px;
      border-radius: 12px;
      background: var(--panel, #1b1e24);
    }
    h2 {
      margin: 0;
      font-size: 11px;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      color: var(--muted, #9aa0a6);
    }
    p {
      margin: 0;
    }
    .hint,
    .muted {
      font-size: 12px;
      color: var(--muted, #9aa0a6);
    }
    .ok {
      color: var(--green, #30d158);
    }
    .warn {
      color: var(--amber, #ffb340);
    }
    .bad {
      color: var(--red, #ff453a);
    }
    .bar {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
    }
    .bar input:not([type]) {
      flex: 1;
      min-width: 200px;
    }
    input,
    select {
      box-sizing: border-box;
      padding: 6px 10px;
      border: 1px solid var(--line, #2f343c);
      border-radius: 8px;
      outline: none;
      color: var(--text, #e8eaed);
      background: var(--field);
      font: inherit;
    }
    input[type="checkbox"] {
      padding: 0;
    }
    .mono {
      font: 13px ui-monospace, SFMono-Regular, Menlo, monospace;
    }
    .short {
      width: 160px;
    }
    button {
      font: inherit;
      color: inherit;
      border: 0;
      cursor: pointer;
      padding: 6px 11px;
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
    button.ghost {
      background: transparent;
      color: var(--muted, #9aa0a6);
    }
    button.link {
      padding: 0;
      background: none;
      color: var(--accent, #4f8cff);
      font-weight: 600;
    }
    .check {
      display: inline-flex;
      gap: 6px;
      align-items: center;
      font-size: 13px;
    }
    .rows {
      display: flex;
      flex-direction: column;
      gap: 6px;
    }
    .row {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      justify-content: space-between;
      padding: 10px 12px;
      border-radius: 10px;
      background: var(--panel2, #23272e);
    }
    .row.hidden {
      opacity: 0.55;
    }
    .sentence {
      display: flex;
      flex: 1;
      flex-direction: column;
      gap: 3px;
      min-width: 240px;
    }
    .test .sentence input {
      width: 100%;
    }
    .actions {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      align-items: flex-start;
    }
    .summary {
      display: inline-flex;
      gap: 12px;
      font-weight: 600;
    }
    .result {
      font-size: 13px;
    }
    .badge {
      margin-left: 6px;
      padding: 1px 8px;
      border-radius: 999px;
      font-size: 11px;
      font-weight: 600;
    }
    .badge.fixed {
      color: var(--green, #30d158);
      background: rgba(48, 209, 88, 0.15);
    }
    .badge.broken {
      color: var(--red, #ff453a);
      background: rgba(255, 69, 58, 0.15);
    }
  `;
}

if (!customElements.get(LEARN_TAG)) customElements.define(LEARN_TAG, AssistRouterLearn);
