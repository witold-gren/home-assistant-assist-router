// The lessons of the editor: the tasks a person new to it asks about first, the ones that go deeper and the ones set up
// once, each a short tour (tour.js) that goes where the task is done and frames one part at a time. A step can choose
// a node of the tree first (`prepare`) and wait for the framed button to be clicked (`advance: "click"`; Next instead
// does what the click would, `act`, so the steps after it have their part on the screen). The list
// (⚙ → Lessons) marks the ones gone through; a lesson that needs something the file has not got yet says what.
// The same lessons as in the editor of Home Dashboard (standard gpu-studio §5a).

import { LitElement, css, html } from "../vendor/lit-all.min.js";
import { dialogStyles } from "./dialogs.js";
import { translate } from "./i18n.js";
import { HOME_KEYS, SETTINGS_PATH, flattenOutline, nodeKey, topicKind } from "./outline.js";
import { readSentences } from "./sentences.js";
import { readDocument, valueAt } from "./source.js";
import { lessonsDone } from "./tour.js";

const choose = (path) => (app) => app?._select?.({ path });

// The topics of the file, and the one a lesson works on: the chosen one, else the first with data, else the first.
const topics = (app) => {
  const { doc } = readDocument(app?._text ?? "");
  const all = valueAt(doc, ["topics"]);
  return all && typeof all === "object" ? Object.keys(all) : [];
};
export function lessonTopic(app) {
  if (app?._selected?.[0] === "topics" && app._selected.length >= 2) return app._selected[1];
  const { doc } = readDocument(app?._text ?? "");
  const keys = topics(app);
  return keys.find((key) => topicKind(valueAt(doc, ["topics", key])) === "data") ?? keys[0] ?? null;
}
const chooseTopic = (app) => {
  const key = lessonTopic(app);
  if (key && (app._selected?.[0] !== "topics" || app._selected[1] !== key || app._selected.length !== 2)) {
    app._select({ path: ["topics", key] });
  }
  // The form, not the YAML of the topic: the lesson frames its fields.
  if (app?._tab !== "form") app?._showTab?.("form");
};
const field = (name) => (app) => [`assist-router-form >>> [data-field='topics/${lessonTopic(app)}/${name}']`];

// The files of commands of Home Assistant: the first one, the one chosen (kept when the lesson made it) and the
// first one with an intent (with the edit not saved yet).
const firstSentences = (app) => app?._sentences?.files?.[0] ?? null;
const sentencesText = (app, file) =>
  app?._sentenceEdits?.[nodeKey(["@sentences", file.language, file.name])] ?? file.text;
const withIntent = (app) =>
  app?._sentences?.files?.find((file) => readSentences(sentencesText(app, file)).intents.length) ?? null;
const chooseSentences = (app) => {
  if (app?._selected?.[0] === "@sentences" && app._selected.length === 3) return;
  const file = firstSentences(app);
  if (file) app._select({ path: ["@sentences", file.language, file.name] });
};
// What Next does instead of the + of the commands: the first file, or a new one with the usual name (not saved).
const openSentences = (app) => app._openSentencesFile(firstSentences(app)?.name ?? app._t("sentences_default_name"));
// The file with an intent, in the form (the lesson on the syntax frames its fields), or in YAML.
const sentencesView = (view) => (app) => {
  const form = app?.renderRoot?.querySelector("assist-router-sentences");
  if (form) form._view = view;
};
const chooseIntentFile = (app) => {
  const selected = app?._selected;
  const chosen = selected?.[0] === "@sentences" ? app._sentences.files.find((file) => file.language === selected[1] && file.name === selected[2]) : null;
  const file = chosen && readSentences(sentencesText(app, chosen)).intents.length ? chosen : withIntent(app);
  if (file && file !== chosen) app._select({ path: ["@sentences", file.language, file.name] });
  // The form of a file comes with the next render: switched back from YAML once it is there.
  setTimeout(() => sentencesView("form")(app), 0);
};

const FORM = ["[data-middle]"];
const SAVE = "assist-router-save-dialog >>>";
const HISTORY = "assist-router-history-dialog >>>";
const LEARN = "assist-router-learn >>>";
const TESTER = "assist-router-tester >>>";
const SENTENCES = "assist-router-sentences >>>";

/** What a lesson needs, and whether the editor has it. */
export const NEEDS = {
  topics: (app) => topics(app).length > 0,
  changes: (app) => Boolean(app?._changed),
  intents: (app) => Boolean(withIntent(app)),
};

export const LESSONS = [
  {
    key: "first_topic",
    icon: "mdi:plus-box-outline",
    steps: [
      { key: "add", targets: ["[data-add-topic]"], side: "right", advance: "click", act: (app) => app._addTopic() },
      { key: "name", targets: ["assist-router-form >>> [data-field='@key']"], fallback: FORM, side: "right" },
      { key: "description", targets: field("description"), fallback: FORM, side: "right" },
      { key: "examples", targets: field("examples"), fallback: FORM, side: "right" },
      { key: "kind", targets: ["assist-router-form >>> [data-kind-choice]"], fallback: FORM, side: "right" },
      { key: "side", targets: ["[data-kind]"], fallback: ["[data-side]"], side: "left" },
    ],
  },
  {
    key: "data",
    icon: "mdi:database-outline",
    needs: "topics",
    steps: [
      { key: "sources", targets: ["assist-router-form >>> [data-sources]"], fallback: FORM, side: "right", prepare: chooseTopic },
      { key: "entities", targets: field("entities"), fallback: FORM, side: "right" },
      { key: "details", targets: field("details"), fallback: FORM, side: "right" },
      { key: "fetch", targets: ["assist-router-form >>> [data-add-fetch]"], fallback: FORM, side: "right" },
      { key: "kind", targets: ["[data-kind]"], fallback: ["[data-side]"], side: "left" },
    ],
  },
  {
    key: "tester",
    icon: "mdi:play-circle-outline",
    steps: [
      { key: "sentence", targets: [`${TESTER} [data-sentence]`], fallback: ["[data-tester]"], side: "left" },
      { key: "who", targets: [`${TESTER} [data-option='speaker']`], fallback: ["[data-tester]"], side: "left" },
      { key: "run", targets: [`${TESTER} [data-run]`], fallback: ["[data-tester]"], side: "left", advance: "click" },
      { key: "trace", targets: [`${TESTER} [data-trace]`], fallback: ["[data-tester]"], side: "left" },
    ],
  },
  {
    key: "save",
    icon: "mdi:content-save-outline",
    needs: "changes",
    steps: [
      { key: "state", targets: ["[data-draft-state]"], side: "below" },
      { key: "open", targets: ["[data-save]"], side: "below-end", advance: "click", act: (app) => app._openSave() },
      { key: "changes", targets: [`${SAVE} [data-changes]`], fallback: [`${SAVE} [data-save-dialog]`], side: "below" },
      { key: "checks", targets: [`${SAVE} [data-checks]`], fallback: [`${SAVE} [data-save-dialog]`], side: "below" },
      { key: "tests", targets: [`${SAVE} [data-tests]`], fallback: [`${SAVE} [data-save-dialog]`], side: "below" },
      { key: "note", targets: [`${SAVE} [data-note]`, `${SAVE} [data-confirm]`], fallback: [`${SAVE} [data-save-dialog]`], side: "below-end" },
    ],
  },
  {
    key: "unrecognized",
    icon: "mdi:comment-question-outline",
    steps: [
      { key: "node", targets: ["[data-node='@unrecognized']"], side: "right", prepare: choose(["@unrecognized"]) },
      { key: "check", targets: [`${LEARN} [data-classify]`], fallback: FORM, side: "below" },
      { key: "row", targets: [`${LEARN} [data-log-sentence]`], fallback: [`${LEARN} [data-learn]`], side: "below" },
      { key: "example", targets: [`${LEARN} [data-add-example]`], fallback: [`${LEARN} [data-learn]`], side: "below" },
      { key: "topic", targets: [`${LEARN} [data-new-topic]`, `${LEARN} [data-try]`], fallback: [`${LEARN} [data-learn]`], side: "below" },
    ],
  },
  {
    key: "tests",
    icon: "mdi:clipboard-check-outline",
    steps: [
      { key: "node", targets: ["[data-node='@tests']"], side: "right", prepare: choose(["@tests"]) },
      { key: "new", targets: [`${LEARN} [data-new-test]`], fallback: FORM, side: "above" },
      { key: "run", targets: [`${LEARN} [data-run-tests]`], fallback: FORM, side: "below" },
      { key: "tester", targets: [`${TESTER} [data-add-test]`], fallback: ["[data-tester]"], side: "left" },
    ],
  },
  {
    key: "answer",
    icon: "mdi:message-reply-text-outline",
    needs: "topics",
    steps: [
      { key: "hint", targets: field("answer_hint"), fallback: FORM, side: "right", prepare: chooseTopic },
      { key: "people", targets: ["assist-router-form >>> [data-hints]"], fallback: FORM, side: "right" },
      { key: "tokens", targets: field("answer_tokens"), fallback: FORM, side: "right" },
      { key: "personal", targets: field("personal"), fallback: FORM, side: "right" },
    ],
  },
  {
    key: "history",
    icon: "mdi:history",
    steps: [
      { key: "undo", targets: ["[data-undo]", "[data-redo]"], side: "below" },
      { key: "discard", targets: ["[data-discard]"], fallback: ["[data-draft-state]"], side: "below" },
      { key: "open", targets: ["[data-history]"], side: "below-end", advance: "click", act: (app) => app._openHistory() },
      { key: "versions", targets: [`${HISTORY} [data-versions]`], fallback: [`${HISTORY} [data-history-dialog]`], side: "right" },
      { key: "restore", targets: [`${HISTORY} [data-restore]`], fallback: [`${HISTORY} [data-history-dialog]`], side: "below-end" },
    ],
  },
  {
    key: "command",
    icon: "mdi:text-box-outline",
    steps: [
      { key: "add", targets: ["[data-add-sentences]"], side: "right", advance: "click", act: openSentences },
      { key: "file", targets: [`${SENTENCES} [data-sentences-file]`], fallback: FORM, side: "right", prepare: chooseSentences },
      { key: "intent", targets: [`${SENTENCES} [data-new-intent]`, `${SENTENCES} [data-add-intent]`], fallback: FORM, side: "right" },
      { key: "sentence", targets: [`${SENTENCES} [data-add-sentence]`], fallback: FORM, side: "right" },
      { key: "response", targets: [`${SENTENCES} [data-response]`], fallback: FORM, side: "right" },
      { key: "save", targets: [`${SENTENCES} [data-sentences-save]`], fallback: FORM, side: "below-end" },
      { key: "test", targets: [`${SENTENCES} [data-sentences-test]`], fallback: FORM, side: "right" },
    ],
  },
  {
    key: "syntax",
    icon: "mdi:code-braces",
    needs: "intents",
    steps: [
      { key: "words", targets: [`${SENTENCES} [data-add-sentence]`], fallback: [`${SENTENCES} [data-intent]`], side: "right", prepare: chooseIntentFile },
      { key: "slots", targets: [`${SENTENCES} [data-sentence-group]`], fallback: [`${SENTENCES} [data-intent]`], side: "right" },
      { key: "group", targets: [`${SENTENCES} [data-add-group]`], fallback: [`${SENTENCES} [data-intent]`], side: "right" },
      { key: "intent", targets: [`${SENTENCES} [data-intent-unhandled]`, `${SENTENCES} [data-intent-name]`], fallback: [`${SENTENCES} [data-intent]`], side: "right" },
      { key: "yaml", targets: [`${SENTENCES} [data-sentences-view='yaml']`], fallback: FORM, side: "below-end", advance: "click", act: sentencesView("yaml") },
      { key: "lists", targets: [`${SENTENCES} [data-sentences-yaml]`], fallback: FORM, side: "right" },
      { key: "check", targets: [`${SENTENCES} [data-sentences-test]`], fallback: FORM, side: "right", prepare: sentencesView("form") },
    ],
  },
  {
    key: "home",
    icon: "mdi:home-heart",
    steps: [
      { key: "household", targets: ["[data-node='household']"], side: "right", prepare: choose(["household"]) },
      { key: "people", targets: ["[data-node='people']"], side: "right", prepare: choose(["people"]) },
      { key: "personas", targets: ["[data-node='personas']"], side: "right", prepare: choose(["personas"]) },
      { key: "settings", targets: ["[data-node='@settings']"], side: "right", prepare: choose(SETTINGS_PATH) },
      { key: "form", targets: FORM, side: "inside" },
    ],
  },
  {
    key: "look",
    icon: "mdi:palette-outline",
    steps: [
      { key: "gear", targets: ["[data-gear]"], side: "below-end", advance: "click", act: (app) => (app._gear = true) },
      { key: "theme", targets: ["[data-segment='theme']"], fallback: ["[data-gear]"], side: "left" },
      { key: "language", targets: ["[data-segment='language']"], fallback: ["[data-gear]"], side: "left" },
      { key: "help", targets: ["[data-help='tree']", "[data-help='middle']"], side: "below" },
      { key: "columns", targets: ["[data-fold-column='left']", "[data-splitter='left']"], side: "right" },
    ],
  },
];

// The list is in three parts: to start with, next steps, set up once.
export const LESSON_GROUPS = [
  ["lessons_start", ["first_topic", "data", "tester", "save"]],
  ["lessons_more", ["unrecognized", "tests", "answer", "history", "command", "syntax"]],
  ["lessons_once", ["home", "look"]],
];

export const lessonByKey = (key) => LESSONS.find((lesson) => lesson.key === key) ?? null;

/** Whether the editor has what a lesson needs. */
export function lessonReady(lesson, app) {
  return !lesson?.needs || NEEDS[lesson.needs](app);
}

/** The lesson of what a part's "?" speaks of: the tree, the right column, or what is chosen in the middle. */
export function lessonFor(part, path) {
  if (part === "tree") return lessonByKey("first_topic");
  if (part === "side") return lessonByKey("tester");
  if (!path?.length) return lessonByKey("first_topic");
  if (path[0] === "topics") return lessonByKey(path.length === 2 ? "data" : "first_topic");
  if (path[0] === "@unrecognized") return lessonByKey("unrecognized");
  if (path[0] === "@tests") return lessonByKey("tests");
  if (path[0] === "@sentences") return lessonByKey("command");
  if (path[0] in HOME_KEYS || path[0] === SETTINGS_PATH[0]) return lessonByKey("home");
  return null;
}

/** The nodes of the tree with no lesson of their own (a test keeps this list empty). */
export function nodesWithoutLesson(groups) {
  return flattenOutline(groups).filter((node) => !lessonFor("middle", node.path)).map((node) => node.key);
}

class AssistRouterLessons extends LitElement {
  static properties = {
    language: {},
    app: { attribute: false },
  };

  _t(key, values) {
    return translate(this.language, key, values);
  }

  _close() {
    this.dispatchEvent(new CustomEvent("close"));
  }

  render() {
    const done = lessonsDone();
    return html`<div
      class="box lessons"
      role="dialog"
      aria-modal="true"
      data-lessons-dialog
      @keydown=${(event) => event.key === "Escape" && this._close()}
    >
      <div class="dhead">
        <h2><ha-icon icon="mdi:school-outline"></ha-icon> ${this._t("lessons_title")}</h2>
        <button class="ghost" data-close aria-label=${this._t("close")} @click=${this._close}>
          <ha-icon icon="mdi:close"></ha-icon>
        </button>
      </div>
      <p class="lead">${this._t("lessons_lead")}</p>
      <div class="scroll">
        ${LESSON_GROUPS.map(
          ([heading, keys]) => html`<h3 data-lessons-group=${heading}>${this._t(heading)}</h3>
            <div class="grid">
              ${keys.map((key) => {
                const lesson = lessonByKey(key);
                const ready = lessonReady(lesson, this.app);
                return html`<button
                  class="lesson ${done.includes(key) ? "done" : ""}"
                  data-lesson=${key}
                  ?disabled=${!ready}
                  @click=${() => this.dispatchEvent(new CustomEvent("lesson-start", { detail: { key } }))}
                >
                  <ha-icon .icon=${lesson.icon}></ha-icon>
                  <span class="text">
                    <strong>${this._t(`lesson_${key}_name`)}</strong>
                    <small>${ready ? this._t(`lesson_${key}_about`) : this._t(`lessons_needs_${lesson.needs}`)}</small>
                  </span>
                  <span class="meta">
                    ${done.includes(key)
                      ? html`<ha-icon class="tick" icon="mdi:check-circle" data-lesson-done></ha-icon>`
                      : this._t("lessons_steps", { count: lesson.steps.length })}
                  </span>
                </button>`;
              })}
            </div>`,
        )}
      </div>
      <p class="hint">${this._t("lessons_hint")}</p>
    </div>`;
  }

  firstUpdated() {
    this.renderRoot.querySelector("[data-lesson]:not([disabled])")?.focus();
  }

  static styles = [
    dialogStyles,
    css`
      .lessons {
        width: min(860px, calc(100vw - 48px));
      }
      h2 {
        display: flex;
        align-items: center;
        gap: 8px;
      }
      .lead,
      .hint {
        margin: 0;
        color: var(--muted);
      }
      .hint {
        font-size: 12px;
      }
      .grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
        gap: 10px;
      }
      .lesson {
        all: unset;
        box-sizing: border-box;
        display: flex;
        align-items: center;
        gap: 12px;
        padding: 12px 14px;
        border: 1px solid var(--line);
        border-radius: 12px;
        cursor: pointer;
      }
      .lesson:hover:not([disabled]),
      .lesson:focus-visible {
        border-color: var(--accent);
      }
      .lesson[disabled] {
        opacity: 0.55;
        cursor: default;
      }
      .lesson > ha-icon {
        --mdc-icon-size: 22px;
        flex: none;
        color: var(--accent);
      }
      .lesson.done > ha-icon,
      .tick {
        color: #1f9d55;
      }
      .text {
        flex: 1;
        min-width: 0;
      }
      .text strong,
      .text small {
        display: block;
      }
      .text small,
      .meta {
        color: var(--muted);
      }
      .meta {
        flex: none;
        font-size: 12px;
      }
      .tick {
        --mdc-icon-size: 20px;
      }
    `,
  ];
}

if (!customElements.get("assist-router-lessons")) customElements.define("assist-router-lessons", AssistRouterLessons);
