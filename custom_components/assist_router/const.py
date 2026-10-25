"""Constants of the Assist Router integration (domain assist_router)."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "assist_router"

# File in the HA config directory: /config/assist/unrecognized_commands.csv
LOG_DIR: Final = "assist"
LOG_FILE: Final = "unrecognized_commands.csv"

KIND_NO_MATCH: Final = "no_intent_match"
KIND_NO_TARGET: Final = "no_valid_targets"

EVENT_UNRECOGNIZED: Final = "assist_router_unrecognized"

# route: the router topic and the template sentence, e.g.
# „kalendarz → jakie są jutro wydarzenia”
COLUMNS: Final = (
    "timestamp", "area", "device", "kind", "text", "response", "route", "speaker",
)  # fmt: skip

# Fallback agent (e.g. Bielik/Ollama) for unrecognized commands - integration options.
CONF_FALLBACK_AGENT: Final = "fallback_agent"
CONF_FALLBACK_TIMEOUT: Final = "fallback_timeout"
DEFAULT_FALLBACK_TIMEOUT: Final = 30

# Writing unrecognized commands to CSV (and an event) - integration options.
CONF_LOG_UNRECOGNIZED: Final = "log_unrecognized"
DEFAULT_LOG_UNRECOGNIZED: Final = True

# Question router (Ollama) - integration options; topics in the ROUTER_FILE file.
CONF_OLLAMA_URL: Final = "ollama_url"
CONF_ROUTER_MODEL: Final = "router_model"
CONF_ROUTER_TIMEOUT: Final = "router_timeout"
CONF_ROUTER_KEEP_ALIVE: Final = "router_keep_alive"
DEFAULT_ROUTER_TIMEOUT: Final = 8
DEFAULT_ROUTER_KEEP_ALIVE: Final = -1
ROUTER_FILE: Final = "router.yaml"
# new example commands saved (the sensor reads the file again)
SIGNAL_EXAMPLES: Final = "assist_router_examples"
# new entry in the unrecognized log, or the log cleared (sensor)
SIGNAL_LOG: Final = "assist_router_log"
# Answer model (optional): an answer from HA data and summaries from Wikipedia.
CONF_ANSWER_MODEL: Final = "answer_model"
CONF_ANSWER_TIMEOUT: Final = "answer_timeout"
DEFAULT_ANSWER_TIMEOUT: Final = 15
# Model context in Ollama. An HA Ollama conversation agent using the same model as the
# answer model should have the same context (otherwise Ollama reloads the model).
ROUTER_NUM_CTX: Final = 4096
ANSWER_NUM_CTX: Final = 8192
TITLE: Final = "Assist Router"

# sensor ids independent of the HA language (key = unique id suffix)
ENTITY_IDS = {
    "examples": "sensor.assist_router_example_commands",
    "unrecognized": "sensor.assist_router_unrecognized_commands",
}
# default ids of earlier versions, built by HA from the translated name - renamed on setup
LEGACY_OBJECT_IDS = {
    "examples": ("assist_router_przykladowe_komendy",),
    "unrecognized": ("assist_router_nierozpoznane_komendy",),
}
