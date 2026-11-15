// The windows of the editor: saving the draft to router.yaml (what changes, the router's check, what is worth a
// look, the test set on the draft, a note) and the history of saves (a version against the file now, restored as a
// draft).

import { LitElement, css, html, nothing } from "../vendor/lit-all.min.js";
import { describeChanges, diffHunks, diffLines } from "./changes.js";
import { translate } from "./i18n.js";

const label = (key) => key.replace(/^topics\//, "");

/** The differences between two texts as lines, only those changed and a few around them. */
export function renderDiff(before, after, t) {
  const hunks = diffHunks(diffLines(before, after));
  return html`<pre class="diff" data-diff>${hunks.map((line) =>
    line.kind === "skip"
      ? html`<div class="skip">${t("lines_skipped", { count: line.count })}</div>`
      : html`<div class=${line.kind}><span class="no">${line.line ?? ""}</span><span class="sign">${
          line.kind === "added" ? "+" : line.kind === "removed" ? "−" : " "
        }</span>${line.text}</div>`,
  )}</pre>`;
}

export const dialogStyles = css`
  :host {
    position: fixed;
    inset: 0;
    z-index: 10;
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--scrim);
    color: var(--text, #e8eaed);
    font: 14px/1.4 -apple-system, "SF Pro Text", Roboto, system-ui, sans-serif;
    --mdc-icon-size: 18px;
  }
  .box {
    display: flex;
    flex-direction: column;
    gap: 12px;
    width: min(880px, calc(100vw - 48px));
    max-height: calc(100vh - 64px);
    padding: 18px 20px;
    border-radius: 14px;
    background: var(--panel);
    box-shadow: 0 30px 80px var(--shadow);
    box-sizing: border-box;
  }
  h2 {
    margin: 0;
    font-size: 17px;
  }
  h3 {
    margin: 4px 0 0;
    font-size: 12px;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--muted);
  }
  .scroll {
    display: flex;
    flex-direction: column;
    gap: 10px;
    min-height: 0;
    overflow: auto;
  }
  .row {
    display: flex;
    gap: 8px;
    justify-content: flex-end;
    align-items: center;
  }
  .grow {
    flex: 1;
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
    background: var(--panel2);
  }
  button:disabled {
    opacity: 0.4;
    cursor: default;
  }
  button.primary {
    background: var(--accent);
    color: #fff;
    font-weight: 600;
  }
  button.danger {
    background: var(--red);
    color: #fff;
    font-weight: 600;
  }
  input {
    font: inherit;
    color: inherit;
    padding: 8px 10px;
    border: 1px solid var(--line);
    border-radius: 9px;
    background: var(--bg);
  }
  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    align-items: center;
  }
  .chip {
    padding: 2px 9px;
    border-radius: 999px;
    font: 12px ui-monospace, SFMono-Regular, Menlo, monospace;
    background: var(--panel2);
  }
  .chip.added {
    color: var(--added);
  }
  .chip.removed {
    color: var(--removed);
  }
  .chip.changed {
    color: var(--amber);
  }
  .note {
    padding: 8px 12px;
    border-radius: 9px;
    background: rgba(79, 140, 255, 0.15);
  }
  .note.error {
    background: rgba(255, 69, 58, 0.15);
  }
  .note.ok {
    background: rgba(48, 209, 88, 0.15);
  }
  .muted {
    color: var(--muted);
  }
  .ok-text {
    margin: 0;
    color: var(--green);
  }
  .row.start {
    justify-content: flex-start;
  }
  .tests {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  ul.checks {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  ul.checks li {
    display: flex;
    gap: 8px;
  }
  ul.checks .mark {
    flex: none;
    width: 1.2em;
    font-weight: 700;
  }
  ul.checks li.error .mark {
    color: var(--red);
  }
  ul.checks li.warn .mark {
    color: var(--amber);
  }
  pre.diff {
    margin: 0;
    padding: 8px 0;
    overflow: auto;
    border-radius: 9px;
    background: var(--bg);
    font: 12px/1.5 ui-monospace, SFMono-Regular, Menlo, monospace;
  }
  pre.diff div {
    padding: 0 10px;
    white-space: pre;
  }
  pre.diff .no {
    display: inline-block;
    width: 4ch;
    margin-right: 6px;
    text-align: right;
    color: var(--faint);
  }
  pre.diff .sign {
    display: inline-block;
    width: 2ch;
  }
  pre.diff .added {
    background: rgba(48, 209, 88, 0.14);
  }
  pre.diff .removed {
    background: rgba(255, 69, 58, 0.14);
  }
  pre.diff .skip {
    padding: 2px 10px;
    color: var(--faint);
    font-style: italic;
  }
  ul {
    margin: 0;
    padding: 0;
    list-style: none;
  }
  li button {
    width: 100%;
    justify-content: space-between;
    background: transparent;
  }
  li button.on {
    background: rgba(79, 140, 255, 0.18);
  }
  .versions {
    display: grid;
    grid-template-columns: 280px minmax(0, 1fr);
    gap: 14px;
    min-height: 0;
  }
  .versions ul {
    overflow: auto;
  }
`;

class SaveDialog extends LitElement {
  static properties = {
    language: {},
    before: {},
    after: {},
    check: { attribute: false },
    error: { attribute: false },
    busy: { type: Boolean },
    // What is worth a look: { loading, items: [{ level, code, … }], error }.
    checks: { attribute: false },
    // The test set: its tests, and its run on the draft: { busy, data, error }.
    tests: { attribute: false },
    testRun: { attribute: false },
    topics: { attribute: false },
    _note: { state: true },
  };

  constructor() {
    super();
    this._note = "";
  }

  _t(key, values) {
    return translate(this.language, key, values);
  }

  _close() {
    this.dispatchEvent(new CustomEvent("close"));
  }

  _checkText(item) {
    return this._t(`check_${item.code}`, {
      topic: item.topic ?? "",
      field: item.field ?? "",
      pattern: item.pattern ?? "",
      action: item.action ?? "",
      key: item.key ?? "",
      problem: item.problem ?? "",
    });
  }

  _renderChecks() {
    const checks = this.checks;
    if (!checks || checks.loading) return html`<p class="muted" data-checks="loading">${this._t("checks_loading")}</p>`;
    if (checks.error) return html`<p class="muted" data-checks="unavailable">${this._t("checks_unavailable")}</p>`;
    const items = checks.items ?? [];
    if (!items.length) return html`<p class="ok-text" data-checks="ok">${this._t("checks_ok")}</p>`;
    const errors = items.filter((item) => item.level === "error");
    const warnings = items.filter((item) => item.level !== "error");
    return html`<ul class="checks" data-checks="found">
      ${[...errors, ...warnings].map(
        (item) => html`<li class=${item.level} data-check-item=${item.code}>
          <span class="mark">${item.level === "error" ? "✗" : "!"}</span>${this._checkText(item)}
        </li>`,
      )}
    </ul>`;
  }

  _renderTests() {
    const tests = this.tests ?? [];
    const run = this.testRun ?? {};
    const missing = [...new Set(tests.map((test) => test.topic).filter((topic) => topic && !(this.topics ?? []).includes(topic)))];
    if (!tests.length) return html`<p class="muted" data-tests="none">${this._t("save_tests_none")}</p>`;
    const summary = run.data?.summary;
    const failed = (run.data?.results ?? []).filter((result) => !result.ok);
    return html`<div class="tests" data-tests>
      ${missing.length
        ? html`<div class="note error" data-tests-missing>${this._t("save_tests_missing", { topics: missing.join(", ") })}</div>`
        : nothing}
      <div class="row start">
        <button data-run-tests ?disabled=${run.busy} @click=${() => this.dispatchEvent(new CustomEvent("run-tests"))}>
          ${run.busy ? this._t("learn_running") : this._t("save_tests_run", { count: tests.length })}
        </button>
        ${summary
          ? html`<span data-tests-summary>
              ${this._t("learn_passed", { count: summary.passed, total: summary.total })}${summary.fixed
                ? ` · ${this._t("learn_fixed", { count: summary.fixed })}`
                : ""}${summary.broken ? ` · ${this._t("learn_broken", { count: summary.broken })}` : ""}
            </span>`
          : nothing}
      </div>
      ${run.error ? html`<div class="note error" data-tests-error>${this._t("error", { message: run.error })}</div>` : nothing}
      ${summary?.broken ? html`<div class="note error" data-tests-broken>${this._t("save_tests_broken", { count: summary.broken })}</div>` : nothing}
      ${failed.length
        ? html`<ul class="checks" data-tests-failed>
            ${failed.map(
              (result) => html`<li class=${result.ok_saved ? "error" : "warn"}>
                <span class="mark">${result.ok_saved ? "✗" : "!"}</span>${this._t("quoted", { text: result.sentence })} → ${result.draft?.intent
                  ? `HA: ${result.draft.intent}`
                  : (result.draft?.topic ?? this._t("learn_no_topic"))}
                <span class="muted">(${this._t("save_tests_expected", { where: result.intent ? `HA: ${result.intent}` : (result.topic ?? "—") })})</span>
              </li>`,
            )}
          </ul>`
        : nothing}
    </div>`;
  }

  _save(force) {
    this.dispatchEvent(new CustomEvent("save", { detail: { note: this._note.trim(), force } }));
  }

  render() {
    const changes = describeChanges(this.before, this.after);
    const none = this.before === this.after;
    const conflict = this.error?.code === "conflict";
    const invalid = this.check && !this.check.ok;
    const chips = (kind, keys) =>
      keys.length
        ? html`<span class="muted">${this._t(`change_${kind}`)}:</span>${keys.map(
            (key) => html`<span class="chip ${kind}" data-change=${kind}>${label(key)}</span>`,
          )}`
        : nothing;
    return html`<div class="box" role="dialog" aria-modal="true" data-save-dialog @keydown=${(event) => event.key === "Escape" && this._close()}>
      <h2>${this._t("save_title")}</h2>
      <div class="scroll">
        ${none
          ? html`<p class="muted">${this._t("no_changes")}</p>`
          : html`<h3>${this._t("changes")}</h3>
              <div class="chips" data-changes>
                ${chips("added", changes.added)} ${chips("removed", changes.removed)} ${chips("changed", changes.changed)}
                ${changes.other ? html`<span class="chip" data-change="other">${this._t("change_other")}</span>` : nothing}
              </div>
              <h3>${this._t("diff_title")}</h3>
              ${renderDiff(this.before, this.after, (key, values) => this._t(key, values))}`}
        ${invalid
          ? html`<div class="note error" data-invalid>${this._t("save_invalid")} <code>${this.check.error}</code></div>`
          : html`<h3>${this._t("checks_title")}</h3>
              ${this._renderChecks()}
              <h3>${this._t("save_tests_title")}</h3>
              ${this._renderTests()}`}
        ${conflict ? html`<div class="note error" data-conflict>${this._t("save_conflict")}</div>` : nothing}
        ${this.error && !conflict
          ? html`<div class="note error" data-error>${this._t("error", { message: this.error.message })}</div>`
          : nothing}
      </div>
      <input
        data-note
        placeholder=${this._t("note")}
        .value=${this._note}
        @input=${(event) => (this._note = event.target.value)}
        @keydown=${(event) => event.key === "Enter" && !none && !invalid && !this.busy && this._save(conflict)}
      />
      <div class="row">
        <button data-cancel @click=${this._close}>${this._t("cancel")}</button>
        ${conflict
          ? html`<button class="danger" data-force ?disabled=${this.busy || invalid} @click=${() => this._save(true)}>
              ${this._t("save_force")}
            </button>`
          : html`<button class="primary" data-confirm ?disabled=${this.busy || none || invalid} @click=${() => this._save(false)}>
              <ha-icon icon="mdi:content-save"></ha-icon>${this._t("save_now")}
            </button>`}
      </div>
    </div>`;
  }

  firstUpdated() {
    this.renderRoot.querySelector("[data-note]")?.focus();
  }

  static styles = dialogStyles;
}

class HistoryDialog extends LitElement {
  static properties = {
    language: {},
    history: { attribute: false },
    current: {},
    users: { attribute: false },
    hass: { attribute: false },
    _chosen: { state: true },
    _text: { state: true },
    _error: { state: true },
  };

  _t(key, values) {
    return translate(this.language, key, values);
  }

  _close() {
    this.dispatchEvent(new CustomEvent("close"));
  }

  async _choose(item) {
    this._chosen = item;
    this._text = null;
    this._error = null;
    try {
      const found = await this.hass.callWS({ type: "assist_router/editor/history_get", version: item.id });
      if (this._chosen === item) this._text = found.text;
    } catch (err) {
      this._error = err.message ?? String(err);
    }
  }

  _when(at) {
    return new Date(at).toLocaleString(this.language, { dateStyle: "medium", timeStyle: "short" });
  }

  render() {
    const history = this.history ?? [];
    return html`<div class="box" role="dialog" aria-modal="true" data-history-dialog @keydown=${(event) => event.key === "Escape" && this._close()}>
      <h2>${this._t("history_title")}</h2>
      ${history.length
        ? html`<div class="versions">
            <ul data-versions>
              ${history.map(
                (item) => html`<li>
                  <button class=${this._chosen?.id === item.id ? "on" : ""} data-version=${item.id} @click=${() => this._choose(item)}>
                    <span>${this._when(item.at)}<br /><span class="muted">${item.note || this._t("history_no_note")}</span></span>
                    <span class="muted">${this.users?.[item.by] ?? ""}</span>
                  </button>
                </li>`,
              )}
            </ul>
            <div class="scroll">
              ${this._error ? html`<div class="note error">${this._t("error", { message: this._error })}</div>` : nothing}
              ${!this._chosen
                ? html`<p class="muted">${this._t("history_pick")}</p>`
                : this._text == null
                  ? html`<p class="muted">${this._t("loading")}</p>`
                  : this._text === this.current
                    ? html`<p class="muted" data-same>${this._t("history_same")}</p>`
                    : renderDiff(this.current, this._text, (key, values) => this._t(key, values))}
            </div>
          </div>`
        : html`<p class="muted" data-history-empty>${this._t("history_empty")}</p>`}
      <div class="row">
        <button data-close @click=${this._close}>${this._t("close")}</button>
        <button
          class="primary"
          data-restore
          ?disabled=${!this._chosen || this._text == null}
          @click=${() => this.dispatchEvent(new CustomEvent("restore", { detail: { version: this._chosen.id } }))}
        >
          <ha-icon icon="mdi:backup-restore"></ha-icon>${this._t("history_restore")}
        </button>
      </div>
    </div>`;
  }

  static styles = dialogStyles;
}

if (!customElements.get("assist-router-save-dialog")) customElements.define("assist-router-save-dialog", SaveDialog);
if (!customElements.get("assist-router-history-dialog")) customElements.define("assist-router-history-dialog", HistoryDialog);
