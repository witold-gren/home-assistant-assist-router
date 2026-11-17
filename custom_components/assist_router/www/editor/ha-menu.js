// The same module as in Home Dashboard (custom_components/home_dashboard/www/app/ha-menu.js); keep them alike.
// The menu (sidebar) of Home Assistant on our own pages: the editor hides it while it is open and
// gives it back on any other page of Home Assistant.
//
// The kiosk mode of Home Assistant hides it as "always hidden" does, but Home Assistant never saves it: changing
// `dockedSidebar` instead got saved as the user's own choice whenever Home Assistant stored its settings (at every
// load, when the preferences of the theme arrive), and the menu stayed hidden everywhere. An older Home Assistant
// without the kiosk mode still gets `dockedSidebar`, given back when leaving.

const haApp = () => document.querySelector("home-assistant");

/**
 * Hides the menu of Home Assistant; returns how to give it back ("kiosk", or the place of the menu before), or null
 * when nothing was changed (no Home Assistant around, or the menu hidden already, e.g. by a kiosk mode of the user's).
 */
export function hideMenu() {
  const app = haApp();
  if (!app?._updateHass || !app.hass) return null;
  if ("kioskMode" in app.hass) {
    if (app.hass.kioskMode) return null;
    app._updateHass({ kioskMode: true });
    return "kiosk";
  }
  if (app.hass.dockedSidebar === "always_hidden") return null;
  const docked = app.hass.dockedSidebar;
  app._updateHass({ dockedSidebar: "always_hidden" });
  return docked;
}

/** Gives back a menu hidden by hideMenu(); nothing for null. */
export function restoreMenu(hidden) {
  const app = haApp();
  if (!hidden || !app?._updateHass || !app.hass) return;
  if (hidden === "kiosk") {
    if (app.hass.kioskMode) app._updateHass({ kioskMode: false });
  } else if (app.hass.dockedSidebar === "always_hidden") {
    app._updateHass({ dockedSidebar: hidden });
  }
}

/** Whether Home Assistant shows its menu as a drawer over the page (a phone), not docked at the side. */
export function menuIsDrawer() {
  return Boolean(haApp()?.shadowRoot?.querySelector("home-assistant-main")?.narrow);
}

/** The panel of Home Assistant a path belongs to: /home-dashboard/... -> /home-dashboard. */
export const panelPath = (pathname = window.location.pathname) => `/${pathname.split("/").filter(Boolean)[0] ?? ""}`;

/**
 * The menu of Home Assistant on a panel of ours with a menu button (an editor): hidden when the panel opens, the
 * button shows and hides it, and it comes back on any other page. connect() and disconnect() go with the panel's.
 */
export class PanelMenu {
  constructor(host) {
    this._host = host;
    this._hidden = null;
    this._shown = false;
    this._follow = () => {
      if (panelPath() !== this._path) {
        this._giveBack();
        this._shown = false;
      } else if (!this._hidden && !this._shown) {
        this._hidden = hideMenu();
      }
    };
  }

  connect() {
    this._path = panelPath();
    this._shown = false;
    this._hidden = hideMenu();
    window.addEventListener("location-changed", this._follow);
    window.addEventListener("popstate", this._follow);
  }

  disconnect() {
    window.removeEventListener("location-changed", this._follow);
    window.removeEventListener("popstate", this._follow);
    this._giveBack();
  }

  /** The menu button: shows the hidden menu, or hides it again; on a phone it opens and closes the drawer. */
  toggle() {
    if (this._hidden) {
      this._giveBack();
      this._shown = true;
      if (menuIsDrawer()) this._askHomeAssistant();
      return;
    }
    if (!menuIsDrawer()) {
      this._hidden = hideMenu();
      if (this._hidden) {
        this._shown = false;
        return;
      }
    }
    this._askHomeAssistant();
  }

  _giveBack() {
    restoreMenu(this._hidden);
    this._hidden = null;
  }

  _askHomeAssistant() {
    this._host.dispatchEvent(new CustomEvent("hass-toggle-menu", { bubbles: true, composed: true }));
  }
}
