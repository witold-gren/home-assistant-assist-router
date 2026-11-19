"""Polish language pack (pl): grammar.

The functions that build sentences (they depend on grammar: cases, plural forms, gender) and the
values derived from the data files. This file runs with every name of texts.yaml, words.yaml and
patterns.yaml already defined, so the functions use them directly.

For a new language: translate the text inside the functions and adapt the grammar (plural forms,
cases, word order). Keep the names of the functions and their arguments - the code calls them.
Comments are in English; the data is Polish on purpose.
"""

from __future__ import annotations

import re
from typing import Any


def words_pattern(words: tuple[str, ...]) -> re.Pattern[str]:
    """Regex matching any of the phrases at the start of an utterance (longest first)."""
    alternatives = "|".join(sorted((re.escape(w) for w in words), key=len, reverse=True))
    return re.compile(rf"^(?:{alternatives})\b", re.IGNORECASE)


# =====================================================================================
# Control (control.py): parsing a command into an HA intent
# =====================================================================================


CHANGES = (CHANGE_SET, CHANGE_MORE, CHANGE_LESS)


def prepare_text(text: str) -> tuple[str, list[str]]:
    """The command after Whisper fixes, and the reasons to ask before executing.

    Reasons: an uncertain fix ("jaś" -> "zgaś") or no known verb.
    """
    doubts = []
    words = []
    for word in text.split():
        bare = re.sub(r"[^\w]", "", word.lower())
        fix = WHISPER_FIXES.get(bare)
        if fix:
            words.append(fix[0])
            if not fix[1]:
                doubts.append(f"„{bare}” rozumiem jako „{fix[0]}”")
        else:
            words.append(word)
    fixed = " ".join(words)
    lowered = fixed.lower()
    if not any(re.search(rf"\b{verb}", lowered) for verb in COMMAND_VERBS):
        doubts.append(NO_KNOWN_VERB)
    return fixed, doubts


def stems(text: str) -> list[str]:
    """Word stems for comparing inflected words: "lampkę przy biurku" -> lamp, przy, biur."""
    words = re.findall(r"\w+", text.lower().translate(ACCENTS))
    return [w[:4] if len(w) > 4 else w for w in words if len(w) > 1]


def control_prompt(
    intents: str, domains: str, areas: str, floors: str, household: str, scripts: str
) -> str:
    """System prompt of the command parser (the lists are already joined)."""
    return " ".join(
        part
        for part in (
            "Jesteś parserem poleceń sterowania domem. Rozbierz polecenie na pola JSON.",
            household,
            f"Intencje: {intents}.",
            f"Domeny: {domains}.",
            f"Obszary: {areas}.",
            f"Piętra: {floors}." if floors else "",
            "nazwa: fragment polecenia nazywający konkretne urządzenie, bez czasownika i bez "
            "nazwy pomieszczenia (np. „lampkę przy biurku”); null, gdy polecenie dotyczy "
            "pomieszczenia albo wszystkich urządzeń danego rodzaju.",
            "wszystkie: true dla „wszystkie”, „wszystko”, „cały dom”.",
            "wartosc: liczba z polecenia (procent jasności, pozycji, głośności albo temperatura); "
            f"null, gdy jej nie ma. zmiana: „{CHANGE_MORE}” (jaśniej, wyżej, cieplej, głośniej), "
            f"„{CHANGE_LESS}” (ciemniej, niżej, chłodniej, ciszej), „{CHANGE_SET}” (konkretna "
            "wartość) albo null.",
            "element: co dopisać do listy (tylko HassListAddItem), inaczej null.",
            "kolor: kolor światła w mianowniku (np. „czerwony”), inaczej null. "
            "barwa: „ciepła”, „neutralna” albo „zimna” dla barwy białego światła, inaczej null.",
            "szukaj: czego szukać przy HassMediaSearchAndPlay (wykonawca, tytuł, gatunek, "
            "np. „Dawid Podsiadło”) w mianowniku, inaczej null; rodzaj: utwór, album, "
            "wykonawca, playlista, gatunek, podcast albo null. wykonawca: przy utworze albo "
            "albumie wykonawca w mianowniku, gdy padł (np. „Małomiasteczkowy Dawida "
            "Podsiadło” -> szukaj „Małomiasteczkowy”, wykonawca „Dawid Podsiadło”), inaczej "
            "null. radio: true dla „w stylu …”, „coś jak …”, „radio z …” (podobna muzyka bez "
            "końca), inaczej false.",
            "Przykłady: „zgaś światło w kuchni” -> HassTurnOff, light, Kuchnia; "
            f"„zrób jaśniej w salonie” -> HassLightSet, light, Salon, zmiana {CHANGE_MORE}; "
            "„zrób ciepłe światło w sypialni” -> HassLightSet, light, Sypialnia, barwa ciepła; "
            "„zmień kolor lampy na niebieski” -> HassLightSet, light, nazwa „lampy”, "
            "kolor niebieski; "
            "„puść Dawida Podsiadło w salonie” -> HassMediaSearchAndPlay, media_player, Salon, "
            "szukaj „Dawid Podsiadło”, rodzaj wykonawca; "
            "„opuść rolety do połowy” -> HassSetPosition, cover, wartosc 50; "
            "„wyłącz wszystkie światła” -> HassTurnOff, light, wszystkie true; "
            "„włącz lampkę przy biurku” -> HassTurnOn, light, nazwa „lampkę przy biurku”.",
            f"Skrypty i sceny (akcje do uruchomienia): {scripts}. Gdy polecenie prosi o to, co "
            "robi któraś akcja - także z przekręconymi przez rozpoznawanie mowy słowami (np. "
            "„zapasz kawę” = zaparz kawę) - wybierz HassTurnOn, domenę script (dla scen: scene) "
            "i jako nazwę podaj dokładną nazwę akcji. Akcję wybierz też wtedy, gdy polecenie "
            "pasuje do jej opisu lepiej niż do pojedynczego urządzenia: dotyczy kilku urządzeń "
            "naraz (telewizor i kino domowe), szczegółu z opisu (rolety wewnętrzne, a nie "
            "zewnętrzne) albo czynności z kilku kroków."
            if scripts
            else "",
            "Odpowiedz tylko JSON-em.",
        )
        if part
    )


NO_WORDS = REPEAT_WORDS + CANCEL_WORDS
# In HA, HassTurnOn opens a cover but locks a lock (lock.lock).
# domain -> intent -> (infinitive for the question, form after execution, yes words, no words);
# the words come from OPEN_CLOSE_VERBS (words.yaml)
OPEN_CLOSE = {
    domain: {
        intent: (verb, done, *((OPEN_WORDS, CLOSE_WORDS) if opens else (CLOSE_WORDS, OPEN_WORDS)))
        for intent, (verb, done, opens) in intents.items()
    }
    for domain, intents in OPEN_CLOSE_VERBS.items()
}
YES = words_pattern(YES_WORDS)
NO = words_pattern(NO_WORDS)
CANCEL = words_pattern(CANCEL_WORDS)
# an explicit request to repeat (without the bare "nie") - also for "are you sure" questions
REPEAT_EXPLICIT = words_pattern(tuple(w for w in REPEAT_WORDS if w != BARE_NO))
ANSWER = words_pattern(YES_WORDS + NO_WORDS)


def describe(command: Any, match: Any) -> str:
    """What is going to be done, for the question "Czy dobrze rozumiem: <...>?"."""
    verb = INTENTS[command.intent][1]
    domain = match.target.domain if match and match.target else command.domain
    if command.intent in ("HassTurnOn", "HassTurnOff") and domain in OPEN_CLOSE:
        verb = OPEN_CLOSE[domain][command.intent][0]
    if command.intent == "HassTurnOn" and domain in ("script", "scene"):
        verb = "uruchomić"
    if match and match.target:
        what = match.target.name
    elif command.all and not command.area:
        what = f"wszystkie: {DOMAINS.get(command.domain or '', 'urządzenia').split(',')[0]}"
    else:
        what = DOMAINS.get(command.domain or "", "urządzenia").split(",")[0]
    where = (
        f" w pomieszczeniu {command.area}" if command.area and not (match and match.target) else ""
    )
    value = f" na {command.value:g}" if command.value is not None else ""
    if command.intent == "HassListAddItem":
        return f"dopisać „{command.item}” do listy"
    if command.intent == "HassMediaSearchAndPlay":
        on = f" na {match.target.name}" if match and match.target else where
        return f"puścić „{command.query}”{on}"
    if command.intent == "HassLightSet":
        if command.color:
            value = f" na kolor {command.color}"
        elif command.white:
            value = f" na barwę {command.white}"
        else:
            value = f" na {command.value:g}%" if command.value is not None else ""
        what = what if match and match.target else "światło"
    return f"{verb} {what}{where}{value}".strip()


def describe_routine(name: str) -> str:
    return f"uruchomić {name}"


def describe_play(query: str, player: str) -> str:
    return f"puścić „{query}” na {player}"


def describe_resume(player: str) -> str:
    return f"wznowić muzykę na {player}"


def done_speech(
    intent_type: str, names: list[str], slots: dict[str, Any], domain: str | None = None
) -> str:
    """What the assistant says after executing a command."""
    verb = DONE.get(intent_type, "Gotowe")
    domain = domain or (slots.get("domain") or [None])[0]
    if domain in OPEN_CLOSE and intent_type in OPEN_CLOSE[domain]:
        verb = OPEN_CLOSE[domain][intent_type][1]
    if intent_type == "HassListAddItem":
        return f"{verb}: {slots.get('item')}."
    if intent_type == "HassTurnOn" and domain in ("script", "scene"):
        verb = "Uruchomiono"
    if intent_type == "HassLightSet" and ("color" in slots or "temperature" in slots):
        color = next((pl for pl, en in COLORS.items() if en == slots.get("color")), None)
        white = next((pl for pl, k in WHITES.items() if k == slots.get("temperature")), None)
        what = f"kolor {color}" if color else f"barwę {white}"
        lights = f": {', '.join(n.lower() for n in names)}" if 0 < len(names) <= 4 else ""
        return f"Ustawiono {what}{lights}."
    value = next(
        (slots[k] for k in ("brightness", "position", "temperature", "volume_level") if k in slots),
        None,
    )
    suffix = (
        f" na {value:g}{'' if 'temperature' in slots else '%'}"
        if isinstance(value, (int, float))
        else ""
    )
    if not names:
        return f"{verb}{suffix}."
    if len(names) > 4:
        where = f" w pomieszczeniu {slots['area']}" if slots.get("area") else ""
        return f"{verb}{suffix}: {len(names)} urządzeń{where}."
    return f"{verb}{suffix}: {', '.join(n.lower() for n in names)}."


# =====================================================================================
# Conversation (conversation.py): replies, questions and log labels
# =====================================================================================


def guess_prompt(household: str, areas: str, actions: str) -> str:
    """System prompt for guessing the garbled sentence."""
    return " ".join(
        part
        for part in (
            "Rozpoznawanie mowy przekręciło polskie zdanie wypowiedziane do asystenta domu. "
            "Odgadnij, co najprawdopodobniej powiedziano: szukaj słów, które brzmią podobnie "
            "(np. „głup nastrój w pisarowie” = „włącz nastrój w salonie”, „jaś światło” = "
            "„zgaś światło”). Zwróć jedno krótkie, sensowne polecenie (w trybie rozkazującym, "
            "jak „włącz”, „zgaś”, „opuść”) albo pytanie. Pomiń słowa, które do niego nie "
            "pasują, i nie wymyślaj nowych treści. Gdy po poprawce zdanie nadal nie ma sensu "
            "albo nie wiadomo, o co chodzi - zwróć null.",
            household,
            f"Pomieszczenia: {areas}.",
            f"Akcje: {actions}." if actions else "",
            "Gdy nie da się rozsądnie zgadnąć, zwróć null.",
        )
        if part
    )


def _device_names(names: list[str]) -> str:
    shown = ", ".join(names[:4])
    return f"{shown} i {len(names) - 4} innych" if len(names) > 4 else shown


def unavailable_command(names: list[str]) -> str:
    """A command not executed: its devices do not respond (state "unavailable")."""
    if len(names) == 1:
        return f"Urządzenie {names[0]} nie odpowiada (jest niedostępne), więc nic nie zmieniłem."
    return (
        f"Urządzenia nie odpowiadają (są niedostępne): {_device_names(names)}, "
        "więc nic nie zmieniłem."
    )


def unavailable_state(names: list[str]) -> str:
    """A question about the state of devices that do not respond."""
    if len(names) == 1:
        return (
            f"Urządzenie {names[0]} nie odpowiada (jest niedostępne), "
            "więc nie wiem, jaki ma teraz stan."
        )
    return (
        f"Urządzenia nie odpowiadają (są niedostępne): {_device_names(names)}, "
        "więc nie znam ich stanu."
    )


def resumed(player: str | None) -> str:
    """Reply after resuming music without a title („włącz muzykę”)."""
    return f"Wznawiam muzykę na {player}." if player else "Wznawiam muzykę."


def playing(title: str, player: str | None, radio: bool = False) -> str:
    """Reply after starting music ("w stylu" = similar music, Music Assistant radio mode)."""
    style = " w stylu" if radio else ""
    on = f" na {player}" if player else ""
    return f"Puszczam{style} {title}{on}."


# =====================================================================================
# Router (router.py, sources.py): understanding questions and preparing data for the LLM
# =====================================================================================


_FEMININE = re.compile(r"\b(" + "|".join(FEMININE_FORMS) + r")\b", re.IGNORECASE)


def gendered(text: str, gender: str | None) -> str:
    """A reply in the persona's grammatical gender (the replies are written as male)."""
    if gender != "female":
        return text

    def swap(match: re.Match[str]) -> str:
        word = FEMININE_FORMS[match.group(0).lower()]
        return word.capitalize() if match.group(0)[0].isupper() else word

    return _FEMININE.sub(swap, text)


def format_now(now: Any) -> str:
    """The current date and time for the prompt: „sobota, 24 października 2026, godzina 9:05”."""
    return (
        f"{WEEKDAY_NAMES[now.weekday()]}, {now.day} {MONTHS_GENITIVE[now.month - 1]} "
        f"{now.year}, godzina {now.hour}:{now.minute:02d}"
    )


def format_sentences(count: int) -> str:
    """How many sentences the summary should have („3–4”)."""
    return f"{count - 1}–{count}" if count > 2 else "2"


def classifier_prompt(household: str, topics: str, examples: str) -> str:
    parts = ["Jesteś klasyfikatorem pytań do asystenta domu."]
    if household:
        parts.append(household)
    parts.append(f"Tematy: {topics}.")
    if examples:
        parts.append(f"Przykłady (pytanie -> temat): {examples}.")
    parts.append("Odpowiedz tylko JSON-em.")
    return " ".join(parts)


def in_room(room: str) -> str:
    """Replacement for MY_ROOM: „w Pokój Dziewczyn”."""
    return f"w {room}"


def minutes_ago(minutes: int) -> str:
    """How long a binary sensor has been in its state."""
    if minutes < 1:
        return "przed chwilą"
    if minutes < 120:
        return f"od {minutes} min"
    return f"od {minutes // 60} h"


def attribute_parts(domain: str, state: str, a: dict[str, Any]) -> list[str]:
    """The most important attributes - what people ask about and the state does not say."""
    parts = []
    if domain == "climate":
        if a.get("current_temperature") is not None:
            parts.append(f"jest {a['current_temperature']}°")
        if a.get("temperature") is not None:
            parts.append(f"ustawione {a['temperature']}°")
        if a.get("hvac_action"):
            parts.append(f"teraz: {a['hvac_action']}")
    elif domain == "media_player":
        title = " - ".join(str(a[k]) for k in ("media_artist", "media_title") if a.get(k))
        if title:
            parts.append(f"gra: {title}")
        if a.get("app_name") or a.get("source"):
            parts.append(f"źródło: {a.get('app_name') or a.get('source')}")
        if a.get("volume_level") is not None:
            parts.append(f"głośność {round(a['volume_level'] * 100)}%")
    elif domain == "cover" and a.get("current_position") is not None:
        parts.append(f"otwarcie {a['current_position']}%")
    elif domain == "light" and state == "on" and a.get("brightness") is not None:
        parts.append(f"jasność {round(a['brightness'] / 255 * 100)}%")
    elif domain == "vacuum" and a.get("battery_level") is not None:
        parts.append(f"bateria {a['battery_level']}%")
    return parts


def scene_description(members: list[str]) -> str:
    """What a scene sets, as its description for the control model (scenes have none in HA)."""
    return "scena - ustawia: " + ", ".join(members[:8]) if members else "scena"


# =====================================================================================
# Voice (voice.py): "who is speaking?" and announcements (Assist Speaker ID)
# =====================================================================================


def percent(score: float) -> str:
    return f"{max(0, round(score * 100))} procent"


def next_speaker(name: str, score: float) -> str:
    return f" Następna osoba: {name}, {percent(score)}."


def speaker_recognized(name: str, score: float, second: str) -> str:
    return f"Mówi {name}, podobieństwo {percent(score)}.{second}"


def speaker_uncertain(first: str, first_score: float, second: str, second_score: float) -> str:
    return (
        f"Nie jestem pewien. Najbardziej podobne głosy: {first} "
        f"{percent(first_score)} i {second} {percent(second_score)}."
    )


def probable_speaker(name: str) -> str:
    """Start of an answer for a probable (not certain) speaker."""
    return f"Wydaje mi się, że pyta {name}."


def speaker_unknown(name: str, score: float, threshold: float | None, second: str) -> str:
    """Best voice below its threshold - say the threshold, so it is clear why."""
    needed = f", a do rozpoznania potrzeba {percent(threshold)}" if threshold else ""
    return f"Nie rozpoznaję tego głosu. Najbliżej: {name}, {percent(score)}{needed}.{second}"


# =====================================================================================
# Example commands (examples.py): generated by the answer model, checked by the router
# =====================================================================================


def examples_request(
    topic: str, examples: str, names: str, people: str, household: str, count: int
) -> str:
    """The user message asking for example sentences of one topic."""
    lines = [f"Temat: {topic}."]
    if examples:
        lines.append(f"Przykłady z konfiguracji: {examples}.")
    if names:
        lines.append(f"Nazwy w domu: {names}.")
    if people:
        lines.append(f"Domownicy: {people}.")
    if household:
        lines.append(household)
    lines.append(f"Napisz {count} zdań.")
    return "\n".join(lines)


# =====================================================================================
# Several commands in one sentence (conversation.py): split by the model
# =====================================================================================


def split_prompt(household: str) -> str:
    """System prompt for splitting a sentence into separate, complete commands."""
    return " ".join(
        part
        for part in (
            "Rozbijasz polecenie dla asystenta domu na osobne, pełne polecenia. Każde polecenie "
            "ma czasownik i to, czego dotyczy - gdy w zdaniu czasownik albo rzecz padła raz dla "
            "kilku miejsc lub urządzeń, powtórz je w każdym poleceniu. Nie zmieniaj słów ani nazw "
            "urządzeń, pomieszczeń i osób, nie dodawaj niczego od siebie. Gdy to jedno polecenie "
            "(także o kilku osobach albo z tytułem jak „Simon i Garfunkel”), zwróć je bez zmian "
            "jako jedyne.",
            "Przykłady: „wyłącz światło w kuchni oraz łazience” -> [„wyłącz światło w kuchni”, "
            "„wyłącz światło w łazience”]; „zamknij rolety w salonie i włącz ekspres do kawy” -> "
            "[„zamknij rolety w salonie”, „włącz ekspres do kawy”]; „zgaś wszystkie światła oraz "
            "włącz alarm” -> [„zgaś wszystkie światła”, „włącz alarm”]; „włącz światło i "
            "telewizor w salonie” -> [„włącz światło w salonie”, „włącz telewizor w salonie”].",
            household,
            'Odpowiedz tylko JSON-em: {"polecenia": [...]}.',
        )
        if part
    )
