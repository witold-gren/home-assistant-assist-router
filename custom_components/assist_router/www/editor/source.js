// router.yaml as text. Its parts are blocks of lines: the comments right above a key, the key and all that is
// indented under it. A change replaces the lines of one block and leaves every other line as it was, so the
// comments and the layout of the file stay; the YAML library only reads where things are. Pure functions.

import { isMap, isScalar, isSeq, parseDocument } from "../vendor/yaml.js";

/** The document of a text, with the first error the YAML library found in it (null when none). */
// The last texts read, newest last. The editor draws itself on every change of a state in the home and reads the same
// text many times for one picture; the documents are only read, never changed, so one reading serves them all.
const READ_CACHE = new Map();
export const READ_CACHE_SIZE = 8;

export function readDocument(text) {
  const cached = READ_CACHE.get(text);
  if (cached) {
    READ_CACHE.delete(text);
    READ_CACHE.set(text, cached);
    return cached;
  }
  const doc = parseDocument(text, { uniqueKeys: true });
  const error = doc.errors[0];
  const read = { doc, error: error ? errorText(error) : null };
  READ_CACHE.set(text, read);
  if (READ_CACHE.size > READ_CACHE_SIZE) READ_CACHE.delete(READ_CACHE.keys().next().value);
  return read;
}

/** An error of the YAML library in one line, with the line it is on. */
export function errorText(error) {
  const first = String(error.message ?? error).split("\n")[0];
  const line = error.linePos?.[0]?.line;
  return line && !/\bline \d+/.test(first) ? `${first} (line ${line})` : first;
}

const keyName = (key) => String(isScalar(key) ? key.value : key);

/** The pair of a mapping at a path of keys, or null. */
export function pairAt(doc, path) {
  let node = doc.contents;
  let pair = null;
  for (const key of path) {
    if (!isMap(node)) return null;
    pair = node.items.find((item) => keyName(item.key) === key) ?? null;
    if (!pair) return null;
    node = pair.value;
  }
  return pair;
}

/** The keys of the mapping at a path (the top of the file for an empty path), in the order of the file. */
export function keysAt(doc, path) {
  const node = path.length ? pairAt(doc, path)?.value : doc.contents;
  return isMap(node) ? node.items.map((item) => keyName(item.key)) : [];
}

/** The plain value at a path, as JavaScript, or undefined. */
export function valueAt(doc, path) {
  const node = path.length ? pairAt(doc, path)?.value : doc.contents;
  return node && typeof node.toJSON === "function" ? node.toJSON() : (node?.value ?? node ?? undefined);
}

function lineStarts(text) {
  const starts = [0];
  for (let index = text.indexOf("\n"); index !== -1; index = text.indexOf("\n", index + 1)) starts.push(index + 1);
  return starts;
}

function lineOf(starts, offset) {
  let low = 0;
  let high = starts.length - 1;
  while (low < high) {
    const middle = (low + high + 1) >> 1;
    if (starts[middle] <= offset) low = middle;
    else high = middle - 1;
  }
  return low;
}

const indentOf = (line) => line.length - line.trimStart().length;
const isComment = (line) => line.trimStart().startsWith("#");

/**
 * The lines of the block at a path: `start` (inclusive) and `end` (exclusive), the line of the key and its
 * indentation. Null when the path is not in the file or its key does not start a line (a key inside `{ … }`).
 */
export function blockRange(text, path, doc = readDocument(text).doc) {
  const pair = pairAt(doc, path);
  if (!pair?.key?.range) return null;
  const lines = text.split("\n");
  const starts = lineStarts(text);
  const keyLine = lineOf(starts, pair.key.range[0]);
  const indent = pair.key.range[0] - starts[keyLine];
  if (lines[keyLine].slice(0, indent).trim()) return null;
  // Under the key: every line indented deeper; a list may also start at the key's own indentation.
  const listHere = isSeq(pair.value) && !pair.value.flow;
  let end = keyLine + 1;
  for (let index = keyLine + 1; index < lines.length; index += 1) {
    const line = lines[index];
    if (!line.trim()) continue;
    const depth = indentOf(line);
    if (depth > indent || (listHere && depth === indent && line.trimStart().startsWith("-"))) end = index + 1;
    else break;
  }
  // Above the key: the comments right over it at its indentation. Those that open the file are its header.
  let start = keyLine;
  while (start > 0 && isComment(lines[start - 1]) && indentOf(lines[start - 1]) === indent) start -= 1;
  if (start === 0 && keyLine > 0) start = keyLine;
  return { start, end, keyLine, indent };
}

/** The text of the block at a path, without its indentation; null when it has no block of its own. */
export function blockText(text, path) {
  const range = blockRange(text, path);
  if (!range) return null;
  return text
    .split("\n")
    .slice(range.start, range.end)
    .map((line) => (line.trim() ? line.slice(range.indent) : ""))
    .join("\n");
}

const failure = (message) => Object.assign(new Error(message), { yaml: true });

/** A block typed by hand: it must read as YAML and hold one key; its lines, without the empty ones after. */
function blockLines(snippet) {
  const { doc, error } = readDocument(snippet);
  if (error) throw failure(error);
  if (!isMap(doc.contents) || doc.contents.items.length !== 1) throw failure("one_key");
  const lines = snippet.replace(/\s+$/, "").split("\n");
  return { lines, key: keyName(doc.contents.items[0].key) };
}

const indented = (lines, indent) => lines.map((line) => (line.trim() ? " ".repeat(indent) + line : ""));

/** The whole text again, which must read as YAML, and the path of what was changed in it. */
function checked(lines, path) {
  const text = lines.join("\n");
  const { doc, error } = readDocument(text);
  if (error) throw failure(error);
  if (path && !pairAt(doc, path)) throw failure("lost");
  return { text, path };
}

/**
 * The text with the block at a path replaced by a block typed by hand, and the path of that block, renamed when
 * its key was. Throws an error (with `yaml` set) when the new text would not read as YAML.
 */
export function replaceBlock(text, path, snippet) {
  const range = blockRange(text, path);
  if (!range) throw failure("lost");
  const { lines, key } = blockLines(snippet);
  const all = text.split("\n");
  const next = [...all.slice(0, range.start), ...indented(lines, range.indent), ...all.slice(range.end)];
  return checked(next, [...path.slice(0, -1), key]);
}

/**
 * The text without the block at a path. The empty line after it goes too when nothing would be left above it
 * but another empty line or the key of its parent.
 */
export function removeBlock(text, path) {
  const range = blockRange(text, path);
  if (!range) throw failure("lost");
  const all = text.split("\n");
  let { start, end } = range;
  const above = all[start - 1];
  if (end < all.length && !all[end].trim() && (start === 0 || !above.trim() || indentOf(above) < range.indent)) end += 1;
  return checked([...all.slice(0, start), ...all.slice(end)], null).text;
}

/** A key not used yet among the keys of a mapping: the one asked for, or it with _2, _3… */
export function freeKey(doc, parentPath, wanted) {
  const used = new Set(keysAt(doc, parentPath));
  if (!used.has(wanted)) return wanted;
  let number = 2;
  while (used.has(`${wanted}_${number}`)) number += 1;
  return `${wanted}_${number}`;
}

/**
 * The text with a block added as the last child of the mapping at a path, indented as its other children are and
 * after an empty line when they are kept apart by one; and the path of the new block.
 */
export function appendBlock(text, parentPath, snippet) {
  const { doc } = readDocument(text);
  const { lines, key } = blockLines(snippet);
  const all = text.split("\n");
  if (!parentPath.length) {
    const body = all.slice();
    while (body.length && !body[body.length - 1].trim()) body.pop();
    return checked([...body, ...(body.length ? [""] : []), ...lines, ""], [key]);
  }
  const parent = blockRange(text, parentPath, doc);
  const value = pairAt(doc, parentPath)?.value;
  const empty = value == null || (isScalar(value) && value.value == null) || (isMap(value) && !value.items.length);
  if (!parent || (!empty && (!isMap(value) || value.flow))) throw failure("not_a_map");
  const children = keysAt(doc, parentPath);
  let indent = parent.indent + 2;
  let apart = false;
  if (children.length) {
    const first = blockRange(text, [...parentPath, children[0]], doc);
    const last = blockRange(text, [...parentPath, children.at(-1)], doc);
    indent = first?.indent ?? indent;
    apart = Boolean(last && last.start > 0 && !all[last.start - 1].trim());
  }
  // A parent written `topics:` with nothing under it, or `topics: {}`, gets its children under it.
  const head = empty
    ? all[parent.keyLine].replace(/:\s*(\{\s*\}|null|~)?\s*(#.*)?$/, (match, nothing, comment) => (comment ? `: ${comment}` : ":"))
    : all[parent.keyLine];
  const before = [...all.slice(0, parent.keyLine), head, ...all.slice(parent.keyLine + 1, parent.end)];
  const next = [...before, ...(apart ? [""] : []), ...indented(lines, indent), ...all.slice(parent.end)];
  return checked(next, [...parentPath, key]);
}
