// The "?" of a dialog (standard section 5): a small window saying what the dialog does, with a quiet link to its
// chapter of the guide; it never opens the guide by itself. The window hangs under the button, inside the dialog
// (a dialog is moved with transform, so a fixed window would land elsewhere).
import { LitElement, css, html, nothing } from "../vendor/lit-all.min.js";
import { translate } from "./i18n.js";
import { editorDocsUrl } from "./docs-anchors.js";

const TAG = "assist-router-help";

class AssistRouterHelp extends LitElement {
  static properties = {
    part: {},
    anchor: {},
    language: {},
    _open: { state: true },
  };

  constructor() {
    super();
    this._open = false;
    this._onKey = (event) => {
      if (event.key === "Escape" && this._open) {
        // Esc closes the window, not the dialog under it.
        event.stopPropagation();
        this._open = false;
      }
    };
  }

  connectedCallback() {
    super.connectedCallback();
    window.addEventListener("keydown", this._onKey, true);
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    window.removeEventListener("keydown", this._onKey, true);
  }

  _t(key) {
    return translate(this.language, key);
  }

  render() {
    const title = this._t(`help_${this.part}_title`);
    return html`<button
        class="help ${this._open ? "on" : ""}"
        data-help=${this.part}
        data-anchor=${this.anchor}
        title=${`${this._t("help_what")} ${title}`}
        aria-label=${`${this._t("help_what")} ${title}`}
        aria-expanded=${this._open ? "true" : "false"}
        @click=${() => (this._open = !this._open)}
      >
        <ha-icon icon="mdi:help-circle-outline"></ha-icon>
      </button>
      ${this._open
        ? html`<div class="shade" data-help-shade @click=${() => (this._open = false)}></div>
            <div class="pop" role="dialog" aria-label=${title} data-help-pop=${this.part}>
              <div class="head">
                <b>${title}</b>
                <button data-help-close aria-label=${this._t("close")} @click=${() => (this._open = false)}>
                  <ha-icon icon="mdi:close"></ha-icon>
                </button>
              </div>
              <p>${this._t(`help_${this.part}`)}</p>
              <a data-help-more href=${editorDocsUrl(this.language, this.anchor)} target="_blank" rel="noopener"
                >${this._t("help_more")} <ha-icon icon="mdi:open-in-new"></ha-icon
              ></a>
            </div>`
        : nothing}`;
  }

  static styles = css`
    :host {
      position: relative;
      display: inline-flex;
    }
    button {
      display: inline-flex;
      padding: 4px;
      border: 0;
      border-radius: 8px;
      background: transparent;
      color: var(--muted, inherit);
      cursor: pointer;
    }
    button ha-icon {
      --mdc-icon-size: 18px;
    }
    .help.on {
      color: var(--accent, inherit);
    }
    .shade {
      position: fixed;
      inset: -100vmax;
      z-index: 20;
    }
    .pop {
      position: absolute;
      top: calc(100% + 6px);
      right: 0;
      z-index: 21;
      box-sizing: border-box;
      width: min(320px, 80vw);
      padding: 12px 14px;
      border: 1px solid var(--line, #8884);
      border-radius: 12px;
      background: var(--panel, #fff);
      color: var(--text, inherit);
      box-shadow: 0 12px 32px rgb(0 0 0 / 0.35);
      font-size: 13px;
      font-weight: 400;
      line-height: 1.45;
      text-align: left;
    }
    .head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
    }
    .head button {
      padding: 2px;
    }
    p {
      margin: 6px 0 10px;
    }
    a {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      color: var(--accent, inherit);
      text-decoration: none;
    }
    a ha-icon {
      --mdc-icon-size: 14px;
    }
  `;
}

if (!customElements.get(TAG)) customElements.define(TAG, AssistRouterHelp);
