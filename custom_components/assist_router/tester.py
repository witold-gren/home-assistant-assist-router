"""The editor's tester: the way of one sentence through Assist and the router, on a router.yaml
that is not saved yet, step by step. Nothing is done: Home Assistant only recognizes the sentence
(its debug of sentences runs no intent), a control command is only planned, a topic's `command`
sentence is only recognized, never sent, the fallback agent is not asked, nothing is said or
announced and nothing goes to the log of unrecognized commands. The models are asked for real,
and so are the services that only return data, as a question would ask them."""

from __future__ import annotations

import dataclasses
import time
from typing import Any

from homeassistant.components import conversation
from homeassistant.components.conversation.agent_manager import get_agent_manager
from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers.template import Template
from homeassistant.util import dt as dt_util

from . import voice
from .control import is_bare_answer, may_be_several_commands
from .conversation import ANSWER_TOKENS, SUMMARY_TOKENS_PER_SENTENCE
from .languages import LANG
from .router import (
    Persona,
    Route,
    RouterConfig,
    answer_messages,
    apply_personal,
    apply_relatives,
    apply_speaker,
    async_classify,
    async_generate,
    async_search_wikipedia,
    async_todo_lines,
    async_topic_sources,
    clean_extract,
    entity_lines,
    hint_for,
    speaker_person,
    summary_messages,
    template_variables,
    with_speaker_room,
)

MAX_PARTS = 4  # commands of one sentence traced one by one


@dataclasses.dataclass(frozen=True)
class TestOptions:
    """Who says the sentence and where: a person of router.yaml, a persona, a room."""

    speaker: str | None = None  # key of a person in router.yaml
    persona: str | None = None
    area: str | None = None
    skip_ha: bool = False  # straight to the router, as if HA did not know the sentence
    answer: bool = True  # ask the answer model too


DEFAULT_OPTIONS = TestOptions()


def _ms(start: float) -> int:
    return round((time.monotonic() - start) * 1000)


async def async_ha_debug(
    hass: HomeAssistant, text: str, language: str | None = None
) -> dict[str, Any] | None:
    """What the built-in agent (with custom_sentences) recognizes in a sentence, without running
    the intent; None when it recognizes nothing."""
    agent = get_agent_manager(hass).default_agent
    if agent is None:
        return None
    user_input = conversation.ConversationInput(
        text=text,
        context=Context(),
        conversation_id=None,
        device_id=None,
        satellite_id=None,
        language=language or hass.config.language,
        agent_id=agent.entity_id,
    )
    return await agent.async_debug_recognize(user_input)


def _ha_summary(found: dict[str, Any] | None) -> dict[str, Any]:
    if found is None:
        return {"match": None}
    return {
        "match": bool(found.get("match")),
        "source": found.get("source"),
        "intent": (found.get("intent") or {}).get("name"),
        "slots": found.get("slots") or {},
        "unmatched": found.get("unmatched_slots") or {},
        "template": found.get("sentence_template") or "",
        "file": found.get("file"),
        "targets": sorted(found.get("targets") or {}),
    }


def _route(route: Route) -> dict[str, Any]:
    return {
        "topic": route.topic,
        "person": route.person,
        "people": list(route.people),
        "when": route.when,
        "phrase": route.phrase,
    }


def _persona(config: RouterConfig, name: str | None) -> Persona | None:
    return next((p for p in config.personas if p.name == name), None)


async def async_trace(
    hass: HomeAssistant,
    agent: Any,
    config: RouterConfig,
    text: str,
    options: TestOptions = DEFAULT_OPTIONS,
    saved: RouterConfig | None = None,
    part: bool = False,
) -> dict[str, Any]:
    """The way of a sentence: `ha`, `parts`, `router`, `route`, `control`, `unclear`, `data`,
    `answer` and the `outcome` with what the assistant would say (`speech`)."""
    text = " ".join(text.split())
    trace: dict[str, Any] = {"text": text, "outcome": None, "speech": None}
    if not part and voice.is_announcement(text):
        trace["outcome"] = "announcement"
        return trace
    if not part and voice.is_who_speaks(text):
        trace["outcome"] = "who_speaks"
        return trace
    only_data = False
    if not options.skip_ha:
        start = time.monotonic()
        found = await async_ha_debug(hass, text)
        trace["ha"] = {**_ha_summary(found), "ms": _ms(start)}
        if found is not None and found.get("match"):
            trace["outcome"] = "ha"
            return trace
        # HA knew the command but not its target: the router helps only with a topic with data
        only_data = found is not None
    if not part and text and may_be_several_commands(text):
        start = time.monotonic()
        parts = await agent._split_commands(text, config)
        if len(parts) > 1:
            trace["split_ms"] = _ms(start)
            trace["parts"] = [
                await async_trace(hass, agent, config, item, options, saved, part=True)
                for item in parts[:MAX_PARTS]
            ]
            trace["outcome"] = "parts"
            return trace
    ollama = agent._ollama()
    if ollama is None:
        trace["outcome"] = "no_model"
        return trace
    start = time.monotonic()
    route = await async_classify(hass, ollama, config, text)
    trace["router"] = {
        "model": ollama.model,
        "ms": _ms(start),
        **(_route(route) if route else {"topic": None}),
    }
    if saved is not None:
        before = await async_classify(hass, ollama, saved, text)
        trace["saved_topic"] = before.topic if before else None
    if route is None:
        trace["outcome"] = "fallback"
        return trace
    person = config.people.get(options.speaker) if options.speaker else None
    speaker = person.speaker if person else None
    route = apply_relatives(config, route, text, speaker)
    route = apply_speaker(config, route, text, speaker)
    topic = config.topics[route.topic]
    if topic.personal:
        route = apply_personal(config, route, speaker)
    trace["route"] = _route(route)
    persona = _persona(config, options.persona)
    if topic.unclear:
        return await _unclear(agent, config, text, trace)
    if topic.control:
        return await _control(agent, config, ollama, text, speaker, options, trace)
    if only_data and not (
        topic.command or topic.search or topic.entities or topic.details or topic.fetch
    ):
        trace["outcome"] = "ha_message"
        return trace
    return await _answer(hass, agent, config, route, text, speaker, persona, options, trace)


async def _unclear(agent: Any, config: RouterConfig, text: str, trace: dict) -> dict:
    start = time.monotonic()
    guess = await agent._guess_sentence(text, config)
    trace["unclear"] = {"guess": guess, "ms": _ms(start)}
    if guess and " ".join(guess.lower().split()) != text.lower():
        trace["outcome"] = "unclear_guess"
        trace["speech"] = LANG.GUESS_QUESTION.format(guess=guess)
    else:
        trace["outcome"] = "unclear_repeat"
        trace["speech"] = LANG.NOT_UNDERSTOOD
    return trace


async def _control(
    agent: Any,
    config: RouterConfig,
    ollama: Any,
    text: str,
    speaker: str | None,
    options: TestOptions,
    trace: dict,
) -> dict:
    """The plan of a control command - what would be done or asked - never done."""
    text = with_speaker_room(config, text, speaker)
    if is_bare_answer(text):
        trace["outcome"] = "control_bare"
        return trace
    if LANG.ALARM_WORDS.search(text):
        trace["outcome"] = "control_alarm"
        trace["speech"] = LANG.ALARM_HINT
        return trace
    start = time.monotonic()
    plan, reason = await agent._plan_control(text, config, ollama, None, here=options.area)
    trace["control"] = {"text": text, "ms": _ms(start), "reason": reason, "plan": None}
    if plan is None:
        trace["outcome"] = "fallback"
        return trace
    trace["control"]["plan"] = {
        "intent": plan.intent,
        "slots": plan.slots,
        "description": plan.description,
        "confirm": plan.confirm,
        "error": plan.error,
        "sensitive": plan.sensitive,
        "entity_id": plan.entity_id,
        "twins": list(plan.twins),
    }
    if plan.error:
        trace["outcome"], trace["speech"] = "control_error", plan.error
    elif plan.confirm:
        question = LANG.SENSITIVE_QUESTION if plan.sensitive else LANG.CONFIRM_QUESTION
        trace["outcome"] = "control_confirm"
        trace["speech"] = question.format(description=plan.description)
    else:
        trace["outcome"] = "control_execute"
    return trace


async def _answer(
    hass: HomeAssistant,
    agent: Any,
    config: RouterConfig,
    route: Route,
    text: str,
    speaker: str | None,
    persona: Persona | None,
    options: TestOptions,
    trace: dict,
) -> dict:
    topic = config.topics[route.topic]
    data: dict[str, Any] = {"command": None, "lines": [], "sources": []}
    trace["data"] = data
    start = time.monotonic()
    if topic.command:
        try:
            rendered = Template(topic.command, hass).async_render(
                template_variables(config, route, text), parse_result=False
            )
            command = " ".join(str(rendered).split())
        except Exception as err:
            command, data["command_error"] = "", str(err)
        if command:
            # recognized only: sent, it could run an automation
            data["command"] = {
                "sentence": command,
                "ha": _ha_summary(await async_ha_debug(hass, command)),
            }
    if topic.entities:
        exposed = config.only_exposed if topic.only_exposed is None else topic.only_exposed
        lines = entity_lines(
            hass, topic.entities, exposed, topic.skip_states, unavailable=topic.unavailable
        )
        lines = await async_todo_lines(hass, lines, topic.entities)
        if not lines and topic.skip_states:
            lines = [LANG.NOTHING_ACTIVE]
        data["lines"] = lines
    if topic.details or topic.fetch or topic.frigate:
        data["sources"] = await async_topic_sources(hass, config, topic, route, dt_util.now(), text)
    data["ms"] = _ms(start)
    parts = []
    if data["lines"]:
        parts.append(f"{LANG.DEVICE_STATES}\n" + "\n".join(data["lines"]))
    parts.extend(data["sources"])
    key = speaker_person(config, speaker)
    speaker_name = config.people[key].name if key else None
    if parts:
        hint = hint_for(config, topic, speaker)
        if topic.personal and not speaker_name:
            hint = f"{LANG.UNKNOWN_SPEAKER_HINT} {hint}"
        messages = answer_messages(
            config, dt_util.now(), "\n".join(parts), text, speaker_name, hint.strip(), persona
        )
        tokens = topic.answer_tokens or ANSWER_TOKENS
        return await _generate(agent, hass, messages, tokens, options, trace, "answer")
    if topic.search and route.phrase:
        ollama = agent._ollama()
        start = time.monotonic()
        article = await async_search_wikipedia(hass, config, route.phrase, ollama.timeout)
        trace["knowledge"] = {"phrase": route.phrase, "found": bool(article), "ms": _ms(start)}
        if not article:
            trace["outcome"] = "fallback"
            return trace
        messages = summary_messages(config, article, text, persona)
        tokens = SUMMARY_TOKENS_PER_SENTENCE * config.sentences
        await _generate(agent, hass, messages, tokens, options, trace, "knowledge")
        if not trace["speech"]:
            trace["speech"] = clean_extract(article, config.sentences)
        return trace
    trace["outcome"] = "fallback"
    return trace


async def _generate(
    agent: Any,
    hass: HomeAssistant,
    messages: list[dict[str, str]],
    tokens: int,
    options: TestOptions,
    trace: dict,
    outcome: str,
) -> dict:
    model = agent._answer_model()
    trace["outcome"] = outcome
    trace["answer"] = {"model": model.model if model else None, "messages": messages, "text": None}
    if model is None or not options.answer:
        return trace
    start = time.monotonic()
    trace["answer"]["text"] = await async_generate(hass, model, messages, tokens)
    trace["answer"]["ms"] = _ms(start)
    trace["speech"] = trace["answer"]["text"]
    return trace
