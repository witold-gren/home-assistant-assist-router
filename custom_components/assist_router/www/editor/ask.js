// A question of the editor in its own window, never window.confirm / alert / prompt: those have the browser's look,
// ignore the theme and the language of the buttons and block the whole page. The window goes into the shadow root of
// the editor, so it has the editor's colours and theme.
//
//   if (!(await ask(this, { text, ok: this._t("delete"), danger: true }))) return;
//   const name = await ask(this, { title, text, ok: this._t("sentences_create"), input: "my_commands.yaml" });

import { LitElement, css, html, nothing } from "../vendor/lit-all.min.js";
import { dialogStyles } from "./dialogs.js";
import { translate } from "./i18n.js";

const APP_TAG = "ASSIST-ROUTER-EDITOR-APP";
const TAG = "assist-router-ask";

/** The editor app this element is in (through the shadow roots), or null. */
export function editorOf(element) {
  let node = element;
  while (node) {
    if (node.tagName === APP_TAG) return node;
    node = node.parentNode ?? node.host ?? null;
  }
  return null;
}

/**
 * Ask over the editor `from` is in. `question`: { title, text, ok (the button, named after the action), danger,
 * icon, input (a starting value: the window has a text field), language }. Resolves to true (or the typed text with
 * `input`) when the action button is clicked, false (null with `input`) when cancelled.
 */
export function ask(from, question) {
  const app = editorOf(from);
  const host = app?.shadowRoot ?? (from?.getRootNode?.() instanceof ShadowRoot ? from.getRootNode() : document.body);
  const box = document.createElement(TAG);
  box.question = { language: app?.hass?.language ?? from?.hass?.language, ...question };
  host.appendChild(box);
  return new Promise((resolve) => {
    box.addEventListener(
      "answer",
      (event) => {
        box.remove();
        resolve(event.detail);
      },
      { once: true },
    );
  });
}

/** Whether a question is open over the editor (its other keys wait then). */
export const asking = (root) => Boolean(root?.querySelector?.(TAG));

class AskDialog extends LitElement {
  static properties = {
    question: { attribute: false },
    _value: { state: true },
  };

  constructor() {
    super();
    this._value = "";
    this._keys = (event) => this._key(event);
  }

  _t(key) {
    return translate(this.question?.language, key);
  }

  get _withField() {
    return this.question?.input !== undefined;
  }

  connectedCallback() {
    super.connectedCallback();
    // The element that opened it, through the shadow roots: the focus goes back there on close.
    let active = document.activeElement;
    while (active?.shadowRoot?.activeElement) active = active.shadowRoot.activeElement;
    this._before = active;
    this._value = this.question?.input ?? "";
    // In capture, so Esc and Tab do not reach the editor or Home Assistant behind the window.
    window.addEventListener("keydown", this._keys, true);
  }

  disconnectedCallback() {
    window.removeEventListener("keydown", this._keys, true);
    this._before?.focus?.();
    super.disconnectedCallback();
  }

  firstUpdated() {
    const field = this.renderRoot.querySelector("[data-ask-input]");
    if (field) {
      field.focus();
      field.select();
    } else {
      // A dangerous action starts on Cancel, so Enter alone never does it.
      this.renderRoot.querySelector(this.question?.danger ? "[data-ask-cancel]" : "[data-ask-ok]")?.focus();
    }
  }

  _answer(ok) {
    if (this._answered) return;
    let detail = ok;
    if (this._withField) {
      const value = this._value.trim();
      if (ok && !value) return;
      detail = ok ? value : null;
    }
    this._answered = true;
    this.dispatchEvent(new CustomEvent("answer", { detail }));
  }

  _key(event) {
    if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      this._answer(false);
    } else if (event.key === "Tab") {
      // The focus stays in the window.
      event.preventDefault();
      event.stopPropagation();
      const parts = [...this.renderRoot.querySelectorAll("input, button:not(:disabled)")];
      const at = parts.indexOf(this.renderRoot.activeElement);
      parts[(at + (event.shiftKey ? -1 : 1) + parts.length) % parts.length]?.focus();
    } else if (event.key === "Enter" && this._withField && event.composedPath()[0]?.dataset?.askInput !== undefined) {
      event.preventDefault();
      event.stopPropagation();
      this._answer(true);
    }
  }

  render() {
    const question = this.question ?? {};
    const empty = this._withField && !this._value.trim();
    return html`<div class="ask-scrim" data-ask-scrim @click=${(event) => event.target === event.currentTarget && this._answer(false)}>
      <div class="box" role="alertdialog" aria-modal="true" aria-labelledby="ask-q" data-ask>
        ${question.title ? html`<h2 id="ask-q" data-ask-title>${question.title}</h2>` : nothing}
        ${question.text
          ? html`<label class="text" id=${question.title ? "ask-text" : "ask-q"} for="ask-input" data-ask-text>${question.text}</label>`
          : nothing}
        ${this._withField
          ? html`<input
              id="ask-input"
              data-ask-input
              .value=${this._value}
              autocomplete="off"
              spellcheck="false"
              @input=${(event) => (this._value = event.target.value)}
            />`
          : nothing}
        <div class="row">
          <button data-ask-cancel @click=${() => this._answer(false)}>${this._t("cancel")}</button>
          <button class=${question.danger ? "danger" : "primary"} data-ask-ok ?disabled=${empty} @click=${() => this._answer(true)}>
            ${question.icon ? html`<ha-icon icon=${question.icon}></ha-icon>` : nothing}${question.ok || this._t("ask_ok")}
          </button>
        </div>
      </div>
    </div>`;
  }

  static styles = [
    dialogStyles,
    css`
      :host {
        z-index: 50;
        background: transparent;
      }
      .ask-scrim {
        position: absolute;
        inset: 0;
        display: flex;
        align-items: center;
        justify-content: center;
        background: var(--scrim);
      }
      .box {
        width: min(480px, calc(100vw - 48px));
      }
      .text {
        margin: 0;
        white-space: pre-line;
        line-height: 1.5;
      }
    `,
  ];
}

if (!customElements.get(TAG)) customElements.define(TAG, AskDialog);
