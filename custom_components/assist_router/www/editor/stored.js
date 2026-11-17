// The browser's own storage (localStorage) for small choices of one device: a private window, blocked site data or a
// full storage throw, and then the choice is simply not remembered.

/** The stored text under a key, or null when there is none or the storage cannot be read. */
export function readStored(key) {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

/** Remember a text under a key; nothing happens when the storage cannot be written. */
export function writeStored(key, value) {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // Not remembered: the editor works the same without it.
  }
}
