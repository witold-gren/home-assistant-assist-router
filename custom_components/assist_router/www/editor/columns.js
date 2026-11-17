// Folding the left and the right column (standard section 5): a folded column stays as a narrow rail with a button
// to unfold it, its width before folding comes back, and the choice is kept by the browser (stored.js).
import { readStored, writeStored } from "./stored.js";

// The width of a folded column (px).
export const RAIL = 28;
// A window narrower than this starts with the right column folded.
export const NARROW = 900;

/** The folded columns as kept, or, the first time, the right one folded in a narrow window. */
export function readFolded(key, width = window.innerWidth) {
  try {
    const saved = JSON.parse(readStored(key) ?? "null");
    if (saved && typeof saved === "object") return { left: Boolean(saved.left), right: Boolean(saved.right) };
  } catch {
    // A broken value: as the first time.
  }
  return { left: false, right: width < NARROW };
}

export function writeFolded(key, folded) {
  writeStored(key, JSON.stringify(folded));
}

/** The column a key folds: Ctrl/⌘+B the left one, Ctrl/⌘+Alt+B the right one (by the key's place, any layout). */
export function foldShortcut(event) {
  if (!(event.ctrlKey || event.metaKey) || event.shiftKey || event.code !== "KeyB") return null;
  return event.altKey ? "right" : "left";
}
