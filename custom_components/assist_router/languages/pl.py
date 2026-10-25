"""Polish language pack (pl).

Everything Assist Router says, recognizes or sends to the LLM in Polish. A new language
is a copy of this module with the same names, translated - see "Adding a language" in the
documentation. Comments are in English; the data is Polish on purpose.
"""

from __future__ import annotations

import re
from typing import Any

CODE = "pl"
WIKIPEDIA_LANGUAGE = "pl"


def words_pattern(words: tuple[str, ...]) -> re.Pattern[str]:
    """Regex matching any of the phrases at the start of an utterance (longest first)."""
    alternatives = "|".join(sorted((re.escape(w) for w in words), key=len, reverse=True))
    return re.compile(rf"^(?:{alternatives})\b", re.IGNORECASE)


# =====================================================================================
# Control (control.py): parsing a command into an HA intent
# =====================================================================================

# intent -> (for the model: when to use it, for questions: verb in the infinitive)
INTENTS: dict[str, tuple[str, str]] = {
    "HassTurnOn": (
        "włącz, zapal, uruchom, otwórz rolety lub bramę, zarygluj zamek, aktywuj scenę",
        "włączyć",
    ),
    "HassTurnOff": (
        "wyłącz, zgaś, zamknij rolety lub bramę, otwórz (odblokuj) zamek, zatrzymaj urządzenie",
        "wyłączyć",
    ),
    "HassLightSet": (
        "jasność, kolor lub barwa światła, rozjaśnij, przyciemnij, zrób jaśniej/ciemniej, "
        "zrób ciepłe/zimne światło, zmień kolor na czerwony",
        "ustawić",
    ),
    "HassSetPosition": (
        "pozycja rolet lub zaworu w procentach, uchyl, opuść do połowy, wyżej/niżej",
        "ustawić pozycję",
    ),
    "HassClimateSetTemperature": (
        "temperatura ogrzewania lub klimatyzacji, cieplej, chłodniej",
        "ustawić temperaturę",
    ),
    "HassSetVolume": ("głośność w procentach", "ustawić głośność"),
    "HassSetVolumeRelative": ("głośniej, ciszej, podgłośnij, przycisz", "zmienić głośność"),
    "HassMediaPause": ("pauza, zatrzymaj muzykę lub film", "wstrzymać"),
    "HassMediaUnpause": ("wznów, graj dalej (bez tytułu)", "wznowić"),
    "HassMediaSearchAndPlay": (
        "puść, zagraj konkretną muzykę: wykonawcę, utwór, album, playlistę, gatunek, podcast",
        "puścić",
    ),
    "HassMediaNext": ("następny utwór, dalej", "przełączyć na następny"),
    "HassMediaPrevious": ("poprzedni utwór, wróć", "przełączyć na poprzedni"),
    "HassVacuumStart": ("odkurzanie, sprzątanie robotem", "uruchomić odkurzacz"),
    "HassVacuumReturnToBase": (
        "odkurzacz do bazy, przerwij sprzątanie",
        "odesłać odkurzacz do bazy",
    ),
    "HassListAddItem": ("dopisz do listy zakupów lub zadań", "dopisać do listy"),
}

# HA domain -> what it is called (for the model; the first word is used in questions)
DOMAINS: dict[str, str] = {
    "light": "światła, lampy, oświetlenie, LED",
    "switch": "przełączniki, gniazdka, wtyczki",
    "cover": "rolety, żaluzje, zasłony, brama, drzwi garażowe",
    "media_player": "głośniki, telewizor, muzyka",
    "climate": "ogrzewanie, klimatyzacja, termostat",
    "fan": "wentylator, oczyszczacz",
    "vacuum": "odkurzacz",
    "lock": "zamek",
    "scene": "scena",
    "script": "skrypt",
    "valve": "zawór",
    "todo": "lista zakupów, lista zadań",
}

# Relative change values the model may return ("set", "more", "less")
CHANGE_SET = "ustaw"
CHANGE_MORE = "więcej"
CHANGE_LESS = "mniej"
CHANGES = (CHANGE_SET, CHANGE_MORE, CHANGE_LESS)

# JSON keys the control prompt asks the model for (meaning -> key in the model's answer)
CONTROL_KEYS: dict[str, str] = {
    "intent": "intencja",
    "domain": "domena",
    "area": "obszar",
    "floor": "pietro",
    "name": "nazwa",
    "all": "wszystkie",
    "value": "wartosc",
    "change": "zmiana",
    "item": "element",
    "color": "kolor",
    "white": "barwa",
    "query": "szukaj",
    "media_class": "rodzaj",
    "artist": "wykonawca",
    "radio": "radio",
}

# Alarm: only sentences (automations), never parsed by the model - a test showed that
# "aktywuj alarm w trybie domowym" could hit the scene "Dzień dobry".
# "alar" also catches speech recognition errors ("halaryn", "alarn").
ALARM_WORDS = re.compile(r"\b(h?alar|czuwani|ochron|syren|uzbr|rozbr)", re.IGNORECASE)
ALARM_HINT = (
    "Alarmem steruję tylko konkretnymi zdaniami, na przykład: „wyłącz alarm”, „włącz alarm "
    "w trybie dom”, „włącz alarm poza domem” albo „fałszywy alarm”."
)
# Words that show the kind of device. A model that does not know a word ("halaryn") may
# guess the domain - without such a word and without a device name we ask instead.
DOMAIN_HINTS: dict[str, tuple[str, ...]] = {
    "light": ("świat", "lamp", "oświetl", "żarów", "led", "kinkiet", "jaśn", "ciemn", "zgaś",
              "zapal", "gaś", "barw", "kolor", "nastr"),
    "cover": ("rolet", "żaluz", "zasłon", "zasłoń", "odsłoń", "bram", "markiz", "opuść",
              "podnie", "uchyl"),
    "climate": ("ogrzew", "grzej", "grzan", "klimat", "termost", "stopn", "temperat", "ciepl",
                "chłod", "zimn"),
    "media_player": ("głośn", "cisz", "muzyk", "telewiz", "tv", "radio", "piosen", "utwór",
                     "film", "puść", "graj", "pauz", "następn", "poprzedn", "projekt", "kino"),
    "vacuum": ("odkurz", "sprząt", "robot", "mop"),
    "lock": ("zamek", "zamk", "drzwi", "rygl", "blokuj"),
    "fan": ("went", "oczyszcz", "wiatrak"),
    "todo": ("list", "dopisz", "zakup"),
}  # fmt: skip
# "all", "whole house" - a large scope is then intended, no question
WHOLE_HOUSE = re.compile(r"\b(wszystk|cał|każd)", re.IGNORECASE)
# light color in the nominative (as the model answers) -> CSS name for HA (rgb_color)
COLORS: dict[str, str] = {
    "biały": "white",
    "czerwony": "red",
    "zielony": "green",
    "niebieski": "blue",
    "żółty": "yellow",
    "pomarańczowy": "orange",
    "fioletowy": "purple",
    "różowy": "hotpink",
    "turkusowy": "turquoise",
    "błękitny": "deepskyblue",
    "złoty": "gold",
    "limonkowy": "lime",
    "purpurowy": "magenta",
    "brązowy": "brown",
}
# shade of white -> kelvin (color_temp_kelvin)
WHITES: dict[str, int] = {"ciepła": 2700, "neutralna": 4000, "zimna": 6500}
# kind of music -> MediaClass for search_media
MEDIA_CLASSES: dict[str, str] = {
    "utwór": "track",
    "album": "album",
    "wykonawca": "artist",
    "playlista": "playlist",
    "gatunek": "genre",
    "podcast": "podcast",
}
# a word in the name of the shopping list (the default list for "dopisz ...")
SHOPPING_LIST_WORD = "zakup"

# letters folded for comparing word stems
ACCENTS = str.maketrans("ąćęłńóśźż", "acelnoszz")

# Whisper mistakes in commands: word -> (fix, certain). An uncertain fix
# ("jaś" -> "zgaś") means asking before executing.
WHISPER_FIXES: dict[str, tuple[str, bool]] = {
    "czystkę": ("wszystkie", True),
    "czystkie": ("wszystkie", True),
    "wszystkę": ("wszystkie", True),
    "wszystkię": ("wszystkie", True),
    "zgaść": ("zgaś", True),
    "gaś": ("zgaś", True),
    "jaś": ("zgaś", False),
    "zgaj": ("zgaś", False),
    "włóż": ("włącz", False),
}
# Stems of command verbs - a command without any of them means asking first.
COMMAND_VERBS = (
    "włącz", "wyłącz", "zapal", "zgaś", "gaś", "otwórz", "otwieraj", "zamknij", "opuść",
    "podnieś", "ustaw", "zrób", "przyciemnij", "rozjaśnij", "ścisz", "przycisz", "podgłośnij",
    "zatrzymaj", "wstrzymaj", "wznów", "puść", "graj", "następn", "poprzedn", "odkurz",
    "posprzątaj", "sprzątaj", "wyślij", "odeślij", "dopisz", "dodaj", "zasłoń", "odsłoń",
    "uchyl", "niech", "aktywuj", "uruchom", "odpal", "zablokuj", "odblokuj", "zarygluj",
    "zmniejsz", "zwiększ", "podkręć", "skręć", "przełącz", "pauza", "stop", "dalej",
    "jaśniej", "ciemniej", "cieplej", "chłodniej", "głośniej", "ciszej", "wyżej", "niżej",
    "przymknij", "przewietrz", "wywietrz", "zaparz", "przygotuj", "nalej", "kalibruj", "skalibruj",
    "zmień", "pogaś", "pozapalaj", "zapal",
)  # fmt: skip
NO_KNOWN_VERB = "brak znanego czasownika"
# words that may stand before the name of a script or scene ("uruchom skrypt ...")
ROUTINE_WORDS = {"uruc", "wlac", "akty", "odpa", "zrob", "scen", "skry", "prosz"}


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
            "null, gdy jej nie ma. zmiana: „więcej” (jaśniej, wyżej, cieplej, głośniej), "
            "„mniej” (ciemniej, niżej, chłodniej, ciszej), „ustaw” (konkretna wartość) albo null.",
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
            "„zrób jaśniej w salonie” -> HassLightSet, light, Salon, zmiana więcej; "
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


# Reasons for a confirmation question (written to the log of unrecognized commands)
CONFIRM_UNCERTAIN_NAME = "niepewna nazwa"
CONFIRM_SEVERAL_DEVICES = "kilka pasujących urządzeń"
CONFIRM_KIND_GUESSED = "rodzaj urządzenia zgadnięty (brak słowa w poleceniu)"
CONFIRM_LARGE_SCOPE = "duży zasięg ({count} urządzeń)"
CONFIRM_SENSITIVE = "urządzenie wrażliwe (zamek, brama, drzwi)"
CONFIRM_LISTED = "urządzenie z listy potwierdzeń"
CONFIRM_ACTION_OR_DEVICE = "akcja czy urządzenie „{device}”"

# Spoken errors when a command cannot be executed
ERROR_DEVICE_NOT_FOUND = "Nie znalazłem urządzenia „{name}”."
ERROR_WHICH_ROOM = "W którym pomieszczeniu?"
ERROR_NO_COLOR = "To światło nie zmienia koloru."
ERROR_NO_WHITE = "To światło nie zmienia barwy."
ERROR_NO_VALUE = "Nie wiem, na jaką wartość ustawić."
ERROR_NO_VOLUME = "Nie wiem, jaką ustawić głośność."
ERROR_NO_LIST_ITEM = "Nie wiem, co i gdzie dopisać."
ERROR_WHAT_TO_PLAY = "Co mam puścić?"
ERROR_NO_PLAYER_IN_AREA = (
    "W pomieszczeniu {area} nie ma teraz głośnika, na którym mogę puścić muzykę."
)
ERROR_WHERE_TO_PLAY = "W którym pomieszczeniu mam puścić?"
PLAY_MUSIC = "puścić muzykę"

# Answers to the assistant's questions ("Czy dobrze rozumiem…?", "Czy chodziło o…?",
# "Czy …?") - one vocabulary for all questions. Phrases at the start of the utterance; the
# refusal is checked first ("nie rób" before "rób"), longer phrases before shorter ones.
YES_WORDS = (
    "tak", "tak jest", "no tak", "dokładnie", "dokładnie tak", "o to chodzi",
    "o to mi chodzi", "właśnie tak", "zgadza się", "zrób", "zrób to", "rób", "wykonaj",
    "działaj", "dawaj", "potwierdzam", "dobrze", "ok", "okej", "jasne", "pewnie", "śmiało",
    "oczywiście", "proszę", "owszem", "zgoda",
)  # fmt: skip
# "you misunderstood" - apologize and ask to repeat, the conversation goes on
REPEAT_WORDS = (
    "nie", "nie o to", "nie to", "o coś innego", "chodzi o coś innego", "nie o to chodzi",
    "jeszcze raz", "powtórzę", "może powtórzę", "powtórz", "źle", "źle zrozumiałeś",
    "pomyłka", "wróć",
)  # fmt: skip
# the bare "no" of REPEAT_WORDS (an explicit request to repeat is everything else)
BARE_NO = "nie"
# end of the conversation - nothing is done
CANCEL_WORDS = (
    "anuluj", "koniec", "nieważne", "zostaw", "zostaw to", "nic nie rób", "nie rób",
    "daj spokój", "daj sobie spokój", "daj sobie z tym spokój", "olej to", "olej",
    "nie trzeba", "nie teraz", "nie chcę", "rezygnuję", "przestań", "stop", "odwołaj",
)  # fmt: skip
NO_WORDS = REPEAT_WORDS + CANCEL_WORDS
# Answering with a verb: the verb of the question = yes, the opposite one = no
# ("Czy włączyć…?" - "włącz" yes, "wyłącz" no; "Czy wyłączyć…?" - the other way round).
ON_WORDS = ("włącz", "zapal", "uruchom", "odpal")
OFF_WORDS = ("wyłącz", "zgaś", "zatrzymaj")
OPEN_WORDS = ("otwórz", "otwieraj", "odblokuj", "podnieś", "odsłoń")
CLOSE_WORDS = ("zamknij", "zarygluj", "zablokuj", "opuść", "zasłoń")
# In HA, HassTurnOn opens a cover but locks a lock (lock.lock).
# domain -> intent -> (infinitive for the question, form after execution, yes words, no words)
OPEN_CLOSE = {
    "cover": {
        "HassTurnOn": ("otworzyć", "Otwarto", OPEN_WORDS, CLOSE_WORDS),
        "HassTurnOff": ("zamknąć", "Zamknięto", CLOSE_WORDS, OPEN_WORDS),
    },
    "lock": {
        "HassTurnOn": ("zamknąć", "Zamknięto", CLOSE_WORDS, OPEN_WORDS),
        "HassTurnOff": ("otworzyć", "Otwarto", OPEN_WORDS, CLOSE_WORDS),
    },
}
YES = words_pattern(YES_WORDS)
NO = words_pattern(NO_WORDS)
CANCEL = words_pattern(CANCEL_WORDS)
# an explicit request to repeat (without the bare "nie") - also for "are you sure" questions
REPEAT_EXPLICIT = words_pattern(tuple(w for w in REPEAT_WORDS if w != BARE_NO))
ANSWER = words_pattern(YES_WORDS + NO_WORDS)
# Lead-ins after "nie, ..." that only introduce the corrected command; they are dropped
# („nie, pytałem czy możesz zgasić światło” -> „możesz zgasić światło”). Optional - most often
# the correction follows right after „nie” („nie, wyłącz światło w łazience”).
REPHRASE_LEADS = re.compile(
    r"^(?:(?:ja\s+)?pyta(?:łem|łam|łeś|łaś)(?:\s+się)?\s+(?:czy|o)\s+"
    r"|chodzi(?:ło)?\s+(?:mi\s+)?o\s+"
    r"|miał(?:em|am)\s+na\s+myśli,?\s+"
    r"|chciał(?:em|am)(?:,?\s+(?:żebyś|abyś|byś))?\s+"
    r"|prosił(?:em|am)(?:\s+o)?\s+"
    r"|(?:mówił|powiedział)(?:em|am),?(?:\s+(?:że|żebyś|abyś))?\s+)",
    re.IGNORECASE,
)
# fillers between answer phrases ("tak, to proszę")
FILLER = frozenset({
    "to", "proszę", "już", "teraz", "no", "go", "ją", "je", "mi", "tak", "nie", "dzięki",
    "dziękuję",
})  # fmt: skip


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


# Reply after execution
DONE = {
    "HassTurnOn": "Włączono",
    "HassTurnOff": "Wyłączono",
    "HassLightSet": "Ustawiono światło",
    "HassSetPosition": "Ustawiono",
    "HassClimateSetTemperature": "Ustawiono temperaturę",
    "HassSetVolume": "Ustawiono głośność",
    "HassSetVolumeRelative": "Zmieniono głośność",
    "HassMediaPause": "Wstrzymano",
    "HassMediaUnpause": "Wznowiono",
    "HassMediaNext": "Następny utwór",
    "HassMediaPrevious": "Poprzedni utwór",
    "HassVacuumStart": "Uruchomiono odkurzacz",
    "HassVacuumReturnToBase": "Odkurzacz wraca do bazy",
    "HassListAddItem": "Dopisano do listy",
    "HassMediaSearchAndPlay": "Puszczam",
}


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

# Reply when nothing understood the command ({text} = what speech recognition heard)
MESSAGE_NO_MATCH = "Powiedziałeś: {text}. Niestety nie mogę tego zrozumieć."
MESSAGE_EMPTY = "Nic nie usłyszałem."
# after asking to repeat MISUNDERSTOOD_LIMIT times in a row
MESSAGE_GIVE_UP = (
    "Przepraszam, nie rozumiem. Jeśli będziesz czegoś potrzebować, poproś mnie jeszcze raz."
)
ASK_TO_REPEAT = "Przepraszam, źle zrozumiałem. Powtórz, proszę."
NOT_UNDERSTOOD = "Nie zrozumiałem. Powtórz, proszę."
NOTHING_DONE = "Dobrze, nic nie robię."
NOTHING_CHANGED = "Dobrze, nic nie zmieniam."
COMMAND_FAILED = "Nie udało się wykonać polecenia."
DEVICE_NOT_AVAILABLE = "Nie znalazłem takiego urządzenia albo nie jest udostępnione asystentowi."
PLAY_FAILED = "Nie udało się puścić muzyki."
PLAY_NOT_FOUND = "Nie znalazłem: {query}."
# confirmation questions ({description} from describe())
CONFIRM_QUESTION = "Czy dobrze rozumiem, że mam {description}?"
SENSITIVE_QUESTION = "Czy {description}?"
GUESS_QUESTION = "Nie jestem pewien, czy dobrze usłyszałem. Czy chodziło o: {guess}?"
# a personal question without a recognized speaker
UNKNOWN_SPEAKER_HINT = "Nie wiadomo, kto pyta - nie zgaduj i nie używaj imion."
# the device states block in the data for the answer model
DEVICE_STATES = "Stany urządzeń:"

# Labels written to the "route" column of the log of unrecognized commands
LOG_NOT_RECOGNIZED = " (nie rozpoznano)"
LOG_ENTITIES = " + {count} encji"
LOG_SOURCES = " + {count} źródeł"
LOG_ANSWER = " + odpowiedź"
LOG_CONTROL = "sterowanie"
LOG_CONTROL_BARE_ANSWER = "sterowanie (sama odpowiedź tak/nie)"
LOG_CONTROL_ALARM = "sterowanie (alarm)"
LOG_CONTROL_NOT_PARSED = "sterowanie (nie rozebrano)"
LOG_NOT_PARSED = "nie rozebrano"
LOG_QUESTION = " (pytanie: {reason})"
LOG_REPHRASED = " (poprawione: {text})"
LOG_PROBABLE = " (prawdopodobnie {name})"
LOG_UNCLEAR = "niezrozumiałe"
LOG_UNCLEAR_GIVE_UP = "niezrozumiałe - koniec rozmowy ({limit}× bez zrozumienia)"
LOG_UNCLEAR_NO_GUESS = "niezrozumiałe (bez propozycji)"

# Variables of the `command` templates in router.yaml. The English names are documented;
# the Polish ones keep older router.yaml files working (`kiedy` gets the Polish day name
# from DAY_ALIASES, e.g. "jutro", while `when` is the day code, e.g. "tomorrow").
COMMAND_VARIABLE_ALIASES = {
    "who": "kto",
    "person": "osoba",
    "people": "osoby",
    "when": "kiedy",
    "text": "tekst",
}

# Guessing what speech recognition garbled (topic with `unclear: true`)
GUESS_KEY = "zdanie"
# words a model sometimes returns instead of null
GUESS_EMPTY = ("", "null", "none", "brak", "nic")


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


def playing(title: str, player: str | None, radio: bool = False) -> str:
    """Reply after starting music ("w stylu" = similar music, Music Assistant radio mode)."""
    style = " w stylu" if radio else ""
    on = f" na {player}" if player else ""
    return f"Puszczam{style} {title}{on}."


# =====================================================================================
# Router (router.py, sources.py): understanding questions and preparing data for the LLM
# =====================================================================================

# Day words in a question -> day codes (sources.py: today, tomorrow, ..., monday ... sunday).
# Order matters: „pojutrze” contains „jutr”.
WHEN_PATTERNS = (
    ("day_after_tomorrow", r"\bpojutrz"),
    ("tomorrow", r"\bjutr"),
    ("monday", r"\bponiedział"),
    ("tuesday", r"\bwtor"),
    ("wednesday", r"\bśrod"),
    ("thursday", r"\bczwart"),
    ("friday", r"\bpiąt"),
    ("weekend", r"\bweekend"),
    ("saturday", r"\bsobot"),
    ("sunday", r"\bniedziel"),
    ("week", r"\b(tydzie|tygodni)"),
    ("today", r"\b(dziś|dzisiaj|dzisiejsz|teraz)"),
)
# Polish names accepted in `days:` of router.yaml (and given to old templates as `kiedy`)
DAY_ALIASES = {
    "dzis": "today",
    "jutro": "tomorrow",
    "pojutrze": "day_after_tomorrow",
    "weekend": "weekend",
    "tydzien": "week",
    "poniedzialek": "monday",
    "wtorek": "tuesday",
    "sroda": "wednesday",
    "czwartek": "thursday",
    "piatek": "friday",
    "sobota": "saturday",
    "niedziela": "sunday",
}
# The start of a knowledge question, not needed in the search phrase.
QUESTION_PREFIX = re.compile(
    r"^(kim (był|była|było|byli|jest|są)|co to (jest|są|było|był|była)|czym (jest|był|była)"
    r"|kto (jest|był|była|był|zdobył|zdobyła|wygrał|wygrała|został|została|napisał|wynalazł)"
    r"( (obecnie|aktualnie|teraz|ostatnio))?"
    r"|gdzie (leży|jest|znajduje się|leżą)|kiedy (był|była|było|byli|żył|żyła|powstał|powstała"
    r"|zbudowano|odkryto)|jak (wysoki|wysoka|wysokie|duży|duża|duże|długi|długa|długie|stary"
    r"|stara|stare|głęboki|głęboka) (jest|był|była)|ile (lat )?(ma|miał|miała|mieszka)"
    r"|(opowiedz|powiedz) (mi )?(coś )?o|co wiesz o)\s+",
    re.IGNORECASE,
)
# Pronunciation and transcription in brackets at the start of an article - not read aloud.
PRONUNCIATION = re.compile(r"\s*\([^()]*(?:wym\.|IPA|ˈ|ː|\[)[^()]*\)")
# A disambiguation page instead of an article
DISAMBIGUATION = ("może oznaczać", "może dotyczyć", "może odnosić się")
# End of a sentence: a full stop after a word longer than 3 letters - abbreviations like
# „ur.”, „m.in.”, „św.” do not end a sentence; the next sentence starts with a capital.
SENTENCE_END = re.compile(r"(?<=[^\s.]{4}[.!?])\s+(?=[A-ZĄĆĘŁŃÓŚŹŻ0-9])")

# Prompts of the answer model; they can be overridden in router.yaml (answer_prompt,
# summary_prompt). Fields: {household}, {now}, {sentences}.
ANSWER_PROMPT = (
    "Jesteś asystentem głosowym domu. {household} Odpowiedz na pytanie po polsku, krótko "
    "(jedno–dwa zdania), zwykłym tekstem do przeczytania na głos. Odpowiadaj na podstawie "
    "danych z Home Assistanta poniżej. Możesz wyciągać z nich proste wnioski: policzyć, "
    "porównać, a koniec lekcji to wyjście ze szkoły. Mów, że nie wiesz, tylko gdy w danych "
    "naprawdę nie ma odpowiedzi. Teraz jest {now}."
)
SUMMARY_PROMPT = (
    "Jesteś asystentem głosowym. Na podstawie fragmentu artykułu z Wikipedii poniżej "
    "odpowiedz na pytanie po polsku w {sentences} zdaniach: najpierw wprost odpowiedź, potem "
    "najważniejsze informacje. Pisz zwykłym tekstem do przeczytania na głos - bez list, "
    "nawiasów, obcych nazw w innych alfabetach i przypisów. Używaj tylko informacji z artykułu."
)
ASKED_BY = "Pyta: {speaker}."
DATA_HEADER = "Dane:"
ARTICLE_HEADER = "Artykuł:"
WEEKDAY_NAMES = ("poniedziałek", "wtorek", "środa", "czwartek", "piątek", "sobota", "niedziela")
MONTHS_GENITIVE = (
    "stycznia", "lutego", "marca", "kwietnia", "maja", "czerwca", "lipca", "sierpnia",
    "września", "października", "listopada", "grudnia",
)  # fmt: skip


def format_now(now: Any) -> str:
    """The current date and time for the prompt: „sobota, 24 października 2026, godzina 9:05”."""
    return (
        f"{WEEKDAY_NAMES[now.weekday()]}, {now.day} {MONTHS_GENITIVE[now.month - 1]} "
        f"{now.year}, godzina {now.hour}:{now.minute:02d}"
    )


def format_sentences(count: int) -> str:
    """How many sentences the summary should have („3–4”)."""
    return f"{count - 1}–{count}" if count > 2 else "2"


# Classifier (router model): the topic of the question
TOPIC_KEY = "temat"


def classifier_prompt(household: str, topics: str, examples: str) -> str:
    parts = ["Jesteś klasyfikatorem pytań do asystenta domu."]
    if household:
        parts.append(household)
    parts.append(f"Tematy: {topics}.")
    if examples:
        parts.append(f"Przykłady (pytanie -> temat): {examples}.")
    parts.append("Odpowiedz tylko JSON-em.")
    return " ".join(parts)


# A question in the 1st person („jakie mam zajęcia”, „moje oceny”) is about the speaker;
# „mamy” (we) and „mama” do not match thanks to the word boundary
FIRST_PERSON = re.compile(
    r"\b(?:mam|mój|moja|moje|mojego|mojej|moich|moim|moją|mnie|mi|ja|jestem|muszę|"
    r"powinienem|powinnam|byłem|byłam|dostałem|dostałam)\b",
    re.IGNORECASE,
)
# „w moim pokoju”, „u mnie w pokoju”, „mój pokój” - the speaker's room
MY_ROOM = re.compile(
    r"\b(?:w\s+moim\s+pokoju|u\s+mnie\s+w\s+pokoju|u\s+mnie|(?:mój|moim|mojego)\s+pok(?:ój|oju))\b",
    re.IGNORECASE,
)


def in_room(room: str) -> str:
    """Replacement for MY_ROOM: „w Pokój Dziewczyn”."""
    return f"w {room}"


# Family words relative to the speaker (family in router.yaml):
# relation (brother, sister, siblings, son, daughter, children) -> pattern
RELATIONS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("brother", re.compile(r"\bbra(?:t|ta|tu|tem|cie|cia|ci|ćmi)\b", re.IGNORECASE)),
    ("sister", re.compile(r"\bsiostr\w*", re.IGNORECASE)),
    ("siblings", re.compile(r"\brodzeństw\w*", re.IGNORECASE)),
    ("son", re.compile(r"\bsyn(?:a|owi|em|u|owie|ów|ami)?\b", re.IGNORECASE)),
    ("daughter", re.compile(r"\bcór(?:ka|ki|kę|ką|ce|ek|kom|kami|eczk\w*)\b", re.IGNORECASE)),
    ("children", re.compile(r"\b(?:moje|nasze)\s+dzie(?:ci|ciom|ćmi)\b", re.IGNORECASE)),
)

# Entity states for the answer model. Binary sensors: on/off by device_class.
BINARY_STATES = {
    "door": ("otwarte", "zamknięte"),
    "garage_door": ("otwarte", "zamknięte"),
    "window": ("otwarte", "zamknięte"),
    "opening": ("otwarte", "zamknięte"),
    "lock": ("otwarty", "zamknięty"),
    "problem": ("problem", "w porządku"),
    "battery": ("słaba bateria", "bateria w porządku"),
    "running": ("pracuje", "nie pracuje"),
    "moisture": ("mokro", "sucho"),
    "motion": ("ruch", "brak ruchu"),
    "occupancy": ("ktoś jest", "nikogo"),
    "presence": ("obecny", "nieobecny"),
    "connectivity": ("połączone", "rozłączone"),
    "plug": ("podłączone", "odłączone"),
    "power": ("zasilanie jest", "brak zasilania"),
    "smoke": ("dym", "brak dymu"),
}
STATES = {
    "on": "włączone", "off": "wyłączone", "home": "w domu", "not_home": "poza domem",
    "locked": "zamknięty", "unlocked": "otwarty", "open": "otwarte", "closed": "zamknięte",
    "disarmed": "rozbrojony", "armed_home": "uzbrojony (tryb w domu)",
    "armed_away": "uzbrojony (tryb poza domem)", "armed_night": "uzbrojony (tryb nocny)",
    "armed_vacation": "uzbrojony (tryb wakacyjny)", "armed_custom_bypass": "uzbrojony (własny)",
    "arming": "uzbrajanie", "pending": "odliczanie", "triggered": "ALARM - wyzwolony",
}  # fmt: skip
# When a topic skips states (e.g. lights that are off) and nothing is left - also an answer.
NOTHING_ACTIVE = "Wszystkie te urządzenia są teraz wyłączone - żadne nie jest włączone."
UNAVAILABLE = "niedostępne"  # state of an entity that does not respond (`unavailable: true`)
ALIASES = "inaczej"  # „Łazienka Oświetlenie (inaczej: Lustro) [Łazienka]: włączone”


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
    elif domain == "vacuum":
        if a.get("battery_level") is not None:
            parts.append(f"bateria {a['battery_level']}%")
    return parts


# A person asked about has no own entity in a source whose entities are assigned to people
NO_OWN_SOURCE = (
    "{name} nie ma przypisanego własnego źródła „{title}” – powiedz to wprost i nie mów, że "
    "nie ma żadnych wydarzeń. Pozostałe dane nie są osobiste dla tej osoby."
)

# A to-do list without items
EMPTY_LIST = "pusta"


def scene_description(members: list[str]) -> str:
    """What a scene sets, as its description for the control model (scenes have none in HA)."""
    return "scena - ustawia: " + ", ".join(members[:8]) if members else "scena"


# sources.py: a list the filter removed everything from (e.g. lessons on Saturday)
EMPTY = "brak"
MORE_ITEMS = "… i {count} więcej"
SOURCE_KEY = "źródło"  # merged service responses: which entity an item comes from
OTHER_ARTICLES = "Inne artykuły:"


# =====================================================================================
# Voice (voice.py): "who is speaking?" and announcements (Assist Speaker ID)
# =====================================================================================

# questions about voice recognition (after speech to text, with Whisper punctuation)
WHO_SPEAKS = re.compile(
    r"\b(?:kto\s+(?:to\s+|teraz\s+)?(?:do\s+ciebie\s+)?mówi|kto\s+mówi\s+do\s+ciebie|"
    r"kim\s+jestem|kto\s+jestem|"
    r"jak\s+(?:mnie\s+)?rozpoznajesz|rozpoznajesz\s+mnie|czy\s+mnie\s+rozpoznajesz|"
    r"jak\s+rozpoznajesz\s+(?:mój\s+|ten\s+|czyj\s+)?głos|"
    r"co\s+to\s+za\s+głos|czyj\s+(?:to\s+)?(?:jest\s+)?(?:ten\s+)?głos|"
    r"(?:czy\s+)?wiesz,?\s+kim\s+jestem|(?:czy\s+)?wiesz,?\s+kto\s+(?:to\s+)?mówi)\b",
    re.IGNORECASE,
)
# announcement (intercom): a word at the start - the speaker's recording on other speakers
ANNOUNCEMENT = re.compile(
    r"^\W*(?:ogłoszenie|komunikat|do\s+wszystkich|intercom|interkom)\b", re.IGNORECASE
)
ANNOUNCED = "Ogłoszenie wysłane."
NO_VOICE = (
    "Nie wiem - głos rozpoznaję tylko w poleceniach mówionych do głośnika z rozpoznawaniem mówcy."
)
TOO_SHORT = (
    "Za krótko, żeby rozpoznać głos. Powiedz dłużej, na przykład: powiedz mi, kto teraz "
    "do ciebie mówi."
)
NO_PRINTS = "Nie mam jeszcze zapisanych wzorców głosu."


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


# Columns of the preview of unrecognized commands in the options (CSV key -> header)
PREVIEW_HEADERS = {
    "timestamp": "Kiedy",
    "area": "Pokój",
    "speaker": "Mówca",
    "text": "Usłyszane",
    "response": "Odpowiedź",
}


# =====================================================================================
# Example commands (examples.py): generated by the answer model, checked by the router
# =====================================================================================

EXAMPLES_PROMPT = (
    "Układasz przykładowe pytania i polecenia, które domownik mówi do polskiego asystenta "
    "głosowego domu. Pisz tak, jak się mówi: krótko (4-10 słów), poprawną polszczyzną, każde "
    "zdanie inne. Opieraj się na podanych nazwach urządzeń, pokoi i osób, ale mów je "
    "naturalnie: odmieniaj i upraszczaj („Salon Lampa 2” -> „drugą lampę w salonie”, "
    "„Roborock S5 Max Bateria” -> „baterię odkurzacza”), bez nawiasów, emoji i angielskich "
    "nazw technicznych. Domownik mówi do asystenta - nie zwracaj się do domowników po "
    "imieniu; imię pada tylko, gdy pytanie dotyczy tej osoby („Jakie lekcje ma jutro Kasia?”). "
    'Nie numeruj. Odpowiedz JSON-em: {"zdania": [...]}.'
)
SENTENCES_KEY = "zdania"


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


NO_ROUTER_ANSWER = "brak odpowiedzi routera"
EXAMPLES_HEADER = (
    "# Assist Router - przykładowe komendy dla tego domu\n"
    "# Wygenerowane {when}; zdania: {writer}, sprawdzenie: router {router}.\n"
    "# „working”: router wybrał właściwy temat (sterowanie: plan polecenia bez błędu,\n"
    "# bez wykonania). „rejected”: dokąd trafiły - wskazówka, co poprawić w router.yaml.\n"
    "# Nadpisywany przy każdym generowaniu (akcja assist_router.generate_examples).\n\n"
)


# =====================================================================================
# Several commands in one sentence (conversation.py): split by the model
# =====================================================================================

# conjunctions that may join several commands („… oraz …”, „…, a potem …”)
CONJUNCTIONS = re.compile(r"\b(?:i|oraz|potem|następnie|a\s+także|a\s+też)\b|,", re.IGNORECASE)
SPLIT_KEY = "polecenia"
# a sentence with several commands in the log of unrecognized commands
LOG_MULTI = "kilka poleceń → {parts}"


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
