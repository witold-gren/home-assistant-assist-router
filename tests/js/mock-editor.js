// The editor's server in memory, as the integration answers: the file, a draft, saving with a history, the
// conflict when the file changed elsewhere. Every message is recorded, so tests can see what the editor sent.

import { isMap, parseDocument } from "/custom_components/assist_router/www/vendor/yaml.js";

export const textHash = (text) => {
  let hash = 0;
  for (const char of text) hash = (Math.imul(hash, 31) + char.charCodeAt(0)) | 0;
  return `h${(hash >>> 0).toString(16)}`;
};

// What the router would say of a text: a mapping with a mapping of topics.
export function checkText(text) {
  const doc = parseDocument(text);
  if (doc.errors.length) return { ok: false, error: doc.errors[0].message.split("\n")[0], topics: [] };
  const topics = doc.get("topics");
  if (!isMap(doc.contents) || !isMap(topics)) return { ok: false, error: "router.yaml: no topics", topics: [] };
  return { ok: true, error: null, topics: topics.items.map((item) => String(item.key.value ?? item.key)) };
}

const failure = (code, message) => Object.assign(new Error(message), { code });

const asList = (value) => (Array.isArray(value) ? value : value == null || value === "" ? [] : [value]);
const glob = (pattern) =>
  new RegExp(`^${pattern.replace(/[.+^${}()|[\]\\]/g, "\\$&").replace(/\*/g, ".*").replace(/\?/g, ".")}$`);

/**
 * The data sources of a topic over states given as Home Assistant gives them (`{ state, attributes }` by entity
 * id), as the router reads them; `services` says which services only read (`read_only`) or change something
 * (`changes`), and `fetched` what each service returns.
 */
export function previewSources(text, name, { states = {}, services = {}, fetched = {}, fetch = false } = {}) {
  const doc = parseDocument(text);
  if (doc.errors.length) throw failure("invalid", doc.errors[0].message.split("\n")[0]);
  const config = doc.toJSON() ?? {};
  const topic = config.topics?.[name];
  if (!topic) throw failure("not_found", "No such topic");
  const ids = Object.keys(states).sort();
  const fits = (id, pattern) => {
    const [ids_, classes] = pattern.split("|");
    return glob(ids_).test(id) && (!classes || classes.split(",").includes(states[id]?.attributes?.device_class));
  };
  const counts = (patterns) =>
    asList(patterns).map((pattern) => {
      const found = ids.filter((id) => (pattern.startsWith("!") ? glob(pattern.slice(1)).test(id) : fits(id, pattern)));
      return { pattern, count: found.length, sample: found.slice(0, 8) };
    });
  // In the order of the patterns, as the router puts them (the first pattern that fits counts).
  const chosen = (patterns) => {
    const all = asList(patterns);
    const order = (id) => all.findIndex((p) => !p.startsWith("!") && fits(id, p));
    return ids
      .filter((id) => !all.some((p) => p.startsWith("!") && glob(p.slice(1)).test(id)) && order(id) >= 0)
      .sort((a, b) => order(a) - order(b) || a.localeCompare(b));
  };
  const label = (id) => states[id]?.attributes?.friendly_name ?? id;
  const matched = chosen(topic.entities);
  const skip = asList(topic.skip_states);
  const lines = matched.filter((id) => !skip.includes(states[id].state)).slice(0, 80).map((id) => `${label(id)}: ${states[id].state}`);
  const details = chosen(topic.details).map(
    (id) => `${label(id)} (stan: ${states[id].state}): ${JSON.stringify(states[id].attributes ?? {})}`,
  );
  const fetchItems = asList(topic.fetch).map((item) => {
    const service = services[item?.action] ?? "missing";
    const targets = chosen(item?.entities);
    return {
      action: item?.action,
      service,
      patterns: counts(item?.entities),
      targets,
      sources: fetch && service === "read_only" && targets.length ? (fetched[item.action] ?? []) : null,
    };
  });
  return {
    entities: {
      patterns: counts(topic.entities),
      matched: matched.length,
      lines,
      limit: 80,
      only_exposed: Boolean(topic.only_exposed ?? config.only_exposed),
      nothing_active: !lines.length && skip.length > 0 && matched.length > 0,
    },
    details: { patterns: counts(topic.details), sources: details },
    fetch: fetchItems,
  };
}

const plain = (text) => String(text ?? "").toLowerCase().replace(/[?!.,]/g, "").replace(/\s+/g, " ").trim();

/**
 * The tester's way of a sentence without models: Home Assistant knows the sentences of `haKnows`; the router
 * chooses the topic one of whose examples is the sentence; `answers` gives the answer of a topic.
 */
export function traceSentence(text, sentence, { states = {}, services = {}, fetched = {}, haKnows = [], answers = {}, compare = null } = {}) {
  const doc = parseDocument(text);
  if (doc.errors.length) throw failure("invalid", doc.errors[0].message.split("\n")[0]);
  const config = doc.toJSON() ?? {};
  const trace = { text: sentence, outcome: null, speech: null };
  if (haKnows.map(plain).includes(plain(sentence))) {
    trace.ha = { match: true, source: "builtin", intent: "HassTurnOn", slots: {}, unmatched: {}, template: "", targets: [], ms: 4 };
    trace.outcome = "ha";
    return trace;
  }
  trace.ha = { match: null, ms: 4 };
  const choose = (topics) =>
    Object.entries(topics ?? {}).find(([, topic]) => asList(topic?.examples).some((example) => plain(example) === plain(sentence)))?.[0] ?? null;
  const name = choose(config.topics);
  trace.router = { model: "demo", ms: 120, topic: name, person: null, people: [], when: null, phrase: null };
  if (compare !== null) trace.saved_topic = choose(parseDocument(compare).toJSON()?.topics);
  if (!name) {
    trace.outcome = "fallback";
    return trace;
  }
  trace.route = { topic: name, person: null, people: [], when: null, phrase: null };
  const topic = config.topics[name] ?? {};
  if (topic.unclear) {
    trace.unclear = { guess: null, ms: 80 };
    trace.outcome = "unclear_repeat";
    return trace;
  }
  if (topic.control) {
    trace.control = { text: sentence, ms: 200, reason: null, plan: { intent: "HassTurnOn", slots: {}, description: sentence, confirm: null, error: null } };
    trace.outcome = "control_execute";
    return trace;
  }
  const preview = previewSources(text, name, { states, services, fetched, fetch: true });
  const sources = [...preview.details.sources, ...preview.fetch.flatMap((item) => item.sources ?? [])];
  trace.data = { command: null, lines: preview.entities.lines, sources, ms: 30 };
  const answer = answers[name] ?? null;
  trace.answer = { model: "demo", messages: [{ role: "system", content: "…" }, { role: "user", content: sentence }], text: answer, ms: 300 };
  trace.outcome = trace.data.lines.length || sources.length ? "answer" : "fallback";
  trace.speech = answer;
  return trace;
}

/** Where a sentence goes on a text: Home Assistant's intent (`haKnows`) or the topic one of whose examples it is. */
export function outcomeOf(text, sentence, haKnows = []) {
  if (haKnows.map(plain).includes(plain(sentence))) return { intent: "HassTurnOn" };
  const topics = parseDocument(text).toJSON()?.topics ?? {};
  const found = Object.entries(topics).find(([, topic]) => asList(topic?.examples).some((example) => plain(example) === plain(sentence)));
  return { topic: found?.[0] ?? null };
}

const passes = (test, outcome) =>
  test.intent ? outcome.intent === test.intent : Boolean(test.topic) && !outcome.intent && outcome.topic === test.topic;

/**
 * The slots of a sentence that a template of Home Assistant matches, or null: `{name}` takes any words, `(a|b)` one
 * of them and `[a]` may be left out. Enough for the demo and the tests, not the whole syntax of HA.
 */
export function templateSlots(template, sentence) {
  const names = [];
  const escape = (text) => text.replace(/[.*+?^$\\/]/g, "\\$&");
  let pattern = "";
  for (const part of plain(template).split(/(\{\w+\}|\(|\)|\[|\]|\|)/).filter(Boolean)) {
    if (/^\{\w+\}$/.test(part)) {
      names.push(part.slice(1, -1));
      pattern += "(.+?)";
    } else if (part === "(") pattern += "(?:";
    else if (part === "[") pattern += "(?:";
    else if (part === "]") pattern += ")?";
    else if (part === ")" || part === "|") pattern += part;
    else pattern += escape(part);
  }
  const found = new RegExp(`^${pattern.replace(/\s+/g, "\\s*")}$`).exec(plain(sentence));
  return found ? Object.fromEntries(names.map((name, index) => [name, found[index + 1]])) : null;
}

/** Whether Home Assistant would read a file of sentences: a mapping with intents, each with data and sentences. */
export function checkSentences(text) {
  const doc = parseDocument(text);
  if (doc.errors.length) return { ok: false, error: doc.errors[0].message.split("\n")[0], intents: [] };
  const intents = doc.toJSON()?.intents;
  if (intents == null || typeof intents !== "object") return { ok: false, error: "intents: must be a mapping", intents: [] };
  for (const [name, spec] of Object.entries(intents)) {
    for (const group of asList(spec?.data)) {
      for (const sentence of asList(group?.sentences)) {
        const open = (sentence.match(/\(/g) ?? []).length;
        const close = (sentence.match(/\)/g) ?? []).length;
        if (open !== close) return { ok: false, error: `${name}: „${sentence}”: Unable to find end of group`, intents: [] };
      }
    }
  }
  return {
    ok: true,
    error: null,
    intents: Object.entries(intents).map(([name, spec]) => ({
      name,
      sentences: asList(spec?.data).reduce((sum, group) => sum + asList(group?.sentences).length, 0),
    })),
  };
}

export function createEditorServer({
  file = "",
  path = "/config/assist/router.yaml",
  draft = null,
  history = [],
  states = {},
  services = {},
  fetched = {},
  haKnows = [],
  answers = {},
  log = [],
  tests = [],
  sentences = [],
  intents = ["HassLightSet", "HassTurnOff", "HassTurnOn"],
  language = "pl",
} = {}) {
  const state = {
    file,
    draft,
    history: structuredClone(history),
    sent: [],
    backup: null,
    log: structuredClone(log),
    hidden: [],
    tests: structuredClone(tests),
    sentences: sentences.map((file) => ({ ...file })),
    reloads: 0,
  };
  const sentenceFile = (file) => ({ ...file, hash: textHash(file.text), check: checkSentences(file.text) });
  let clock = 0;
  const stamp = () => new Date(Date.UTC(2026, 10, 13, 10, 0, clock++)).toISOString();
  const handle = async (message) => {
    state.sent.push(message);
    switch (message.type) {
      case "config/auth/list":
        return [{ id: "admin-id", name: "Tomek" }];
      case "assist_router/editor/load":
        return {
          text: state.file,
          hash: textHash(state.file),
          path,
          check: state.file ? checkText(state.file) : { ok: false, error: "missing", topics: [] },
          draft: state.draft && structuredClone(state.draft),
          history: state.history.map(({ id, at, by, note }) => ({ id, at, by, note })),
          languages: ["pl"],
        };
      case "assist_router/editor/check":
        return checkText(message.text);
      case "assist_router/editor/save_draft":
        state.draft = { text: message.text, base: state.draft?.base ?? message.base, updated_at: stamp(), by: "admin-id" };
        return { updated_at: state.draft.updated_at, base: state.draft.base };
      case "assist_router/editor/discard":
        state.draft = null;
        return null;
      case "assist_router/editor/save": {
        if (!state.draft) throw failure("no_draft", "There is no draft to save");
        const check = checkText(state.draft.text);
        if (!check.ok) throw failure("invalid", check.error);
        if (textHash(state.file) !== message.base && !message.force) {
          throw failure("conflict", "router.yaml was changed elsewhere since the draft began");
        }
        if (state.file) {
          state.history.unshift({ id: `v${state.history.length + 1}`, text: state.file, at: stamp(), by: "admin-id", note: message.note ?? "" });
        }
        state.backup = state.file;
        state.file = state.draft.text;
        state.draft = null;
        return { hash: textHash(state.file), topics: check.topics };
      }
      case "assist_router/editor/history_get": {
        const found = state.history.find((item) => item.id === message.version);
        if (!found) throw failure("not_found", "No such version");
        return { text: found.text, at: found.at, by: found.by };
      }
      case "assist_router/editor/restore": {
        const found = state.history.find((item) => item.id === message.version);
        if (!found) throw failure("not_found", "No such version");
        state.draft = { text: found.text, base: textHash(state.file), updated_at: stamp(), by: "admin-id" };
        return { draft: structuredClone(state.draft) };
      }
      case "assist_router/editor/sources":
        return previewSources(message.text, message.topic, { states, services, fetched, fetch: message.fetch });
      case "assist_router/editor/test":
        return traceSentence(message.text, message.sentence, {
          states,
          services,
          fetched,
          haKnows,
          answers,
          compare: message.compare ? state.file : null,
        });
      case "assist_router/editor/checks": {
        const check = checkText(message.text);
        if (!check.ok) throw failure("invalid", check.error);
        const topics = parseDocument(message.text).toJSON().topics;
        const checks = [];
        for (const [name, topic] of Object.entries(topics)) {
          if (!String(topic?.description ?? "").trim()) checks.push({ level: "warn", code: "no_description", topic: name });
          if (!asList(topic?.examples).length && !topic?.control && !topic?.unclear) {
            checks.push({ level: "warn", code: "no_examples", topic: name });
          }
          const preview = previewSources(message.text, name, { states, services });
          for (const found of [...preview.entities.patterns, ...preview.details.patterns]) {
            if (!found.count && !found.pattern.startsWith("!")) {
              checks.push({ level: "warn", code: "pattern_empty", topic: name, field: "entities", pattern: found.pattern });
            }
          }
          for (const item of preview.fetch) {
            if (item.service !== "read_only") checks.push({ level: item.service === "changes" ? "error" : "warn", code: `fetch_${item.service}`, topic: name, action: item.action });
          }
        }
        return { checks };
      }
      case "assist_router/editor/unrecognized":
        return {
          groups: state.log.map((group) => ({ ...group, hidden: state.hidden.includes(group.key) })),
          rows: state.log.reduce((sum, group) => sum + group.count, 0),
        };
      case "assist_router/editor/unrecognized_hide":
        state.hidden = state.hidden.filter((key) => key !== message.key).concat(message.hidden ? [message.key] : []);
        return { hidden: state.hidden.length };
      case "assist_router/editor/classify":
        return message.sentences.map((sentence) => ({ sentence, ...outcomeOf(message.text, sentence, haKnows) }));
      case "assist_router/editor/tests_load":
        return { tests: structuredClone(state.tests), path: "/config/assist/router_tests.yaml", error: null };
      case "assist_router/editor/tests_save":
        if (message.tests.some((test) => !String(test.sentence ?? "").trim())) throw failure("invalid", "a test needs a sentence");
        state.tests = structuredClone(message.tests);
        return { tests: structuredClone(state.tests) };
      case "assist_router/editor/tests_run": {
        const results = state.tests.map((test) => {
          const draftOutcome = outcomeOf(message.text, test.sentence, haKnows);
          const saved = outcomeOf(state.file, test.sentence, haKnows);
          return { ...test, draft: draftOutcome, ok: passes(test, draftOutcome), saved, ok_saved: passes(test, saved) };
        });
        return {
          results,
          model: "demo",
          ms: 10,
          summary: {
            total: results.length,
            passed: results.filter((r) => r.ok).length,
            failed: results.filter((r) => !r.ok).length,
            fixed: results.filter((r) => r.ok && !r.ok_saved).length,
            broken: results.filter((r) => !r.ok && r.ok_saved).length,
          },
        };
      }
      case "assist_router/editor/sentences_load":
        return { files: state.sentences.map(sentenceFile), languages: [language], language, intents };
      case "assist_router/editor/sentences_save": {
        const check = checkSentences(message.text);
        if (!check.ok) throw failure("invalid", check.error);
        const found = state.sentences.find((file) => file.language === message.language && file.name === message.name);
        if (found && textHash(found.text) !== message.base && !message.force) throw failure("conflict", "The file was changed elsewhere");
        if (found) found.text = message.text;
        else state.sentences.push({ language: message.language, name: message.name, text: message.text });
        state.reloads += 1;
        return { hash: textHash(message.text), check, intents };
      }
      case "assist_router/editor/sentences_delete":
        state.sentences = state.sentences.filter((file) => !(file.language === message.language && file.name === message.name));
        state.reloads += 1;
        return { removed: message.name };
      case "assist_router/editor/sentences_test":
        return message.sentences.map((sentence) => {
          for (const file of state.sentences) {
            const data = parseDocument(file.text).toJSON()?.intents ?? {};
            for (const [intent, spec] of Object.entries(data)) {
              const known = asList(spec?.data).flatMap((group) => asList(group?.sentences));
              for (const template of known) {
                const slots = templateSlots(template, sentence);
                if (slots) return { sentence, match: true, source: "custom", intent, file: `${file.language}/${file.name}`, slots, unmatched: {}, template, targets: [] };
              }
            }
          }
          if (haKnows.map(plain).includes(plain(sentence))) {
            return { sentence, match: true, source: "builtin", intent: "HassTurnOn", file: null, slots: {}, unmatched: {}, template: "", targets: [] };
          }
          return { sentence, match: null };
        });
      case "assist_router/editor/services":
        return Object.keys(services)
          .filter((action) => services[action] === "read_only")
          .sort();
      default:
        throw failure("unknown_command", `Unknown command ${message.type}`);
    }
  };
  return { state, handle };
}
