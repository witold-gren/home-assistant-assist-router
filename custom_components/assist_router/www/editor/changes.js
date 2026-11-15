// What a draft changes against the file: the items added, removed and changed, and the lines that differ.
// Pure functions.

import { keysAt, readDocument, blockText } from "./source.js";

/** The items of a text (top keys and topics) with their blocks; null when the text does not read as YAML. */
function items(text) {
  const { doc, error } = readDocument(text);
  if (error) return null;
  const out = new Map();
  for (const key of keysAt(doc, [])) if (key !== "topics") out.set(key, blockText(text, [key]));
  for (const key of keysAt(doc, ["topics"])) out.set(`topics/${key}`, blockText(text, ["topics", key]));
  return out;
}

/**
 * The items added, removed and changed between two texts, by their keys (`people`, `topics/weather`); `other` is
 * set when the lines differ in what no item holds (the header of the file, comments between topics).
 */
export function describeChanges(before, after) {
  const result = { added: [], removed: [], changed: [], other: false };
  if (before === after) return result;
  const a = items(before ?? "");
  const b = items(after ?? "");
  if (!a || !b) return { ...result, other: true };
  for (const [key, text] of b) {
    if (!a.has(key)) result.added.push(key);
    else if (a.get(key) !== text) result.changed.push(key);
  }
  for (const key of a.keys()) if (!b.has(key)) result.removed.push(key);
  result.other = !result.added.length && !result.removed.length && !result.changed.length;
  return result;
}

/** The lines of two texts as kept, removed and added; past `limit` cells of the table, a plain swap of the middle. */
export function diffLines(before, after, limit = 4_000_000) {
  const a = before ? before.split("\n") : [];
  const b = after ? after.split("\n") : [];
  let start = 0;
  while (start < a.length && start < b.length && a[start] === b[start]) start += 1;
  let endA = a.length;
  let endB = b.length;
  while (endA > start && endB > start && a[endA - 1] === b[endB - 1]) {
    endA -= 1;
    endB -= 1;
  }
  const head = a.slice(0, start).map((text, index) => ({ kind: "same", text, line: index + 1 }));
  const shift = endB - endA;
  const tail = a.slice(endA).map((text, index) => ({ kind: "same", text, line: endA + index + 1 + shift }));
  const middleA = a.slice(start, endA);
  const middleB = b.slice(start, endB);
  if (middleA.length * middleB.length > limit) {
    return [
      ...head,
      ...middleA.map((text) => ({ kind: "removed", text })),
      ...middleB.map((text, index) => ({ kind: "added", text, line: start + index + 1 })),
      ...tail,
    ];
  }
  const cols = middleB.length + 1;
  const table = new Uint32Array((middleA.length + 1) * cols);
  for (let i = middleA.length - 1; i >= 0; i -= 1) {
    for (let j = middleB.length - 1; j >= 0; j -= 1) {
      table[i * cols + j] =
        middleA[i] === middleB[j] ? table[(i + 1) * cols + j + 1] + 1 : Math.max(table[(i + 1) * cols + j], table[i * cols + j + 1]);
    }
  }
  const middle = [];
  let i = 0;
  let j = 0;
  const line = () => start + j + 1;
  while (i < middleA.length && j < middleB.length) {
    if (middleA[i] === middleB[j]) {
      middle.push({ kind: "same", text: middleA[i], line: line() });
      i += 1;
      j += 1;
    } else if (table[(i + 1) * cols + j] >= table[i * cols + j + 1]) {
      middle.push({ kind: "removed", text: middleA[i] });
      i += 1;
    } else {
      middle.push({ kind: "added", text: middleB[j], line: line() });
      j += 1;
    }
  }
  for (; i < middleA.length; i += 1) middle.push({ kind: "removed", text: middleA[i] });
  for (; j < middleB.length; j += 1) middle.push({ kind: "added", text: middleB[j], line: line() });
  return [...head, ...middle, ...tail];
}

/** Only the changed lines with a few around them, and the number of lines left out between them. */
export function diffHunks(lines, context = 3) {
  const keep = new Set();
  lines.forEach((line, index) => {
    if (line.kind === "same") return;
    for (let near = index - context; near <= index + context; near += 1) keep.add(near);
  });
  const out = [];
  let skipped = 0;
  lines.forEach((line, index) => {
    if (keep.has(index)) {
      if (skipped) out.push({ kind: "skip", count: skipped });
      skipped = 0;
      out.push(line);
    } else skipped += 1;
  });
  if (skipped && out.length) out.push({ kind: "skip", count: skipped });
  return out;
}
