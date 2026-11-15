// The editor of router.yaml on a computer: a panel of Home Assistant for administrators. The app loads on the
// first hass, so the panel itself stays small.

const TAG = "assist-router-editor";

class AssistRouterEditorPanel extends HTMLElement {
  set hass(hass) {
    this._hass = hass;
    if (!this._started) {
      this._started = true;
      import("./editor-app.js").then(({ mountEditor }) => {
        this._app = mountEditor(this, this._hass);
      });
    }
    if (this._app) this._app.hass = hass;
  }

  get hass() {
    return this._hass;
  }
}

if (!customElements.get(TAG)) customElements.define(TAG, AssistRouterEditorPanel);
