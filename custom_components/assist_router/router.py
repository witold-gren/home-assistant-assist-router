"""Question router: a small model (Ollama) picks the topic, HA answers a template sentence.

When the HA agent does not recognize a sentence, the model gets the list of topics and
returns only the topic (JSON). It answers nothing itself, and a short reply is fast
(Bielik Minitron 7B: about 0.5 s). The person, the day and the Wikipedia search term come
from the question text by plain matching - the model need not (and cannot) make them up.
Then:

- a topic with ``command`` - an HA template gives the template sentence (e.g. „jakie są
  jutro wydarzenia”), which the HA agent recognizes as usual; the automation's text is
  the data from which the answer model (optional) writes the answer to the user's
  question - without it the automation text itself is read;
- a topic with ``search: wikipedia`` - a Wikipedia article fragment that the answer
  model summarizes in a few sentences (without the model: the article's first sentences);
- the rest (or when something fails) - the fallback agent as before.

The Ollama connection (address, model, timeout) is in the integration options, and the
topics in the ``/config/assist/router.yaml`` file (no file or address = router disabled).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import datetime
import fnmatch
import json
import logging
from pathlib import Path
import re
from typing import Any

import aiohttp
from homeassistant.components.homeassistant.exposed_entities import async_should_expose
from homeassistant.core import HomeAssistant, SupportsResponse
from homeassistant.helpers import (
    area_registry as ar,
    device_registry as dr,
    entity_registry as er,
    label_registry as lr,
)
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util
import yaml

from .control import text_aliases
from .languages import LANG, available_languages, set_language
from .sources import (
    DAY_CODES,
    MAX_ITEMS,
    WEEK,
    compact,
    day_range,
    fill,
    merge,
    range_bounds,
    render,
)

_LOGGER = logging.getLogger(__name__)

SEARCH_WIKIPEDIA = "wikipedia"
WIKIPEDIA_EXTRA_CHARS = 1000  # intro of each further hit
USER_AGENT = (
    "home-assistant-assist-router (https://github.com/witold-gren/home-assistant-assist-router)"
)


@dataclass(frozen=True)
class Fetch:
    """A service with a response, e.g. calendar.get_events; ``{start}``/``{end}`` in the data
    = the day range from the question."""

    action: str
    entities: tuple[str, ...]
    data: dict[str, Any] = field(default_factory=dict)
    title: str | None = None  # header for the model, e.g. „Prognoza godzinowa”
    limit: int = MAX_ITEMS  # most list items (e.g. 24 hours of forecast)
    merge: str | None = None  # list to merge from all entities, e.g. events


@dataclass(frozen=True)
class Topic:
    name: str
    description: str
    examples: tuple[str, ...] = ()
    command: str | None = None
    search: str | None = None
    entities: tuple[str, ...] = ()  # entity_id patterns (fnmatch), e.g. sensor.volvo_*
    skip_states: tuple[str, ...] = ()  # skipped states, e.g. off - players that are off
    only_exposed: bool | None = None  # overrides the top-of-file setting for this topic
    # unavailable entities as „niedostępne” instead of skipping („czy lustro jest włączone?”)
    unavailable: bool = False
    control: bool = False  # control command topic (parsing into an HA intent)
    # a meaningless sentence (speech recognition error): guess what was said, and ask
    unclear: bool = False
    details: tuple[str, ...] = ()  # entity patterns whose attributes go to the model
    fetch: tuple[Fetch, ...] = ()  # services with a response
    days: str | None = None  # day code when the question gives none (date filter), e.g. today
    drop: frozenset[str] = frozenset()  # attribute keys skipped in this topic
    # speaker data also without „mam”/„moje” („Dzień dobry”); a parent - theirs and children's
    personal: bool = False
    answer_hint: str = ""  # extra instruction for the answer model in this topic
    answer_tokens: int = 0  # a longer answer (e.g. a day summary); 0 = default
    # HA's answer to the `command` template sentence read verbatim, without the answer model
    # (e.g. news in a fixed layout)
    verbatim: bool = False
    # speaker-dependent instructions: person key, girl/boy, child/parent, unknown
    answer_hints: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class OllamaSettings:
    """From the integration options."""

    url: str
    model: str
    timeout: float
    keep_alive: int  # minutes; -1 = model always in memory
    # Context (tokens). Ollama loads the model with the context from the request - a value
    # different from the previous request (e.g. HA agent with the same model) = reload.
    num_ctx: int = 4096


@dataclass(frozen=True)
class Person:
    name: str  # form for template sentences, e.g. „Ola”
    pattern: re.Pattern[str]  # word start in the question, e.g. „kasi|katarz”
    speaker: str = ""  # voice identifier in Assist Speaker ID (defaults to the person key)
    # this person's entities (entity_id patterns, e.g. their calendar): skipped when
    # the question is about another person
    owns: tuple[str, ...] = ()
    room: str | None = None  # their room: „w moim pokoju” from this person = this area
    # Home Assistant labels (id or name) marking this person's entities - set in the HA UI
    labels: tuple[str, ...] = ()


@dataclass(frozen=True)
class Family:
    """Who is a parent, who a child, who a man - „brat”, „córka” relative to the speaker."""

    parents: tuple[str, ...] = ()
    children: tuple[str, ...] = ()
    men: frozenset[str] = frozenset()


@dataclass(frozen=True)
class RouterConfig:
    """From the router.yaml file."""

    household: str
    people: dict[str, Person]
    topics: dict[str, Topic]
    sentences: int
    wikipedia_language: str
    answer_prompt: str = ""
    summary_prompt: str = ""
    only_exposed: bool = False  # topic entities only from those exposed to Assist
    control_model: str = "router"  # which model parses commands: router or answer
    # control: always ask (entity_id patterns or names), e.g. fridge, servers
    confirm_entities: tuple[str, ...] = ()
    # „puść …”: area -> players in order (first available)
    music_players: dict[str, tuple[str, ...]] = field(default_factory=dict)
    family: Family = field(default_factory=Family)
    # announcements (intercom): players other than satellites, e.g. HomePods
    announce_players: tuple[str, ...] = ()


def polish_now(now: datetime) -> str:
    """The current date and time for the prompt (language pack)."""
    return LANG.format_now(now)


def answer_messages(
    config: RouterConfig,
    now: datetime,
    data: str,
    question: str,
    speaker: str | None = None,
    hint: str = "",
) -> list[dict[str, str]]:
    """Messages for the answer model: data from HA + the user's question.

    ``speaker`` - name of the recognized speaker: „mam”, „moje” in the question mean them.
    """
    system = (config.answer_prompt or LANG.ANSWER_PROMPT).format(
        household=config.household, now=polish_now(now), sentences=config.sentences
    )
    if speaker:
        system += "\n" + LANG.ASKED_BY.format(speaker=speaker)
    if hint:
        system += f"\n{hint}"
    return [
        {"role": "system", "content": f"{system}\n{LANG.DATA_HEADER}\n{data}"},
        {"role": "user", "content": question},
    ]


def summary_messages(config: RouterConfig, article: str, question: str) -> list[dict[str, str]]:
    """Messages for the answer model: article fragment + the user's question."""
    sentences = LANG.format_sentences(config.sentences)
    system = (config.summary_prompt or LANG.SUMMARY_PROMPT).format(
        household=config.household, now="", sentences=sentences
    )
    return [
        {"role": "system", "content": f"{system}\n{LANG.ARTICLE_HEADER}\n{article}"},
        {"role": "user", "content": question},
    ]


@dataclass(frozen=True)
class Route:
    topic: str
    person: str | None
    when: str | None
    phrase: str | None
    people: tuple[str, ...] = ()  # all people from the question, in order


def _parse_fetch(topic: str, raw: Any) -> Fetch:
    if not isinstance(raw, dict) or "." not in str(raw.get("action", "")):
        raise ValueError(f"router.yaml: topic '{topic}': fetch needs 'action: domain.service'")
    entities = raw.get("entities") or ()
    return Fetch(
        action=str(raw["action"]),
        entities=tuple(str(e) for e in ([entities] if isinstance(entities, str) else entities)),
        data=dict(raw.get("data") or {}),
        title=str(raw["title"]) if raw.get("title") else None,
        limit=int(raw.get("limit") or MAX_ITEMS),
        merge=str(raw["merge"]) if raw.get("merge") else None,
    )


def parse_config(data: Any) -> RouterConfig:
    """Configuration from YAML; ValueError with a description when something is missing."""
    if not isinstance(data, dict):
        raise ValueError("router.yaml must be a mapping")
    raw_topics = data.get("topics")
    if not raw_topics:
        raise ValueError("router.yaml: missing 'topics'")
    if not isinstance(raw_topics, dict):
        raise ValueError("router.yaml: 'topics' must be a mapping")
    topics: dict[str, Topic] = {}
    for name, raw in raw_topics.items():
        raw = raw or {}
        if not isinstance(raw, dict):
            raise ValueError(f"router.yaml: topic '{name}' must be a mapping")
        search = raw.get("search")
        if search not in (None, SEARCH_WIKIPEDIA):
            raise ValueError(f"router.yaml: topic '{name}': unknown search '{search}'")
        topics[str(name)] = Topic(
            name=str(name),
            description=str(raw.get("description", "")),
            examples=tuple(str(e) for e in raw.get("examples") or ()),
            command=str(raw["command"]).strip() if raw.get("command") else None,
            search=search,
            entities=tuple(str(e) for e in raw.get("entities") or ()),
            skip_states=tuple(str(e) for e in raw.get("skip_states") or ()),
            only_exposed=raw.get("only_exposed"),
            unavailable=bool(raw.get("unavailable", False)),
            control=bool(raw.get("control", False)),
            unclear=bool(raw.get("unclear", False)),
            details=tuple(str(e) for e in raw.get("details") or ()),
            fetch=tuple(_parse_fetch(name, f) for f in raw.get("fetch") or ()),
            days=_day_code(name, raw.get("days")),
            drop=frozenset(str(k) for k in raw.get("drop") or ()),
            personal=bool(raw.get("personal", False)),
            answer_hint=" ".join(str(raw.get("answer_hint") or "").split()),
            answer_tokens=int(raw.get("answer_tokens") or 0),
            verbatim=bool(raw.get("verbatim", False)),
            answer_hints={
                str(k): " ".join(str(v).split()) for k, v in (raw.get("answer_hints") or {}).items()
            },
        )
    raw_people = data.get("people") or {}
    if not isinstance(raw_people, dict):
        raise ValueError("router.yaml: 'people' must be a mapping")
    people: dict[str, Person] = {}
    for key, raw in raw_people.items():
        # „ola: Ola” or „ola: {name: Ola, match: "ol(a|i)|aleksandr", speaker: ola,
        #                       owns: [calendar.kalendarz_ola], labels: [ola], room: Pokój Oli}”
        raw = raw if isinstance(raw, dict) else {"name": raw}
        name = str(raw.get("name") or key)
        match = str(raw.get("match") or re.escape(name.lower()[:4]))
        try:
            pattern = re.compile(rf"\b(?:{match})", re.IGNORECASE)
        except re.error as err:
            raise ValueError(f"router.yaml: person '{key}': bad match: {err}") from err
        speaker = str(raw.get("speaker") or key)
        owns = raw.get("owns") or ()
        owns = (owns,) if isinstance(owns, str) else tuple(str(p) for p in owns)
        room = str(raw["room"]) if raw.get("room") else None
        labels = raw.get("labels") or ()
        labels = (labels,) if isinstance(labels, str) else tuple(str(x) for x in labels)
        people[str(key)] = Person(
            name=name,
            pattern=pattern,
            speaker=speaker,
            owns=owns,
            room=room,
            labels=tuple(label.casefold() for label in labels),
        )
    language = data.get("language")
    if language and not set_language(str(language)):
        raise ValueError(
            f"router.yaml: no language pack '{language}' (available: {available_languages()})"
        )
    return RouterConfig(
        household=str(data.get("household", "")),
        people=people,
        topics=topics,
        sentences=int(data.get("sentences", 4)),
        wikipedia_language=str(data.get("wikipedia_language") or LANG.WIKIPEDIA_LANGUAGE),
        answer_prompt=str(data.get("answer_prompt") or ""),
        only_exposed=bool(data.get("only_exposed", False)),
        control_model="answer" if data.get("control_model") == "answer" else "router",
        summary_prompt=str(data.get("summary_prompt") or ""),
        confirm_entities=tuple(str(p) for p in data.get("confirm_entities") or ()),
        music_players={
            str(area): tuple(str(p) for p in (players if isinstance(players, list) else [players]))
            for area, players in (data.get("music_players") or {}).items()
        },
        family=_parse_family(data.get("family") or {}, people),
        announce_players=tuple(str(p) for p in data.get("announce_players") or ()),
    )


def _day_code(topic: str, value: Any) -> str | None:
    """`days:` of a topic as a day code; the language pack's names are accepted too."""
    if value in (None, ""):
        return None
    code = LANG.DAY_ALIASES.get(str(value), str(value))
    if code not in DAY_CODES and not (code.isdigit() and int(code) > 0):
        raise ValueError(f"router.yaml: topic '{topic}': unknown days '{value}'")
    return code


def _parse_family(raw: dict[str, Any], people: dict[str, Person]) -> Family:
    def keys(field_name: str) -> tuple[str, ...]:
        value = raw.get(field_name) or ()
        found = tuple(str(k) for k in ([value] if isinstance(value, str) else value))
        unknown = [k for k in found if k not in people]
        if unknown:
            raise ValueError(f"router.yaml: family.{field_name}: unknown people {unknown}")
        return found

    return Family(keys("parents"), keys("children"), frozenset(keys("men")))


class RouterConfigFile:
    """The router.yaml file, read again when it changes (no HA restart)."""

    def __init__(self, hass: HomeAssistant, path: Path) -> None:
        self._hass = hass
        self.path = path
        self._mtime: float | None = None
        self._config: RouterConfig | None = None

    async def async_get(self) -> RouterConfig | None:
        return await self._hass.async_add_executor_job(self._load)

    def _load(self) -> RouterConfig | None:
        try:
            mtime = self.path.stat().st_mtime
        except FileNotFoundError:
            self._mtime, self._config = None, None
            return None
        if mtime != self._mtime:
            self._mtime = mtime
            try:
                with self.path.open(encoding="utf-8") as handle:
                    self._config = parse_config(yaml.safe_load(handle))
            except (OSError, ValueError, yaml.YAMLError) as err:
                _LOGGER.warning("Router disabled, invalid %s: %s", self.path, err)
                self._config = None
        return self._config


def build_system_prompt(config: RouterConfig) -> str:
    topics = "; ".join(
        f"{t.name} ({t.description})" if t.description else t.name for t in config.topics.values()
    )
    examples = "; ".join(
        f'"{example}" -> {t.name}' for t in config.topics.values() for example in t.examples
    )
    return LANG.classifier_prompt(config.household, topics, examples)


def build_schema(config: RouterConfig) -> dict[str, Any]:
    # Only the topic: with several fields the small model guesses the person and the day.
    return {
        "type": "object",
        "properties": {LANG.TOPIC_KEY: {"type": "string", "enum": list(config.topics)}},
        "required": [LANG.TOPIC_KEY],
    }


def build_request(ollama: OllamaSettings, config: RouterConfig, text: str) -> dict[str, Any]:
    return {
        "model": ollama.model,
        "stream": False,
        "keep_alive": f"{ollama.keep_alive}m" if ollama.keep_alive >= 0 else -1,
        "format": build_schema(config),
        "options": {"temperature": 0, "num_predict": 30, "num_ctx": ollama.num_ctx},
        "messages": [
            {"role": "system", "content": build_system_prompt(config)},
            {"role": "user", "content": text},
        ],
    }


def template_variables(config: RouterConfig, route: Route, text: str) -> dict[str, Any]:
    """Variables of a topic's `command` template: who, person, people, when, text.

    The language pack adds its own names of the same variables for older router.yaml files
    (Polish: kto, osoba, osoby, kiedy, tekst); the old day variable gets the pack's day name.
    """
    variables: dict[str, Any] = {
        "who": route.person,
        "person": config.people[route.person].name if route.person else None,
        "people": [config.people[key].name for key in route.people],
        "when": route.when,
        "text": text,
    }
    aliases = LANG.COMMAND_VARIABLE_ALIASES
    variables |= {alias: variables[name] for name, alias in aliases.items()}
    if route.when and "when" in aliases:
        day_names = {code: name for name, code in LANG.DAY_ALIASES.items()}
        variables[aliases["when"]] = day_names.get(route.when, route.when)
    return variables


def find_people(config: RouterConfig, text: str) -> list[str]:
    """Keys of the people named in the question, in the order spoken („Ola i Kuba”)."""
    found = [
        (match.start(), key)
        for key, person in config.people.items()
        if (match := person.pattern.search(text))
    ]
    return [key for _, key in sorted(found)]


def find_person(config: RouterConfig, text: str) -> str | None:
    """Key of the person named in the question (the first from the start) or None."""
    people = find_people(config, text)
    return people[0] if people else None


def speaker_person(config: RouterConfig, speaker: str | None) -> str | None:
    """router.yaml person key for a voice identifier from Assist Speaker ID."""
    if not speaker:
        return None
    return next((key for key, person in config.people.items() if person.speaker == speaker), None)


def apply_speaker(config: RouterConfig, route: Route, text: str, speaker: str | None) -> Route:
    """A question without a name but in the 1st person concerns the recognized speaker.

    A name in the question always wins („jakie zajęcia ma Kasia”); a question without the
    1st person („jaki jest plan lekcji”) stays for everyone.
    """
    key = speaker_person(config, speaker)
    if key is None or route.people or not LANG.FIRST_PERSON.search(text):
        return route
    return replace(route, person=key, people=(key,))


def entity_owners(
    config: RouterConfig, entity_id: str, labels: frozenset[str] = frozenset()
) -> set[str]:
    """People an entity belongs to: their ``owns`` patterns match it or it has one of their
    ``labels`` (HA labels, see ``entity_labels``)."""
    return {
        key
        for key, person in config.people.items()
        if any(fnmatch.fnmatchcase(entity_id, pattern) for pattern in person.owns)
        or labels & set(person.labels)
    }


def owned_by_others(
    config: RouterConfig,
    people: tuple[str, ...],
    entity_id: str,
    labels: frozenset[str] = frozenset(),
) -> bool:
    """The entity belongs (``owns`` or ``labels``) only to people other than those asked about.

    Without a person in the question (and without a recognized speaker) nothing is skipped;
    entities owned by nobody (e.g. the family calendar) are always taken.
    """
    if not people:
        return False
    owners = entity_owners(config, entity_id, labels)
    return bool(owners) and not owners & set(people)


def entity_labels(hass: HomeAssistant, entity_id: str) -> frozenset[str]:
    """Ids and names (case-folded) of the HA labels of an entity."""
    entry = er.async_get(hass).async_get(entity_id)
    if entry is None or not entry.labels:
        return frozenset()
    registry = lr.async_get(hass)
    names = {
        label.name for label_id in entry.labels if (label := registry.async_get_label(label_id))
    }
    return frozenset(x.casefold() for x in (*entry.labels, *names))


def with_speaker_room(config: RouterConfig, text: str, speaker: str | None) -> str:
    """„Zgaś światło w moim pokoju” from Kasia -> „Zgaś światło w Pokój Dziewczyn” (``room``)."""
    key = speaker_person(config, speaker)
    room = config.people[key].room if key else None
    if not room or not LANG.MY_ROOM.search(text):
        return text
    return LANG.MY_ROOM.sub(LANG.in_room(room), text, count=1)


def relatives(config: RouterConfig, text: str, speaker: str | None) -> list[str]:
    """People from family terms in the question, relative to the speaker, in the order spoken.

    „Gdzie jest mój brat?” from Kasia = Jan; „moja córka” from Tomek = all daughters.
    Without a speaker, without ``family`` or when the term does not fit the speaker (a child
    asking about a „syn”) - an empty list.
    """
    key = speaker_person(config, speaker)
    family = config.family
    if key is None or not (family.parents or family.children):
        return []
    siblings = [c for c in family.children if c != key] if key in family.children else []
    kids = list(family.children) if key in family.parents else []
    groups = {
        "brother": [c for c in siblings if c in family.men],
        "sister": [c for c in siblings if c not in family.men],
        "siblings": siblings,
        "son": [c for c in kids if c in family.men],
        "daughter": [c for c in kids if c not in family.men],
        "children": kids,
    }
    found: list[tuple[int, int, str]] = []  # (position in the question, order in family, person)
    for name, pattern in LANG.RELATIONS:
        if match := pattern.search(text):
            found.extend((match.start(), i, k) for i, k in enumerate(groups[name]))
    out: list[str] = []
    for _, _, k in sorted(found):
        if k not in out:
            out.append(k)
    return out


def apply_relatives(config: RouterConfig, route: Route, text: str, speaker: str | None) -> Route:
    """Adds people from family terms to people from names (e.g. „moja siostra i Jan”)."""
    extra = [k for k in relatives(config, text, speaker) if k not in route.people]
    if not extra:
        return route
    people = (*route.people, *extra)
    return replace(route, person=people[0], people=people)


def apply_personal(config: RouterConfig, route: Route, speaker: str | None) -> Route:
    """Personal topic (``personal``): without a person in the question - the speaker's data,
    and for a parent also their children's („Jak wygląda mój dzień?” from mom - her plan
    and a summary about the children).

    Unknown speaker - no filter (everyone's data).
    """
    key = speaker_person(config, speaker)
    if key is None or route.people:
        return route
    people = (key, *(config.family.children if key in config.family.parents else ()))
    return replace(route, person=key, people=people)


def hint_for(config: RouterConfig, topic: Topic, speaker: str | None) -> str:
    """Speaker-dependent instruction for the answer model (``answer_hints``).

    Order: person key, ``girl``/``boy`` (children), ``child``/``parent``, ``unknown``
    (speaker not recognized), and finally the shared ``answer_hint``. A simple instruction
    for one person works more reliably than one long one with conditions like "if a
    child..., if a parent...".
    """
    hints = topic.answer_hints
    key = speaker_person(config, speaker)
    family = config.family
    if key is None:
        order = ["unknown"]
    else:
        order = [key]
        if key in family.children:
            order += ["boy" if key in family.men else "girl", "child"]
        elif key in family.parents:
            order += ["parent"]
    return next((hints[k] for k in order if hints.get(k)), topic.answer_hint)


def find_when(text: str) -> str | None:
    lowered = text.lower()
    return next((when for when, pattern in LANG.WHEN_PATTERNS if re.search(pattern, lowered)), None)


def search_phrase(text: str) -> str | None:
    """Encyclopedia term: the question without „kim był”, „co to jest” and final punctuation."""
    phrase = LANG.QUESTION_PREFIX.sub("", text.strip().rstrip("?.!").strip())
    return " ".join(phrase.split()) or None


def parse_route(config: RouterConfig, content: str, text: str) -> Route | None:
    """Topic from the model's JSON + person, day and term from the text; None on bad JSON."""
    try:
        data = json.loads(content)
    except ValueError:
        return None
    if not isinstance(data, dict) or data.get(LANG.TOPIC_KEY) not in config.topics:
        return None
    topic = config.topics[data[LANG.TOPIC_KEY]]
    people = find_people(config, text)
    return Route(
        topic=topic.name,
        person=people[0] if people else None,
        people=tuple(people),
        when=find_when(text),
        phrase=search_phrase(text) if topic.search else None,
    )


async def async_chat(
    hass: HomeAssistant, ollama: OllamaSettings, body: dict[str, Any]
) -> str | None:
    """Content of the Ollama answer or None (error, timeout).

    Without "thinking" (Qwen, Gemma) - time matters; a model without this option (400)
    gets the same request without it.
    """
    session = async_get_clientsession(hass)
    try:
        async with asyncio.timeout(ollama.timeout):
            for request in ({**body, "think": False}, body):
                async with session.post(f"{ollama.url}/api/chat", json=request) as resp:
                    if resp.status == 400 and "think" in request:
                        continue
                    resp.raise_for_status()
                    result = await resp.json()
                    return str((result.get("message") or {}).get("content", ""))
    except TimeoutError:
        _LOGGER.warning("Model %s did not answer within %s s", ollama.model, ollama.timeout)
    except (aiohttp.ClientError, ValueError) as err:
        _LOGGER.warning("Model %s failed: %s", ollama.model, err)
    return None


async def async_classify(
    hass: HomeAssistant, ollama: OllamaSettings, config: RouterConfig, text: str
) -> Route | None:
    """Question topic from the model or None (error, timeout, bad answer)."""
    content = await async_chat(hass, ollama, build_request(ollama, config, text))
    if content is None:
        return None
    route = parse_route(config, content, text)
    if route is None:
        _LOGGER.warning("Router model %s returned an unusable answer: %s", ollama.model, content)
    return route


async def async_generate(
    hass: HomeAssistant, ollama: OllamaSettings, messages: list[dict[str, str]], max_tokens: int
) -> str | None:
    """The answer model's answer (one line of text) or None."""
    body = {
        "model": ollama.model,
        "stream": False,
        "keep_alive": f"{ollama.keep_alive}m" if ollama.keep_alive >= 0 else -1,
        "options": {"temperature": 0.2, "num_predict": max_tokens, "num_ctx": ollama.num_ctx},
        "messages": messages,
    }
    content = await async_chat(hass, ollama, body)
    text = " ".join((content or "").split())
    return text or None


async def async_preload(hass: HomeAssistant, ollama: OllamaSettings) -> None:
    """Load the model into memory (the first load takes a dozen or so seconds)."""
    body = {
        "model": ollama.model,
        "keep_alive": f"{ollama.keep_alive}m" if ollama.keep_alive >= 0 else -1,
        "options": {"num_ctx": ollama.num_ctx},
    }
    session = async_get_clientsession(hass)
    try:
        async with asyncio.timeout(PRELOAD_TIMEOUT):
            async with session.post(f"{ollama.url}/api/generate", json=body) as resp:
                resp.raise_for_status()
                await resp.read()
    except (TimeoutError, aiohttp.ClientError) as err:
        _LOGGER.warning("Could not preload model %s: %r", ollama.model, err)
    else:
        _LOGGER.debug("Model %s loaded", ollama.model)


PRELOAD_TIMEOUT = 180


async def async_list_models(hass: HomeAssistant, url: str) -> list[str]:
    """Models available in Ollama (for the options list); connection error -> exception."""
    session = async_get_clientsession(hass)
    async with asyncio.timeout(10):
        async with session.get(f"{url.rstrip('/')}/api/tags") as resp:
            resp.raise_for_status()
            body = await resp.json()
    return sorted(m["name"] for m in body.get("models", []) if m.get("name"))


def clean_extract(text: str, sentences: int) -> str | None:
    """Start of the article to read: no pronunciation, at most ``sentences`` sentences."""
    text = " ".join(LANG.PRONUNCIATION.sub("", text).split())
    if not text or any(marker in text[:200] for marker in LANG.DISAMBIGUATION):
        return None
    parts = LANG.SENTENCE_END.split(text)
    return " ".join(parts[:sentences])


# How much article text the model gets to summarize (intro + start of the body).
WIKIPEDIA_CHARS = 4000
_HEADING = re.compile(r"^=+\s*(.*?)\s*=+$", re.MULTILINE)
# footnotes and cross-references: [a], [12], [patrz niżej], [potrzebny przypis]
_FOOTNOTE = re.compile(r"\[[^\[\]]{1,25}\]")


def clean_article(text: str, chars: int = WIKIPEDIA_CHARS) -> str:
    """Article text to summarize: no pronunciation or headings, cut at a sentence end."""
    text = _HEADING.sub(lambda m: f"{m.group(1)}.", text)
    text = " ".join(_FOOTNOTE.sub("", LANG.PRONUNCIATION.sub("", text)).split())
    if len(text) <= chars:
        return text
    cut = text[:chars]
    end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    return cut[: end + 1] if end > 0 else cut


def title_matches(phrase: str, title: str) -> bool:
    """Whether the article concerns the term: a shared start (4 letters) of some word.

    The search always finds something, also for Whisper garble
    („Ile kaw dzisiaj wypiłem” -> „Tonpress”) - we do not read such an article.
    """
    stems = {word[:4] for word in re.findall(r"\w+", phrase.lower()) if len(word) >= 4}
    return any(word[:4] in stems for word in re.findall(r"\w+", title.lower()) if len(word) >= 4)


ENTITY_LIMIT = 80
FETCH_TIMEOUT = 10  # s per service with a response (cloud calendars can be slow)


def _pattern_index(state, patterns: tuple[str, ...]) -> int | None:
    """Index of the first matching pattern: `domain.*` or `domain.*|class1,class2`
    (only sensors of those kinds); None when none matches or the entity is
    excluded by a `!` pattern, e.g. `!light.ipad_*`."""
    if any(fnmatch.fnmatchcase(state.entity_id, p[1:]) for p in patterns if p.startswith("!")):
        return None
    for index, pattern in enumerate(patterns):
        if pattern.startswith("!"):
            continue
        glob, _, classes = pattern.partition("|")
        if not fnmatch.fnmatchcase(state.entity_id, glob):
            continue
        if classes and (state.attributes.get("device_class") or "") not in classes.split(","):
            continue
        return index
    return None


def _match(state, patterns: tuple[str, ...]) -> bool:
    return _pattern_index(state, patterns) is not None


def by_pattern(states, patterns: tuple[str, ...]) -> list:
    """Entities matching the patterns in their router.yaml order (more important first -
    the entity limit will not cut off e.g. people because of dozens of motion sensors)."""
    found = [(i, s.entity_id, s) for s in states if (i := _pattern_index(s, patterns)) is not None]
    return [s for _, _, s in sorted(found, key=lambda f: f[:2])]


def _extras(state) -> str:
    """The most important attributes in brackets (language pack)."""
    parts = LANG.attribute_parts(state.domain, state.state, state.attributes)
    if state.domain == "binary_sensor":
        minutes = int((dt_util.utcnow() - state.last_changed).total_seconds() // 60)
        parts.append(LANG.minutes_ago(minutes))
    return f" ({', '.join(parts)})" if parts else ""


def entity_lines(
    hass: HomeAssistant,
    patterns: tuple[str, ...],
    only_exposed: bool = False,
    skip_states: tuple[str, ...] = (),
    skip: Callable[[str], bool] | None = None,
    unavailable: bool = False,
) -> list[str]:
    """States of matching entities as lines „Nazwa (inaczej: alias) [pokój]: stan”.

    The router.yaml patterns decide what goes to the model; ``only_exposed`` additionally
    limits it to entities exposed to Assist. Entities without a value (unknown/unavailable)
    - e.g. car lights reported only while driving - and states from ``skip_states`` (e.g.
    players that are off) are left out. ``unavailable`` - unavailable entities stay as
    „niedostępne”, so the model does not answer „nie mam informacji”. Aliases from the
    entity registry: the question may use a different name than HA („lustro”).
    """
    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)
    area_reg = ar.async_get(hass)
    lines = []
    for state in by_pattern(hass.states.async_all(), patterns):
        if only_exposed and not async_should_expose(hass, "conversation", state.entity_id):
            continue
        if skip is not None and skip(state.entity_id):
            continue  # e.g. an entity of a person other than the one asked about
        missing = state.state == "unavailable" and unavailable
        if (
            state.state in ("unknown", "", *(() if missing else ("unavailable",)))
            or state.state in skip_states
        ):
            continue
        value = state.state
        if missing:
            value = LANG.UNAVAILABLE
        elif state.domain == "binary_sensor" and value in ("on", "off"):
            pair = LANG.BINARY_STATES.get(state.attributes.get("device_class") or "")
            value = (pair[0] if value == "on" else pair[1]) if pair else LANG.STATES[value]
        else:
            value = LANG.STATES.get(value, value)
        unit = "" if missing else state.attributes.get("unit_of_measurement") or ""
        entry = ent_reg.async_get(state.entity_id)
        area_id = entry.area_id if entry else None
        if entry and not area_id and entry.device_id:
            device = dev_reg.async_get(entry.device_id)
            area_id = device.area_id if device else None
        area = area_reg.async_get_area(area_id) if area_id else None
        where = f" [{area.name}]" if area and area.name.lower() not in state.name.lower() else ""
        aliases = sorted(text_aliases(entry.aliases)) if entry else []
        name = f"{state.name}{f' ({LANG.ALIASES}: ' + ', '.join(aliases) + ')' if aliases else ''}"
        extras = "" if missing else _extras(state)
        lines.append(f"{name}{where}: {value}{' ' + unit if unit else ''}{extras}")
        if len(lines) >= ENTITY_LIMIT:
            break
    return lines


async def async_todo_lines(
    hass: HomeAssistant, lines: list[str], patterns: tuple[str, ...]
) -> list[str]:
    """To-do lists: the items themselves instead of the item count (todo.get_items)."""
    todo = [s.entity_id for s in hass.states.async_all("todo") if _match(s, patterns)]
    if not todo:
        return lines
    try:
        response = await hass.services.async_call(
            "todo", "get_items", {"status": "needs_action"}, target={"entity_id": todo},
            blocking=True, return_response=True,
        )  # fmt: skip
    except Exception:  # list unavailable - only the item count stays
        _LOGGER.debug("todo.get_items failed", exc_info=True)
        return lines
    extra = []
    for entity_id, data in (response or {}).items():
        state = hass.states.get(entity_id)
        items = [i.get("summary", "") for i in (data or {}).get("items", []) if i.get("summary")]
        name = state.name if state else entity_id
        extra.append(f"{name}: {', '.join(items) if items else LANG.EMPTY_LIST}")
    names = {hass.states.get(e).name for e in todo if hass.states.get(e)}
    return [line for line in lines if _line_name(line) not in names] + extra


def _line_name(line: str) -> str:
    """Entity name from the line „Nazwa (inaczej: …) [pokój]: stan”."""
    return line.split(":")[0].split(" [")[0].split(f" ({LANG.ALIASES}")[0]


async def async_topic_sources(
    hass: HomeAssistant, config: RouterConfig, topic: Topic, route: Route, now: datetime
) -> list[str]:
    """Entity attributes (``details``) and service responses (``fetch``) trimmed to the
    person and day from the question - data for the answer model without Assist automations."""
    people = [config.people[key].pattern for key in route.people] or None
    days = day_range(route.when or topic.days, now.date())
    out = []
    for state in sorted(hass.states.async_all(), key=lambda s: s.entity_id):
        if owned_by_others(
            config, route.people, state.entity_id, entity_labels(hass, state.entity_id)
        ):
            continue
        if topic.details and _match(state, topic.details):
            value = compact(dict(state.attributes), people, days, topic.drop, now.tzinfo)
            out.append(render(f"{state.name} (stan: {state.state})", value))
    for item in topic.fetch:
        domain, service = item.action.split(".", 1)
        if hass.services.supports_response(domain, service) is not SupportsResponse.ONLY:
            # only services that solely return data - fetch never switches anything
            _LOGGER.warning("Router fetch %s skipped: not a read-only service", item.action)
            continue
        matched = {
            s.entity_id: entity_labels(hass, s.entity_id)
            for s in hass.states.async_all()
            if _match(s, item.entities)
        }
        targets = [
            entity_id
            for entity_id, labels in matched.items()
            if not owned_by_others(config, route.people, entity_id, labels)
        ]
        if note := _no_own_source(config, route, item, matched):
            out.append(note)
        if not targets:
            continue
        start, end = range_bounds(days or day_range(WEEK, now.date()))
        try:
            async with asyncio.timeout(FETCH_TIMEOUT):
                response = await hass.services.async_call(
                    domain, service, fill(item.data, start, end), target={"entity_id": targets},
                    blocking=True, return_response=True,
                )  # fmt: skip
        except Exception:  # service unavailable - the topic answers from the remaining data
            _LOGGER.warning("Router fetch %s failed", item.action, exc_info=True)
            continue
        names = {e: (s.name if (s := hass.states.get(e)) else e) for e in response or {}}
        out.extend(fetch_sources(item, response or {}, names, people, days, topic.drop, now))
    return out


def _no_own_source(
    config: RouterConfig, route: Route, item: Fetch, matched: dict[str, frozenset[str]]
) -> str | None:
    """„Asia nie ma przypisanego własnego źródła…” - for the person asked about, when the
    source's entities are assigned to people (``owns``/``labels``) but none to this person, so
    the answer model says so instead of „there are no events”."""
    if route.person is None:
        return None
    owners = [entity_owners(config, entity_id, labels) for entity_id, labels in matched.items()]
    if not any(owners) or any(route.person in found for found in owners):
        return None
    title = item.title or item.action
    return LANG.NO_OWN_SOURCE.format(name=config.people[route.person].name, title=title)


def fetch_sources(
    item: Fetch,
    response: dict[str, Any],
    names: dict[str, str],
    people: list[re.Pattern[str]] | None,
    days: tuple | None,
    drop: frozenset[str],
    now: datetime,
) -> list[str]:
    """A service response as sources for the model: one per entity or one merged."""
    parts = {"": merge(response, item.merge, names)} if item.merge else response
    out = []
    for entity_id, data in parts.items():
        value = compact(data, people, days, drop, now.tzinfo, item.limit)
        name = item.title or names.get(entity_id, entity_id)
        if item.title and not item.merge and len(parts) > 1:
            name = f"{item.title} - {names.get(entity_id, entity_id)}"
        out.append(
            render(name, value) if value not in ({}, [], LANG.EMPTY) else f"{name}: {LANG.EMPTY}"
        )
    return out


async def async_search_wikipedia(
    hass: HomeAssistant, config: RouterConfig, phrase: str, timeout: float
) -> str | None:
    """Cleaned fragment (WIKIPEDIA_CHARS) of the best-matching article or None.

    No result - a second try with the Wikipedia spelling suggestion (a typo or a word
    garbled by speech recognition: „piłce norznej” -> „piłce nożnej”).
    """
    article = await _wikipedia_article(hass, config, phrase, timeout)
    if article is None:
        body = await _wikipedia_get(
            hass, config, timeout, phrase,
            {"list": "search", "srsearch": phrase, "srinfo": "suggestion", "srlimit": "1"},
        )  # fmt: skip
        suggestion = ((body or {}).get("query") or {}).get("searchinfo", {}).get("suggestion")
        if suggestion and suggestion.lower() != phrase.lower():
            phrase = suggestion
            article = await _wikipedia_article(hass, config, phrase, timeout)
    if article is None:
        return None
    # intros of further hits: „kto jest obecnie mistrzem…” - the first result is often
    # a future tournament, and the answer is in the article about the last one
    more = await _wikipedia_intros(hass, config, phrase, timeout)
    extra = [f"{title}: {intro}" for title, intro in more if intro[:200] not in article]
    return article + (f"\n\n{LANG.OTHER_ARTICLES}\n" + "\n".join(extra) if extra else "")


async def _wikipedia_get(
    hass: HomeAssistant, config: RouterConfig, timeout: float, phrase: str, params: dict
) -> dict | None:
    session = async_get_clientsession(hass)
    url = f"https://{config.wikipedia_language}.wikipedia.org/w/api.php"
    try:
        async with asyncio.timeout(timeout):
            async with session.get(
                url, params={"action": "query", "format": "json", **params},
                headers={"User-Agent": USER_AGENT},
            ) as resp:  # fmt: skip
                resp.raise_for_status()
                return await resp.json()
    except (TimeoutError, aiohttp.ClientError, ValueError) as err:
        _LOGGER.warning("Wikipedia search for %r failed: %r", phrase, err)
        return None


async def _wikipedia_intros(
    hass: HomeAssistant, config: RouterConfig, phrase: str, timeout: float
) -> list[tuple[str, str]]:
    """Intros of the 2nd and 3rd hit (title, text) - matching the term, no disambiguations."""
    params = {
        "generator": "search",
        "gsrsearch": phrase,
        "gsrlimit": "3",
        "prop": "extracts",
        "exintro": "1",
        "exlimit": "3",
        "explaintext": "1",
        "redirects": "1",
    }
    body = await _wikipedia_get(hass, config, timeout, phrase, params)
    pages = sorted(
        (((body or {}).get("query") or {}).get("pages") or {}).values(),
        key=lambda page: page.get("index", 0),
    )
    out = []
    for page in pages[1:]:
        intro = clean_article(page.get("extract", ""), WIKIPEDIA_EXTRA_CHARS)
        title = page.get("title", "")
        if (
            intro
            and title_matches(phrase, title)
            and not any(marker in intro[:200] for marker in LANG.DISAMBIGUATION)
        ):
            out.append((title, intro))
    return out


async def _wikipedia_article(
    hass: HomeAssistant, config: RouterConfig, phrase: str, timeout: float
) -> str | None:
    params = {
        "generator": "search",
        "gsrsearch": phrase,
        "gsrlimit": "1",
        "prop": "extracts",
        "explaintext": "1",
        "redirects": "1",
    }
    body = await _wikipedia_get(hass, config, timeout, phrase, params)
    pages = ((body or {}).get("query") or {}).get("pages") or {}
    for page in pages.values():
        if not title_matches(phrase, page.get("title", "")):
            _LOGGER.debug("Wikipedia article %r does not match %r", page.get("title"), phrase)
            continue
        article = clean_article(page.get("extract", ""))
        if article and not any(marker in article[:200] for marker in LANG.DISAMBIGUATION):
            return article
    return None
