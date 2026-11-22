// The editor of router.yaml on a computer. Three columns: the tree of the file, the form or the YAML of what is
// chosen (or the whole file) and what the router makes of it. Every change goes to a draft kept on the server, which changes
// nothing until it is saved; the lines of the file not edited stay as they were, comments too.

import { LitElement, css, html, nothing } from "../vendor/lit-all.min.js";
import { PanelMenu } from "./ha-menu.js";
import { translate } from "./i18n.js";
import { formFor } from "./forms.js";
import {
  buildOutline,
  filterOutline,
  flattenOutline,
  HOME_KEYS,
  KIND_ICONS,
  LEARN_NODES,
  nodeKey,
  SETTINGS_PATH,
  topicKind,
} from "./outline.js";
import { appendBlock, blockText, freeKey, keysAt, readDocument, removeBlock, replaceBlock, valueAt } from "./source.js";
import "./dialogs.js";
import { ask, asking } from "./ask.js";
import "./forms.js";
import "./tester.js";
import "./learn.js";
import "./tour.js";
import { tourSeen } from "./tour.js";
import { lessonByKey, lessonFor, lessonReady } from "./lessons.js";
import { newSentencesFile, sentencesFileName } from "./sentences.js";
import { readStored, writeStored } from "./stored.js";
import { addressKey, writeAddress } from "./address.js";
import { RAIL, foldShortcut, readFolded, writeFolded } from "./columns.js";
import { DOCS_ANCHORS, docsAnchorFor, editorDocsUrl } from "./docs-anchors.js";
import { callWS } from "./ws.js";

const APP_TAG = "assist-router-editor-app";
const DOMAIN = "assist_router";
// Steps that can be undone; typing in one place within this time is one step, not one per letter.
export const UNDO_LIMIT = 200;
const COALESCE_MS = 1500;
// A draft is kept this long after the last change, so typing does not send every letter.
export const DRAFT_SAVE_MS = 800;
// The router's own check of the text waits as long after typing.
export const CHECK_MS = 400;
const WIDTHS_KEY = "assist-router-editor-widths";
const COLLAPSED_KEY = "assist-router-editor-collapsed";
const FOLDED_KEY = "assist-router-editor-folded";
const THEME_KEY = "assist-router-editor-theme";
// The look of the editor: as Home Assistant (light or dark), or one chosen here and kept by the browser.
export const THEMES = ["auto", "light", "dark"];
const THEME_ICONS = { auto: "mdi:theme-light-dark", light: "mdi:weather-sunny", dark: "mdi:weather-night" };
const LANGUAGE_KEY = "assist-router-editor-language";
// The language of the editor: as Home Assistant, or one chosen here and kept by the browser.
export const EDITOR_LANGUAGES = ["auto", "pl", "en"];

/** Home Assistant's hass with the language chosen for the editor; the same hass while it follows Home Assistant. */
export function withLanguage(hass, chosen) {
  if (!hass || !EDITOR_LANGUAGES.includes(chosen) || chosen === "auto" || hass.language === chosen) return hass;
  return { ...hass, language: chosen };
}
// The documentation site and the guide's address live in docs-anchors.js (the dialogs need them too).
export { DOCS_SITE, editorDocsUrl } from "./docs-anchors.js";

/** The look to show: the chosen one, or Home Assistant's (its dark mode, else the system's). */
export function editorTheme(chosen, hass, prefersDark = window.matchMedia?.("(prefers-color-scheme: dark)").matches) {
  if (chosen === "light" || chosen === "dark") return chosen;
  const dark = hass?.themes?.darkMode ?? prefersDark;
  return dark ? "dark" : "light";
}
// The side columns: their width when nothing was chosen, and how narrow and wide a drag can make them.
export const COLUMNS = { left: { start: 300, min: 220, max: 560 }, right: { start: 340, min: 260, max: 640 } };

/** A width a drag asked for, kept within what the column allows. */
export function columnWidth(side, width) {
  const { min, max } = COLUMNS[side];
  return Math.round(Math.min(max, Math.max(min, Number(width) || COLUMNS[side].start)));
}

/** A block with another key on its first line that is not a comment. */
export function renameBlock(snippet, key) {
  const lines = snippet.split("\n");
  const index = lines.findIndex((line) => line.trim() && !line.trimStart().startsWith("#"));
  if (index >= 0) lines[index] = lines[index].replace(/^("[^"]*"|'[^']*'|[^\s#:][^:]*?)(\s*:)/, `${key}$2`);
  return lines.join("\n");
}

/** A new topic to fill in, in the language of the editor. */
export function topicTemplate(key, t) {
  return `${key}:\n  description: ${t("new_topic_description")}\n  examples:\n    - ${t("new_topic_example")}`;
}

const readJson = (key, fallback) => {
  try {
    return JSON.parse(readStored(key) ?? "null") ?? fallback;
  } catch {
    return fallback;
  }
};

class AssistRouterEditorApp extends LitElement {
  static properties = {
    hass: { attribute: false, noAccessor: true },
    _loaded: { state: true },
    _text: { state: true },
    _file: { state: true },
    _check: { state: true },
    _draftAt: { state: true },
    _saving: { state: true },
    _selected: { state: true },
    _tab: { state: true },
    _nodeText: { state: true },
    _nodeError: { state: true },
    _search: { state: true },
    _collapsed: { state: true },
    _widths: { state: true },
    _folded: { state: true },
    _dialog: { state: true },
    _help: { state: true },
    _saveError: { state: true },
    _busy: { state: true },
    _notice: { state: true },
    _past: { state: true },
    _future: { state: true },
    _users: { state: true },
    _theme: { state: true },
    _language: { state: true },
    _gear: { state: true },
    _tests: { state: true },
    _tryRequest: { state: true },
    _saveChecks: { state: true },
    _sentences: { state: true },
    _sentenceEdits: { state: true },
    _testRun: { state: true },
    // The tour of the editor (tour.js) over everything, or one of its lessons (lessons.js).
    _tour: { state: true },
    _lesson: { state: true },
  };

  constructor() {
    super();
    this._loaded = false;
    this._text = "";
    this._file = "";
    this._selected = null;
    // The node named by the address (#/...), chosen once the file (and the files of sentences) have loaded.
    this._wanted = addressKey();
    this._tab = "node";
    this._nodeText = null;
    this._search = "";
    this._past = [];
    this._future = [];
    this._history = [];
    this._users = {};
    this._tests = [];
    this._sentences = { files: [], intents: [], languages: [], language: "en" };
    this._sentenceEdits = {};
    const widths = readJson(WIDTHS_KEY, {});
    this._widths = { left: columnWidth("left", widths.left), right: columnWidth("right", widths.right) };
    this._folded = readFolded(FOLDED_KEY);
    this._collapsed = new Set(readJson(COLLAPSED_KEY, []));
    this._theme = THEMES.includes(readStored(THEME_KEY)) ? readStored(THEME_KEY) : "auto";
    this._language = EDITOR_LANGUAGES.includes(readStored(LANGUAGE_KEY)) ? readStored(LANGUAGE_KEY) : "auto";
    this._gear = false;
    this._tour = false;
    this._lesson = null;
    this._onOutside = this._onOutside.bind(this);
    this._onKey = this._onKey.bind(this);
    this._onVisible = this._onVisible.bind(this);
  }

  // Home Assistant's hass comes in here; the editor and everything in it see it with the language chosen for the editor.
  set hass(value) {
    const old = this._hass;
    this._haHass = value;
    this._hass = withLanguage(value, this._language);
    this.requestUpdate("hass", old);
  }

  get hass() {
    return this._hass;
  }

  _t(key, values, fallback) {
    return translate(this.hass?.language, key, values, fallback);
  }

  updated(changed) {
    // The address follows the chosen node; it is left alone while the node it names waits for the first state.
    if (changed.has("_selected") && this._wanted === null) writeAddress(this._selected ? nodeKey(this._selected) : null);
    const theme = editorTheme(this._theme, this.hass);
    if (this.dataset.theme !== theme) this.dataset.theme = theme;
  }

  _nextTheme() {
    this._setTheme(THEMES[(THEMES.indexOf(this._theme) + 1) % THEMES.length]);
  }

  _setTheme(theme) {
    this._theme = theme;
    writeStored(THEME_KEY, theme);
  }

  _setLanguage(language) {
    this._language = language;
    writeStored(LANGUAGE_KEY, language);
    this.hass = this._haHass;
  }

  // ⚙: a small window under the button with the look and the language; a choice works at once and the window stays.
  _toggleGear() {
    this._gear = !this._gear;
    if (this._gear) this._help = null;
  }

  _onOutside(event) {
    const path = event.composedPath();
    // A click in the tour (its Next button) leaves the window open: a lesson frames what is in it.
    if (path.some((node) => node.tagName === "ASSIST-ROUTER-EDITOR-TOUR")) return;
    if (this._gear && !path.some((node) => node.classList?.contains("gear-wrap"))) this._gear = false;
  }

  connectedCallback() {
    super.connectedCallback();
    window.addEventListener("keydown", this._onKey);
    window.addEventListener("click", this._onOutside);
    document.addEventListener("visibilitychange", this._onVisible);
    this._menu.connect();
    this._load();
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    window.removeEventListener("keydown", this._onKey);
    window.removeEventListener("click", this._onOutside);
    document.removeEventListener("visibilitychange", this._onVisible);
    this._menu.disconnect();
    this._saveDraft();
  }

  // Loading and the draft ---------------------------------------------------------------------------

  _ws(message) {
    return callWS(this.hass, { ...message, type: `${DOMAIN}/${message.type}` });
  }

  async _load() {
    try {
      const loaded = await this._ws({ type: "editor/load" });
      this._file = loaded.text;
      this._hash = loaded.hash;
      this._path = loaded.path;
      this._history = loaded.history;
      this._fileCheck = loaded.check;
      this._languages = loaded.languages ?? [];
      this._text = loaded.draft?.text ?? loaded.text;
      this._base = loaded.draft?.base ?? loaded.hash;
      this._draft = Boolean(loaded.draft);
      this._draftAt = loaded.draft?.updated_at ?? null;
      this._check = loaded.draft ? null : loaded.check;
      this._nodeText = null;
      this._nodeError = null;
      if (this._selected && !this._has(this._selected)) this._selected = null;
      this._loaded = true;
      // The first time the editor opens in this browser it shows itself round.
      if (!this._toured) {
        this._toured = true;
        if (!tourSeen() && !this._dialog) this._tour = true;
      }
      if (loaded.draft) this._runCheck();
      this._loadTests();
      this._followAddress(false);
      this._loadSentences().then(() => this._followAddress(true));
    } catch (err) {
      this._notice = { kind: "error", text: this._t("error", { message: err.message ?? String(err) }) };
      this._loaded = true;
    }
  }

  /**
   * Choose the node the address named when the editor opened. The files of sentences come later than router.yaml:
   * until they are here (`last` false) a node not found yet keeps waiting.
   */
  _followAddress(last) {
    const key = this._wanted;
    if (!key) return;
    const item = flattenOutline(this._outline().groups).find((node) => node.key === key);
    if (!item && !last) return;
    this._wanted = null;
    if (item) this._select(item);
    else writeAddress(this._selected ? nodeKey(this._selected) : null);
  }

  async _loadSentences() {
    try {
      this._sentences = await this._ws({ type: "editor/sentences_load" });
    } catch {
      // the files of sentences stay as they were loaded last
    }
  }

  _sentenceFile(path) {
    return this._sentences.files.find((file) => file.language === path[1] && file.name === path[2]);
  }

  /** The group of the tree with the files of sentences of Home Assistant's own agent. */
  _sentencesGroup() {
    const children = this._sentences.files.map((file) => {
      const path = ["@sentences", file.language, file.name];
      const key = nodeKey(path);
      const dirty = this._sentenceEdits[key] != null || !file.hash;
      return {
        key,
        path,
        name: file.name,
        label: `${file.language}/${file.name}${dirty ? " •" : ""}`,
        icon: "mdi:text-box-outline",
        hint: file.check?.intents?.map((item) => item.name).join(", ") ?? "",
        warn: file.check && !file.check.ok ? this._t("sentences_file_error", { error: file.check.error }) : null,
        block: false,
        children: [],
      };
    });
    return { key: "commands", label: this._t("group_commands"), children };
  }

  async _addSentencesFile() {
    const typed = await ask(this, {
      title: this._t("sentences_new_title"),
      text: this._t("sentences_new_name"),
      ok: this._t("sentences_create"),
      input: this._t("sentences_default_name"),
    });
    const name = sentencesFileName(typed);
    if (!name) return;
    const language = this._sentences.language;
    if (this._sentences.files.some((file) => file.language === language && file.name === name)) {
      this._notice = { kind: "error", text: this._t("sentences_exists", { name }) };
      return;
    }
    this._openSentencesFile(name);
  }

  /** A file of commands chosen by its name; a new one (written only by its Save) when it is not there yet. */
  _openSentencesFile(name) {
    const language = this._sentences.language;
    if (!this._sentences.files.some((file) => file.language === language && file.name === name)) {
      const file = { language, name, text: newSentencesFile(language), hash: "", check: null };
      this._sentences = { ...this._sentences, files: [...this._sentences.files, file] };
    }
    this._select({ path: ["@sentences", language, name] });
  }

  _onSentencesChange(path, text) {
    const key = nodeKey(path);
    const edits = { ...this._sentenceEdits };
    if (text == null) delete edits[key];
    else edits[key] = text;
    this._sentenceEdits = edits;
  }

  _onSentencesSaved(path, detail) {
    const files = this._sentences.files.map((file) =>
      file.language === path[1] && file.name === path[2] ? { ...file, text: detail.text, hash: detail.hash, check: detail.check } : file,
    );
    this._sentences = { ...this._sentences, files, intents: detail.intents ?? this._sentences.intents };
    this._onSentencesChange(path, null);
    this._notice = { kind: "ok", text: this._t("sentences_saved_notice", { name: `${path[1]}/${path[2]}` }) };
  }

  _onSentencesDeleted(path) {
    this._sentences = {
      ...this._sentences,
      files: this._sentences.files.filter((file) => !(file.language === path[1] && file.name === path[2])),
    };
    this._onSentencesChange(path, null);
    this._selected = null;
  }

  async _loadTests() {
    try {
      const loaded = await this._ws({ type: "editor/tests_load" });
      this._tests = loaded.tests;
      if (loaded.error) this._notice = { kind: "error", text: this._t("tests_file_error", { error: loaded.error }) };
    } catch {
      this._tests = [];
    }
  }

  /** The test set written at once: it is a file of its own, not a part of the draft. */
  async _saveTests(tests, notice = null) {
    try {
      const saved = await this._ws({ type: "editor/tests_save", tests });
      this._tests = saved.tests;
      if (notice) this._notice = { kind: "ok", text: notice };
    } catch (err) {
      this._notice = { kind: "error", text: this._t("error", { message: err.message ?? String(err) }) };
    }
  }

  _addTest(test) {
    if (!test || this._tests.some((item) => item.sentence.toLowerCase() === test.sentence.toLowerCase())) {
      this._notice = { kind: "ok", text: this._t("tests_already") };
      return;
    }
    this._saveTests([...this._tests, test], this._t("tests_added", { sentence: test.sentence }));
  }

  // Back to the editor with nothing of its own changed: the file may have been edited elsewhere meanwhile.
  _onVisible() {
    if (document.visibilityState === "visible" && this._loaded && !this._draft && !this._dirty && !this._dialog) this._load();
  }

  get _changed() {
    return this._text !== this._file;
  }

  get _conflict() {
    return this._draft && this._base !== this._hash;
  }

  _setText(next, { coalesce = null } = {}) {
    if (next === this._text) return;
    const now = Date.now();
    const merge = coalesce && this._lastEdit?.key === coalesce && now - this._lastEdit.at < COALESCE_MS;
    if (!merge) this._past = [...this._past, this._text].slice(-UNDO_LIMIT);
    this._lastEdit = coalesce ? { key: coalesce, at: now } : null;
    this._future = [];
    this._text = next;
    this._scheduleDraft();
    this._scheduleCheck();
  }

  _scheduleDraft() {
    this._dirty = true;
    clearTimeout(this._draftTimer);
    this._draftTimer = setTimeout(() => this._saveDraft(), DRAFT_SAVE_MS);
  }

  /**
   * Save the draft on the server: one save at a time (a slow Home Assistant gets fewer saves, not a queue of them);
   * changes made while one is on its way are saved right after it.
   */
  async _saveDraft() {
    clearTimeout(this._draftTimer);
    if (!this._dirty || !this.hass) return;
    if (this._draftInFlight) return;
    this._draftInFlight = true;
    this._dirty = false;
    this._saving = true;
    try {
      if (!this._changed) {
        // Back to the file as it is: no draft is needed.
        if (this._draft) await this._ws({ type: "editor/discard" });
        this._draft = false;
        this._base = this._hash;
        this._draftAt = null;
      } else {
        const saved = await this._ws({ type: "editor/save_draft", text: this._text, base: this._base });
        this._draft = true;
        this._base = saved.base;
        this._draftAt = saved.updated_at;
      }
    } catch (err) {
      this._dirty = true;
      this._notice = { kind: "error", text: this._t("error", { message: err.message ?? String(err) }) };
      return;
    } finally {
      this._draftInFlight = false;
      this._saving = false;
    }
    // Changes typed while the save was on its way.
    if (this._dirty) this._saveDraft();
  }

  _scheduleCheck() {
    clearTimeout(this._checkTimer);
    this._check = null;
    this._checkTimer = setTimeout(() => this._runCheck(), CHECK_MS);
  }

  async _runCheck() {
    const text = this._text;
    const { error } = readDocument(text);
    if (error) {
      this._check = { ok: false, error, topics: [] };
      return;
    }
    try {
      const check = await this._ws({ type: "editor/check", text });
      if (text === this._text) this._check = check;
    } catch (err) {
      this._check = { ok: false, error: err.message ?? String(err), topics: [] };
    }
  }

  async _discard() {
    if (!(await ask(this, { title: this._t("discard_title"), text: this._t("discard_confirm"), ok: this._t("discard_ok"), danger: true }))) return;
    clearTimeout(this._draftTimer);
    this._dirty = false;
    await this._ws({ type: "editor/discard" });
    this._past = [];
    this._future = [];
    await this._load();
  }

  _undo() {
    if (!this._past.length) return;
    this._future = [this._text, ...this._future];
    this._restoreText(this._past.at(-1));
    this._past = this._past.slice(0, -1);
  }

  _redo() {
    if (!this._future.length) return;
    this._past = [...this._past, this._text];
    this._restoreText(this._future[0]);
    this._future = this._future.slice(1);
  }

  _restoreText(text) {
    this._text = text;
    this._lastEdit = null;
    this._nodeText = null;
    this._nodeError = null;
    if (this._selected && !this._has(this._selected)) this._selected = null;
    this._scheduleDraft();
    this._scheduleCheck();
  }

  _onKey(event) {
    // The tour and the lessons have their keys of their own.
    if (this._tour || this._lesson) return;
    // An open question (ask.js) has the keys too: Esc and Tab are its own, the shortcuts wait.
    if (asking(this.renderRoot)) return;
    if (event.key === "Escape" && this._gear) {
      this._gear = false;
      return;
    }
    if (event.key === "Escape" && this._help) {
      this._help = null;
      return;
    }
    // Ctrl/⌘+B folds the left column, Ctrl/⌘+Alt+B the right one, also while typing in a field.
    const column = foldShortcut(event);
    if (column && !this._dialog) {
      event.preventDefault();
      this._toggleColumn(column);
      return;
    }
    const mod = event.ctrlKey || event.metaKey;
    if (!mod || this._dialog) return;
    const key = event.key.toLowerCase();
    if (key === "s") {
      event.preventDefault();
      this._openSave();
      return;
    }
    // In a text field its own undo works; elsewhere the editor's.
    const typing = event.composedPath().some((element) => element.tagName === "TEXTAREA" || element.tagName === "INPUT");
    if (typing) return;
    if (key === "z" || key === "y") {
      event.preventDefault();
      if (key === "y" || event.shiftKey) this._redo();
      else this._undo();
    }
  }

  // The tree and editing -----------------------------------------------------------------------------

  _has(path) {
    // The settings and the parts of the home are in the tree even when the file has none of them yet.
    if (nodeKey(path) === nodeKey(SETTINGS_PATH) || (path.length === 1 && (path[0] in HOME_KEYS || path[0] in LEARN_NODES))) {
      return true;
    }
    if (path[0] === "@sentences") return Boolean(this._sentenceFile(path));
    const { doc } = readDocument(this._text);
    return valueAt(doc, path) !== undefined || blockText(this._text, path) !== null;
  }

  _select(item) {
    this._unfoldTo(item.path);
    this._selected = item.path;
    // The form, unless the YAML was the last choice and the node has lines of its own.
    const yaml = this._preferYaml && blockText(this._text, item.path) !== null;
    this._tab = formFor(item.path) && !yaml ? "form" : "node";
    this._nodeText = null;
    this._nodeError = null;
    this._lastEdit = null;
  }

  _onNodeInput(event) {
    const value = event.target.value;
    this._nodeText = value;
    try {
      const result = replaceBlock(this._text, this._selected, value);
      this._nodeError = null;
      this._setText(result.text, { coalesce: `node:${nodeKey(this._editStart ?? this._selected)}` });
      if (nodeKey(result.path) !== nodeKey(this._selected)) {
        this._editStart ??= this._selected;
        this._selected = result.path;
      }
    } catch (err) {
      this._nodeError = this._errorText(err);
    }
  }

  _errorText(err) {
    return ["one_key", "lost", "not_a_map"].includes(err.message) ? this._t(err.message) : err.message;
  }

  _onFileInput(event) {
    this._setText(event.target.value, { coalesce: "file" });
  }

  // Tab in the YAML indents by two spaces instead of leaving the field.
  _onTab(event) {
    if (event.key !== "Tab" || event.shiftKey || event.ctrlKey || event.metaKey || event.altKey) return;
    event.preventDefault();
    const area = event.target;
    area.setRangeText("  ", area.selectionStart, area.selectionEnd, "end");
    area.dispatchEvent(new Event("input", { bubbles: true }));
  }

  _addTopic() {
    const { doc } = readDocument(this._text);
    const key = freeKey(doc, ["topics"], this._t("new_topic_key"));
    try {
      const block = topicTemplate(key, (name) => this._t(name));
      const result = this._outline().hasTopics
        ? appendBlock(this._text, ["topics"], block)
        : appendBlock(this._text, [], `topics:\n${block.replace(/^/gm, "  ")}`);
      this._setText(result.text);
      this._select({ path: ["topics", key] });
      this._focusNode();
    } catch (err) {
      this._notice = { kind: "error", text: this._errorText(err) };
    }
  }

  _duplicate() {
    const path = this._selected;
    const { doc } = readDocument(this._text);
    const key = freeKey(doc, path.slice(0, -1), `${path.at(-1)}_${this._t("copy_suffix")}`);
    try {
      const result = appendBlock(this._text, path.slice(0, -1), renameBlock(blockText(this._text, path), key));
      this._setText(result.text);
      this._select({ path: result.path });
      this._focusNode();
    } catch (err) {
      this._notice = { kind: "error", text: this._errorText(err) };
    }
  }

  async _delete() {
    const path = this._selected;
    const question = { title: this._t("delete_title"), text: this._t("delete_confirm", { name: path.at(-1) }), ok: this._t("delete"), danger: true };
    if (!(await ask(this, question))) return;
    try {
      this._setText(removeBlock(this._text, path));
      this._selected = null;
      this._nodeText = null;
      this._nodeError = null;
    } catch (err) {
      this._notice = { kind: "error", text: this._errorText(err) };
    }
  }

  async _focusNode() {
    await this.updateComplete;
    const form = this.renderRoot.querySelector("assist-router-form");
    if (form) {
      await form.updateComplete;
      form.renderRoot.querySelector("textarea, input:not([data-key])")?.focus();
    } else {
      this.renderRoot.querySelector("[data-node-yaml]")?.focus();
    }
  }

  _showTab(tab) {
    this._tab = tab;
    if (tab !== "file") this._preferYaml = tab === "node";
  }

  _onFormEdit(event) {
    const { text, coalesce, path } = event.detail;
    this._setText(text, { coalesce });
    if (path) this._selected = path;
  }

  _outline() {
    if (this._outlineFor !== this._text || this._outlineLanguage !== this.hass?.language) {
      this._outlineFor = this._text;
      this._outlineLanguage = this.hass?.language;
      this._outlineCache = buildOutline(this._text, (key, values, fallback) => this._t(key, values, fallback));
    }
    return this._outlineCache;
  }

  /** The tree unfolded on the way to a node: its parents and the group it is in. */
  _unfoldTo(path) {
    const key = nodeKey(path);
    const groups = [...this._outline().groups, this._sentencesGroup()];
    const group = groups.find((item) => flattenOutline(item.children).some((node) => node.key === key));
    const ways = [group?.key, ...path.slice(0, -1).map((_, at) => nodeKey(path.slice(0, at + 1)))].filter(Boolean);
    if (!ways.some((way) => this._collapsed.has(way))) return;
    const next = new Set(this._collapsed);
    ways.forEach((way) => next.delete(way));
    this._collapsed = next;
    writeStored(COLLAPSED_KEY, JSON.stringify([...next]));
  }

  _toggle(item) {
    const next = new Set(this._collapsed);
    if (next.has(item.key)) next.delete(item.key);
    else next.add(item.key);
    this._collapsed = next;
    writeStored(COLLAPSED_KEY, JSON.stringify([...next]));
  }

  /**
   * What the button of a group folds: the parts inside it that unfold (people, rooms of music…), or, in a group
   * of single items, the group itself; and whether any of them is open now.
   */
  _groupFolding(group) {
    const inside = flattenOutline(group.children)
      .filter((item) => item.children?.length)
      .map((item) => item.key);
    const keys = inside.length ? inside : [group.key];
    const groupOpen = !this._collapsed.has(group.key);
    const open = groupOpen && keys.some((key) => !this._collapsed.has(key));
    return { keys, open };
  }

  _foldGroup(group) {
    const { keys, open } = this._groupFolding(group);
    const next = new Set(this._collapsed);
    if (open) keys.forEach((key) => next.add(key));
    else [...keys, group.key].forEach((key) => next.delete(key));
    this._collapsed = next;
    writeStored(COLLAPSED_KEY, JSON.stringify([...next]));
  }

  // Every part that unfolds folds, or all unfold; the groups stay open, each folds by its own arrow.
  _foldAll(fold) {
    const { groups } = this._outline();
    const keys = flattenOutline(groups.flatMap((group) => group.children))
      .filter((item) => item.children?.length)
      .map((item) => item.key);
    this._collapsed = new Set(fold ? keys : []);
    writeStored(COLLAPSED_KEY, JSON.stringify([...this._collapsed]));
  }

  // The menu of Home Assistant: hidden while the editor is open, the menu button shows and hides it (ha-menu.js).
  _menu = new PanelMenu(this);

  _toggleMenu() {
    this._gear = false;
    this._menu.toggle();
  }

  /** A bar between columns: dragged, it sets the width of its side column; a double click gives the first back. */
  /** Fold or unfold a column; its width stays as it was, for when it unfolds. */
  _toggleColumn(side) {
    this._folded = { ...this._folded, [side]: !this._folded[side] };
    writeFolded(FOLDED_KEY, this._folded);
  }

  /** The button that folds a column, at its top. */
  _foldButton(side) {
    const label = this._t(`fold_${side}`);
    return html`<button class="ghost fold-column" data-fold-column=${side} title=${label} aria-label=${label}
      @click=${() => this._toggleColumn(side)}>
      <ha-icon icon=${side === "left" ? "mdi:chevron-left" : "mdi:chevron-right"}></ha-icon>
    </button>`;
  }

  /** A folded column: a narrow rail with the button that unfolds it. */
  _renderRail(side) {
    const label = this._t(`unfold_${side}`);
    return html`<aside class="rail" data-rail=${side}>
      <button class="ghost" data-unfold-column=${side} title=${label} aria-label=${label} @click=${() => this._toggleColumn(side)}>
        <ha-icon icon=${side === "left" ? "mdi:chevron-right" : "mdi:chevron-left"}></ha-icon>
      </button>
    </aside>`;
  }

  _renderSplitter(side) {
    // The bar beside a folded column does not drag.
    if (this._folded[side]) return html`<div class="splitter off" data-splitter=${side}></div>`;
    const move = (event) => {
      const box = this.getBoundingClientRect();
      const width = side === "left" ? event.clientX - box.left : box.right - event.clientX;
      this._widths = { ...this._widths, [side]: columnWidth(side, width) };
    };
    const start = (event) => {
      event.preventDefault();
      const bar = event.currentTarget;
      bar.setPointerCapture?.(event.pointerId);
      bar.classList.add("dragging");
      const stop = () => {
        bar.classList.remove("dragging");
        bar.removeEventListener("pointermove", move);
        bar.removeEventListener("pointerup", stop);
        bar.removeEventListener("pointercancel", stop);
        writeStored(WIDTHS_KEY, JSON.stringify(this._widths));
      };
      bar.addEventListener("pointermove", move);
      bar.addEventListener("pointerup", stop);
      bar.addEventListener("pointercancel", stop);
    };
    const reset = () => {
      this._widths = { ...this._widths, [side]: COLUMNS[side].start };
      writeStored(WIDTHS_KEY, JSON.stringify(this._widths));
    };
    return html`<div
      class="splitter"
      role="separator"
      aria-orientation="vertical"
      title=${this._t("resize")}
      data-splitter=${side}
      @pointerdown=${start}
      @dblclick=${reset}
    ></div>`;
  }

  // Saving and the history ---------------------------------------------------------------------------

  async _openSave() {
    if (!this._changed) return;
    await this._saveDraft();
    this._saveError = null;
    this._testRun = null;
    this._dialog = "save";
    if (!this._check) await this._runCheck();
    this._loadChecks();
  }

  // What is worth a look before saving (patterns that find nothing, services that change things, prompts).
  async _loadChecks() {
    const text = this._text;
    this._saveChecks = { loading: true };
    try {
      const { checks } = await this._ws({ type: "editor/checks", text });
      if (text === this._text) this._saveChecks = { items: checks };
    } catch (err) {
      this._saveChecks = { error: err.message ?? String(err) };
    }
  }

  async _runSaveTests() {
    this._testRun = { busy: true };
    try {
      const data = await this._ws({ type: "editor/tests_run", text: this._text, compare: true });
      this._testRun = { data };
    } catch (err) {
      this._testRun = { error: err.message ?? String(err) };
    }
  }

  async _save({ note, force }) {
    this._busy = true;
    this._saveError = null;
    try {
      await this._saveDraft();
      await this._ws({ type: "editor/save", base: this._base, note, force });
      this._dialog = null;
      this._past = [];
      this._future = [];
      await this._load();
      this._notice = { kind: "ok", text: this._t("saved") };
    } catch (err) {
      this._saveError = { code: err.code, message: err.message ?? String(err) };
    } finally {
      this._busy = false;
    }
  }

  async _openHistory() {
    this._dialog = "history";
    if (!Object.keys(this._users).length) {
      try {
        const users = await callWS(this.hass, { type: "config/auth/list" });
        this._users = Object.fromEntries(users.map((user) => [user.id, user.name]));
      } catch {
        this._users = {};
      }
    }
  }

  async _restore({ version }) {
    if (this._draft && !(await ask(this, { title: this._t("history_restore_title"), text: this._t("history_restore_confirm"), ok: this._t("history_restore_ok") })))
      return;
    clearTimeout(this._draftTimer);
    this._dirty = false;
    try {
      await this._ws({ type: "editor/restore", version });
      this._dialog = null;
      this._past = [...this._past, this._text];
      this._future = [];
      await this._load();
    } catch (err) {
      this._notice = { kind: "error", text: this._t("error", { message: err.message ?? String(err) }) };
    }
  }

  // Rendering ---------------------------------------------------------------------------------------

  render() {
    if (!this.hass) return nothing;
    if (!this._loaded) return html`<p class="empty">${this._t("loading")}</p>`;
    return html`
      ${this._renderTop()} ${this._renderNotices()}
      <div
        class="cols"
        style="--left: ${this._folded.left ? RAIL : this._widths.left}px; --right: ${this._folded.right ? RAIL : this._widths.right}px"
      >
        ${this._folded.left ? this._renderRail("left") : this._renderTree()} ${this._renderSplitter("left")}
        ${this._renderMiddle()} ${this._renderSplitter("right")}
        ${this._folded.right ? this._renderRail("right") : this._renderSide()}
      </div>
      ${this._renderHelp()}
      ${this._dialog === "save"
        ? html`<assist-router-save-dialog
            .language=${this.hass.language}
            .before=${this._file}
            .after=${this._text}
            .check=${this._check}
            .error=${this._saveError}
            .checks=${this._saveChecks}
            .tests=${this._tests}
            .testRun=${this._testRun}
            .topics=${keysAt(readDocument(this._text).doc, ["topics"])}
            ?busy=${this._busy}
            @run-tests=${this._runSaveTests}
            @close=${() => (this._dialog = null)}
            @save=${(event) => this._save(event.detail)}
          ></assist-router-save-dialog>`
        : nothing}
      ${this._dialog === "history"
        ? html`<assist-router-history-dialog
            .language=${this.hass.language}
            .hass=${this.hass}
            .history=${this._history}
            .current=${this._file}
            .users=${this._users}
            @close=${() => (this._dialog = null)}
            @restore=${(event) => this._restore(event.detail)}
          ></assist-router-history-dialog>`
        : nothing}
      ${this._dialog === "lessons"
        ? html`<assist-router-lessons
            .language=${this.hass.language}
            .app=${this}
            @close=${() => (this._dialog = null)}
            @lesson-start=${(event) => this._startLesson(lessonByKey(event.detail.key))}
          ></assist-router-lessons>`
        : nothing}
      ${this._tour || this._lesson
        ? html`<assist-router-editor-tour
            .host=${this}
            .t=${(key, values) => this._t(key, values)}
            .lesson=${this._lesson}
            @tour-close=${this._closeTour}
          ></assist-router-editor-tour>`
        : nothing}
    `;
  }

  _openTour() {
    this._gear = false;
    this._help = null;
    this._lesson = null;
    this._tour = true;
  }

  _startLesson(lesson) {
    if (!lesson || !lessonReady(lesson, this)) return;
    this._gear = false;
    this._help = null;
    this._tour = false;
    // A window the lesson opens (saving, the history) is closed with it; one open before stays.
    this._lessonDialog = this._dialog === "lessons" ? null : this._dialog;
    this._dialog = this._lessonDialog;
    this._lesson = lesson;
  }

  _closeTour() {
    if (this._lesson && this._dialog !== this._lessonDialog) this._dialog = this._lessonDialog ?? null;
    if (this._lesson) this._gear = false;
    this._tour = false;
    this._lesson = null;
  }

  /** The "?" of a part of the editor: what the part is for, and the chapter of the guide about it in a new tab. */
  _helpButton(part, anchor) {
    const label = `${this._t("help_what")} ${this._t(`help_${part}_title`)}`;
    return html`<button
      class="ghost help ${this._help?.part === part ? "on" : ""}"
      data-help=${part}
      data-anchor=${anchor}
      title=${label}
      aria-label=${label}
      aria-expanded=${this._help?.part === part ? "true" : "false"}
      @click=${(event) => this._toggleHelp(part, anchor, event.currentTarget)}
    >
      <ha-icon icon="mdi:help-circle-outline"></ha-icon>
    </button>`;
  }

  /** The window of a part's "?": opens under its button (inside the screen), a second click or Esc closes it. */
  _toggleHelp(part, anchor, button) {
    if (this._help?.part === part) {
      this._help = null;
      return;
    }
    const box = button.getBoundingClientRect();
    const width = Math.min(340, window.innerWidth - 16);
    const left = Math.max(8, Math.min(box.left, window.innerWidth - width - 8));
    this._help = { part, anchor, top: box.bottom + 6, left, width };
  }

  _renderHelp() {
    const help = this._help;
    if (!help) return nothing;
    return html`<div class="help-shade" data-help-shade @click=${() => (this._help = null)}></div>
      <div
        class="help-pop"
        role="dialog"
        aria-label=${this._t(`help_${help.part}_title`)}
        data-help-pop=${help.part}
        style="top: ${help.top}px; left: ${help.left}px; width: ${help.width}px"
      >
        <div class="help-head">
          <b>${this._t(`help_${help.part}_title`)}</b>
          <button class="ghost" data-help-close aria-label=${this._t("close")} @click=${() => (this._help = null)}>
            <ha-icon icon="mdi:close"></ha-icon>
          </button>
        </div>
        <p>${this._t(`help_${help.part}`)}</p>
        ${this._renderHelpLesson(help.part)}
        <a data-help-more href=${editorDocsUrl(this.hass?.language, help.anchor)} target="_blank" rel="noopener"
          >${this._t("help_more")} <ha-icon icon="mdi:open-in-new"></ha-icon
        ></a>
      </div>`;
  }

  // The lesson of what the "?" speaks of ("Show me step by step").
  _renderHelpLesson(part) {
    const lesson = lessonFor(part, this._selected);
    if (!lesson) return nothing;
    const ready = lessonReady(lesson, this);
    return html`<button
      class="ghost help-lesson"
      data-help-lesson=${lesson.key}
      ?disabled=${!ready}
      title=${ready ? "" : this._t(`lessons_needs_${lesson.needs}`)}
      @click=${() => this._startLesson(lesson)}
    >
      <ha-icon icon="mdi:school-outline"></ha-icon>${this._t("lessons_show", { name: this._t(`lesson_${lesson.key}_name`) })}
    </button>`;
  }

  _renderTop() {
    const state = this._saving ? this._t("state_saving") : this._changed ? this._t("state_draft") : this._t("state_clean");
    return html`<header class="top">
      <button class="ghost menu" data-ha-menu aria-label=${this._t("menu")} title=${this._t("menu")} @click=${this._toggleMenu}>
        <ha-icon icon="mdi:menu"></ha-icon>
      </button>
      <ha-icon class="app-icon" icon="mdi:robot-outline" data-app-icon></ha-icon>
      <h1>${this._t("title")}</h1>
      <span class="board" data-path>${this._path ?? ""}</span>
      <span class="grow"></span>
      <span class="pill ${this._changed ? "draft" : ""}" data-draft-state=${this._changed ? "draft" : "clean"}>
        <ha-icon .icon=${this._changed ? "mdi:pencil" : "mdi:check"}></ha-icon>${state}
      </span>
      <button class="ghost" data-undo title=${this._t("undo")} ?disabled=${!this._past.length} @click=${this._undo}>
        <ha-icon icon="mdi:undo"></ha-icon>
      </button>
      <button class="ghost" data-redo title=${this._t("redo")} ?disabled=${!this._future.length} @click=${this._redo}>
        <ha-icon icon="mdi:redo"></ha-icon>
      </button>
      ${this._draft || this._changed
        ? html`<button class="ghost" data-discard @click=${this._discard}>${this._t("discard")}</button>`
        : nothing}
      <button
        class="ghost"
        data-theme-button=${this._theme}
        title=${this._t(`theme_${this._theme}`)}
        aria-label=${this._t(`theme_${this._theme}`)}
        @click=${this._nextTheme}
      >
        <ha-icon .icon=${THEME_ICONS[this._theme]}></ha-icon>
      </button>
      <span class="gear-wrap">
        <button
          class="ghost"
          data-gear
          aria-haspopup="dialog"
          aria-expanded=${this._gear ? "true" : "false"}
          title=${this._t("gear_title")}
          aria-label=${this._t("gear_title")}
          @click=${this._toggleGear}
        >
          <ha-icon icon="mdi:cog-outline"></ha-icon>
        </button>
        ${this._gear ? this._renderGear() : nothing}
      </span>
      <button
        class="ghost"
        data-docs
        title=${this._t("docs")}
        aria-label=${this._t("docs")}
        @click=${() => window.open(editorDocsUrl(this.hass?.language), "_blank", "noopener")}
      >
        <ha-icon icon="mdi:help-circle-outline"></ha-icon>
      </button>
      <button class="ghost" data-history @click=${this._openHistory}>
        <ha-icon icon="mdi:history"></ha-icon>${this._t("history")}
      </button>
      <button class="primary" data-save ?disabled=${!this._changed} @click=${this._openSave}>
        <ha-icon icon="mdi:content-save"></ha-icon>${this._t("save")}
      </button>
    </header>`;
  }

  _renderGear() {
    const segment = (group, values, current, choose) => html`<div class="segment" role="group" data-segment=${group}>
      ${values.map(
        (value) => html`<button
          type="button"
          data-value=${value}
          class=${value === current ? "on" : ""}
          aria-pressed=${value === current ? "true" : "false"}
          @click=${() => choose(value)}
        >
          ${this._t(`gear_${group}_${value}`)}
        </button>`,
      )}
    </div>`;
    return html`<div class="gear-pop" role="dialog" data-gear-pop aria-label=${this._t("gear_title")}>
      <b>${this._t("gear_title")}</b>
      <span class="gear-group">${this._t("gear_theme")}</span>
      ${segment("theme", THEMES, this._theme, (theme) => this._setTheme(theme))}
      <span class="gear-group">${this._t("gear_language")}</span>
      ${segment("language", EDITOR_LANGUAGES, this._language, (language) => this._setLanguage(language))}
      <p class="gear-hint">${this._t("gear_hint")}</p>
      <div class="gear-links">
        <button type="button" class="gear-link" data-gear-tour @click=${this._openTour}>
          <ha-icon icon="mdi:map-marker-path"></ha-icon>${this._t("tour_open")}
        </button>
        <button
          type="button"
          class="gear-link"
          data-gear-lessons
          @click=${() => {
            this._gear = false;
            this._dialog = "lessons";
          }}
        >
          <ha-icon icon="mdi:school-outline"></ha-icon>${this._t("lessons_title")}
        </button>
      </div>
    </div>`;
  }

  _renderNotices() {
    return html`
      ${this._conflict ? html`<div class="notice error" data-conflict-notice><span>${this._t("conflict")}</span></div>` : nothing}
      ${this._notice
        ? html`<div class="notice ${this._notice.kind}" data-notice=${this._notice.kind}>
            <span>${this._notice.text}</span>
            <button class="ghost" aria-label=${this._t("close")} @click=${() => (this._notice = null)}>
              <ha-icon icon="mdi:close"></ha-icon>
            </button>
          </div>`
        : nothing}
    `;
  }

  _renderTree() {
    const outline = this._outline();
    const groups = filterOutline([...outline.groups, this._sentencesGroup()], this._search);
    const searching = Boolean(this._search.trim());
    const selected = this._selected && nodeKey(this._selected);
    const node = (item, depth) => {
      const open = searching || !this._collapsed.has(item.key);
      return html`
        <div
          class="node ${selected === item.key ? "sel" : ""} ${item.warn ? "warn" : ""} ${item.missing ? "missing" : ""}"
          style="padding-left: ${8 + depth * 16}px"
          data-node=${item.key}
          title=${item.warn ?? item.hint ?? ""}
          @click=${() => this._select(item)}
        >
          ${item.children.length
            ? html`<button
                class="fold"
                aria-label=${this._t("fold")}
                data-fold=${item.key}
                @click=${(event) => {
                  event.stopPropagation();
                  this._toggle(item);
                }}
              >
                <ha-icon .icon=${open ? "mdi:chevron-down" : "mdi:chevron-right"}></ha-icon>
              </button>`
            : html`<span class="fold"></span>`}
          <ha-icon class="icon" .icon=${item.warn ? "mdi:alert-outline" : item.icon}></ha-icon>
          <span class="label">${item.label}</span>
          ${item.kind ? html`<span class="count">${item.examples || ""}</span>` : nothing}
        </div>
        ${open ? item.children.map((child) => node(child, depth + 1)) : nothing}
      `;
    };
    return html`<nav class="tree" data-tree>
      <label class="search">
        <ha-icon icon="mdi:magnify"></ha-icon>
        <input
          data-search
          placeholder=${this._t("search")}
          .value=${this._search}
          @input=${(event) => (this._search = event.target.value)}
        />
      </label>
      <div class="tree-tools">
        <button class="ghost" data-fold-all @click=${() => this._foldAll(true)}>
          <ha-icon icon="mdi:unfold-less-horizontal"></ha-icon>${this._t("fold_all")}
        </button>
        <button class="ghost" data-unfold-all @click=${() => this._foldAll(false)}>
          <ha-icon icon="mdi:unfold-more-horizontal"></ha-icon>${this._t("unfold_all")}
        </button>
        <span class="grow"></span>
        ${this._helpButton("tree", DOCS_ANCHORS.screen)} ${this._foldButton("left")}
      </div>
      ${outline.error ? html`<p class="tree-error" data-tree-error>${this._t("file_error", { error: outline.error })}</p>` : nothing}
      ${groups.map((group) => {
        const groupOpen = searching || !this._collapsed.has(group.key);
        const folding = this._groupFolding(group);
        return html`
          <div class="group" data-group=${group.key}>
            <button
              class="fold"
              aria-label=${this._t("fold")}
              aria-expanded=${groupOpen}
              data-group-fold=${group.key}
              @click=${() => this._toggle(group)}
            >
              <ha-icon .icon=${groupOpen ? "mdi:chevron-down" : "mdi:chevron-right"}></ha-icon>
            </button>
            <span class="group-name" @click=${() => this._toggle(group)}>${group.label}</span>
            ${group.key === "topics" && !outline.error
              ? html`<button class="ghost add" data-add-topic title=${this._t("add_topic")} @click=${this._addTopic}>
                  <ha-icon icon="mdi:plus"></ha-icon>
                </button>`
              : nothing}
            ${group.key === "commands"
              ? html`<button class="ghost add" data-add-sentences title=${this._t("sentences_add_file")} @click=${this._addSentencesFile}>
                  <ha-icon icon="mdi:plus"></ha-icon>
                </button>`
              : nothing}
            ${group.children.length
              ? html`<button
                  class="ghost add"
                  data-group-fold-all=${group.key}
                  data-open=${folding.open}
                  title=${this._t(folding.open ? "group_fold_all" : "group_unfold_all")}
                  @click=${() => this._foldGroup(group)}
                >
                  <ha-icon .icon=${folding.open ? "mdi:unfold-less-horizontal" : "mdi:unfold-more-horizontal"}></ha-icon>
                </button>`
              : nothing}
          </div>
          ${groupOpen ? group.children.map((item) => node(item, 0)) : nothing}
        `;
      })}
    </nav>`;
  }

  _renderMiddle() {
    return html`<main class="middle" data-middle>
      <div class="tabs" data-tabs>
        <div class="seg" ?hidden=${formFor(this._selected) === "sentences"}>
          <button
            class=${this._tab === "form" ? "on" : ""}
            data-tab="form"
            ?disabled=${!formFor(this._selected)}
            @click=${() => this._showTab("form")}
          >
            ${this._t("tab_form")}
          </button>
          <button class=${this._tab === "node" ? "on" : ""} data-tab="node" @click=${() => this._showTab("node")}>
            ${this._t("tab_node")}
          </button>
          <button class=${this._tab === "file" ? "on" : ""} data-tab="file" @click=${() => this._showTab("file")}>
            ${this._t("tab_file")}
          </button>
        </div>
        ${this._tab !== "file" && this._selected
          ? html`<span class="crumbs" data-crumbs>${this._crumbs()}</span>
              <span class="grow"></span>
              ${this._selected.length > 1 && blockText(this._text, this._selected) !== null
                ? html`<button class="ghost" data-duplicate @click=${this._duplicate}>
                    <ha-icon icon="mdi:content-copy"></ha-icon>${this._t("duplicate")}
                  </button>`
                : nothing}
              ${blockText(this._text, this._selected) !== null
                ? html`<button class="ghost danger" data-delete @click=${this._delete}>
                    <ha-icon icon="mdi:delete-outline"></ha-icon>${this._t("delete")}
                  </button>`
                : nothing}`
          : html`<span class="grow"></span>`}
        ${this._helpButton("middle", this._tab === "file" ? DOCS_ANCHORS.parts : docsAnchorFor(this._selected))}
      </div>
      ${formFor(this._selected) === "sentences"
        ? this._renderForm()
        : this._tab === "file"
          ? this._renderFile()
          : this._tab === "form" && formFor(this._selected)
            ? this._renderForm()
            : this._renderNode()}
    </main>`;
  }

  _crumbs() {
    if (nodeKey(this._selected) === nodeKey(SETTINGS_PATH)) return this._t("key_settings");
    if (this._selected[0] in LEARN_NODES) return this._t(`key_${this._selected[0].slice(1)}`);
    if (this._selected[0] === "@sentences") return `custom_sentences › ${this._selected[1]} › ${this._selected[2]}`;
    return this._selected.join(" › ");
  }

  _renderForm() {
    const form = formFor(this._selected);
    if (form === "sentences") {
      const path = this._selected;
      return html`<assist-router-sentences
        class="form-pane"
        .hass=${this.hass}
        .file=${this._sentenceFile(path)}
        .edited=${this._sentenceEdits[nodeKey(path)] ?? null}
        .intents=${this._sentences.intents}
        @change=${(event) => this._onSentencesChange(path, event.detail.text)}
        @saved=${(event) => this._onSentencesSaved(path, event.detail)}
        @deleted=${() => this._onSentencesDeleted(path)}
      ></assist-router-sentences>`;
    }
    if (form === "unrecognized" || form === "tests") {
      return html`<assist-router-learn
        class="form-pane"
        .mode=${form}
        .hass=${this.hass}
        .text=${this._text}
        .tests=${this._tests}
        @edit=${this._onFormEdit}
        @select=${(event) => this._select({ path: event.detail.path })}
        @tests-changed=${(event) => this._saveTests(event.detail.tests)}
        @try=${(event) => (this._tryRequest = { sentence: event.detail.sentence, at: Date.now() })}
      ></assist-router-learn>`;
    }
    return html`<assist-router-form
      class="form-pane"
      .text=${this._text}
      .path=${this._selected}
      .hass=${this.hass}
      .languages=${this._languages}
      @edit=${this._onFormEdit}
      @select=${(event) => this._select({ path: event.detail.path })}
    ></assist-router-form>`;
  }

  _renderNode() {
    if (!this._selected) return html`<p class="empty" data-pick>${this._t("pick")}</p>`;
    const block = blockText(this._text, this._selected);
    if (block === null) {
      const { doc } = readDocument(this._text);
      const reason =
        nodeKey(this._selected) === nodeKey(SETTINGS_PATH)
          ? "settings_no_block"
          : this._selected[0] in LEARN_NODES
            ? "learn_no_block"
            : this._selected[0] === "@sentences"
              ? "sentences_no_block"
          : valueAt(doc, this._selected) === undefined && this._has(this._selected)
            ? "missing_node"
            : this._has(this._selected)
              ? "no_block"
              : "lost";
      return html`<p class="empty" data-no-block=${reason}>${this._t(reason)}</p>`;
    }
    return html`
      <textarea
        class="code"
        data-node-yaml
        spellcheck="false"
        .value=${this._nodeText ?? block}
        @input=${this._onNodeInput}
        @keydown=${this._onTab}
        @blur=${() => {
          // Leaving a valid block shows it again as the file holds it.
          if (!this._nodeError) this._nodeText = null;
          this._editStart = null;
        }}
      ></textarea>
      ${this._nodeError
        ? html`<p class="field-error" data-node-error>${this._t("node_error", { error: this._nodeError })}</p>`
        : html`<p class="hint">${this._t("node_hint")}</p>`}
    `;
  }

  _renderFile() {
    return html`<textarea
        class="code"
        data-file-yaml
        spellcheck="false"
        .value=${this._text}
        @input=${this._onFileInput}
        @keydown=${this._onTab}
      ></textarea>
      ${this._outline().error
        ? html`<p class="field-error" data-file-error>${this._t("file_error", { error: this._outline().error })}</p>`
        : nothing}`;
  }

  _renderSide() {
    const check = this._check;
    const { doc } = readDocument(this._text);
    const topic = this._selected?.[0] === "topics" && this._selected.length === 2 ? valueAt(doc, this._selected) : undefined;
    const kind = topic !== undefined ? topicKind(topic) : null;
    const item = this._selected && flattenOutline(this._outline().groups).find((node) => node.key === nodeKey(this._selected));
    return html`<aside class="side" data-side>
      <div class="side-help">${this._helpButton("side", DOCS_ANCHORS.save)} ${this._foldButton("right")}</div>
      <section class="card" data-check=${check ? (check.ok ? "ok" : "error") : "pending"}>
        <h3>${this._t("check_title")}</h3>
        ${!check
          ? html`<p class="muted">${this._t("check_pending")}</p>`
          : check.ok
            ? html`<p class="ok"><ha-icon icon="mdi:check-circle"></ha-icon>${this._t("check_ok", { count: check.topics.length })}</p>`
            : html`<p class="bad"><ha-icon icon="mdi:alert-circle"></ha-icon>${this._t("check_error")}</p>
                <code class="error-text">${check.error}</code>`}
      </section>
      <section class="card" data-file-card>
        <h3>${this._t("file_title")}</h3>
        ${this._file ? nothing : html`<p class="muted" data-file-missing>${this._t("file_missing")}</p>`}
        ${this._draftAt && this._changed
          ? html`<p data-draft-at>${this._t("draft_at", { time: new Date(this._draftAt).toLocaleString(this.hass.language) })}</p>`
          : nothing}
        <p class="muted">${this._t("draft_note")}</p>
      </section>
      ${kind
        ? html`<section class="card" data-kind=${kind}>
            <h3>${this._t("kind_title")}</h3>
            <p class="kind"><ha-icon .icon=${KIND_ICONS[kind]}></ha-icon>${this._t(`kind_${kind}`)}</p>
            <p class="muted">${this._t(`kind_hint_${kind}`)}</p>
            <p>${this._t("examples_count", { count: Array.isArray(topic?.examples) ? topic.examples.length : 0 })}</p>
            ${item?.warn ? html`<p class="warn" data-warn><ha-icon icon="mdi:alert-outline"></ha-icon>${item.warn}</p>` : nothing}
          </section>`
        : nothing}
      <assist-router-tester
        .hass=${this.hass}
        .text=${this._text}
        .request=${this._tryRequest}
        @select=${(event) => this._select({ path: event.detail.path })}
        @add-test=${(event) => this._addTest(event.detail.test)}
      ></assist-router-tester>
    </aside>`;
  }

  static styles = css`
    /* The dark look; the light one (data-theme="light") changes the same colours below. */
    :host {
      color-scheme: dark;
      --bg: #111318;
      --panel: #1b1e24;
      --panel2: #23272e;
      --line: #2f343c;
      --text: #e8eaed;
      --muted: #9aa0a6;
      --accent: #4f8cff;
      --amber: #ffb340;
      --red: #ff453a;
      --green: #30d158;
      --field: #0d0f13;
      --on: #3a3f48;
      --hover: rgba(255, 255, 255, 0.04);
      --faint: #5f6670;
      --added: #6fdc8c;
      --removed: #ff7b72;
      --scrim: rgba(0, 0, 0, 0.55);
      --shadow: rgba(0, 0, 0, 0.6);
      display: flex;
      flex-direction: column;
      height: 100vh;
      color: var(--text);
      background: var(--bg);
      font: 14px/1.4 -apple-system, "SF Pro Text", Roboto, system-ui, sans-serif;
      --mdc-icon-size: 18px;
    }
    :host([data-theme="light"]) {
      color-scheme: light;
      --bg: #f2f3f7;
      --panel: #ffffff;
      --panel2: #eceef3;
      --line: #d5d9e0;
      --text: #1d2026;
      --muted: #5f6670;
      --accent: #2f6fe4;
      --amber: #a15c00;
      --red: #d0021b;
      --green: #1c7f37;
      --field: #ffffff;
      --on: #ffffff;
      --hover: rgba(0, 0, 0, 0.04);
      --faint: #8a9099;
      --added: #1c7f37;
      --removed: #c62828;
      --scrim: rgba(0, 0, 0, 0.3);
      --shadow: rgba(0, 0, 0, 0.18);
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
    button.ghost {
      background: transparent;
      color: var(--muted);
    }
    button.ghost.danger {
      color: var(--red);
    }
    .top {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 10px 16px;
      background: var(--panel);
      border-bottom: 1px solid var(--line);
    }
    button.menu {
      padding: 6px;
      --mdc-icon-size: 22px;
    }
    .app-icon {
      --mdc-icon-size: 22px;
      color: var(--accent);
      flex: none;
    }
    h1 {
      margin: 0 8px 0 0;
      font-size: 16px;
    }
    .board {
      overflow: hidden;
      color: var(--muted);
      font: 12px ui-monospace, SFMono-Regular, Menlo, monospace;
      white-space: nowrap;
      text-overflow: ellipsis;
    }
    .grow {
      flex: 1;
    }
    .pill {
      display: inline-flex;
      gap: 6px;
      align-items: center;
      padding: 4px 10px;
      border-radius: 999px;
      font-size: 12px;
      color: var(--muted);
      background: var(--panel2);
      white-space: nowrap;
    }
    .pill.draft {
      color: var(--amber);
      background: rgba(255, 179, 64, 0.15);
    }
    .notice {
      display: flex;
      gap: 10px;
      align-items: center;
      padding: 8px 16px;
      background: rgba(79, 140, 255, 0.15);
    }
    .notice.error {
      background: rgba(255, 69, 58, 0.15);
    }
    .notice.ok {
      background: rgba(48, 209, 88, 0.15);
    }
    .notice span {
      flex: 1;
    }
    .cols {
      flex: 1;
      display: grid;
      grid-template-columns: var(--left) 6px minmax(0, 1fr) 6px var(--right);
      min-height: 0;
    }
    .tree,
    .side {
      overflow: auto;
      background: var(--panel);
    }
    .tree {
      padding: 10px 8px;
    }
    .search {
      display: flex;
      gap: 8px;
      align-items: center;
      margin: 0 4px 6px;
      padding: 6px 10px;
      border-radius: 9px;
      color: var(--muted);
      background: var(--panel2);
    }
    .search input {
      flex: 1;
      min-width: 0;
      border: 0;
      outline: none;
      color: var(--text);
      background: transparent;
      font: inherit;
    }
    .tree-tools {
      display: flex;
      gap: 2px;
    }
    .tree-tools button {
      padding: 4px 8px;
      font-size: 12px;
    }
    .tree-error {
      margin: 8px;
      color: var(--red);
    }
    .group {
      display: flex;
      gap: 4px;
      align-items: center;
      min-height: 28px;
      margin: 12px 8px 4px 0;
      font-size: 11px;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      color: var(--muted);
    }
    .group .add {
      padding: 4px;
    }
    .group-name {
      flex: 1;
      cursor: pointer;
      user-select: none;
    }
    .node {
      display: flex;
      align-items: center;
      gap: 6px;
      padding: 5px 8px;
      border-radius: 8px;
      cursor: pointer;
    }
    .node:hover {
      background: var(--hover);
    }
    .node.sel {
      background: rgba(79, 140, 255, 0.18);
      outline: 1px solid rgba(79, 140, 255, 0.5);
    }
    ha-icon {
      display: inline-flex;
      min-width: 18px;
      min-height: 18px;
    }
    .node .icon {
      color: var(--muted);
    }
    .node.warn .icon {
      color: var(--amber);
    }
    .node.missing {
      color: var(--muted);
      opacity: 0.65;
    }
    .form-pane {
      flex: 1;
    }
    .node .label {
      flex: 1;
      min-width: 0;
      overflow: hidden;
      white-space: nowrap;
      text-overflow: ellipsis;
    }
    .node .count {
      font-size: 12px;
      color: var(--muted);
    }
    .fold {
      flex: none;
      justify-content: center;
      width: 18px;
      height: 18px;
      padding: 0;
      background: none;
      color: var(--muted);
    }
    .splitter {
      cursor: col-resize;
      background: var(--line);
      touch-action: none;
    }
    .splitter:hover,
    .splitter.dragging {
      background: var(--accent);
    }
    .middle {
      display: flex;
      flex-direction: column;
      gap: 8px;
      min-width: 0;
      min-height: 0;
      padding: 10px 16px 14px;
    }
    .help {
      flex: none;
      padding: 4px;
      color: var(--muted);
    }
    .help ha-icon {
      --mdc-icon-size: 18px;
    }
    .help.on {
      color: var(--accent);
    }
    .fold-column {
      flex: none;
      padding: 4px;
    }
    .rail {
      display: flex;
      justify-content: center;
      padding-top: 8px;
      min-width: 0;
      overflow: hidden;
      background: var(--panel);
    }
    .rail button {
      padding: 4px 2px;
    }
    .splitter.off {
      cursor: default;
      pointer-events: none;
    }
    .help-shade {
      position: fixed;
      inset: 0;
      z-index: 20;
    }
    .gear-wrap {
      position: relative;
      display: inline-flex;
    }
    .gear-pop {
      position: absolute;
      top: calc(100% + 6px);
      right: 0;
      z-index: 22;
      display: grid;
      gap: 8px;
      min-width: 260px;
      padding: 12px 14px;
      border: 1px solid var(--line);
      border-radius: 12px;
      background: var(--panel);
      color: var(--text);
      box-shadow: 0 12px 32px var(--shadow);
      font-size: 13px;
    }
    .gear-group {
      margin-top: 4px;
      color: var(--muted);
      font-size: 12px;
    }
    .segment {
      display: flex;
      gap: 2px;
      padding: 2px;
      border-radius: 9px;
      background: var(--panel2);
    }
    .segment button {
      flex: 1;
      justify-content: center;
      padding: 5px 10px;
      border-radius: 7px;
      background: transparent;
      color: var(--muted);
      white-space: nowrap;
    }
    .segment button.on {
      background: var(--on);
      color: var(--text);
      font-weight: 600;
    }
    .gear-links {
      display: grid;
      gap: 2px;
      padding-top: 6px;
      border-top: 1px solid var(--line);
    }
    .gear-link,
    .help-lesson {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 6px 8px;
      border: 0;
      border-radius: 8px;
      color: var(--text);
      background: none;
      font: inherit;
      text-align: left;
      cursor: pointer;
    }
    .gear-link:hover,
    .help-lesson:hover:not([disabled]) {
      background: var(--hover);
    }
    .help-lesson {
      margin: 0 0 8px;
      padding: 6px 10px;
      color: var(--accent);
      border: 1px solid var(--line);
    }
    .help-lesson[disabled] {
      opacity: 0.55;
      cursor: default;
    }
    .gear-hint {
      max-width: 300px;
      margin: 2px 0 0;
      color: var(--muted);
      font-size: 12px;
    }
    .help-pop {
      position: fixed;
      z-index: 21;
      box-sizing: border-box;
      padding: 12px 14px;
      border: 1px solid var(--line);
      border-radius: 12px;
      background: var(--panel);
      color: var(--text);
      box-shadow: 0 12px 32px rgb(0 0 0 / 0.35);
      font-size: 13px;
      line-height: 1.45;
    }
    .help-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
    }
    .help-head button {
      padding: 2px;
    }
    .help-pop p {
      margin: 6px 0 10px;
    }
    .help-pop a {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      color: var(--accent);
      text-decoration: none;
    }
    .help-pop a ha-icon {
      --mdc-icon-size: 14px;
    }
    .side-help {
      display: flex;
      justify-content: flex-end;
      margin-bottom: -8px;
    }
    .tabs {
      display: flex;
      gap: 10px;
      align-items: center;
      min-height: 36px;
    }
    .seg {
      display: flex;
      gap: 2px;
      padding: 3px;
      border-radius: 9px;
      background: var(--panel2);
    }
    .seg[hidden] {
      display: none;
    }
    .seg button {
      padding: 4px 10px;
      background: transparent;
      color: var(--muted);
    }
    .seg button.on {
      background: var(--on);
      color: var(--text);
    }
    .crumbs {
      overflow: hidden;
      color: var(--muted);
      font: 12px ui-monospace, SFMono-Regular, Menlo, monospace;
      white-space: nowrap;
      text-overflow: ellipsis;
    }
    textarea.code {
      flex: 1;
      min-height: 0;
      padding: 12px 14px;
      resize: none;
      border: 1px solid var(--line);
      border-radius: 10px;
      outline: none;
      color: var(--text);
      background: var(--field);
      font: 13px/1.55 ui-monospace, SFMono-Regular, Menlo, monospace;
      tab-size: 2;
      white-space: pre;
    }
    textarea.code:focus {
      border-color: rgba(79, 140, 255, 0.6);
    }
    .hint,
    .field-error {
      margin: 0;
      font-size: 12px;
      color: var(--muted);
    }
    .field-error {
      color: var(--red);
    }
    .empty {
      margin: 40px auto;
      max-width: 420px;
      text-align: center;
      color: var(--muted);
    }
    .side {
      display: flex;
      flex-direction: column;
      gap: 10px;
      padding: 14px 16px;
    }
    .card {
      padding: 12px 14px;
      border-radius: 12px;
      background: var(--panel2);
    }
    .card h3 {
      margin: 0 0 6px;
      font-size: 11px;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      color: var(--muted);
    }
    .card p {
      display: flex;
      gap: 6px;
      align-items: flex-start;
      margin: 4px 0;
    }
    .muted {
      color: var(--muted);
    }
    .ok {
      color: var(--green);
    }
    .bad,
    .warn {
      color: var(--amber);
    }
    .bad {
      color: var(--red);
    }
    .error-text {
      display: block;
      white-space: pre-wrap;
      font: 12px ui-monospace, SFMono-Regular, Menlo, monospace;
    }
    .kind {
      font-weight: 600;
    }
  `;
}

if (!customElements.get(APP_TAG)) customElements.define(APP_TAG, AssistRouterEditorApp);

/** The editor in a host element (the panel, or a page of the tests); the app, to give it a newer hass. */
export function mountEditor(host, hass) {
  const app = document.createElement(APP_TAG);
  app.hass = hass;
  host.appendChild(app);
  return app;
}
