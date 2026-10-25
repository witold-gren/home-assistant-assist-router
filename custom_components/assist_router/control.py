"""Control: parsing a command (Ollama, JSON) into an HA intent and its parameters.

The model gets a command HA did not recognize and returns the intent and parameters chosen
from lists (intents, domains, areas, floors) plus the fragment naming the device. Python
matches that fragment with the names and aliases of the entities exposed to Assist (word
stems, so inflected forms match), computes relative changes ("brighter") and decides whether
to ask first. HA executes it - ``intent.async_handle``: target matching, exposure check, the
satellite's room as the default.

Words, prompts and replies come from the active language pack (``languages``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
import fnmatch
import json
import re
from typing import Any

from homeassistant.components.homeassistant.exposed_entities import async_should_expose
from homeassistant.components.media_player import MediaPlayerEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.helpers import (
    area_registry as ar,
    entity_registry as er,
    floor_registry as fr,
)

from .languages import LANG

# Actions: to the user a script and a scene are the same ("do X") - the model mixes them up,
# so the name is looked up in both; and they are always started (HassTurnOff stops a script).
ACTION_DOMAINS = frozenset({"script", "scene"})
# Commands for devices in a room - without a room: the speaker's room
# (without an area HA takes ALL devices of that kind in the home).
PLACE_INTENTS = frozenset({
    "HassTurnOn", "HassTurnOff", "HassLightSet", "HassSetPosition",
    "HassClimateSetTemperature", "HassSetVolume", "HassSetVolumeRelative",
})  # fmt: skip
LARGE_SCOPE = 8  # this many devices at once without "all/whole" - ask first
# kind (HA class from MEDIA_CLASSES) -> media_type of music_assistant.play_media; "" = no kind
# (MA looks for the best match); MA does not play a genre - search_media is used
MA_MEDIA_TYPES: dict[str, str | None] = {
    "": "", "track": "track", "album": "album", "artist": "artist",
    "playlist": "playlist", "podcast": "podcast", "genre": None,
}  # fmt: skip
COLOR_MODES = {"hs", "xy", "rgb", "rgbw", "rgbww"}
SEARCH_AND_PLAY = MediaPlayerEntityFeature.SEARCH_MEDIA | MediaPlayerEntityFeature.PLAY_MEDIA
# how much "brighter", "higher", "warmer" without a number changes
STEP = {"brightness": 25, "position": 25, "temperature": 1.0}
SENSITIVE_COVER_CLASSES = {"garage", "gate", "door"}
# name match: below CERTAIN = ask; two results closer than AMBIGUOUS = ask
CERTAIN = 0.8
AMBIGUOUS = 0.1


def text_aliases(aliases: Any) -> list[str]:
    """Aliases that are text. Newer HA also stores markers (ComputedNameType - "use the
    entity name") among entity aliases; they mean the name, which is listed anyway."""
    return [alias for alias in aliases or () if isinstance(alias, str)]


def prepare_text(text: str) -> tuple[str, list[str]]:
    """The command after speech recognition fixes, and the reasons to ask first."""
    return LANG.prepare_text(text)


def stems(text: str) -> list[str]:
    """Word stems for comparing inflected forms (language pack)."""
    return LANG.stems(text)


@dataclass
class Target:
    entity_id: str
    name: str
    domain: str
    device_class: str | None
    area: str | None
    names: list[str]  # name and aliases


@dataclass
class Home:
    """Entities exposed to Assist, areas (with aliases) and floors."""

    targets: list[Target]
    areas: dict[str, str]  # name or alias -> area name
    floors: dict[str, str]
    domains: list[str]


def home_from_dict(data: dict[str, Any]) -> Home:
    """Home from a snapshot (tools/snapshot_data.py) - parser tests without a running HA."""
    targets = [Target(**t) for t in data["targets"]]
    return Home(targets, data["areas"], data["floors"], data["domains"])


def home_to_dict(home: Home) -> dict[str, Any]:
    return {
        "targets": [t.__dict__ for t in home.targets],
        "areas": home.areas,
        "floors": home.floors,
        "domains": home.domains,
    }


def collect_home(hass: HomeAssistant) -> Home:
    ent_reg = er.async_get(hass)
    area_reg = ar.async_get(hass)
    floors = {
        alias: floor.name
        for floor in fr.async_get(hass).async_list_floors()
        for alias in (floor.name, *text_aliases(floor.aliases))
    }
    areas = {
        alias: area.name
        for area in area_reg.async_list_areas()
        for alias in (area.name, *text_aliases(area.aliases))
    }
    targets = []
    for state in hass.states.async_all():
        if not async_should_expose(hass, "conversation", state.entity_id):
            continue
        entry = ent_reg.async_get(state.entity_id)
        area_id = entry.area_id if entry else None
        if entry and not area_id and entry.device_id:
            from homeassistant.helpers import device_registry as dr

            device = dr.async_get(hass).async_get(entry.device_id)
            area_id = device.area_id if device else None
        area = area_reg.async_get_area(area_id) if area_id else None
        aliases = text_aliases(entry.aliases if entry else ())
        targets.append(
            Target(
                entity_id=state.entity_id,
                name=state.name,
                domain=state.domain,
                device_class=state.attributes.get("device_class"),
                area=area.name if area else None,
                names=[state.name, *aliases],
            )
        )
    domains = sorted({t.domain for t in targets} & set(LANG.DOMAINS))
    return Home(targets, areas, floors, domains)


# --- parser prompt and schema ---


def build_control_prompt(
    home: Home, household: str = "", actions: dict[str, str] | None = None
) -> str:
    """Parser prompt; ``actions`` - scripts (name -> description) the model may choose when
    the command asks for something a script does ("make coffee")."""
    intents = "; ".join(f"{name} ({desc})" for name, (desc, _) in LANG.INTENTS.items())
    scripts = "; ".join(
        f"„{name}”" + (f" - {' '.join(desc.split())[:160]}" if desc else "")
        for name, desc in (actions or {}).items()
    )
    domains = "; ".join(f"{d} ({LANG.DOMAINS[d]})" for d in home.domains)
    return LANG.control_prompt(
        intents=intents,
        domains=domains,
        areas=", ".join(sorted(set(home.areas.values()))),
        floors=", ".join(sorted(set(home.floors.values()))),
        household=household,
        scripts=scripts,
    )


def build_control_schema(home: Home) -> dict[str, Any]:
    def nullable(values: list[str]) -> dict[str, Any]:
        return {"type": ["string", "null"], "enum": [*values, None]}

    properties = {
        "intent": {"type": "string", "enum": list(LANG.INTENTS)},
        "domain": nullable(home.domains),
        "area": nullable(sorted(set(home.areas.values()))),
        "floor": nullable(sorted(set(home.floors.values()))),
        "name": {"type": ["string", "null"]},
        "all": {"type": "boolean"},
        "value": {"type": ["number", "null"]},
        "change": nullable(list(LANG.CHANGES)),
        "item": {"type": ["string", "null"]},
        "color": nullable(list(LANG.COLORS)),
        "white": nullable(list(LANG.WHITES)),
        "query": {"type": ["string", "null"]},
        "media_class": nullable(list(LANG.MEDIA_CLASSES)),
        "artist": {"type": ["string", "null"]},
        "radio": {"type": "boolean"},
    }
    keys = LANG.CONTROL_KEYS
    return {
        "type": "object",
        "properties": {keys[k]: v for k, v in properties.items()},
        "required": [keys[k] for k in properties],
    }


@dataclass
class Command:
    intent: str
    domain: str | None = None
    area: str | None = None
    floor: str | None = None
    name: str | None = None
    all: bool = False
    value: float | None = None
    change: str | None = None
    item: str | None = None
    color: str | None = None  # color name from LANG.COLORS
    white: str | None = None  # shade of white from LANG.WHITES
    query: str | None = None
    media_class: str | None = None  # kind name from LANG.MEDIA_CLASSES
    artist: str | None = None  # artist of a track or album („Małomiasteczkowy Dawida Podsiadło”)
    radio: bool = False  # „w stylu …”, „radio z …” - endless similar music (Music Assistant)


def _text(value: Any) -> str | None:
    return " ".join(value.split()) or None if isinstance(value, str) else None


def parse_command(home: Home, content: str) -> Command | None:
    try:
        raw = json.loads(content)
    except ValueError:
        return None
    if not isinstance(raw, dict):
        return None
    data = {key: raw.get(json_key) for key, json_key in LANG.CONTROL_KEYS.items()}
    if data["intent"] not in LANG.INTENTS:
        return None
    value = data["value"]
    name = data["name"]
    return Command(
        intent=data["intent"],
        domain=data["domain"] if data["domain"] in home.domains else None,
        area=home.areas.get(data["area"] or ""),
        floor=home.floors.get(data["floor"] or ""),
        name=" ".join(name.split()) or None if isinstance(name, str) else None,
        all=bool(data["all"]),
        value=float(value) if isinstance(value, (int, float)) else None,
        change=data["change"] if data["change"] in LANG.CHANGES else None,
        item=(data["item"] or None) if isinstance(data["item"], str) else None,
        color=data["color"] if data["color"] in LANG.COLORS else None,
        white=data["white"] if data["white"] in LANG.WHITES else None,
        query=_text(data["query"]),
        media_class=data["media_class"] if data["media_class"] in LANG.MEDIA_CLASSES else None,
        artist=_text(data["artist"]),
        radio=bool(data["radio"]),
    )


# --- device name matching ---


@dataclass
class Match:
    target: Target | None
    score: float
    ambiguous: bool = False
    alternatives: list[Target] = field(default_factory=list)


def _domain_ok(domain: str, wanted: str | None) -> bool:
    if not wanted:
        return True
    if wanted in ACTION_DOMAINS:
        return domain in ACTION_DOMAINS
    return domain == wanted


def normalize_action(command: Command, match: Match | None) -> None:
    """Script or scene - always run (with its own domain, not the one the model guessed)."""
    if match and match.target and match.target.domain in ACTION_DOMAINS:
        command.domain = match.target.domain
        if command.intent == "HassTurnOff":
            command.intent = "HassTurnOn"


# kinds of devices a script or scene can be confused with ("uruchom ekspres" - the machine)
DEVICE_DOMAINS = frozenset({
    "light", "switch", "cover", "media_player", "climate", "fan", "vacuum", "lock", "valve",
    "button",
})  # fmt: skip


def devices_named_in(home: Home, text: str, words: set[str]) -> list[Target]:
    """Devices (not scripts or scenes) whose name uses one of ``words`` said in the command.

    Only word stems of 3+ letters count, so prepositions („do”, „w”) do not match.
    """
    said = {w for w in words if len(w) >= 3}
    found = []
    for target in home.targets:
        if target.domain not in DEVICE_DOMAINS:
            continue
        area = set(stems(target.area)) if target.area else set()
        if any(said & (set(stems(name)) - area) for name in target.names):
            found.append(target)
    return found


def action_or_device(home: Home, text: str, target: Target) -> Target | None:
    """A device the command may mean instead of the script or scene the model chose.

    „Uruchom ekspres do kawy” shares only „ekspres” with the script „Ekspres - zrób kawę” -
    and the same word names the coffee machine, so the command may be about the device.
    """
    said = set(stems(text))
    shared = set()
    for name in target.names:
        shared |= said & set(stems(name))
    rivals = devices_named_in(home, text, shared)
    return rivals[0] if rivals else None


def resolve_in_text(home: Home, text: str, command: Command) -> Match:
    """Device whose name words (without the room name) were all said in the command.

    For „zgaś lampę w garderobie” when the model gave only „lampę”: „Garderoba Lampa”
    has both words in the command. The name with the most words wins.
    """
    said = set(stems(text))
    found: list[tuple[int, Target]] = []
    for target in home.targets:
        if not _domain_ok(target.domain, command.domain):
            continue
        for name in target.names:
            have = set(stems(name))
            if target.area:
                have = (have - set(stems(target.area))) or have
            if len(have) >= 2 and have <= said:
                found.append((len(have), target))
                break
    if not found:
        return Match(None, 0.0)
    found.sort(key=lambda f: -f[0])
    best_len, best = found[0]
    rivals = [t for n, t in found[1:] if n == best_len and t.entity_id != best.entity_id]
    return Match(best, 1.0, ambiguous=bool(rivals), alternatives=rivals[:3])


def resolve_name(home: Home, fragment: str, command: Command) -> Match:
    """The device meant: word stems compared with names and aliases.

    Score (stem F1): 1.0 = the same words in any inflection; the area and domain from the
    command narrow down the candidates, and a shared room boosts the score.
    """
    wanted = set(stems(fragment))
    if not wanted:
        return Match(None, 0.0)
    scored: list[tuple[float, Target]] = []
    for target in home.targets:
        if not _domain_ok(target.domain, command.domain):
            continue
        best = 0.0
        # a room given together with the name („Łazienka HomePod”) does not count toward
        # the name either
        said = (wanted - set(stems(target.area))) or wanted if target.area else wanted
        for name in target.names:
            have = set(stems(name))
            # the room name inside the device name need not be said in the command
            if target.area:
                have_without_area = have - set(stems(target.area))
                have = have_without_area or have
            common = len(said & have)
            if common:
                precision, recall = common / len(have), common / len(said)
                best = max(best, 2 * precision * recall / (precision + recall))
        if best and command.area and target.area == command.area:
            best = min(1.0, best + 0.05)
        if best:
            scored.append((best, target))
    if not scored:
        return Match(None, 0.0)
    scored.sort(key=lambda s: -s[0])
    top_score, top = scored[0]
    close = [t for s, t in scored[1:] if top_score - s < AMBIGUOUS and t.entity_id != top.entity_id]
    return Match(top, top_score, ambiguous=bool(close), alternatives=close[:3])


# --- intent parameters, relative changes, confirmation ---


@dataclass
class Plan:
    """What to execute: intent, HA slots, description for the question and whether to ask."""

    intent: str
    slots: dict[str, Any]
    description: str
    confirm: str | None = None  # reason for asking (for the log)
    domain: str | None = None  # target domain (lock, covers - different verbs)
    error: str | None = None  # cannot be executed - message for the user
    # an "are you sure" question (lock, confirmation list) instead of "did I get it right";
    # after "no" we do nothing, instead of asking to repeat
    sensitive: bool = False
    entity_id: str | None = None  # a single target entity (e.g. a script - run with variables)
    # twin entities of the target (same name and room); the HA intent rejects such a name
    twins: tuple[str, ...] = ()


def twins(home: Home, target: Target) -> list[Target]:
    """Entities with the same name in the same room: one device seen by two integrations
    (HomePod: Apple TV and Music Assistant). The HA intent rejects such a name
    (DUPLICATE_NAME), so we call the service on each of them (``twin_calls``)."""
    key = target.name.lower()
    return [
        t
        for t in home.targets
        if t.name.lower() == key and t.area == target.area and t.domain == target.domain
    ]


def twin_calls(plan: Plan) -> list[tuple[str, str, dict[str, Any]]] | None:
    """Services instead of the intent for twins (no entity_id); None = no equivalent."""
    slots = plan.slots
    simple = {
        "HassTurnOn": ("homeassistant", "turn_on"),
        "HassTurnOff": ("homeassistant", "turn_off"),
        "HassMediaPause": ("media_player", "media_pause"),
        "HassMediaUnpause": ("media_player", "media_play"),
        "HassMediaNext": ("media_player", "media_next_track"),
        "HassMediaPrevious": ("media_player", "media_previous_track"),
        "HassVacuumStart": ("vacuum", "start"),
        "HassVacuumReturnToBase": ("vacuum", "return_to_base"),
    }
    if plan.intent in simple:
        return [(*simple[plan.intent], {})]
    if plan.intent == "HassSetVolume":
        return [("media_player", "volume_set", {"volume_level": slots["volume_level"] / 100})]
    if plan.intent == "HassSetVolumeRelative":
        step = "volume_down" if slots.get("volume_step") == "down" else "volume_up"
        return [("media_player", step, {})]
    if plan.intent == "HassSetPosition":
        return [("cover", "set_cover_position", {"position": slots["position"]})]
    if plan.intent == "HassClimateSetTemperature":
        return [("climate", "set_temperature", {"temperature": slots["temperature"]})]
    if plan.intent == "HassLightSet":
        data: dict[str, Any] = {}
        if "brightness" in slots:
            data["brightness_pct"] = slots["brightness"]
        if "color" in slots:
            data["color_name"] = slots["color"]
        if "temperature" in slots:
            data["color_temp_kelvin"] = slots["temperature"]
        return [("light", "turn_on", data)]
    return None


def _targets_in_scope(home: Home, command: Command, match: Match | None) -> list[Target]:
    if match and match.target:
        return [match.target]
    return [
        t
        for t in home.targets
        if (not command.domain or t.domain == command.domain)
        and (not command.area or t.area == command.area)
    ]


def _relative(
    hass: HomeAssistant, targets: list[Target], attribute: str, change: str
) -> float | None:
    """New value for „jaśniej/ciemniej”, „wyżej/niżej”, „cieplej/chłodniej”."""
    values = []
    for target in targets:
        state = hass.states.get(target.entity_id)
        if state is None:
            continue
        if attribute == "brightness":
            raw = state.attributes.get("brightness")
            values.append(
                round(raw / 255 * 100) if raw is not None else (0 if state.state == "off" else 100)
            )
        elif attribute == "position" and state.attributes.get("current_position") is not None:
            values.append(state.attributes["current_position"])
        elif attribute == "temperature" and state.attributes.get("temperature") is not None:
            values.append(state.attributes["temperature"])
    if not values:
        return None
    current = sum(values) / len(values)
    step = STEP[attribute] if change == LANG.CHANGE_MORE else -STEP[attribute]
    new = current + step
    return max(0, min(100, round(new))) if attribute != "temperature" else round(new * 2) / 2


def describe(command: Command, match: Match | None) -> str:
    """What is going to be done, for the confirmation question (language pack)."""
    return LANG.describe(command, match)


def area_mentioned(home: Home, area: str, text: str) -> bool:
    """Whether the area (name or alias, inflected) was said in the command - the model can
    confuse „garderobie” with „Garaż”."""
    said = set(stems(text))
    return any(
        set(stems(alias)) <= said
        for alias, name in home.areas.items()
        if name == area and stems(alias)
    )


def find_target(home: Home, command: Command, text: str = "") -> Match | None:
    """Device from the model's fragment; when uncertain or ambiguous - from the whole command."""
    if text and command.area and not area_mentioned(home, command.area, text):
        command.area = None
    match = resolve_name(home, command.name, command) if command.name else None
    weak = match is None or match.target is None or match.score < CERTAIN or match.ambiguous
    if text and weak:
        in_text = resolve_in_text(home, text, command)
        if in_text.target and (command.name or not command.area):
            # several good candidates: they are replaced only by a device whose name has more
            # words from the command („lampę w garderobie” -> Garderoba Lampa), not as many
            # („roletą wewnętrzną okno” - the outer window blind does not beat the inner ones)
            strong = match and match.target and match.ambiguous and match.score >= CERTAIN
            said = set(stems(text))
            if not strong or _said(in_text.target, said) > _said(match.target, said):
                return in_text
    return match


def _said(target: Target, said: set[str]) -> int:
    """How many words of some device name (with the room) were said in the command."""
    return max(len(set(stems(name)) & said) for name in target.names)


def plan_command(
    hass: HomeAssistant,
    home: Home,
    command: Command,
    text: str = "",
    doubts: list[str] | None = None,
    confirm_entities: tuple[str, ...] = (),
    music_players: dict[str, tuple[str, ...]] | None = None,
    here: str | None = None,
) -> Plan:
    """Command execution plan.

    ``confirm_entities`` - entity_id patterns or device names that always require asking
    (fridge, servers); ``music_players`` - area -> players in order (first available);
    ``here`` - the satellite's area when the command names no room.
    """
    if command.intent == "HassLightSet" and not command.domain:
        command.domain = "light"
    if command.intent == "HassMediaSearchAndPlay":
        return _plan_play(hass, home, command, text, music_players or {}, here)
    match = find_target(home, command, text)
    normalize_action(command, match)
    same = twins(home, match.target) if match and match.target else []
    if match and match.ambiguous and all(t in same for t in match.alternatives):
        match.ambiguous = False  # "several matches" is one device from two integrations
    slots: dict[str, Any] = {}
    confirm = "; ".join(doubts) if doubts else None
    sensitive = False

    if match and match.target and not match.ambiguous and match.score >= CERTAIN:
        slots["name"] = match.target.name
    elif match and match.target:
        slots["name"] = match.target.name
        confirm = (
            LANG.CONFIRM_UNCERTAIN_NAME if not match.ambiguous else LANG.CONFIRM_SEVERAL_DEVICES
        )
    if match and match.target and match.ambiguous:
        confirm = LANG.CONFIRM_SEVERAL_DEVICES
    elif not (match and match.target) and command.name and not command.area and not command.domain:
        return Plan(
            command.intent,
            {},
            describe(command, match),
            error=LANG.ERROR_DEVICE_NOT_FOUND.format(name=command.name),
        )
    if (
        text
        and match
        and match.target
        and match.target.domain in ACTION_DOMAINS
        and (device := action_or_device(home, text, match.target))
    ):
        # the model chose a script, but the words that point to it also name a device
        confirm = LANG.CONFIRM_ACTION_OR_DEVICE.format(device=device.name)
    no_place = (
        command.intent in PLACE_INTENTS
        and "name" not in slots
        and not command.area
        and not command.floor
        and not command.all
    )
    if no_place:
        if not here:
            return Plan(
                command.intent,
                {},
                describe(command, match),
                error=LANG.ERROR_WHICH_ROOM,
            )
        command.area = here  # the room of the speaker the command came from
    if kind_guessed(command, match, text):
        confirm = LANG.CONFIRM_KIND_GUESSED
    if command.area and "name" not in slots:
        slots["area"] = command.area
    if command.floor and "name" not in slots and "area" not in slots:
        slots["floor"] = command.floor
    if command.domain and "name" not in slots:
        slots["domain"] = [command.domain]

    targets = _targets_in_scope(home, command, match)
    if text and len(targets) > LARGE_SCOPE and not LANG.WHOLE_HOUSE.search(text):
        confirm = LANG.CONFIRM_LARGE_SCOPE.format(count=len(targets))
    if any(
        t.domain == "lock" or (t.domain == "cover" and t.device_class in SENSITIVE_COVER_CLASSES)
        for t in targets
    ) and command.intent in ("HassTurnOn", "HassTurnOff", "HassSetPosition"):
        confirm = LANG.CONFIRM_SENSITIVE
        sensitive = True
    if any(always_confirm(t, confirm_entities) for t in targets):
        confirm = LANG.CONFIRM_LISTED
        sensitive = True

    attribute = {
        "HassLightSet": "brightness",
        "HassSetPosition": "position",
        "HassClimateSetTemperature": "temperature",
    }.get(command.intent)
    if command.intent == "HassLightSet" and (command.color or command.white):
        lights = [t for t in targets if t.domain == "light"]
        modes = _color_modes(hass, lights)
        if command.color:
            if lights and not modes & COLOR_MODES:
                return Plan(
                    command.intent,
                    slots,
                    describe(command, match),
                    error=LANG.ERROR_NO_COLOR,
                )
            slots["color"] = LANG.COLORS[command.color]
        else:
            if lights and not modes & (COLOR_MODES | {"color_temp"}):
                return Plan(
                    command.intent,
                    slots,
                    describe(command, match),
                    error=LANG.ERROR_NO_WHITE,
                )
            slots["temperature"] = LANG.WHITES[command.white]
        if command.value is not None:
            slots["brightness"] = max(0, min(100, round(command.value)))
    elif attribute:
        value = command.value
        if value is None and command.change in (LANG.CHANGE_MORE, LANG.CHANGE_LESS):
            value = _relative(hass, targets, attribute, command.change)
        if value is None:
            return Plan(
                command.intent,
                slots,
                describe(command, match),
                error=LANG.ERROR_NO_VALUE,
            )
        slots[attribute] = value
        command.value = value
    elif command.intent == "HassSetVolume":
        if command.value is None:
            return Plan(
                command.intent,
                slots,
                describe(command, match),
                error=LANG.ERROR_NO_VOLUME,
            )
        slots["volume_level"] = max(0, min(100, round(command.value)))
    elif command.intent == "HassSetVolumeRelative":
        slots["volume_step"] = "down" if command.change == LANG.CHANGE_LESS else "up"
    elif command.intent == "HassListAddItem":
        lists = [t for t in home.targets if t.domain == "todo"]
        if not command.item or not lists:
            return Plan(
                command.intent,
                slots,
                describe(command, match),
                error=LANG.ERROR_NO_LIST_ITEM,
            )
        shopping = next((t for t in lists if LANG.SHOPPING_LIST_WORD in t.name.lower()), lists[0])
        slots = {
            "item": command.item,
            "name": (
                match.target.name
                if match and match.target and match.target.domain == "todo"
                else shopping.name
            ),
        }

    if not slots and not command.all:
        # „włącz światło” without a place - the speaker's room (HA: preferred area from device_id)
        slots["domain"] = [command.domain] if command.domain else []
    if "domain" in slots and not slots["domain"]:
        slots.pop("domain")
    domain = match.target.domain if match and match.target else command.domain
    return Plan(
        command.intent,
        slots,
        describe(command, match),
        confirm=confirm,
        domain=domain,
        sensitive=sensitive,
        entity_id=match.target.entity_id if match and match.target else None,
        twins=tuple(t.entity_id for t in same) if len(same) > 1 and "name" in slots else (),
    )


def named_routine(home: Home, text: str) -> Target | None:
    """Script or scene whose name (at least 3 words) someone simply said:
    „Opuść rolety wewnętrzne w salonie” = the script, not a command for the covers."""
    said = set(stems(text)) - LANG.ROUTINE_WORDS
    for target in home.targets:
        if target.domain not in ("script", "scene"):
            continue
        for name in target.names:
            have = set(stems(name))
            if len(have) >= 3 and have == said:
                return target
    return None


def routine_plan(target: Target, confirm_entities: tuple[str, ...] = ()) -> Plan:
    return Plan(
        "HassTurnOn",
        {"name": target.name},
        LANG.describe_routine(target.name),
        confirm=LANG.CONFIRM_LISTED if always_confirm(target, confirm_entities) else None,
        domain=target.domain,
        sensitive=always_confirm(target, confirm_entities),
        entity_id=target.entity_id,
    )


def kind_guessed(command: Command, match: Match | None, text: str) -> bool:
    """The model picked a device kind (e.g. light), although the command has neither a device
    name nor a word pointing to that kind („wyłącz halaryn”)."""
    return bool(
        text
        and command.domain in LANG.DOMAIN_HINTS
        and not (match and match.target)
        and not any(hint in text.lower() for hint in LANG.DOMAIN_HINTS[command.domain])
    )


def always_confirm(target: Target, patterns: tuple[str, ...]) -> bool:
    """Whether the device is on the "always ask" list (entity_id pattern or name)."""
    names = {n.casefold() for n in target.names}
    return any(
        fnmatch.fnmatchcase(target.entity_id, pattern) or pattern.casefold() in names
        for pattern in patterns
    )


def _color_modes(hass: HomeAssistant, lights: list[Target]) -> set[str]:
    modes: set[str] = set()
    for light in lights:
        state = hass.states.get(light.entity_id)
        if state is not None:
            modes |= set(state.attributes.get("supported_color_modes") or ())
    return modes


def _can_play(hass: HomeAssistant, entity_id: str) -> bool:
    state = hass.states.get(entity_id)
    return (
        state is not None
        and state.state != "unavailable"
        and state.attributes.get("supported_features", 0) & SEARCH_AND_PLAY == SEARCH_AND_PLAY
    )


def pick_player(
    hass: HomeAssistant, home: Home, area: str, music_players: dict[str, tuple[str, ...]]
) -> str | None:
    """Player in the room: from the list in router.yaml (first available); without a list,
    an exposed player with search in that area or with the room name in its name
    (Music Assistant players usually have no area)."""
    for key, players in music_players.items():
        if home.areas.get(key, key) == area:
            return next((p for p in players if _can_play(hass, p)), None)
    area_stems = set(stems(area))
    return next(
        (
            t.entity_id
            for t in home.targets
            if t.domain == "media_player"
            and (t.area == area or area_stems <= set(stems(t.name)))
            and _can_play(hass, t.entity_id)
        ),
        None,
    )


def _plan_play(
    hass: HomeAssistant,
    home: Home,
    command: Command,
    text: str,
    music_players: dict[str, tuple[str, ...]],
    here: str | None,
) -> Plan:
    """„Puść …” - search and play on the chosen player (search_media)."""
    command.domain = "media_player"
    if text and command.area and not area_mentioned(home, command.area, text):
        command.area = None
    if not command.query:
        return Plan(command.intent, {}, LANG.PLAY_MUSIC, error=LANG.ERROR_WHAT_TO_PLAY)
    player = None
    if command.name:
        match = resolve_name(home, command.name, command)
        if match.target and match.score >= CERTAIN and _can_play(hass, match.target.entity_id):
            player = match.target.entity_id
    area = command.area or here
    if player is None and area:
        player = pick_player(hass, home, area, music_players)
    if player is None:
        return Plan(
            command.intent,
            {},
            describe(command, None),
            error=(
                LANG.ERROR_NO_PLAYER_IN_AREA.format(area=area) if area else LANG.ERROR_WHERE_TO_PLAY
            ),
        )
    slots: dict[str, Any] = {"search_query": command.query, "entity_id": player}
    if command.media_class:
        slots["media_class"] = LANG.MEDIA_CLASSES[command.media_class]
    if command.artist:
        slots["artist"] = command.artist
    if command.radio:
        slots["radio_mode"] = True
    target = next((t for t in home.targets if t.entity_id == player), None)
    state = hass.states.get(player)
    name = target.name if target else state.name if state else player
    return Plan(
        command.intent,
        slots,
        LANG.describe_play(command.query, name),
        domain="media_player",
    )


def _plain(text: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", text.lower()).split())


def is_bare_answer(text: str) -> bool:
    """A bare reply („tak, dokładnie tak, o to mi chodzi”, „nie rób”, „daj spokój”) - not a
    command that merely starts with „zrób” („zrób jaśniej w salonie”)."""
    rest = _plain(text)
    if not rest or not LANG.ANSWER.match(rest):
        return False
    while rest:
        if match := LANG.ANSWER.match(rest):
            rest = rest[match.end() :].strip()
        elif rest.split()[0] in LANG.FILLER:
            rest = rest.split(" ", 1)[1] if " " in rest else ""
        else:
            return False
    return True


def is_cancel(text: str) -> bool:
    """„anuluj”, „koniec”, „daj spokój”, „olej to” - end of the conversation."""
    return bool(LANG.CANCEL.match(_plain(text)))


def is_repeat(text: str) -> bool:
    """„jeszcze raz”, „(nie,) o coś innego”, „powtórzę” - an explicit request to repeat."""
    plain = _plain(text)
    # „nie o to chodzi” - the whole phrase; „nie, o coś innego” - what comes after „nie”
    return bool(
        LANG.REPEAT_EXPLICIT.match(plain)
        or (
            plain.startswith(f"{LANG.BARE_NO} ")
            and LANG.REPEAT_EXPLICIT.match(plain[len(LANG.BARE_NO) + 1 :])
        )
    )


def answer_kind(text: str, intent_type: str | None = None, domain: str | None = None) -> str | None:
    """„yes” / „no” to a confirmation question; None = another utterance (a new command).

    ``intent_type`` - the intent from the question: for a reply with a verb it decides
    whether it is consent („włącz” to „Czy włączyć…?”) or refusal („wyłącz”).
    """
    text = " ".join(re.sub(r"[^\w\s]", " ", text).split())
    if LANG.NO.match(text):
        return "no"
    if LANG.YES.match(text):
        return "yes"
    if domain in LANG.OPEN_CLOSE and intent_type in LANG.OPEN_CLOSE[domain]:
        _, _, same, opposite = LANG.OPEN_CLOSE[domain][intent_type]
    elif intent_type in ("HassTurnOn", "HassTurnOff"):
        same, opposite = (
            (LANG.ON_WORDS, LANG.OFF_WORDS)
            if intent_type == "HassTurnOn"
            else (LANG.OFF_WORDS, LANG.ON_WORDS)
        )
    else:
        same, opposite = (), ()
    if same:
        # a bare verb („włącz”, „wyłącz to”) - a longer sentence is a new command
        if LANG.words_pattern(same).match(text) and len(text.split()) <= 2:
            return "yes"
        if LANG.words_pattern(opposite).match(text) and len(text.split()) <= 2:
            return "no"
    return None


# --- reply after execution ---


def done_speech(
    intent_type: str, names: list[str], slots: dict[str, Any], domain: str | None = None
) -> str:
    """What the assistant says after executing a command (language pack)."""
    return LANG.done_speech(intent_type, names, slots, domain)
