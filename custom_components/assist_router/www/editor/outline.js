// The tree of router.yaml: the home (people, family, personas, players, settings), the topics of questions and
// the special topics (control, knowledge, unclear sentences, everything else). Pure functions.

import { isMap } from "../vendor/yaml.js";
import { blockRange, keysAt, pairAt, readDocument, valueAt } from "./source.js";

// The parts of the home, in the order the tree shows them; any other key of the file comes after them.
export const HOME_KEYS = {
  household: "mdi:home-heart",
  people: "mdi:account-multiple",
  family: "mdi:family-tree",
  personas: "mdi:drama-masks",
  music_players: "mdi:music",
  announce_players: "mdi:bullhorn",
  confirm_entities: "mdi:shield-check",
};
// The settings of the router, shown together under one node of the tree.
export const SETTINGS_KEYS = [
  "language",
  "sentences",
  "wikipedia_language",
  "only_exposed",
  "control_model",
  "answer_prompt",
  "summary_prompt",
];
// The node of the settings has no key of its own in the file.
export const SETTINGS_PATH = ["@settings"];
// Learning from what was said: the log of unrecognized commands and the test set (files of their own).
export const LEARN_NODES = { "@unrecognized": "mdi:comment-question-outline", "@tests": "mdi:clipboard-check-outline" };
// The parts whose entries are shown in the tree one by one.
export const NESTED = ["people", "personas", "music_players"];
// The keys of a topic that give it data of the home to answer from.
export const SOURCE_KEYS = ["entities", "fetch", "frigate", "command", "details", "search"];

export const KIND_ICONS = {
  data: "mdi:database-outline",
  control: "mdi:gesture-tap",
  knowledge: "mdi:book-open-variant",
  unclear: "mdi:help-circle-outline",
  other: "mdi:chat-outline",
};

/** What a topic is, as the router treats it: control, knowledge, unclear, other (no data) or data. */
export function topicKind(topic) {
  if (!topic || typeof topic !== "object") return "other";
  if (topic.control) return "control";
  if (topic.unclear) return "unclear";
  if (topic.search) return "knowledge";
  return SOURCE_KEYS.some((key) => topic[key] != null && topic[key] !== "") ? "data" : "other";
}

export const nodeKey = (path) => path.join("/");

/**
 * The tree of a text: groups `home`, `topics`, `special` and `learn`, each with its nodes `{ key, path, name, icon, kind,
 * hint, warn, children, block, missing }`; `block` is false for what has no lines of its own (a key inside `{ … }`).
 * The parts of the home are there even when the file has none yet (`missing`), so a form can fill them in.
 * `error` is the YAML error of the text, and then the tree is empty.
 */
export function buildOutline(text, t = (key) => key) {
  const { doc, error } = readDocument(text);
  const groups = [
    { key: "home", label: t("group_home"), children: [] },
    { key: "topics", label: t("group_topics"), children: [] },
    { key: "special", label: t("group_special"), children: [] },
    { key: "learn", label: t("group_learn"), children: [] },
  ];
  // The nodes of learning read other files, so they are there even when this text is not YAML.
  groups[3].children = Object.entries(LEARN_NODES).map(([key, icon]) => ({
    key,
    path: [key],
    name: key,
    label: t(`key_${key.slice(1)}`, null, key),
    icon,
    block: false,
    children: [],
  }));
  if (error || (doc.contents && !isMap(doc.contents))) return { error: error ?? t("error_not_a_map"), groups };
  const node = (path, extra) => ({
    key: nodeKey(path),
    path,
    name: path.at(-1),
    block: Boolean(blockRange(text, path, doc)),
    children: [],
    ...extra,
  });
  const top = keysAt(doc, []);
  for (const key of Object.keys(HOME_KEYS)) {
    const item = node([key], { icon: HOME_KEYS[key], label: t(`key_${key}`, null, key), missing: !top.includes(key) });
    if (NESTED.includes(key)) {
      item.children = keysAt(doc, [key]).map((child) => node([key, child], { icon: item.icon, label: child }));
    }
    groups[0].children.push(item);
  }
  const settings = node(SETTINGS_PATH, { icon: "mdi:cog-outline", label: t("key_settings", null, "settings"), block: false });
  settings.children = SETTINGS_KEYS.filter((key) => top.includes(key)).map((key) =>
    node([key], { icon: "mdi:tune-variant", label: t(`key_${key}`, null, key) }),
  );
  groups[0].children.push(settings);
  for (const key of top.filter((key) => key !== "topics" && !(key in HOME_KEYS) && !SETTINGS_KEYS.includes(key))) {
    groups[0].children.push(node([key], { icon: "mdi:code-braces", label: key }));
  }
  for (const name of keysAt(doc, ["topics"])) {
    const topic = valueAt(doc, ["topics", name]);
    const kind = topicKind(topic);
    const description = typeof topic?.description === "string" ? topic.description.trim() : "";
    const examples = Array.isArray(topic?.examples) ? topic.examples.length : 0;
    const warn = !description ? t("warn_no_description") : !examples ? t("warn_no_examples") : null;
    const item = node(["topics", name], { icon: KIND_ICONS[kind], label: name, kind, hint: description, examples, warn });
    groups[kind === "data" ? 1 : 2].children.push(item);
  }
  return { error: null, groups, hasTopics: Boolean(pairAt(doc, ["topics"])) };
}

/** Every node of the tree, depth first. */
export function flattenOutline(groups) {
  const out = [];
  const walk = (item) => {
    out.push(item);
    item.children?.forEach(walk);
  };
  groups.forEach(walk);
  return out;
}

/** The tree with only what matches a search (by key, label or description) and the parents of what does. */
export function filterOutline(groups, search) {
  const words = search.trim().toLowerCase().split(/\s+/).filter(Boolean);
  if (!words.length) return groups;
  const matches = (item) => {
    const text = `${item.name ?? ""} ${item.label ?? ""} ${item.hint ?? ""}`.toLowerCase();
    return words.every((word) => text.includes(word));
  };
  const keep = (item) => {
    const children = (item.children ?? []).map(keep).filter(Boolean);
    return matches(item) || children.length ? { ...item, children: matches(item) ? item.children : children } : null;
  };
  return groups.map((group) => ({ ...group, children: group.children.map(keep).filter(Boolean) }));
}
