// Where the "?" of each part of the editor opens the guide (docs/editor.md and docs/editor.pl.md share these anchors;
// tests/test_docs.py checks every one is there in both languages).

// The documentation site (GitHub Pages) with the step-by-step guide to this editor in English and Polish.
export const DOCS_SITE = "https://witold-gren.github.io/home-assistant-assist-router/";

/** The guide to the editor on the documentation site, in the language of Home Assistant, at a chapter. */
export function editorDocsUrl(language, anchor = "") {
  const polish = String(language ?? "").split("-")[0] === "pl";
  return `${DOCS_SITE}${polish ? "pl/" : ""}editor/${anchor ? `#${anchor}` : ""}`;
}

export const DOCS_ANCHORS = {
  screen: "screen",
  topic: "topic",
  learning: "learning",
  tests: "tests",
  command: "command",
  save: "save",
  history: "history",
  parts: "editor",
};

/** The anchor of the chapter about a node of the tree, by its path (nothing chosen: the screen of the editor). */
export function docsAnchorFor(path) {
  const [first] = path ?? [];
  if (!first) return DOCS_ANCHORS.screen;
  if (first === "topics") return DOCS_ANCHORS.topic;
  if (first === "@unrecognized") return DOCS_ANCHORS.learning;
  if (first === "@tests") return DOCS_ANCHORS.tests;
  if (first === "@sentences") return DOCS_ANCHORS.command;
  return DOCS_ANCHORS.parts;
}
