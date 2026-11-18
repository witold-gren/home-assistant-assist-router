"""Streaming a spoken answer: text to speech starts while the model is still writing.

The Assist pipeline listens to the chat log of its conversation. Text added there as deltas
(``ChatLog.async_add_delta_content_stream``) goes to a text to speech engine that takes text
in parts (e.g. Piper over Wyoming) once there is enough of it; a short answer is read as a
whole, as before. ``ReplyStream`` writes one answer there piece by piece, with the same
clean-up the finished answer gets: whitespace collapsed (``" ".join(text.split())``), the
persona's grammatical gender applied to whole words, an optional opening sentence first.

Streaming happens only when somebody listens: inside the pipeline's chat log of the same
conversation (``listening_chat_log``). Anywhere else - typed questions without a pipeline,
the editor's tester - the answer is made as a whole, exactly as before.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
import logging

from homeassistant.components.conversation.chat_log import ChatLog, current_chat_log
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

_END = None  # the end of the stream in the queue


def listening_chat_log(conversation_id: str | None) -> ChatLog | None:
    """The pipeline's chat log of this conversation when it listens to deltas, else None."""
    chat_log = current_chat_log.get()
    if (
        chat_log is None
        or chat_log.delta_listener is None
        or not conversation_id
        or chat_log.conversation_id != conversation_id
    ):
        return None
    return chat_log


class ReplyStream:
    """One spoken answer written into a chat log as it comes.

    ``push`` takes raw text of any size (a model's token, a sentence); the text goes on in
    whole words. ``finish`` sends the last word and returns the whole spoken text - the
    speech of the result must be exactly this text (the pipeline does not read the result's
    speech once it has streamed).
    """

    def __init__(
        self,
        hass: HomeAssistant,
        chat_log: ChatLog,
        agent_id: str,
        *,
        prefix: str = "",
        words: Callable[[str], str] | None = None,
    ) -> None:
        self._words = words or (lambda text: text)
        self._prefix = prefix  # said with the first words of the answer, never alone
        self._queue: asyncio.Queue[str | None] = asyncio.Queue()
        self._rest = ""  # the start of a word that may go on in the next part
        self.text = ""  # spoken so far
        self._task = hass.async_create_task(
            self._write(chat_log, agent_id), "assist_router reply stream", eager_start=False
        )

    def push(self, text: str) -> None:
        if not text or not (self.text or self._rest or text.strip()):
            return  # nothing yet: leading whitespace is not an answer
        if self._prefix:
            text, self._prefix = f"{self._prefix} {text}", ""
        text = self._rest + text
        cut = max(text.rfind(" "), text.rfind("\n"), text.rfind("\t"))
        if cut < 0:
            self._rest = text
            return
        self._rest = text[cut + 1 :]
        self._say(text[: cut + 1])

    async def finish(self) -> str:
        """Send the rest, wait until the chat log has it all; the whole spoken text."""
        self._say(self._rest)
        self._rest = ""
        self._queue.put_nowait(_END)
        try:
            await self._task
        except Exception:
            # the chat log must not break the answer - the result still carries it
            _LOGGER.warning("Could not stream the answer to the chat log", exc_info=True)
        return self.text

    def _say(self, text: str) -> None:
        words = " ".join(text.split())
        if not words:
            return
        part = self._words(words)
        if self.text:
            part = " " + part
        self.text += part
        self._queue.put_nowait(part)

    async def _write(self, chat_log: ChatLog, agent_id: str) -> None:
        async for _content in chat_log.async_add_delta_content_stream(agent_id, self._deltas()):
            pass

    async def _deltas(self) -> AsyncIterator[dict]:
        first = await self._queue.get()
        if first is _END:
            return  # nothing said: no assistant message at all
        yield {"role": "assistant"}
        yield {"content": first}
        while (part := await self._queue.get()) is not _END:
            yield {"content": part}
