// The tester of the editor: a sentence goes the way a spoken one would (Home Assistant, the router, the data,
// the answer) on the draft, step by step. The server does nothing on the way: control is only planned, nothing is
// said, announced or logged.

import { LitElement, css, html, nothing } from "../vendor/lit-all.min.js";
import { translate } from "./i18n.js";
import { keysAt, readDocument, valueAt } from "./source.js";
import { readStored, writeStored } from "./stored.js";
import { callWS } from "./ws.js";

// A test runs the whole router, with its model: it may take longer than a plain question to Home Assistant.
const TEST_TIMEOUT_MS = 180000;

const TESTER_TAG = "assist-router-tester";
const RECENT_KEY = "assist-router-editor-tests";
export const RECENT_LIMIT = 10;

const readRecent = () => {
  try {
    const recent = JSON.parse(readStored(RECENT_KEY) ?? "[]");
    return Array.isArray(recent) ? recent.filter((item) => typeof item === "string") : [];
  } catch {
    return [];
  }
};

/** The sentences tried last, newest first, each once. */
export function rememberSentence(recent, sentence) {
  const text = sentence.trim();
  return text ? [text, ...recent.filter((item) => item !== text)].slice(0, RECENT_LIMIT) : recent;
}

class AssistRouterTester extends LitElement {
  static properties = {
    hass: { attribute: false },
    text: { attribute: false },
    // A sentence sent here from elsewhere in the editor ({ sentence, at }), tested at once.
    request: { attribute: false },
    _sentence: { state: true },
    _options: { state: true },
    _open: { state: true },
    _busy: { state: true },
    _trace: { state: true },
    _error: { state: true },
    _recent: { state: true },
  };

  constructor() {
    super();
    this._sentence = "";
    this._options = { speaker: "", persona: "", area: "", compare: false, skip_ha: false, answer: true };
    this._open = false;
    this._recent = readRecent();
  }

  _t(key, values, fallback) {
    return translate(this.hass?.language, key, values, fallback);
  }

  updated(changed) {
    if (changed.has("request") && this.request?.sentence) {
      this._sentence = this.request.sentence;
      this._run(this.request.sentence);
      this.scrollIntoView?.({ block: "nearest" });
    }
  }

  async _run(sentence = this._sentence) {
    const text = sentence.trim();
    if (!text || this._busy) return;
    this._sentence = text;
    this._busy = true;
    this._error = null;
    this._recent = rememberSentence(this._recent, text);
    writeStored(RECENT_KEY, JSON.stringify(this._recent));
    const { speaker, persona, area, ...flags } = this._options;
    try {
      this._trace = await callWS(
        this.hass,
        {
          type: "assist_router/editor/test",
          text: this.text,
          sentence: text,
          speaker: speaker || null,
          persona: persona || null,
          area: area || null,
          ...flags,
        },
        TEST_TIMEOUT_MS,
      );
    } catch (err) {
      this._trace = null;
      this._error = err.message ?? String(err);
    } finally {
      this._busy = false;
    }
  }

  _set(key, value) {
    this._options = { ...this._options, [key]: value };
  }

  _openTopic(topic) {
    this.dispatchEvent(new CustomEvent("select", { detail: { path: ["topics", topic] } }));
  }

  render() {
    if (!this.hass) return nothing;
    const { doc } = readDocument(this.text ?? "");
    const people = keysAt(doc, ["people"]);
    const personas = keysAt(doc, ["personas"]);
    const areas = Object.values(this.hass.areas ?? {}).map((area) => area.name).filter(Boolean).sort();
    return html`<section class="card" data-tester>
      <h3>${this._t("tester_title")}</h3>
      <form
        class="ask"
        @submit=${(event) => {
          event.preventDefault();
          this._run();
        }}
      >
        <input
          data-sentence
          list="recent"
          placeholder=${this._t("tester_placeholder")}
          .value=${this._sentence}
          @input=${(event) => (this._sentence = event.target.value)}
        />
        <button class="primary" type="submit" data-run ?disabled=${this._busy || !this._sentence.trim()}>
          ${this._busy ? this._t("tester_running") : this._t("tester_run")}
        </button>
      </form>
      <datalist id="recent">${this._recent.map((item) => html`<option value=${item}></option>`)}</datalist>
      <details class="options" ?open=${this._open} @toggle=${(event) => (this._open = event.target.open)}>
        <summary>${this._t("tester_options")}</summary>
        <label
          >${this._t("tester_speaker")}
          <select data-option="speaker" @change=${(event) => this._set("speaker", event.target.value)}>
            <option value="">${this._t("tester_nobody")}</option>
            ${people.map((key) => {
              const person = valueAt(doc, ["people", key]);
              const name = typeof person === "string" ? person : (person?.name ?? key);
              return html`<option value=${key} ?selected=${this._options.speaker === key}>${name}</option>`;
            })}
          </select>
        </label>
        ${personas.length
          ? html`<label
              >${this._t("tester_persona")}
              <select data-option="persona" @change=${(event) => this._set("persona", event.target.value)}>
                <option value="">${this._t("tester_no_persona")}</option>
                ${personas.map((key) => html`<option value=${key} ?selected=${this._options.persona === key}>${key}</option>`)}
              </select>
            </label>`
          : nothing}
        <label
          >${this._t("tester_area")}
          <input
            data-option="area"
            list="tester-areas"
            .value=${this._options.area}
            @input=${(event) => this._set("area", event.target.value)}
          />
        </label>
        <datalist id="tester-areas">${areas.map((name) => html`<option value=${name}></option>`)}</datalist>
        ${["compare", "skip_ha", "answer"].map(
          (key) => html`<label class="check">
            <input
              type="checkbox"
              data-option=${key}
              .checked=${this._options[key]}
              @change=${(event) => this._set(key, event.target.checked)}
            />${this._t(`tester_${key}`)}
          </label>`,
        )}
      </details>
      <p class="hint">${this._t("tester_hint")}</p>
      ${this._error ? html`<p class="bad" data-tester-error>${this._t("error", { message: this._error })}</p>` : nothing}
      ${this._trace ? this._renderTrace(this._trace) : nothing}
    </section>`;
  }

  _renderTrace(trace, nested = false) {
    return html`<div class="trace ${nested ? "nested" : ""}" data-trace=${nested ? "part" : "sentence"}>
      ${nested ? html`<p class="part-text">${this._t("quoted", { text: trace.text })}</p>` : nothing} ${this._renderOutcome(trace, nested)}
      <ol class="steps">
        ${trace.ha ? this._renderHa(trace.ha) : nothing}
        ${trace.parts
          ? html`<li data-step="parts">
              <span class="step">${this._t("step_parts", { count: trace.parts.length })}</span>
              ${trace.parts.map((part) => this._renderTrace(part, true))}
            </li>`
          : nothing}
        ${trace.router ? this._renderRouter(trace) : nothing}
        ${trace.route ? this._renderRoute(trace.route) : nothing}
        ${trace.unclear ? this._step("unclear", trace.unclear.ms, html`<span>${trace.unclear.guess ?? "—"}</span>`) : nothing}
        ${trace.control ? this._renderControl(trace.control) : nothing}
        ${trace.data ? this._renderData(trace.data) : nothing}
        ${trace.knowledge
          ? this._step(
              "knowledge",
              trace.knowledge.ms,
              html`<span>${trace.knowledge.phrase} · ${trace.knowledge.found ? this._t("tester_found") : this._t("tester_not_found")}</span>`,
            )
          : nothing}
        ${trace.answer ? this._renderAnswer(trace.answer) : nothing}
      </ol>
    </div>`;
  }

  _renderOutcome(trace, nested = false) {
    const kind = trace.outcome ?? "fallback";
    const good = ["ha", "answer", "knowledge", "control_execute", "parts"].includes(kind);
    const test = trace.ha?.match
      ? { sentence: trace.text, intent: trace.ha.intent ?? "trigger" }
      : trace.router?.topic
        ? { sentence: trace.text, topic: trace.router.topic }
        : null;
    return html`<div class="outcome ${good ? "good" : "other"}" data-outcome=${kind}>
      <strong>${this._t(`outcome_${kind}`, null, kind)}</strong>
      ${trace.speech ? html`<span class="speech" data-speech>${this._t("quoted", { text: trace.speech })}</span>` : nothing}
      ${test && !nested
        ? html`<button
            class="small"
            data-add-test
            title=${this._t("tester_add_test_hint")}
            @click=${() => this.dispatchEvent(new CustomEvent("add-test", { detail: { test } }))}
          >
            ${this._t("tester_add_test")}
          </button>`
        : nothing}
    </div>`;
  }

  _step(name, ms, body) {
    return html`<li data-step=${name}>
      <span class="step">${this._t(`step_${name}`)}${ms != null ? html`<span class="ms">${ms} ms</span>` : nothing}</span>
      ${body}
    </li>`;
  }

  _renderHa(ha) {
    let body;
    if (ha.match === true) {
      body = html`<span class="ok">${this._t("ha_match", { intent: ha.intent ?? ha.template })}</span>
        <span class="muted">${this._t(`ha_source_${ha.source}`, null, ha.source ?? "")}${ha.file ? ` · ${ha.file}` : ""}</span>
        ${ha.template ? html`<code>${ha.template}</code>` : nothing}`;
    } else if (ha.match === false) {
      body = html`<span class="warn">${this._t("ha_partial", { intent: ha.intent })}</span>
        ${Object.keys(ha.unmatched ?? {}).length ? html`<code>${JSON.stringify(ha.unmatched)}</code>` : nothing}`;
    } else {
      body = html`<span class="muted">${this._t("ha_none")}</span>`;
    }
    return this._step("ha", ha.ms, body);
  }

  _renderRouter(trace) {
    const { router } = trace;
    const changed = "saved_topic" in trace && trace.saved_topic !== router.topic;
    return this._step(
      "router",
      router.ms,
      html`${router.topic
          ? html`<button class="link" data-topic=${router.topic} @click=${() => this._openTopic(router.topic)}>${router.topic}</button>`
          : html`<span class="warn">${this._t("router_none")}</span>`}
        <span class="muted">${router.model}</span>
        ${"saved_topic" in trace
          ? html`<span class=${changed ? "warn" : "muted"} data-saved-topic
              >${this._t(changed ? "router_saved_other" : "router_saved_same", { topic: trace.saved_topic ?? "—" })}</span
            >`
          : nothing}`,
    );
  }

  _renderRoute(route) {
    const parts = [
      route.people.length ? this._t("route_people", { people: route.people.join(", ") }) : null,
      route.when ? this._t("route_when", { when: route.when }) : null,
      route.phrase ? this._t("route_phrase", { phrase: route.phrase }) : null,
    ].filter(Boolean);
    return this._step("route", null, html`<span class="muted">${parts.length ? parts.join(" · ") : this._t("route_none")}</span>`);
  }

  _renderControl(control) {
    const plan = control.plan;
    return this._step(
      "control",
      control.ms,
      plan
        ? html`<span>${plan.description}</span>
            <code>${plan.intent} ${JSON.stringify(plan.slots)}</code>
            ${plan.confirm ? html`<span class="warn">${this._t("control_confirm", { reason: plan.confirm })}</span>` : nothing}
            ${plan.error ? html`<span class="bad">${plan.error}</span>` : nothing}
            <span class="muted">${this._t("control_dry")}</span>`
        : html`<span class="warn">${control.reason ?? this._t("control_not_parsed")}</span>`,
    );
  }

  _renderData(data) {
    return this._step(
      "data",
      data.ms,
      html`${data.command
          ? html`<span>${this._t("data_command", { sentence: data.command.sentence })}</span>
              <span class=${data.command.ha.match ? "ok" : "warn"}
                >${data.command.ha.match ? this._t("data_command_known") : this._t("data_command_unknown")}</span
              >`
          : nothing}
        ${data.command_error ? html`<span class="bad">${data.command_error}</span>` : nothing}
        ${this._expand("data_lines", data.lines)} ${this._expand("data_sources", data.sources)}
        ${!data.command && !data.lines.length && !data.sources.length ? html`<span class="muted">${this._t("data_none")}</span>` : nothing}`,
    );
  }

  _expand(key, items) {
    if (!items?.length) return nothing;
    return html`<details data-expand=${key}>
      <summary>${this._t(key, { count: items.length })}</summary>
      <pre>${items.join(key === "data_sources" ? "\n\n" : "\n")}</pre>
    </details>`;
  }

  _renderAnswer(answer) {
    const prompt = answer.messages.map((message) => `[${message.role}]\n${message.content}`).join("\n\n");
    return this._step(
      "answer",
      answer.ms,
      html`${answer.text
          ? html`<span>${answer.text}</span>`
          : html`<span class="muted">${answer.model ? this._t("answer_skipped") : this._t("answer_no_model")}</span>`}
        ${answer.model ? html`<span class="muted">${answer.model}</span>` : nothing}
        <details data-expand="prompt">
          <summary>${this._t("answer_prompt")}</summary>
          <pre>${prompt}</pre>
        </details>`,
    );
  }

  static styles = css`
    :host {
      display: block;
    }
    .card {
      padding: 12px 14px;
      border-radius: 12px;
      background: var(--panel2, #23272e);
    }
    h3 {
      margin: 0 0 8px;
      font-size: 11px;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      color: var(--muted, #9aa0a6);
    }
    .ask {
      display: flex;
      gap: 6px;
    }
    input,
    select {
      box-sizing: border-box;
      min-width: 0;
      padding: 7px 10px;
      border: 1px solid var(--line, #2f343c);
      border-radius: 8px;
      outline: none;
      color: var(--text, #e8eaed);
      background: var(--field);
      font: inherit;
    }
    .ask input {
      flex: 1;
    }
    button {
      font: inherit;
      color: inherit;
      border: 0;
      cursor: pointer;
      padding: 7px 12px;
      border-radius: 9px;
      background: var(--panel, #1b1e24);
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
    button.link {
      padding: 0;
      background: none;
      color: var(--accent, #4f8cff);
      font-weight: 600;
    }
    .options {
      margin-top: 8px;
      font-size: 13px;
    }
    .options summary {
      cursor: pointer;
      color: var(--muted, #9aa0a6);
    }
    .options label {
      display: flex;
      flex-direction: column;
      gap: 3px;
      margin-top: 6px;
    }
    .options label.check {
      flex-direction: row;
      align-items: center;
      gap: 6px;
    }
    .hint,
    .muted {
      font-size: 12px;
      color: var(--muted, #9aa0a6);
    }
    .hint {
      margin: 8px 0 0;
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
    .outcome {
      display: flex;
      flex-direction: column;
      gap: 4px;
      margin: 10px 0 6px;
      padding: 8px 10px;
      border-radius: 8px;
      background: rgba(255, 179, 64, 0.12);
    }
    .outcome.good {
      background: rgba(48, 209, 88, 0.12);
    }
    .speech {
      font-style: italic;
    }
    button.small {
      align-self: flex-start;
      padding: 3px 9px;
      font-size: 12px;
    }
    .steps {
      display: flex;
      flex-direction: column;
      gap: 8px;
      margin: 0;
      padding-left: 18px;
    }
    .steps li {
      display: flex;
      flex-direction: column;
      align-items: flex-start;
      gap: 3px;
    }
    .steps li > .step,
    .steps li > details {
      align-self: stretch;
    }
    .step {
      display: flex;
      justify-content: space-between;
      font-size: 12px;
      font-weight: 600;
      color: var(--muted, #9aa0a6);
    }
    .ms {
      font-weight: 400;
    }
    code,
    pre {
      font: 12px/1.45 ui-monospace, SFMono-Regular, Menlo, monospace;
      white-space: pre-wrap;
      word-break: break-word;
    }
    pre {
      max-height: 240px;
      overflow: auto;
      margin: 4px 0 0;
      padding: 8px;
      border-radius: 6px;
      background: var(--field);
    }
    details summary {
      cursor: pointer;
      font-size: 12px;
      color: var(--muted, #9aa0a6);
    }
    .nested {
      margin-top: 6px;
      padding-left: 8px;
      border-left: 2px solid var(--line, #2f343c);
    }
    .part-text {
      margin: 0;
      font-weight: 600;
    }
  `;
}

if (!customElements.get(TESTER_TAG)) customElements.define(TESTER_TAG, AssistRouterTester);
