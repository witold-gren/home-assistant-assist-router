"""Streaming the models' answers to the pipeline's text to speech while they are written.

A question is asked the way the Assist pipeline asks it: inside the chat log of the
conversation, with a delta listener (the pipeline's text to speech reads those deltas).
"""

from __future__ import annotations

import json
from typing import Literal
import uuid

from homeassistant.components import conversation
from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers import chat_session, intent
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
    AiohttpClientMockResponse,
)

from custom_components.assist_router import conversation as agent_module
from custom_components.assist_router.const import CONF_FALLBACK_AGENT, CONF_FALLBACK_TIMEOUT
from custom_components.assist_router.streaming import ReplyStream, listening_chat_log

from .conftest import AGENT_ID, OLLAMA, WIKI
from .test_router import _answer, _probable_setup, _rows, _speech, _with_answer_model

ANSWER = "Kasia kończy dziś lekcje o 12:35, a potem idzie na basen i wraca około szesnastej."


def _ndjson(*parts: str) -> str:
    """Ollama's streamed answer: one JSON line per part, the last one done."""
    lines = [{"message": {"role": "assistant", "content": part}, "done": False} for part in parts]
    lines.append({"message": {"role": "assistant", "content": ""}, "done": True})
    return "\n".join(json.dumps(line, ensure_ascii=False) for line in lines) + "\n"


def _chat(answer_parts: tuple[str, ...], topic: str = "lekcje", requests: list | None = None):
    """Mock /api/chat: the router model picks ``topic``, the answer model streams its parts
    when asked to stream and answers as a whole otherwise."""

    async def handler(method, url, data):
        if requests is not None:
            requests.append(data)
        if data["model"] == "bielik-1.5b":
            return AiohttpClientMockResponse(method, url, json=_answer(topic))
        if data.get("stream"):
            return AiohttpClientMockResponse(method, url, text=_ndjson(*answer_parts))
        content = "".join(answer_parts)
        return AiohttpClientMockResponse(method, url, json={"message": {"content": content}})

    return handler


async def _ask_listening(
    hass: HomeAssistant, text: str, conversation_id: str | None = None
) -> tuple[conversation.ConversationResult, list]:
    """Like the Assist pipeline: the chat log of the conversation with a delta listener."""
    deltas: list[dict] = []
    with (
        chat_session.async_get_chat_session(hass, conversation_id) as session,
        conversation.async_get_chat_log(
            hass, session, chat_log_delta_listener=lambda _log, delta: deltas.append(delta)
        ),
    ):
        result = await conversation.async_converse(
            hass, text, session.conversation_id, Context(), language="pl", agent_id=AGENT_ID
        )
    return result, deltas


def _streamed(deltas: list[dict]) -> list[str]:
    return [delta["content"] for delta in deltas if delta.get("content")]


# --- the stream itself ---


async def test_reply_stream_says_whole_words_cleaned_up(hass: HomeAssistant) -> None:
    deltas: list[dict] = []
    with (
        chat_session.async_get_chat_session(hass) as session,
        conversation.async_get_chat_log(
            hass, session, chat_log_delta_listener=lambda _log, delta: deltas.append(delta)
        ) as chat_log,
    ):
        assert listening_chat_log(session.conversation_id) is chat_log
        assert listening_chat_log("another") is None
        stream = ReplyStream(
            hass,
            chat_log,
            AGENT_ID,
            prefix="Wydaje mi się, że pyta Kasia.",
            words=lambda text: text.replace("znalazłem", "znalazłam"),
        )
        for part in ("\n ", "Nie zna", "lazłem  ", "nic\n\nw ", "kalendarzu", "."):
            stream.push(part)
        spoken = await stream.finish()

    assert spoken == "Wydaje mi się, że pyta Kasia. Nie znalazłam nic w kalendarzu."
    assert deltas[0] == {"role": "assistant"}
    assert "".join(_streamed(deltas)) == spoken
    assert chat_log.content[-1].content == spoken


async def test_reply_stream_with_nothing_said_adds_nothing(hass: HomeAssistant) -> None:
    deltas: list[dict] = []
    with (
        chat_session.async_get_chat_session(hass) as session,
        conversation.async_get_chat_log(
            hass, session, chat_log_delta_listener=lambda _log, delta: deltas.append(delta)
        ) as chat_log,
    ):
        before = len(chat_log.content)
        stream = ReplyStream(hass, chat_log, AGENT_ID, prefix="Wydaje mi się, że pyta Kasia.")
        stream.push(" \n")  # a model that answered only whitespace
        assert await stream.finish() == ""
        assert len(chat_log.content) == before
    assert deltas == []


def test_without_a_listening_chat_log_nothing_streams() -> None:
    assert listening_chat_log("01abc") is None


async def test_the_agent_says_it_streams(hass: HomeAssistant, setup: MockConfigEntry) -> None:
    info = conversation.async_get_agent_info(hass, AGENT_ID)
    assert info is not None and info.supports_streaming is True


# --- the answer model ---


async def test_answer_model_streams_to_the_pipeline(
    hass: HomeAssistant, router: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    await _with_answer_model(hass, router, aioclient_mock)
    requests: list[dict] = []
    parts = (
        " Kasia kończy dziś lekcje o 12:35,",
        " a potem idzie na basen",
        " i wraca około szesnastej.",
    )
    aioclient_mock.post(f"{OLLAMA}/api/chat", side_effect=_chat(parts, requests=requests))

    result, deltas = await _ask_listening(hass, "kiedy Kasia wraca ze szkoły")

    assert _speech(result) == ANSWER
    assert len(_streamed(deltas)) > 1 and "".join(_streamed(deltas)) == ANSWER
    answer_request = next(r for r in requests if r["model"] == "gemma-mala")
    assert answer_request["stream"] is True and answer_request["think"] is False
    assert next(r for r in requests if r["model"] == "bielik-1.5b")["stream"] is False
    assert _rows(hass)[0]["response"] == ANSWER


async def test_without_the_pipeline_the_answer_comes_whole(
    hass: HomeAssistant, router: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    await _with_answer_model(hass, router, aioclient_mock)
    requests: list[dict] = []
    aioclient_mock.post(f"{OLLAMA}/api/chat", side_effect=_chat((ANSWER,), requests=requests))

    result = await conversation.async_converse(
        hass, "kiedy Kasia wraca ze szkoły", None, Context(), language="pl", agent_id=AGENT_ID
    )

    assert _speech(result) == ANSWER
    assert all(request["stream"] is False for request in requests)


async def test_a_model_failing_halfway_keeps_what_was_said(
    hass: HomeAssistant, router: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    await _with_answer_model(hass, router, aioclient_mock)

    async def handler(method, url, data):
        if data["model"] == "bielik-1.5b":
            return AiohttpClientMockResponse(method, url, json=_answer("lekcje"))
        broken = _ndjson("Kasia kończy dziś lekcje o 12:35, ").splitlines()[0]
        return AiohttpClientMockResponse(
            method, url, text=broken + "\n" + json.dumps({"error": "model unloaded"}) + "\n"
        )

    aioclient_mock.post(f"{OLLAMA}/api/chat", side_effect=handler)

    result, deltas = await _ask_listening(hass, "kiedy Kasia wraca ze szkoły")

    assert _speech(result) == "Kasia kończy dziś lekcje o 12:35,"
    assert "".join(_streamed(deltas)) == _speech(result)


async def test_a_model_failing_at_once_reads_the_data_as_before(
    hass: HomeAssistant, router: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    await _with_answer_model(hass, router, aioclient_mock)

    async def handler(method, url, data):
        if data["model"] == "bielik-1.5b":
            return AiohttpClientMockResponse(method, url, json=_answer("lekcje"))
        return AiohttpClientMockResponse(method, url, status=500)

    aioclient_mock.post(f"{OLLAMA}/api/chat", side_effect=handler)

    result, deltas = await _ask_listening(hass, "kiedy Kasia wraca ze szkoły")

    assert _speech(result) == "Kasia kończy o 12:35."  # the automation's own answer
    assert _streamed(deltas) == []


async def test_the_probable_speaker_is_said_first(
    hass: HomeAssistant,
    router: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _probable_setup(hass, router, aioclient_mock, monkeypatch, "plany")
    aioclient_mock.clear_requests()
    aioclient_mock.post(f"{OLLAMA}/api/chat", side_effect=_chat(("Masz ", "basen."), topic="plany"))

    result, deltas = await _ask_listening(hass, "Co mam jutro w planach?")

    assert _speech(result) == "Wydaje mi się, że pyta Kasia. Masz basen."
    assert _streamed(deltas)[0].startswith("Wydaje mi się, że pyta Kasia. Masz")
    assert "".join(_streamed(deltas)) == _speech(result)
    assert "(prawdopodobnie Kasia)" in _rows(hass)[-1]["route"]


async def test_wikipedia_summary_streams(
    hass: HomeAssistant, router: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    await _with_answer_model(hass, router, aioclient_mock)
    summary = (
        "Kopernik był astronomem. ",
        "Stworzył model heliocentryczny. ",
        "Urodził się w Toruniu.",
    )
    aioclient_mock.post(f"{OLLAMA}/api/chat", side_effect=_chat(summary, topic="wiedza"))
    page = {"title": "Mikołaj Kopernik", "extract": "Mikołaj Kopernik (ur. 1473 w Toruniu)."}
    aioclient_mock.get(WIKI, json={"query": {"pages": {"1": page}}})

    result, deltas = await _ask_listening(hass, "kim był Mikołaj Kopernik")

    assert _speech(result) == "".join(summary)
    assert "".join(_streamed(deltas)) == _speech(result)
    assert _rows(hass)[0]["route"] == "wiedza → Mikołaj Kopernik + streszczenie"


async def test_a_female_persona_streams_female_forms(
    hass: HomeAssistant,
    router: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pathlib import Path

    from .test_router import ROUTER_YAML

    Path(hass.config.path("assist", "router.yaml")).write_text(
        ROUTER_YAML
        + "personas:\n  elza:\n    pipelines: [Elza]\n"
        + "    gender: female\n    prompt: Jesteś Elzą.\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        agent_module, "current_pipeline", lambda hass, context: ("01elza", "Salon Elza", None)
    )
    await _with_answer_model(hass, router, aioclient_mock)
    parts = ("Nie zna", "lazłem nic ", "o lekcjach Kasi.")
    aioclient_mock.post(f"{OLLAMA}/api/chat", side_effect=_chat(parts))

    result, deltas = await _ask_listening(hass, "kiedy Kasia wraca ze szkoły")

    assert _speech(result) == "Nie znalazłam nic o lekcjach Kasi."
    assert "".join(_streamed(deltas)) == _speech(result)


# --- several commands in one sentence: one joined reply, no streaming ---


async def test_several_commands_do_not_stream(
    hass: HomeAssistant,
    router: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _with_answer_model(hass, router, aioclient_mock)
    requests: list[dict] = []
    aioclient_mock.post(f"{OLLAMA}/api/chat", side_effect=_chat((ANSWER,), requests=requests))
    seen: list[bool] = []
    real = agent_module.AssistRouterAgent._reply_stream

    def watch(self, conversation_id, prefix=""):
        seen.append(agent_module.STREAMING.get())
        return real(self, conversation_id, prefix)

    monkeypatch.setattr(agent_module.AssistRouterAgent, "_reply_stream", watch)

    async def split(self, text, config=None):
        return ["kiedy Kasia wraca ze szkoły", "kiedy Jan wraca ze szkoły"]

    monkeypatch.setattr(agent_module.AssistRouterAgent, "_split_commands", split)
    monkeypatch.setattr(agent_module, "may_be_several_commands", lambda text: True)

    result, deltas = await _ask_listening(hass, "kiedy Kasia i Jan wracają ze szkoły")

    assert _speech(result) == f"{ANSWER} {ANSWER}"
    assert seen and not any(seen)
    assert _streamed(deltas) == []
    assert all(request["stream"] is False for request in requests)


# --- the fallback agent: its own conversation, its text passed on ---


class StreamingLLM(conversation.AbstractConversationAgent):
    """A fallback agent that streams into the chat log of its conversation, like Ollama."""

    def __init__(self, parts: tuple[str, ...], fail: bool = False) -> None:
        self.parts, self.fail = parts, fail
        self.conversation_ids: list[str | None] = []

    @property
    def supported_languages(self) -> list[str] | Literal["*"]:
        return "*"

    async def async_process(
        self, user_input: conversation.ConversationInput
    ) -> conversation.ConversationResult:
        self.conversation_ids.append(user_input.conversation_id)

        async def deltas():
            yield {"role": "assistant"}
            for part in self.parts:
                yield {"content": part}
            if self.fail:
                raise RuntimeError("connection lost")

        with (
            chat_session.async_get_chat_session(self.hass, user_input.conversation_id) as session,
            conversation.async_get_chat_log(self.hass, session, user_input) as chat_log,
        ):
            async for _content in chat_log.async_add_delta_content_stream("test_llm", deltas()):
                pass
        response = intent.IntentResponse(language=user_input.language)
        response.async_set_speech("\n" + "".join(self.parts))
        return conversation.ConversationResult(
            response=response, conversation_id=session.conversation_id or uuid.uuid4().hex
        )


async def _with_streaming_fallback(
    hass: HomeAssistant, setup: MockConfigEntry, llm: StreamingLLM
) -> None:
    llm.hass = hass
    llm_entry = MockConfigEntry(domain="test_llm")
    llm_entry.add_to_hass(hass)
    conversation.async_set_agent(hass, llm_entry, llm)
    hass.config_entries.async_update_entry(
        setup, options={CONF_FALLBACK_AGENT: llm_entry.entry_id, CONF_FALLBACK_TIMEOUT: 30}
    )
    await hass.async_block_till_done()


async def test_fallback_agent_streams_through_its_own_conversation(
    hass: HomeAssistant, setup: MockConfigEntry
) -> None:
    parts = (
        "Kanapkę zrobisz sam, ",
        "ja nie mam rąk, ",
        "ale mogę podpowiedzieć przepis na dobrą kanapkę.",
    )
    llm = StreamingLLM(parts)
    await _with_streaming_fallback(hass, setup, llm)

    result, deltas = await _ask_listening(hass, "zrób mi kanapkę")
    spoken = "".join(parts).strip()

    assert _speech(result) == spoken
    assert "".join(_streamed(deltas)) == spoken
    # the agent got its own conversation, not the one the pipeline listens to
    assert llm.conversation_ids[0] and llm.conversation_ids[0] != result.conversation_id

    # a follow-up question in the same conversation: the agent's own conversation goes on
    again, deltas = await _ask_listening(hass, "zrób mi drugą kanapkę", result.conversation_id)
    assert again.conversation_id == result.conversation_id
    assert llm.conversation_ids == [llm.conversation_ids[0]] * 2
    assert "".join(_streamed(deltas)) == spoken


async def test_fallback_agent_failing_halfway_keeps_what_was_said(
    hass: HomeAssistant, setup: MockConfigEntry
) -> None:
    llm = StreamingLLM(("Kanapkę zrobisz sam, ", "ja nie mam rąk."), fail=True)
    await _with_streaming_fallback(hass, setup, llm)

    result, deltas = await _ask_listening(hass, "zrób mi kanapkę")

    assert _speech(result) == "Kanapkę zrobisz sam, ja nie mam rąk."
    assert "".join(_streamed(deltas)) == _speech(result)


async def test_fallback_agent_without_the_pipeline_answers_as_before(
    hass: HomeAssistant, setup: MockConfigEntry
) -> None:
    llm = StreamingLLM(("Kanapkę zrobisz sam.",))
    await _with_streaming_fallback(hass, setup, llm)

    result = await conversation.async_converse(
        hass, "zrób mi kanapkę", None, Context(), language="pl", agent_id=AGENT_ID
    )

    assert _speech(result) == "Kanapkę zrobisz sam."


async def test_commands_waiting_for_an_answer_turn_streaming_off(
    hass: HomeAssistant, setup: MockConfigEntry, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After a question in a sentence with several commands the rest waits; the next turn's
    reply is joined with theirs, so it must not stream."""
    import time

    seen: list[bool] = []

    async def turn(self, user_input, rephrased_from=None, part=False):
        seen.append(agent_module.STREAMING.get())
        response = intent.IntentResponse(language="pl")
        response.async_set_speech("Gotowe.")
        return conversation.ConversationResult(
            response=response, conversation_id=user_input.conversation_id
        )

    monkeypatch.setattr(agent_module.AssistRouterAgent, "_process_turn", turn)
    agent = hass.data["entity_components"]["conversation"].get_entity(AGENT_ID)

    await _ask_listening(hass, "tak")
    with chat_session.async_get_chat_session(hass) as session:
        conversation_id = session.conversation_id
    agent._queued[conversation_id] = (["włącz światło"], time.monotonic() + 30)
    await _ask_listening(hass, "tak", conversation_id)

    assert seen == [True, False, False]  # the answer and the waiting command
    assert agent_module.STREAMING.get() is True
