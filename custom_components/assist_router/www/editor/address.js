// The chosen node in the address of the page (#/rooms/0/blocks): a link or a reload opens the editor on it. The node
// named by the address is chosen only once the first state has arrived from the server; until then the address stays.

/** The key of the node named by the address (#/a/b -> "a/b"), or null. */
export function addressKey(hash = window.location.hash) {
  if (!hash.startsWith("#/")) return null;
  try {
    const key = hash.slice(2).split("/").map(decodeURIComponent).join("/");
    return key || null;
  } catch {
    return null;
  }
}

/** The hash for a node key ("" for none). */
export const addressHash = (key) => (key ? `#/${String(key).split("/").map(encodeURIComponent).join("/")}` : "");

/** Put the chosen node in the address without a new step of the browser's history. */
export function writeAddress(key) {
  const hash = addressHash(key);
  if (window.location.hash === hash || (!hash && !window.location.hash)) return;
  const { pathname, search } = window.location;
  window.history.replaceState(window.history.state, "", `${pathname}${search}${hash}`);
}
