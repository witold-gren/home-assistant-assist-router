"""Adding the integration in one click. Options: a menu - settings (CSV log, fallback
agent, router), editing the router.yaml file and example commands for this home."""

from __future__ import annotations

import asyncio
from pathlib import Path
import shutil
from typing import Any

import aiohttp
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector
import voluptuous as vol
import yaml

from . import examples
from .const import (
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
    TITLE,
)
from .log_file import markdown_table
from .router import async_list_models, parse_config

SELF_ENTITY = "conversation.assist_router"
# the step description has a limit - a longer examples preview is cut (full: the file)
PREVIEW_CHARS = 6000
LOG_PREVIEW_ROWS = 30  # latest log entries in the preview


def _seconds(minimum: int, maximum: int) -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=minimum,
            max=maximum,
            step=1,
            unit_of_measurement="s",
            mode=selector.NumberSelectorMode.BOX,
        )
    )


class AssistRouterConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title=TITLE, data={})
        return self.async_show_form(step_id="user")

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return AssistRouterOptionsFlow()


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def _write_with_backup(path: Path, text: str) -> None:
    """New file content; the previous one is kept alongside as .bak."""
    if path.exists():
        shutil.copy2(path, path.with_name(path.name + ".bak"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _preview(data: dict[str, Any]) -> str:
    """Working topic sentences as markdown for the step description."""
    lines: list[str] = []
    for name, topic in data.items():
        if not isinstance(topic, dict):
            continue
        working = examples.working(topic)
        rejected = len(examples.rejected(topic))
        lines.append(f"**{name}** ({len(working)} ✓, {rejected} ✗)")
        lines.extend(f"- {text}" for text in working)
    text = "\n".join(lines) or "-"
    return text if len(text) <= PREVIEW_CHARS else text[:PREVIEW_CHARS] + "\n…"


class AssistRouterOptionsFlow(OptionsFlow):
    """Menu: settings (steps 1 and 2), router file, example commands."""

    def __init__(self) -> None:
        self._options: dict[str, Any] = {}
        self._models: list[str] = []
        self._task: asyncio.Task | None = None
        self._per_topic = 5
        self._result: dict[str, Any] | None = None
        self._error: str | None = None

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_show_menu(
            step_id="init", menu_options=["settings", "router_file", "examples", "log"]
        )

    # --- router.yaml file ---

    async def async_step_router_file(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit /config/assist/router.yaml: validated before saving, the old one kept as .bak.

        The router reads the file again after a change - no restart and no reload.
        """
        path: Path = self.config_entry.runtime_data.router.path
        errors: dict[str, str] = {}
        placeholders = {"path": str(path), "error": ""}
        if user_input is not None:
            text = user_input.get("content") or ""
            try:
                parse_config(yaml.safe_load(text))
            except (ValueError, TypeError, AttributeError, yaml.YAMLError) as err:
                errors["base"] = "invalid_router"
                placeholders["error"] = str(err)
            else:
                await self.hass.async_add_executor_job(_write_with_backup, path, text)
                return self.async_abort(
                    reason="router_saved", description_placeholders=placeholders
                )
            content = text
        else:
            content = await self.hass.async_add_executor_job(_read, path)
        schema = vol.Schema(
            {
                vol.Required("content", default=content): selector.TextSelector(
                    selector.TextSelectorConfig(multiline=True)
                )
            }
        )
        return self.async_show_form(
            step_id="router_file",
            data_schema=schema,
            errors=errors,
            description_placeholders=placeholders,
        )

    # --- example commands ---

    async def async_step_examples(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Preview of saved examples; ticking „wygeneruj” = new ones (a few minutes)."""
        path = self.config_entry.runtime_data.router.path.with_name(examples.EXAMPLES_FILE)
        if user_input is not None:
            if not user_input.get("generate"):
                return self.async_abort(reason="examples_closed")
            self._per_topic = int(user_input.get("per_topic", 5))
            return await self.async_step_examples_generate()
        data = await self.hass.async_add_executor_job(examples.load, path)
        schema = vol.Schema(
            {
                vol.Optional("generate", default=not data): selector.BooleanSelector(),
                vol.Optional("per_topic", default=5): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1, max=20, step=1, mode=selector.NumberSelectorMode.BOX
                    )
                ),
            }
        )
        return self.async_show_form(
            step_id="examples",
            data_schema=schema,
            description_placeholders={"path": str(path), "examples": _preview(data)},
        )

    async def async_step_examples_generate(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        agent = self.config_entry.runtime_data.agent
        if self._task is None:
            if agent is None:
                return self.async_abort(reason="not_loaded")
            self._task = self.hass.async_create_task(
                agent.async_generate_examples(self._per_topic), "assist_router examples"
            )
        if not self._task.done():
            return self.async_show_progress(
                step_id="examples_generate",
                progress_action="generating",
                progress_task=self._task,
            )
        try:
            self._result = self._task.result()
        except Exception as err:
            self._error = str(err)
            return self.async_show_progress_done(next_step_id="examples_failed")
        return self.async_show_progress_done(next_step_id="examples_done")

    async def async_step_examples_done(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        topics = (self._result or {}).get("topics", {})
        working = sum(t["working"] for t in topics.values())
        rejected = sum(t["rejected"] for t in topics.values())
        return self.async_abort(
            reason="examples_saved",
            description_placeholders={
                "working": str(working),
                "rejected": str(rejected),
                "path": str((self._result or {}).get("file", "")),
            },
        )

    async def async_step_examples_failed(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return self.async_abort(
            reason="examples_failed", description_placeholders={"error": self._error or "?"}
        )

    # --- unrecognized log ---

    async def async_step_log(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Latest unrecognized commands as a table; ticking „wyczyść” clears the file."""
        log = self.config_entry.runtime_data.log
        if user_input is not None:
            if not user_input.get("clear"):
                return self.async_abort(reason="log_closed")
            count = await log.async_clear()
            return self.async_abort(
                reason="log_cleared",
                description_placeholders={"count": str(count), "path": str(log.path)},
            )
        rows = await log.async_rows()
        return self.async_show_form(
            step_id="log",
            data_schema=vol.Schema(
                {vol.Optional("clear", default=False): selector.BooleanSelector()}
            ),
            description_placeholders={
                "path": str(log.path),
                "count": str(len(rows)),
                "shown": str(min(len(rows), LOG_PREVIEW_ROWS)),
                "table": markdown_table(rows, LOG_PREVIEW_ROWS),
            },
        )

    # --- settings ---

    async def async_step_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            if user_input.get(CONF_FALLBACK_AGENT) == SELF_ENTITY:
                user_input.pop(CONF_FALLBACK_AGENT)
            url = (user_input.get(CONF_OLLAMA_URL) or "").strip().rstrip("/")
            self._options = {**user_input}
            if not url:
                # without an address the router is disabled
                self._options.pop(CONF_OLLAMA_URL, None)
                return self.async_create_entry(data=self._options)
            self._options[CONF_OLLAMA_URL] = url
            try:
                self._models = await async_list_models(self.hass, url)
            except (TimeoutError, aiohttp.ClientError, ValueError):
                errors[CONF_OLLAMA_URL] = "cannot_connect"
            else:
                if self._models:
                    return await self.async_step_router()
                errors[CONF_OLLAMA_URL] = "no_models"
        options = {**self.config_entry.options, **(user_input or {})}
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_LOG_UNRECOGNIZED,
                    default=options.get(CONF_LOG_UNRECOGNIZED, DEFAULT_LOG_UNRECOGNIZED),
                ): selector.BooleanSelector(),
                vol.Optional(
                    CONF_FALLBACK_AGENT,
                    description={"suggested_value": options.get(CONF_FALLBACK_AGENT)},
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain="conversation", exclude_entities=[SELF_ENTITY]
                    )
                ),
                vol.Required(
                    CONF_FALLBACK_TIMEOUT,
                    default=options.get(CONF_FALLBACK_TIMEOUT, DEFAULT_FALLBACK_TIMEOUT),
                ): _seconds(5, 120),
                vol.Optional(
                    CONF_OLLAMA_URL,
                    description={"suggested_value": options.get(CONF_OLLAMA_URL)},
                ): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.URL)
                ),
            }
        )
        return self.async_show_form(step_id="settings", data_schema=schema, errors=errors)

    async def async_step_router(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            # without an answer model the automation text / start of the article is read
            return self.async_create_entry(data={**self._options, **user_input})
        options = self.config_entry.options
        current = options.get(CONF_ROUTER_MODEL)
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_ROUTER_MODEL,
                    default=current if current in self._models else self._models[0],
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=self._models, mode=selector.SelectSelectorMode.DROPDOWN
                    )
                ),
                vol.Optional(
                    CONF_ANSWER_MODEL,
                    description={"suggested_value": options.get(CONF_ANSWER_MODEL)},
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=self._models, mode=selector.SelectSelectorMode.DROPDOWN
                    )
                ),
                vol.Required(
                    CONF_ANSWER_TIMEOUT,
                    default=options.get(CONF_ANSWER_TIMEOUT, DEFAULT_ANSWER_TIMEOUT),
                ): _seconds(2, 120),
                vol.Required(
                    CONF_ROUTER_TIMEOUT,
                    default=options.get(CONF_ROUTER_TIMEOUT, DEFAULT_ROUTER_TIMEOUT),
                ): _seconds(2, 60),
                vol.Required(
                    CONF_ROUTER_KEEP_ALIVE,
                    default=options.get(CONF_ROUTER_KEEP_ALIVE, DEFAULT_ROUTER_KEEP_ALIVE),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=-1,
                        max=1440,
                        step=1,
                        unit_of_measurement="min",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
            }
        )
        return self.async_show_form(step_id="router", data_schema=schema)
