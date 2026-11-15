// One value of router.yaml changed the way a form changes it: only the lines of that value are written again, in
// the style the file already uses (a list in brackets or one item per line, a long text folded), and the comments
// around them stay. Values are written as YAML 1.1, which is how the router reads the file ("yes" stays a text).
// Pure functions.

import { Document, isMap, isScalar, isSeq, visit } from "../vendor/yaml.js";
import { appendBlock, blockRange, keysAt, pairAt, readDocument, removeBlock } from "./source.js";

// The longest line written; a longer text is folded, a longer list goes one item per line.
export const LINE_WIDTH = 100;
const FLOW_ITEMS_WIDTH = 72;
// Marks that end or change a text written without quotes inside brackets.
const FLOW_SPECIAL = /[?:,[\]{}#&*!|>'"%@`]|^-|^\s|\s$/;

const failure = (message) => Object.assign(new Error(message), { yaml: true });

const isEmptyNode = (node) =>
  node == null || (isScalar(node) && node.value == null) || ((isMap(node) || isSeq(node)) && !node.items.length);

const lineStarts = (text) => {
  const starts = [0];
  for (let index = text.indexOf("\n"); index !== -1; index = text.indexOf("\n", index + 1)) starts.push(index + 1);
  return starts;
};

const lineOf = (starts, offset) => {
  let line = 0;
  while (line + 1 < starts.length && starts[line + 1] <= offset) line += 1;
  return line;
};

/** A key as YAML writes it: plain when it can be, in quotes when it must. */
export function yamlKey(key) {
  const line = new Document({ [key]: 1 }, { version: "1.1" }).toString();
  return line.slice(0, line.lastIndexOf(":"));
}

const shortList = (node) =>
  node.items.every((item) => isScalar(item) && !String(item.value).includes("\n")) &&
  node.items.reduce((sum, item) => sum + String(item.value).length + 2, 2) <= FLOW_ITEMS_WIDTH;

/**
 * The lines `key: value` for a value. `flow` writes a list in brackets (true) or one item per line (false); left
 * out, a short list of words goes in brackets. A text longer than the line is folded (`>-`), one with line breaks
 * kept (`|-`); `folded` asks for folding anyway.
 */
export function fieldLines(key, value, { flow, folded = false, indentSeq = true, width = LINE_WIDTH } = {}) {
  const doc = new Document({ [key]: value }, { version: "1.1" });
  const top = doc.contents.items[0].value;
  visit(doc, {
    Seq(_, node) {
      node.flow = node === top && flow !== undefined ? flow : shortList(node);
      // In brackets the router's reader (PyYAML) ends a plain text at ? and : too, so such texts go in quotes.
      if (node.flow) {
        for (const item of node.items) {
          if (isScalar(item) && typeof item.value === "string" && FLOW_SPECIAL.test(item.value)) item.type = "QUOTE_DOUBLE";
        }
      }
    },
    Map(_, node) {
      node.flow = false;
    },
    Scalar(_, node) {
      if (typeof node.value !== "string" || node === doc.contents.items[0].key) return;
      if (node.value.includes("\n")) node.type = "BLOCK_LITERAL";
      else if (node === top && (folded || key.length + node.value.length + 2 > width)) node.type = "BLOCK_FOLDED";
    },
  });
  const text = doc.toString({ lineWidth: Math.max(40, width), minContentWidth: 20, indentSeq, flowCollectionPadding: false });
  return text.replace(/\n+$/, "").split("\n");
}

// A comment at the end of the key's line (after a value on that line, or after the colon of a value below it).
function tailComment(line, column) {
  const match = /^\s+#.*$/.exec(line.slice(column));
  return match ? match[0] : "";
}

/**
 * The lines of a list written one item per line, for a new list of texts: items still in it keep their lines and
 * the comments above and beside them; new ones get a line of their own. Null when the list is not one text per
 * line, so the caller writes it whole.
 */
function listLines(lines, starts, range, node, values) {
  if (!node.items.every((item) => isScalar(item) && typeof item.value !== "object" && item.range)) return null;
  const old = [];
  let from = range.keyLine + 1;
  for (const item of node.items) {
    const first = lineOf(starts, item.range[0]);
    if (lineOf(starts, item.range[1]) !== first) return null;
    old.push({ value: String(item.value), lines: lines.slice(from, first + 1), used: false });
    from = first + 1;
  }
  const after = lines.slice(from, range.end);
  const itemLine = old.length ? old[0].lines.at(-1) : null;
  const prefix = itemLine ? itemLine.slice(0, itemLine.indexOf("-") + 1) : `${" ".repeat(range.indent + 2)}-`;
  const out = [];
  for (const value of values) {
    const found = old.find((item) => !item.used && item.value === value);
    if (found) {
      found.used = true;
      out.push(...found.lines);
      continue;
    }
    // A new item in one line; one so long that it would be folded makes the list be written whole.
    const written = fieldLines("x", [value], { flow: false, width: 1000 });
    if (written.length !== 2) return null;
    out.push(`${prefix} ${written[1].trimStart().slice(2)}`);
  }
  return [...out, ...after];
}

/**
 * The text with the value at a path set (written again only when it differs), or taken out when the value is
 * undefined. A key missing so far is added to its mapping, which is made too when missing; a mapping written in
 * one line (`{ … }`) is written out on its lines. Throws an error (with `yaml` set) when the result would not
 * read as YAML or the path goes through something that is not a mapping.
 */
export function setField(text, path, value) {
  const { doc, error } = readDocument(text);
  if (error) throw failure(error);
  if (!path.length) throw failure("not_a_map");
  const key = path.at(-1);
  const parentPath = path.slice(0, -1);
  const pair = pairAt(doc, path);
  const gone = value === undefined;
  if (pair) {
    const range = blockRange(text, path, doc);
    if (range) return gone ? removeBlock(text, path) : replaceValue(text, pair, range, value);
  } else if (gone) {
    return text;
  }
  if (!parentPath.length) return insertTopLevel(text, doc, fieldLines(key, value));
  const parentPair = pairAt(doc, parentPath);
  const parent = parentPair?.value;
  if (parentPair && !isEmptyNode(parent) && !isMap(parent)) throw failure("not_a_map");
  if (parentPair && blockRange(text, parentPath, doc) && (isEmptyNode(parent) || !parent.flow)) {
    return appendBlock(text, parentPath, fieldLines(key, value).join("\n")).text;
  }
  // The mapping is missing or written in one line: it is written whole, with this value in it.
  const whole = isMap(parent) ? parent.toJSON() : {};
  if (gone) delete whole[key];
  else whole[key] = value;
  return setField(text, parentPath, whole);
}

function replaceValue(text, pair, range, value) {
  const node = pair.value;
  if (JSON.stringify(node?.toJSON?.() ?? node?.value ?? null) === JSON.stringify(value)) return text;
  const lines = text.split("\n");
  const starts = lineStarts(text);
  const head = lines[range.keyLine];
  const keyEnd = pair.key.range[1] - starts[range.keyLine];
  const keyText = head.slice(range.indent, keyEnd);
  let body = null;
  if (isSeq(node) && !node.flow && Array.isArray(value) && value.every((item) => typeof item === "string")) {
    const items = listLines(lines, starts, range, node, value);
    if (items) body = [head, ...items];
    if (body && !value.length) body = null;
  }
  if (!body) {
    const style = {
      flow: isSeq(node) ? Boolean(node.flow) : undefined,
      folded: isScalar(node) && node.type === "BLOCK_FOLDED",
      indentSeq: !(isSeq(node) && !node.flow && node.items[0]?.range && lineIndent(lines, starts, node) === range.indent),
      width: LINE_WIDTH - range.indent,
    };
    const valueLine = node?.range ? lineOf(starts, node.range[0]) : range.keyLine;
    const tail =
      valueLine === range.keyLine && node?.range
        ? lineOf(starts, node.range[1]) === range.keyLine
          ? tailComment(head, node.range[1] - starts[range.keyLine])
          : ""
        : tailComment(head, head.indexOf(":", keyEnd) + 1);
    const written = fieldLines("x", value, style);
    written[0] = `${keyText}${written[0].slice(1)}${tail}`;
    body = written.map((line, index) => (index && line.trim() ? " ".repeat(range.indent) + line : line));
    body[0] = " ".repeat(range.indent) + body[0];
  }
  const next = [...lines.slice(0, range.keyLine), ...body, ...lines.slice(range.end)].join("\n");
  const { error } = readDocument(next);
  if (error) throw failure(error);
  return next;
}

const lineIndent = (lines, starts, node) => {
  const line = lines[lineOf(starts, node.items[0].range[0])];
  return line.length - line.trimStart().length;
};

// A new key of the file goes after the last key before `topics` (topics stay at the end), or at the end.
function insertTopLevel(text, doc, lines) {
  const keys = keysAt(doc, []);
  const at = keys.indexOf("topics");
  if (at < 0) return appendBlock(text, [], lines.join("\n")).text;
  const all = text.split("\n");
  let next;
  const previous = at > 0 ? blockRange(text, [keys[at - 1]], doc) : null;
  if (previous) {
    const apart = previous.start > 0 && !all[previous.start - 1].trim();
    next = [...all.slice(0, previous.end), ...(apart ? [""] : []), ...lines, ...all.slice(previous.end)];
  } else {
    const topics = blockRange(text, ["topics"], doc);
    next = [...all.slice(0, topics.start), ...lines, "", ...all.slice(topics.start)];
  }
  const result = next.join("\n");
  const { error } = readDocument(result);
  if (error) throw failure(error);
  return result;
}

/** The text with the key at a path renamed in place, and the new path. Throws `key_taken` or `key_empty`. */
export function renameKey(text, path, key) {
  const { doc, error } = readDocument(text);
  if (error) throw failure(error);
  const name = String(key ?? "").trim();
  if (!name) throw failure("key_empty");
  const next = [...path.slice(0, -1), name];
  if (name === path.at(-1)) return { text, path };
  if (pairAt(doc, next)) throw failure("key_taken");
  const pair = pairAt(doc, path);
  if (!pair?.key?.range) throw failure("lost");
  const [start, end] = pair.key.range;
  const result = text.slice(0, start) + yamlKey(name) + text.slice(end);
  if (readDocument(result).error) throw failure(readDocument(result).error);
  return { text: result, path: next };
}

/**
 * The text with one item of a list set (an index past the end adds it, undefined takes it out). Only the lines of
 * that item are written again, so the comments between the items stay; a list in brackets, or one missing, is
 * written whole.
 */
export function setListItem(text, listPath, index, value) {
  const { doc, error } = readDocument(text);
  if (error) throw failure(error);
  const node = pairAt(doc, listPath)?.value;
  const items = isSeq(node) ? node.toJSON() : [];
  const range = blockRange(text, listPath, doc);
  if (!isSeq(node) || node.flow || !range || !node.items.length || !node.items.every((item) => item?.range)) {
    const next = [...items];
    if (value === undefined) next.splice(index, 1);
    else next[index] = value;
    return setField(text, listPath, next.length ? next : undefined);
  }
  if (index < items.length && JSON.stringify(items[index]) === JSON.stringify(value)) return text;
  if (value === undefined && items.length === 1) return setField(text, listPath, undefined);
  const lines = text.split("\n");
  const starts = lineStarts(text);
  const dash = (item) => {
    const line = lines[lineOf(starts, item.range[0])];
    return line.indexOf("-") >= 0 ? line.indexOf("-") : range.indent + 2;
  };
  // The lines of an item: from its dash to the next item, without the empty lines and comments over the next.
  const span = (at) => {
    const start = lineOf(starts, node.items[at].range[0]);
    let end = at + 1 < node.items.length ? lineOf(starts, node.items[at + 1].range[0]) : range.end;
    const column = dash(node.items[at]);
    while (end - 1 > start && (!lines[end - 1].trim() || (isCommentLine(lines[end - 1]) && indentOfLine(lines[end - 1]) <= column))) {
      end -= 1;
    }
    return { start, end, column };
  };
  const written = (column) => {
    const out = fieldLines("x", [value], { flow: false }).slice(1);
    return out.map((line) => (line.trim() ? " ".repeat(column) + line.slice(2) : line));
  };
  let next;
  if (index >= items.length) {
    const last = span(items.length - 1);
    next = [...lines.slice(0, last.end), ...written(last.column), ...lines.slice(last.end)];
  } else if (value === undefined) {
    // Taken out with the comments right over it, and an empty line left with nothing to keep apart.
    let { start, end, column } = span(index);
    while (start > range.keyLine + 1 && isCommentLine(lines[start - 1]) && indentOfLine(lines[start - 1]) === column) start -= 1;
    const above = lines[start - 1];
    if (end < lines.length && !lines[end].trim() && (!above.trim() || indentOfLine(above) < column)) end += 1;
    next = [...lines.slice(0, start), ...lines.slice(end)];
  } else {
    const item = span(index);
    next = [...lines.slice(0, item.start), ...written(item.column), ...lines.slice(item.end)];
  }
  const result = next.join("\n");
  const check = readDocument(result).error;
  if (check) throw failure(check);
  return result;
}

const isCommentLine = (line) => line.trimStart().startsWith("#");
const indentOfLine = (line) => line.length - line.trimStart().length;
