"""Assist Router conversation agent: a wrapper around the Home Assistant agent.

Passes the command unchanged to the built-in HA agent (all sentences, intents,
custom_sentences, room context work as before). It reacts only to the result:

- ``no_intent_match`` - instead of „Wybacz, niestety nie mogę tego zrozumieć” it says
  „Powiedziałeś: <transkrypcja z Whispera>. Niestety nie mogę tego zrozumieć.”;
- ``no_intent_match`` and ``no_valid_targets`` - appends a row to the CSV and fires the
  ``assist_router_unrecognized`` event (when logging is enabled in the options);
- ``no_intent_match`` + router (Ollama in the options, topics in router.yaml) - a small
  model picks the topic, the HA agent gets the template sentence, and the answer model
  writes the answer to the question from its text; knowledge questions - a Wikipedia
  summary (see router.py);
- ``no_intent_match`` + fallback agent in the options (e.g. Bielik/Ollama) - when the
  router did not help, asks it and returns its answer; when it does not answer in time
  or reports an error, „Powiedziałeś: …” stays. In the CSV the ``response`` column is
  what the user heard, and ``route`` - what the router chose.
"""

from __future__ import annotations

import asyncio
from collections import OrderedDict
import dataclasses
import inspect
import json
import logging
import time
from typing import Any, Literal

from homeassistant.components import conversation
from homeassistant.components.conversation.agent_manager import async_get_agent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import (
    area_registry as ar,
    device_registry as dr,
    entity_registry as er,
    intent,
)
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.service import async_get_all_descriptions
from homeassistant.helpers.template import Template
from homeassistant.util import dt as dt_util
import voluptuous as vol

from . import RuntimeData, examples, voice
from .const import (
    ANSWER_NUM_CTX,
    CONF_ANSWER_MODEL,
    CONF_ANSWER_TIMEOUT,
    CONF_FALLBACK_AGENT,
    CONF_FALLBACK_TIMEOUT,
    CONF_LOG_UNRECOGNIZED,
    CONF_OLLAMA_URL,
    CONF_ROUTER_KEEP_ALIVE,
    CONF_ROUTER_MODEL,
    CONF_ROUTER_TIMEOUT,
    DEFAULT_ANSWER_TIMEOUT,
    DEFAULT_FALLBACK_TIMEOUT,
    DEFAULT_LOG_UNRECOGNIZED,
    DEFAULT_ROUTER_KEEP_ALIVE,
    DEFAULT_ROUTER_TIMEOUT,
    DOMAIN,
    EVENT_UNRECOGNIZED,
    KIND_NO_MATCH,
    KIND_NO_TARGET,
    ROUTER_NUM_CTX,
    SIGNAL_EXAMPLES,
    TITLE,
)
from .control import (
    MA_MEDIA_TYPES,
    Plan,
    answer_kind,
    build_control_prompt,
    build_control_schema,
    collect_home,
    done_speech,
    is_bare_answer,
    is_cancel,
    is_repeat,
    may_be_several_commands,
    named_routine,
    parse_command,
    plan_command,
    prepare_text,
    rephrased_command,
    routine_plan,
    twin_calls,
)
from .languages import LANG, available_languages
from .router import (
    OllamaSettings,
    Route,
    RouterConfig,
    answer_messages,
    apply_personal,
    apply_relatives,
    apply_speaker,
    async_chat,
    async_classify,
    async_generate,
    async_preload,
    async_search_wikipedia,
    async_todo_lines,
    async_topic_sources,
    clean_extract,
    entity_labels,
    entity_lines,
    hint_for,
    owned_by_others,
    speaker_person,
    summary_messages,
    template_variables,
    with_speaker_room,
)

_LOGGER = logging.getLogger(__name__)

# Model answer length limit (tokens): answer from data and summary.
ANSWER_TOKENS = 160
SUMMARY_TOKENS_PER_SENTENCE = 70

# How many seconds a confirmation question („Czy wyłączyć…?”) waits for „tak”/„nie”
CONFIRM_SECONDS = 30
# How many times in a row we ask to repeat before apologizing and ending the
# conversation, and how long we remember the previous request.
MISUNDERSTOOD_LIMIT = 2
MISUNDERSTOOD_SECONDS = 120

# How many conversations to remember: HA conversation -> separate fallback agent one
MAX_FALLBACK_CONVERSATIONS = 50

KINDS = {
    intent.IntentResponseErrorCode.NO_INTENT_MATCH: KIND_NO_MATCH,
    intent.IntentResponseErrorCode.NO_VALID_TARGETS: KIND_NO_TARGET,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[RuntimeData],
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([AssistRouterAgent(entry)])


def current_speaker(hass: HomeAssistant) -> tuple[str | None, str | None]:
    """Recognized speaker (identifier, name) from the Assist Speaker ID integration, if any.

    Assist Speaker ID sets it in the speech-to-text step of the same pipeline run; text
    typed by hand or no integration = (None, None).
    """
    try:
        from custom_components.speaker_id.api import get_speaker
    except ImportError:
        return None, None
    speaker = get_speaker(hass)
    if speaker is None or not speaker.speaker:
        return None, None
    return speaker.speaker, speaker.name


def probable_speaker(hass: HomeAssistant) -> tuple[str | None, str | None]:
    """Probable speaker (identifier, name) of an unrecognized voice - Assist Speaker ID 0.2+
    reports the most similar person when close enough; older versions or none = (None, None).
    """
    result = speaker_result(hass)
    probable = getattr(result, "probable", None)
    if not probable:
        return None, None
    return probable, getattr(result, "probable_name", None)


def speaker_result(hass: HomeAssistant) -> Any | None:
    """Full Assist Speaker ID result of this utterance (also "unknown" with scores) or None."""
    try:
        from custom_components.speaker_id.api import get_speaker
    except ImportError:
        return None
    return get_speaker(hass)


async def announce_last(
    hass: HomeAssistant, exclude: str | None, media_players: list[str]
) -> list[str] | None:
    """Assist Speaker ID plays the speaker's recording on other speakers; None = no recording.

    One speaker per room: the player from ``announce_players`` (e.g. HomePod) when
    available, and the satellite only where there is none (Speaker ID 0.1.1+,
    ``prefer_players``)."""
    try:
        from custom_components.speaker_id.api import async_announce_last
    except ImportError:
        return None
    extra = {}
    if "prefer_players" in inspect.signature(async_announce_last).parameters:
        extra["prefer_players"] = True  # Speaker ID 0.1.0 does not know this option
    return await async_announce_last(hass, exclude=exclude, media_players=media_players, **extra)


def enrollment_reply(hass: HomeAssistant) -> tuple[str, bool] | None:
    """Assist Speaker ID records a voice sample: (short message, keep listening) or None.

    The utterance is then only a sample - no command recognition and no model, so that a
    child does not wait for a long answer and forget what to say next.
    """
    try:
        from custom_components.speaker_id.api import enrollment_reply as reply
    except ImportError:
        return None
    return reply(hass)


class AssistRouterAgent(conversation.ConversationEntity):
    """HA agent + router, fallback agent, repeat and logging of unrecognized commands."""

    _attr_has_entity_name = True
    _attr_name = None

    def __init__(self, entry: ConfigEntry[RuntimeData]) -> None:
        self._entry = entry
        self._log = entry.runtime_data.log
        self._router = entry.runtime_data.router
        entry.runtime_data.agent = self  # generate_examples action
        self._attr_unique_id = entry.entry_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=TITLE,
            manufacturer="home-assistant-assist-router",
            entry_type=DeviceEntryType.SERVICE,
        )
        # Fixed identifier, easy to find in the pipeline settings.
        self.entity_id = "conversation.assist_router"
        # The fallback agent has its own conversation history. The HA conversation history
        # already contains the error „Wybacz, niestety nie mogę tego zrozumieć”, and an LLM
        # that sees it can repeat it instead of answering the question.
        self._fallback_conversations: OrderedDict[str, str] = OrderedDict()
        self._preloading: set[str] = set()
        # conversation -> (plan waiting for „tak”, deadline)
        self._pending: dict[str, tuple[Plan, float]] = {}
        # „Czy chodziło o: …?” - the sentence guessed after speech recognition garble
        self._pending_text: dict[str, tuple[str, float]] = {}
        # conversation -> (times in a row we asked to repeat, deadline) and conversations
        # where the current utterance ended with a repeat request (then the counter stays)
        self._misunderstood: dict[str, tuple[int, float]] = {}
        self._repeat_turn: set[str] = set()
        # conversation -> (commands still to run after the current question, expiry)
        self._queued: dict[str, tuple[list[str], float]] = {}

    @property
    def supported_languages(self) -> list[str] | Literal["*"]:
        return available_languages()

    async def async_process(
        self, user_input: conversation.ConversationInput
    ) -> conversation.ConversationResult:
        if (reply := enrollment_reply(self.hass)) is not None:
            result = self._speak(user_input, user_input.conversation_id, reply[0])
            result.continue_conversation = reply[1]
            return result
        if voice.is_announcement(user_input.text):
            # „Ogłoszenie, dzieci, obiad!” - the speaker's recording (unchanged) on the other
            # speakers; without a recording (typed text) - the usual path (HA reads it with TTS)
            config = await self._router.async_get()
            players = list(config.announce_players) if config else []
            if await announce_last(self.hass, user_input.satellite_id, players) is not None:
                return self._speak(user_input, user_input.conversation_id, voice.ANNOUNCED)
        if voice.is_who_speaks(user_input.text):
            # „Kto to mówi?” - the voice recognition result of this utterance, without HA and models
            config = await self._router.async_get()
            names = {p.speaker: p.name for p in config.people.values()} if config else {}
            speech = voice.answer(speaker_result(self.hass), names)
            return self._speak(user_input, user_input.conversation_id, speech)
        result = await self._process_turn(user_input)
        key = result.conversation_id or user_input.conversation_id or ""
        queued = None if result.continue_conversation else self._queued.pop(key, None)
        if queued and queued[1] >= time.monotonic() and not is_cancel(user_input.text):
            # the question of one of several commands is answered - run the rest
            # („anuluj” drops them too)
            result = await self._run_parts(
                dataclasses.replace(user_input, conversation_id=key), queued[0], result
            )
        # every utterance that did not end with a repeat request resets the counter
        if key in self._repeat_turn:
            self._repeat_turn.discard(key)
        else:
            self._misunderstood.pop(key, None)
        return result

    async def _process_turn(
        self,
        user_input: conversation.ConversationInput,
        rephrased_from: str | None = None,
        part: bool = False,
    ) -> conversation.ConversationResult:
        """One utterance: a reply to the assistant's question, or the HA agent and the router.

        ``rephrased_from`` - the original reply when this text is a correction („nie, …”);
        ``part`` - one of several commands of a sentence (it is not split again).
        """
        if (confirmed := await self._answer_pending(user_input)) is not None:
            return confirmed
        key = user_input.conversation_id or ""
        if (
            rephrased_from is None
            and self._misunderstood.get(key, (0, 0.0))[1] >= time.monotonic()
            and (corrected := rephrased_command(user_input.text)) is not None
        ):
            # after „Powtórz, proszę” a „nie, …” reply carries the repeated command
            return await self._rephrase(user_input, corrected)
        agent = async_get_agent(self.hass, conversation.HOME_ASSISTANT_AGENT)
        if agent is None:
            raise RuntimeError("Built-in Home Assistant conversation agent is not available")
        # agent_id of the HA agent: its conversation history and traces work as usual.
        inner = dataclasses.replace(user_input, agent_id=conversation.HOME_ASSISTANT_AGENT)
        result = await agent.async_process(inner)

        response = result.response
        if response.response_type != intent.IntentResponseType.ERROR:
            return result
        kind = KINDS.get(response.error_code)
        if kind is None:
            return result

        text = " ".join(user_input.text.split())
        if not part and text and may_be_several_commands(text):
            parts = await self._split_commands(text)
            if len(parts) > 1:
                # several commands in one sentence - each one takes the whole usual path
                user_input = dataclasses.replace(user_input, conversation_id=result.conversation_id)
                multi = await self._run_parts(user_input, parts)
                await self._write_log(
                    user_input, kind, text, multi, LANG.LOG_MULTI.format(parts=" | ".join(parts))
                )
                return multi
        speaker = current_speaker(self.hass)
        probable = False
        if speaker[0] is None and (guess := probable_speaker(self.hass))[0]:
            # voice not recognized for sure - the most similar person, said out loud if used
            speaker, probable = guess, True
        answer, route = None, ""
        if kind == KIND_NO_MATCH and text:
            answer, route = await self._route(
                user_input, text, result.conversation_id, speaker=speaker, probable=probable
            )
            if answer is None:
                answer = await self._ask_fallback(
                    user_input, result.conversation_id, speaker=None if probable else speaker[1]
                )
        elif kind == KIND_NO_TARGET and text:
            # HA took the question for a command for a nonexistent area/device
            # („ile godzin Kuba jest w szkole” -> area „szkole”). The router helps only with
            # a topic with data; otherwise the HA message stays (without the fallback agent).
            answer, route = await self._route(
                user_input,
                text,
                result.conversation_id,
                only_data=True,
                speaker=speaker,
                probable=probable,
            )
        if answer is not None:
            result = answer
        elif kind == KIND_NO_MATCH:
            response.async_set_speech(
                LANG.MESSAGE_NO_MATCH.format(text=text) if text else LANG.MESSAGE_EMPTY
            )
        if rephrased_from:
            route += LANG.LOG_REPHRASED.format(text=rephrased_from)
        name = speaker[1]
        await self._write_log(
            user_input, kind, text, result, route, f"{name}?" if probable and name else name
        )
        return result

    async def _write_log(
        self,
        user_input: conversation.ConversationInput,
        kind: str,
        text: str,
        result: conversation.ConversationResult,
        route: str,
        speaker: str | None = None,
    ) -> None:
        """A row in the log of unrecognized commands and the event (when enabled)."""
        if not self._entry.options.get(CONF_LOG_UNRECOGNIZED, DEFAULT_LOG_UNRECOGNIZED):
            return
        area, device = self._where(user_input)
        if speaker is None:
            speaker = current_speaker(self.hass)[1]
        row = {
            "timestamp": dt_util.now().strftime("%Y-%m-%d %H:%M:%S"),
            "area": area,
            "device": device,
            "kind": kind,
            "text": text,
            "response": result.response.speech.get("plain", {}).get("speech", ""),
            "route": route,
            "speaker": speaker or "",
        }
        try:
            await self._log.async_append(row)
        except Exception:
            # Writing to the file must not break the voice answer.
            _LOGGER.warning(
                "Could not write the unrecognized command to the log file", exc_info=True
            )
        self.hass.bus.async_fire(EVENT_UNRECOGNIZED, row)

    async def _split_commands(self, text: str) -> list[str]:
        """Separate, complete commands of a sentence (model of control); ``[text]`` when it is
        one command, the model is not set up or its answer is unusable."""
        config = await self._router.async_get()
        ollama = self._ollama()
        if config is None or ollama is None:
            return [text]
        model = self._answer_model() if config.control_model == "answer" else None
        settings = model or ollama
        body = {
            "model": settings.model,
            "stream": False,
            "keep_alive": f"{settings.keep_alive}m" if settings.keep_alive >= 0 else -1,
            "format": {
                "type": "object",
                "properties": {LANG.SPLIT_KEY: {"type": "array", "items": {"type": "string"}}},
                "required": [LANG.SPLIT_KEY],
            },
            "options": {"temperature": 0, "num_predict": 200, "num_ctx": settings.num_ctx},
            "messages": [
                {"role": "system", "content": LANG.split_prompt(config.household)},
                {"role": "user", "content": text},
            ],
        }
        content = await async_chat(self.hass, settings, body)
        try:
            parts = json.loads(content or "").get(LANG.SPLIT_KEY)
        except (ValueError, AttributeError):
            return [text]
        if not isinstance(parts, list):
            return [text]
        parts = [" ".join(str(p).split()) for p in parts if isinstance(p, str) and p.strip()]
        return parts or [text]

    async def _run_parts(
        self,
        user_input: conversation.ConversationInput,
        parts: list[str],
        before: conversation.ConversationResult | None = None,
    ) -> conversation.ConversationResult:
        """Several commands one after another, each the whole usual path; one joined reply.

        A command that ends with a question stops here: the replies so far + the question are
        said, and the remaining commands wait (``_queued``) until the question is answered.
        ``before`` - the reply said before these commands (the answer to such a question).
        """
        speeches = []
        if before is not None:
            speeches.append(before.response.speech.get("plain", {}).get("speech", ""))
        result = before
        for index, text in enumerate(parts):
            result = await self._process_turn(dataclasses.replace(user_input, text=text), part=True)
            user_input = dataclasses.replace(user_input, conversation_id=result.conversation_id)
            speeches.append(result.response.speech.get("plain", {}).get("speech", ""))
            if result.continue_conversation:
                rest = parts[index + 1 :]
                if rest:
                    key = result.conversation_id or ""
                    self._queued[key] = (rest, time.monotonic() + CONFIRM_SECONDS)
                break
        if result is None:  # no commands - nothing to say
            response = intent.IntentResponse(language=user_input.language)
            result = conversation.ConversationResult(
                response=response, conversation_id=user_input.conversation_id
            )
        result.response.async_set_speech(" ".join(s.strip() for s in speeches if s.strip()))
        return result

    def _ollama(self) -> OllamaSettings | None:
        options = self._entry.options
        if not options.get(CONF_OLLAMA_URL) or not options.get(CONF_ROUTER_MODEL):
            return None
        return OllamaSettings(
            url=options[CONF_OLLAMA_URL],
            model=options[CONF_ROUTER_MODEL],
            timeout=float(options.get(CONF_ROUTER_TIMEOUT, DEFAULT_ROUTER_TIMEOUT)),
            keep_alive=int(options.get(CONF_ROUTER_KEEP_ALIVE, DEFAULT_ROUTER_KEEP_ALIVE)),
            # the same model in both roles = the same context (otherwise Ollama reloads)
            num_ctx=ANSWER_NUM_CTX
            if options.get(CONF_ROUTER_MODEL) == options.get(CONF_ANSWER_MODEL)
            else ROUTER_NUM_CTX,
        )

    def _answer_model(self) -> OllamaSettings | None:
        options = self._entry.options
        if not options.get(CONF_OLLAMA_URL) or not options.get(CONF_ANSWER_MODEL):
            return None
        return OllamaSettings(
            url=options[CONF_OLLAMA_URL],
            model=options[CONF_ANSWER_MODEL],
            timeout=float(options.get(CONF_ANSWER_TIMEOUT, DEFAULT_ANSWER_TIMEOUT)),
            keep_alive=int(options.get(CONF_ROUTER_KEEP_ALIVE, DEFAULT_ROUTER_KEEP_ALIVE)),
            num_ctx=ANSWER_NUM_CTX,
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # The first model load takes longer than the router timeout - we load it right away.
        for settings in (self._ollama(), self._answer_model()):
            if settings is not None:
                self._preload(settings)

    def _preload(self, settings: OllamaSettings) -> None:
        """Load the model in the background (at most one at a time per model)."""
        if settings.model in self._preloading:
            return
        self._preloading.add(settings.model)

        async def preload() -> None:
            try:
                await async_preload(self.hass, settings)
            finally:
                self._preloading.discard(settings.model)

        self._entry.async_create_background_task(self.hass, preload(), f"preload {settings.model}")

    async def _route(
        self,
        user_input: conversation.ConversationInput,
        text: str,
        conversation_id: str | None,
        only_data: bool = False,
        speaker: tuple[str | None, str | None] = (None, None),
        probable: bool = False,
    ) -> tuple[conversation.ConversationResult | None, str]:
        """Router answer (template sentence or Wikipedia) and the route description for CSV.

        No result (None) = the question goes on to the fallback agent. ``speaker`` - the
        recognized speaker (Assist Speaker ID): a 1st-person question concerns their data.
        ``probable`` - the speaker is only probable: when the answer depends on them, it
        starts with „Wydaje mi się, że pyta Zosia.”; otherwise they are not used at all.
        """
        ollama = self._ollama()
        if ollama is None:
            return None, ""
        config = await self._router.async_get()
        if config is None:
            return None, ""
        route = await async_classify(self.hass, ollama, config, text)
        if route is None:
            # Usually the model was not in memory (e.g. pushed out by another one) - we load
            # it in the background so the next question reaches the router.
            self._preload(ollama)
            return None, ""
        classified = route
        # „mój brat”, „moja córka” - relative to the speaker; then „mam”, „moje” = the speaker
        route = apply_relatives(config, route, text, speaker[0])
        route = apply_speaker(config, route, text, speaker[0])
        topic = config.topics[route.topic]
        if topic.personal:
            route = apply_personal(config, route, speaker[0])
        asked = text
        if topic.control:
            # „w moim pokoju” - the speaker's room from router.yaml (room)
            text = with_speaker_room(config, text, speaker[0])
        used = route != classified or text != asked
        if probable and not used:
            speaker = (None, None)  # a guess that changes nothing is not worth saying
        key = speaker_person(config, speaker[0])
        speaker_name = config.people[key].name if key else speaker[1]
        if topic.unclear:
            return await self._unclear(user_input, text, conversation_id, config)
        if topic.control:
            answer, label = await self._control(user_input, text, conversation_id, config, ollama)
        elif only_data and not (
            topic.command or topic.search or topic.entities or topic.details or topic.fetch
        ):
            return None, route.topic
        else:
            answer, label = await self._answer_topic(
                user_input, text, conversation_id, config, ollama, route, speaker, speaker_name
            )
        if answer is not None and probable and used and speaker_name:
            speech = answer.response.speech.get("plain", {}).get("speech", "")
            answer.response.async_set_speech(f"{LANG.probable_speaker(speaker_name)} {speech}")
            label += LANG.LOG_PROBABLE.format(name=speaker_name)
        return answer, label

    async def _answer_topic(
        self,
        user_input: conversation.ConversationInput,
        text: str,
        conversation_id: str | None,
        config: RouterConfig,
        ollama: OllamaSettings,
        route: Route,
        speaker: tuple[str | None, str | None],
        speaker_name: str | None,
    ) -> tuple[conversation.ConversationResult | None, str]:
        """Answer of a data topic: automation sentence, entities and sources for the answer
        model, or Wikipedia. None = nothing to say (the fallback agent may answer)."""
        topic = config.topics[route.topic]
        label = route.topic
        data_parts: list[str] = []
        command_data = ""
        routed: conversation.ConversationResult | None = None
        if topic.command:
            variables = template_variables(config, route, text)
            try:
                rendered = Template(topic.command, self.hass).async_render(
                    variables, parse_result=False
                )
                command = " ".join(str(rendered).split())
            except Exception:
                _LOGGER.warning("Router command template for %s failed", route.topic, exc_info=True)
                command = ""
            if command:
                label = f"{route.topic} → {command}"
                routed, data = await self._ask_home_assistant(user_input, command, conversation_id)
                if routed is not None and data:
                    command_data = data
                    data_parts.append(data)
                    if topic.verbatim:
                        # the automation's answer in its layout (several sentences - all of them)
                        return self._speak(user_input, conversation_id, data), label
                else:
                    label += LANG.LOG_NOT_RECOGNIZED
        lines = []
        if topic.entities:
            exposed = config.only_exposed if topic.only_exposed is None else topic.only_exposed
            lines = entity_lines(
                self.hass,
                topic.entities,
                exposed,
                topic.skip_states,
                skip=lambda entity_id: owned_by_others(
                    config, route.people, entity_id, entity_labels(self.hass, entity_id)
                ),
                unavailable=topic.unavailable,
            )
            lines = await async_todo_lines(self.hass, lines, topic.entities)
            if not lines and topic.skip_states:
                # everything skipped (e.g. no player is playing) - that is an answer too
                lines = [LANG.NOTHING_ACTIVE]
        if lines:
            # topic entity states (e.g. all car sensors) - the answer model will pick
            data_parts.append(f"{LANG.DEVICE_STATES}\n" + "\n".join(lines))
            label += LANG.LOG_ENTITIES.format(count=len(lines))
        if topic.details or topic.fetch:
            sources = await async_topic_sources(self.hass, config, topic, route, dt_util.now())
            if sources:
                data_parts.extend(sources)
                label += LANG.LOG_SOURCES.format(count=len(sources))
        if data_parts:
            data = "\n".join(data_parts)
            answer_model = self._answer_model()
            answer = None
            if answer_model:
                hint = hint_for(config, topic, speaker[0])
                if topic.personal and not speaker_name:
                    # without a recognized speaker the model would guess the person from the
                    # data (e.g. from the work calendar) - we say plainly that it is not known
                    hint = f"{LANG.UNKNOWN_SPEAKER_HINT} {hint}"
                messages = answer_messages(
                    config, dt_util.now(), data, text, speaker_name, hint.strip()
                )
                tokens = topic.answer_tokens or ANSWER_TOKENS
                answer = await async_generate(self.hass, answer_model, messages, tokens)
                if answer is None:
                    # model pushed out of memory or busy - the next question will make it in time
                    self._preload(answer_model)
            if answer:
                label += LANG.LOG_ANSWER
            else:
                # without an answer model - the automation text (bare entity states are not
                # suitable for reading aloud)
                answer = command_data
            if answer:
                if routed is None:
                    response = intent.IntentResponse(language=user_input.language)
                    routed = conversation.ConversationResult(
                        response=response, conversation_id=conversation_id
                    )
                routed.response.async_set_speech(answer)
                return routed, label

        if topic.search and route.phrase:
            label = f"{route.topic} → {route.phrase}"
            article = await async_search_wikipedia(self.hass, config, route.phrase, ollama.timeout)
            speech = None
            if article and (answer_model := self._answer_model()):
                speech = await async_generate(
                    self.hass,
                    answer_model,
                    summary_messages(config, article, text),
                    SUMMARY_TOKENS_PER_SENTENCE * config.sentences,
                )
                if speech:
                    label += " + streszczenie"
            if article and not speech:
                speech = clean_extract(article, config.sentences)
            if speech:
                response = intent.IntentResponse(language=user_input.language)
                response.async_set_speech(speech)
                return (
                    conversation.ConversationResult(
                        response=response, conversation_id=conversation_id
                    ),
                    label,
                )
            label += " (brak w Wikipedii)"
        return None, label

    async def _control(
        self,
        user_input: conversation.ConversationInput,
        text: str,
        conversation_id: str | None,
        config: RouterConfig,
        ollama: OllamaSettings,
    ) -> tuple[conversation.ConversationResult | None, str]:
        """Control command: parsing (model), plan (Python), execution or a question."""
        if is_bare_answer(text):
            # a bare „tak”/„nie rób” without an open question - not a command
            return None, LANG.LOG_CONTROL_BARE_ANSWER
        if LANG.ALARM_WORDS.search(text):
            # the alarm only via automation sentences - the model could pick the wrong device
            return (
                self._speak(user_input, conversation_id, LANG.ALARM_HINT),
                LANG.LOG_CONTROL_ALARM,
            )
        plan, reason = await self._plan_control(text, config, ollama, user_input.device_id)
        if plan is None:
            return None, reason or LANG.LOG_CONTROL_NOT_PARSED
        return await self._run_plan(user_input, conversation_id, plan)

    async def _plan_control(
        self,
        text: str,
        config: RouterConfig,
        ollama: OllamaSettings,
        device_id: str | None,
    ) -> tuple[Plan | None, str | None]:
        """Parsing (model) and plan (Python) of a command, without execution; None + reason."""
        home = collect_home(self.hass)
        text, doubts = prepare_text(text)
        routine = named_routine(home, text)
        if routine is not None:
            # script or scene name without „uruchom” - no model
            return routine_plan(routine, config.confirm_entities), None
        model = self._answer_model() if config.control_model == "answer" else None
        settings = model or ollama
        body = {
            "model": settings.model,
            "stream": False,
            "keep_alive": f"{settings.keep_alive}m" if settings.keep_alive >= 0 else -1,
            "format": build_control_schema(home),
            "options": {"temperature": 0, "num_predict": 160, "num_ctx": settings.num_ctx},
            "messages": [
                {
                    "role": "system",
                    "content": build_control_prompt(
                        home, config.household, await self._script_actions(home)
                    ),
                },
                {"role": "user", "content": text},
            ],
        }
        content = await async_chat(self.hass, settings, body)
        command = parse_command(home, content) if content else None
        if command is None:
            return None, LANG.LOG_CONTROL_NOT_PARSED
        plan = plan_command(
            self.hass,
            home,
            command,
            text,
            doubts,
            confirm_entities=config.confirm_entities,
            music_players=config.music_players,
            here=self._device_area(device_id),
        )
        if not plan.slots and "brak znanego czasownika" in doubts:
            # neither a verb nor a target - we do not guess what to do
            label = (
                f"{LANG.LOG_CONTROL} → {plan.intent} {json.dumps(plan.slots, ensure_ascii=False)}"
            )
            return None, f"{label} (bez celu i czasownika)"
        return plan, None

    async def async_generate_examples(
        self, per_topic: int = 5, only: set[str] | None = None
    ) -> dict[str, Any]:
        """Example commands for this home, saved in assist/router_examples.yaml.

        The sentences are written by the answer model (or the router's), checked by the real
        router, and control commands also by the plan - without execution.
        """
        ollama = self._ollama()
        config = await self._router.async_get()
        if ollama is None or config is None:
            raise HomeAssistantError("Router is not configured (Ollama URL, router.yaml)")
        writer = self._answer_model() or ollama
        any_room = next(iter(collect_home(self.hass).areas.values()), None)

        async def check_control(text: str) -> str | None:
            if LANG.ALARM_WORDS.search(text):
                return "alarm tylko przez zdania automatyzacji"
            plan, reason = await self._plan_control(text, config, ollama, None)
            if plan is None:
                return reason or LANG.LOG_NOT_PARSED
            if plan.error and not (plan.error == LANG.ERROR_WHICH_ROOM and any_room):
                return plan.error
            return None

        result = await examples.async_generate(
            self.hass,
            config,
            collect_home(self.hass),
            writer,
            ollama,
            check_control,
            per_topic=per_topic,
            only=only,
        )
        text = examples.render(result, writer.model, ollama.model)
        path = self._router.path.with_name(examples.EXAMPLES_FILE)
        await self.hass.async_add_executor_job(path.write_text, text, "utf-8")
        summary = {
            name: {"working": len(e.working), "rejected": len(e.rejected)}
            for name, e in result.items()
        }
        async_dispatcher_send(self.hass, SIGNAL_EXAMPLES)
        return {"file": str(path), "topics": summary}

    async def _run_plan(
        self,
        user_input: conversation.ConversationInput,
        conversation_id: str | None,
        plan: Plan,
    ) -> tuple[conversation.ConversationResult | None, str]:
        """Error message, confirmation question or execution."""
        label = f"{LANG.LOG_CONTROL} → {plan.intent} {json.dumps(plan.slots, ensure_ascii=False)}"
        if plan.error:
            return self._speak(user_input, conversation_id, plan.error), f"{label} ({plan.error})"
        if plan.confirm:
            self._pending[conversation_id or ""] = (plan, time.monotonic() + CONFIRM_SECONDS)
            question = (
                LANG.SENSITIVE_QUESTION if plan.sensitive else LANG.CONFIRM_QUESTION
            ).format(description=plan.description)
            result = self._speak(user_input, conversation_id, question)
            result.continue_conversation = True
            return result, label + LANG.LOG_QUESTION.format(reason=plan.confirm)
        speech = await self._execute(user_input, plan)
        return self._speak(user_input, conversation_id, speech), label

    async def _unclear(
        self,
        user_input: conversation.ConversationInput,
        text: str,
        conversation_id: str | None,
        config: RouterConfig,
    ) -> tuple[conversation.ConversationResult | None, str]:
        """Speech recognition garble: guess what was said (room and action names), and
        ask „Czy chodziło o …?”; with no suggestion - ask to repeat."""
        guess = await self._guess_sentence(text, config)
        if guess and " ".join(guess.lower().split()) != text.lower():
            self._pending_text[conversation_id or ""] = (guess, time.monotonic() + CONFIRM_SECONDS)
            speech = LANG.GUESS_QUESTION.format(guess=guess)
            label = f"{LANG.LOG_UNCLEAR} → {guess}"
        else:
            result = self._repeat_or_give_up(user_input, conversation_id, LANG.NOT_UNDERSTOOD)
            if not result.continue_conversation:
                return (
                    result,
                    LANG.LOG_UNCLEAR_GIVE_UP.format(limit=MISUNDERSTOOD_LIMIT),
                )
            return result, LANG.LOG_UNCLEAR_NO_GUESS
        result = self._speak(user_input, conversation_id, speech)
        result.continue_conversation = True
        return result, label

    async def _guess_sentence(self, text: str, config: RouterConfig) -> str | None:
        """The most likely sentence that speech recognition garbled."""
        settings = self._answer_model() or self._ollama()
        if settings is None:
            return None
        home = collect_home(self.hass)
        actions = await self._script_actions(home)
        system = LANG.guess_prompt(
            household=config.household,
            areas=", ".join(sorted(set(home.areas.values()))),
            actions=", ".join(actions),
        )
        body = {
            "model": settings.model,
            "stream": False,
            "keep_alive": f"{settings.keep_alive}m" if settings.keep_alive >= 0 else -1,
            "format": {
                "type": "object",
                "properties": {LANG.GUESS_KEY: {"type": ["string", "null"]}},
                "required": [LANG.GUESS_KEY],
            },
            "options": {"temperature": 0, "num_predict": 60, "num_ctx": settings.num_ctx},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": text}],
        }
        content = await async_chat(self.hass, settings, body)
        try:
            guess = json.loads(content or "").get(LANG.GUESS_KEY)
        except (ValueError, AttributeError):
            return None
        if not isinstance(guess, str):
            return None
        guess = " ".join(guess.split()).rstrip(".!?")
        # the model sometimes returns the string "null" instead of the value null
        return None if guess.lower() in LANG.GUESS_EMPTY else guess

    async def _answer_pending_text(
        self, user_input: conversation.ConversationInput
    ) -> conversation.ConversationResult | None:
        """Answer to „Czy chodziło o …?”: yes = the guessed sentence takes the whole usual path."""
        key = user_input.conversation_id or ""
        pending = self._pending_text.pop(key, None)
        if pending is None or pending[1] < time.monotonic():
            return None
        if (corrected := rephrased_command(user_input.text)) is not None:
            return await self._rephrase(user_input, corrected)
        kind = answer_kind(user_input.text)
        if kind is None:
            return None  # another utterance - that one is the command
        if kind == "yes":
            # _process_turn, not async_process - the misunderstanding counter counts this utterance
            return await self._process_turn(dataclasses.replace(user_input, text=pending[0]))
        if is_cancel(user_input.text):
            return self._speak(user_input, user_input.conversation_id, LANG.NOTHING_DONE)
        return self._ask_to_repeat(user_input)

    async def _rephrase(
        self, user_input: conversation.ConversationInput, text: str
    ) -> conversation.ConversationResult:
        """„nie, wyłącz światło w łazience” - the question is dropped and the corrected command
        takes the whole usual path, as if it were said for the first time. Not a request to
        repeat, so it can be corrected again and again."""
        self._misunderstood.pop(user_input.conversation_id or "", None)
        return await self._process_turn(
            dataclasses.replace(user_input, text=text), rephrased_from=user_input.text
        )

    def _ask_to_repeat(
        self, user_input: conversation.ConversationInput
    ) -> conversation.ConversationResult:
        """„nie”, „o coś innego”, „jeszcze raz” - an apology, the microphone stays open, and
        the next sentence goes the normal way („koniec” ends the conversation)."""
        return self._repeat_or_give_up(user_input, user_input.conversation_id, LANG.ASK_TO_REPEAT)

    def _repeat_or_give_up(
        self,
        user_input: conversation.ConversationInput,
        conversation_id: str | None,
        speech: str,
    ) -> conversation.ConversationResult:
        """Request to repeat - unless it is already another time in a row in this conversation:
        then an apology and the conversation ends (microphone closes), to avoid looping."""
        key = conversation_id or ""
        count, until = self._misunderstood.get(key, (0, 0.0))
        count = (count if until >= time.monotonic() else 0) + 1
        if count >= MISUNDERSTOOD_LIMIT:
            self._misunderstood.pop(key, None)
            self._pending.pop(key, None)
            self._pending_text.pop(key, None)
            return self._speak(user_input, conversation_id, LANG.MESSAGE_GIVE_UP)
        self._misunderstood[key] = (count, time.monotonic() + MISUNDERSTOOD_SECONDS)
        self._repeat_turn.add(key)
        result = self._speak(user_input, conversation_id, speech)
        result.continue_conversation = True
        return result

    async def _answer_pending(
        self, user_input: conversation.ConversationInput
    ) -> conversation.ConversationResult | None:
        """„tak/nie” reply to a confirmation question; another utterance drops the question."""
        if (answered := await self._answer_pending_text(user_input)) is not None:
            return answered
        key = user_input.conversation_id or ""
        pending = self._pending.pop(key, None)
        if pending is None or pending[1] < time.monotonic():
            return None
        if (corrected := rephrased_command(user_input.text)) is not None:
            return await self._rephrase(user_input, corrected)
        plan = pending[0]
        kind = answer_kind(user_input.text, plan.intent, plan.domain)
        if kind is None:
            return None
        if kind == "yes":
            speech = await self._execute(user_input, plan)
            return self._speak(user_input, user_input.conversation_id, speech)
        if is_cancel(user_input.text) or (plan.sensitive and not is_repeat(user_input.text)):
            # for „Czy otworzyć drzwi?” a bare „nie” means „nie otwieraj”
            return self._speak(user_input, user_input.conversation_id, LANG.NOTHING_CHANGED)
        return self._ask_to_repeat(user_input)

    def _device_area(self, device_id: str | None) -> str | None:
        """Area of the device the command came from (satellite) - the default room."""
        device = dr.async_get(self.hass).async_get(device_id) if device_id else None
        area = (
            ar.async_get(self.hass).async_get_area(device.area_id)
            if device and device.area_id
            else None
        )
        return area.name if area else None

    async def _play(self, user_input: conversation.ConversationInput, plan: Plan) -> str:
        """„Puść …”: playback on the player chosen in the plan.

        A Music Assistant player - music_assistant.play_media (MA search with type, artist and
        radio mode); others, or when MA fails - search_media and the first result (like
        HassMediaSearchAndPlay, but with the player from the plan - Music Assistant players
        usually have no area, so HA matching would not find them).
        """
        player = plan.slots["entity_id"]
        if (said := await self._play_music_assistant(user_input, plan)) is not None:
            return said
        search: dict[str, Any] = {"search_query": plan.slots["search_query"]}
        if plan.slots.get("media_class"):
            search["media_filter_classes"] = [plan.slots["media_class"]]
        try:
            response = await self.hass.services.async_call(
                "media_player",
                "search_media",
                search,
                target={"entity_id": player},
                blocking=True,
                context=user_input.context,
                return_response=True,
            )
            found = (response or {}).get(player)
            results = getattr(found, "result", None) or (
                found.get("result") if isinstance(found, dict) else None
            )
            if not results:
                return LANG.PLAY_NOT_FOUND.format(query=plan.slots["search_query"])
            first = results[0]
            item = first if isinstance(first, dict) else first.as_dict()
            await self.hass.services.async_call(
                "media_player",
                "play_media",
                {
                    "entity_id": player,
                    "media_content_id": item["media_content_id"],
                    "media_content_type": item["media_content_type"],
                },
                blocking=True,
                context=user_input.context,
            )
        except HomeAssistantError as err:
            _LOGGER.warning("Search and play on %s failed: %s", player, err)
            return LANG.PLAY_FAILED
        state = self.hass.states.get(player)
        title = item.get("title") or plan.slots["search_query"]
        return LANG.playing(title, state.name if state else None)

    async def _play_music_assistant(
        self, user_input: conversation.ConversationInput, plan: Plan
    ) -> str | None:
        """music_assistant.play_media on a Music Assistant player; None - not an MA player,
        MA does not support this kind (genre) or it reported an error."""
        player = plan.slots["entity_id"]
        entry = er.async_get(self.hass).async_get(player)
        media_type = MA_MEDIA_TYPES.get(plan.slots.get("media_class") or "", "")
        if (
            entry is None
            or entry.platform != "music_assistant"
            or not self.hass.services.has_service("music_assistant", "play_media")
            or media_type is None
        ):
            return None
        data: dict[str, Any] = {"media_id": plan.slots["search_query"]}
        if media_type:
            data["media_type"] = media_type
        if plan.slots.get("artist") and media_type in ("track", "album", ""):
            data["artist"] = plan.slots["artist"]
        if plan.slots.get("radio_mode"):
            data["radio_mode"] = True
        try:
            await self.hass.services.async_call(
                "music_assistant",
                "play_media",
                data,
                target={"entity_id": player},
                blocking=True,
                context=user_input.context,
            )
        except HomeAssistantError as err:
            _LOGGER.info("Music Assistant play_media on %s failed (%s) - search_media", player, err)
            return None
        state = self.hass.states.get(player)
        what = plan.slots["search_query"]
        if data.get("artist"):
            what += f" ({data['artist']})"
        return LANG.playing(what, state.name if state else None, bool(data.get("radio_mode")))

    async def _script_actions(self, home) -> dict[str, str]:
        """Exposed scripts (with descriptions) and scenes - actions the control model can choose.

        Scenes have no description field in HA, so the description lists what the scene sets.
        """
        actions: dict[str, str] = {}
        scripts = [t for t in home.targets if t.domain == "script"]
        if scripts:
            descriptions = (await async_get_all_descriptions(self.hass)).get("script", {})
            for target in scripts:
                info = descriptions.get(target.entity_id.split(".", 1)[1], {})
                actions[target.name] = str(info.get("description") or "")
        for target in (t for t in home.targets if t.domain == "scene"):
            state = self.hass.states.get(target.entity_id)
            members = [
                (self.hass.states.get(e).name if self.hass.states.get(e) else e)
                for e in (state.attributes.get("entity_id") or [] if state else [])
            ]
            actions[target.name] = LANG.scene_description(members)
        return actions

    async def _run_script(self, user_input: conversation.ConversationInput, plan: Plan) -> str:
        """Script run directly: satellite fields (e.g. „Kawa gotowa” on this speaker) get the
        speaker the command came from."""
        object_id = plan.entity_id.split(".", 1)[1]
        fields = (
            (await async_get_all_descriptions(self.hass)).get("script", {}).get(object_id, {})
        ).get("fields", {})
        variables = {
            name: user_input.satellite_id
            for name, spec in fields.items()
            if user_input.satellite_id and "assist_satellite" in json.dumps(spec.get("selector"))
        }
        try:
            await self.hass.services.async_call(
                "script", "turn_on", {"entity_id": plan.entity_id, "variables": variables},
                blocking=True, context=user_input.context,
            )  # fmt: skip
        except HomeAssistantError as err:
            _LOGGER.warning("Script %s failed: %s", plan.entity_id, err)
            return LANG.COMMAND_FAILED
        state = self.hass.states.get(plan.entity_id)
        return done_speech(plan.intent, [state.name if state else object_id], {}, "script")

    async def _execute(self, user_input: conversation.ConversationInput, plan: Plan) -> str:
        """Execution via HA intents (target matching, exposure, satellite room)."""
        if plan.intent == "HassMediaSearchAndPlay":
            return await self._play(user_input, plan)
        if plan.intent == "HassTurnOn" and plan.domain == "script" and plan.entity_id:
            return await self._run_script(user_input, plan)
        if plan.twins and (calls := twin_calls(plan)) is not None:
            return await self._run_twins(user_input, plan, calls)
        slots = {key: {"value": value} for key, value in plan.slots.items()}
        try:
            response = await intent.async_handle(
                self.hass,
                DOMAIN,
                plan.intent,
                slots,
                text_input=user_input.text,
                context=user_input.context,
                language=user_input.language,
                assistant=conversation.DOMAIN,
                device_id=user_input.device_id,
                satellite_id=user_input.satellite_id,
                conversation_agent_id=self.entity_id,
            )
        except intent.MatchFailedError:
            return LANG.DEVICE_NOT_AVAILABLE
        except intent.IntentError as err:
            _LOGGER.warning("Intent %s failed: %s", plan.intent, err)
            return LANG.COMMAND_FAILED
        if response.response_type == intent.IntentResponseType.ERROR:
            return response.speech.get("plain", {}).get("speech") or LANG.COMMAND_FAILED
        names = [state.name for state in response.matched_states]
        return done_speech(plan.intent, names, plan.slots, plan.domain)

    async def _run_twins(
        self,
        user_input: conversation.ConversationInput,
        plan: Plan,
        calls: list[tuple[str, str, dict[str, Any]]],
    ) -> str:
        """Service on each twin entity (HomePod via Apple TV and via Music Assistant) - the HA
        intent will not accept a name shared by two entities in one room."""
        entity_ids = [
            entity_id
            for entity_id in plan.twins
            if (state := self.hass.states.get(entity_id)) and state.state != "unavailable"
        ]
        if plan.intent in ("HassMediaPause", "HassMediaNext", "HassMediaPrevious"):
            # playback control - the entity that is playing (the other has no queue)
            playing = [e for e in entity_ids if self.hass.states.get(e).state == "playing"]
            entity_ids = playing or entity_ids
        done = False
        for entity_id in entity_ids:
            for domain, service, data in calls:
                try:
                    await self.hass.services.async_call(
                        domain,
                        service,
                        {**data, "entity_id": entity_id},
                        blocking=True,
                        context=user_input.context,
                    )
                    done = True
                except (HomeAssistantError, vol.Invalid) as err:
                    _LOGGER.debug("%s.%s on %s failed: %s", domain, service, entity_id, err)
        if not done:
            return LANG.COMMAND_FAILED
        return done_speech(plan.intent, [plan.slots["name"]], plan.slots, plan.domain)

    def _speak(
        self, user_input: conversation.ConversationInput, conversation_id: str | None, speech: str
    ) -> conversation.ConversationResult:
        response = intent.IntentResponse(language=user_input.language)
        response.async_set_speech(speech)
        return conversation.ConversationResult(response=response, conversation_id=conversation_id)

    async def _ask_home_assistant(
        self, user_input: conversation.ConversationInput, command: str, conversation_id: str | None
    ) -> tuple[conversation.ConversationResult | None, str]:
        """Template question (or several, separated by „;”) for the HA agent.

        Returns the result of the last recognized question and the joined answer text -
        e.g. „dzieci” = each child's lesson plan in turn.
        """
        agent = async_get_agent(self.hass, conversation.HOME_ASSISTANT_AGENT)
        if agent is None:
            return None, ""
        routed, texts = None, []
        for question in (q.strip() for q in command.split(";")):
            if not question:
                continue
            inner = dataclasses.replace(
                user_input,
                text=question,
                agent_id=conversation.HOME_ASSISTANT_AGENT,
                conversation_id=conversation_id,
            )
            result = await agent.async_process(inner)
            speech = result.response.speech.get("plain", {}).get("speech", "").strip()
            if result.response.response_type != intent.IntentResponseType.ERROR and speech:
                routed = result
                texts.append(speech)
        return routed, "\n".join(texts)

    async def _ask_fallback(
        self,
        user_input: conversation.ConversationInput,
        conversation_id: str | None,
        speaker: str | None = None,
    ) -> conversation.ConversationResult | None:
        """Fallback agent answer (e.g. Bielik) or None (none, error, timeout).

        The agent gets its own conversation (follow-up questions in the same HA conversation
        have context), and the result comes back with the HA conversation id.
        """
        agent_id = self._entry.options.get(CONF_FALLBACK_AGENT)
        if not agent_id or agent_id == self.entity_id:
            return None
        agent = async_get_agent(self.hass, agent_id)
        if agent is None:
            _LOGGER.warning("Fallback conversation agent %s not found", agent_id)
            return None
        timeout = self._entry.options.get(CONF_FALLBACK_TIMEOUT, DEFAULT_FALLBACK_TIMEOUT)
        prompt = user_input.extra_system_prompt
        if speaker:
            # recognized speaker (Assist Speaker ID) - the agent knows who is asking („moje”, „mam”)
            prompt = f"{prompt}\nPyta: {speaker}." if prompt else f"Pyta: {speaker}."
        inner = dataclasses.replace(
            user_input,
            agent_id=agent_id,
            conversation_id=self._fallback_conversations.get(conversation_id or ""),
            extra_system_prompt=prompt,
        )
        try:
            async with asyncio.timeout(timeout):
                if isinstance(agent, conversation.ConversationEntity):
                    agent.async_set_context(user_input.context)
                    result = await agent.internal_async_process(inner)
                else:
                    result = await agent.async_process(inner)
        except TimeoutError:
            _LOGGER.warning("Fallback agent %s did not answer within %s s", agent_id, timeout)
            return None
        except Exception:
            _LOGGER.warning("Fallback agent %s failed", agent_id, exc_info=True)
            return None
        if result.response.response_type == intent.IntentResponseType.ERROR:
            return None
        speech = result.response.speech.get("plain", {}).get("speech", "")
        if not speech.strip():
            return None
        if speech != speech.strip():
            # Ollama starts the answer with a newline - unnecessary in the CSV and the notification
            result.response.async_set_speech(speech.strip())
        if conversation_id and result.conversation_id:
            self._fallback_conversations[conversation_id] = result.conversation_id
            self._fallback_conversations.move_to_end(conversation_id)
            while len(self._fallback_conversations) > MAX_FALLBACK_CONVERSATIONS:
                self._fallback_conversations.popitem(last=False)
        return dataclasses.replace(
            result, conversation_id=conversation_id or result.conversation_id
        )

    def _where(self, user_input: conversation.ConversationInput) -> tuple[str, str]:
        """Room and name of the voice device (the satellite, or the device when there is none)."""
        ent_reg = er.async_get(self.hass)
        dev_reg = dr.async_get(self.hass)
        area_id: str | None = None
        name = ""
        device_id = user_input.device_id
        if user_input.satellite_id and (entry := ent_reg.async_get(user_input.satellite_id)):
            area_id = entry.area_id
            device_id = device_id or entry.device_id
            state = self.hass.states.get(user_input.satellite_id)
            name = state.name if state else (entry.name or entry.original_name or "")
        if device_id and (device := dev_reg.async_get(device_id)):
            area_id = area_id or device.area_id
            name = name or device.name_by_user or device.name or ""
        area = ar.async_get(self.hass).async_get_area(area_id) if area_id else None
        return (area.name if area else "", name)
