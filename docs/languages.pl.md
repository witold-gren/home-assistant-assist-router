# Dodanie języka {#adding-a-language}

Wszystko, co Assist Router mówi, rozpoznaje albo wysyła do modelu językowego w jednym języku, jest w
**pakiecie językowym**: katalogu w `custom_components/assist_router/languages/` nazwanym kodem języka.
Integracja ma polski, `pl/`. Do przetłumaczenia większości nie trzeba znać Pythona - trzy z czterech
plików to zwykły YAML, a testy mówią dokładnie, co jeszcze jest źle.

## Co jest w pakiecie {#pack}

| Plik | Co zawiera | Co robisz |
|---|---|---|
| `texts.yaml` | wszystko, co asystent mówi na głos (potwierdzenia, błędy, „Czy chodziło o…?”), wpisy dziennika, prompty wysyłane do modelu, słowa kluczy JSON, o które proszą prompty (`TOPIC_KEY`, `SENTENCES_KEY` …) | tłumaczysz wartości; każde `{pole}` zostaje |
| `words.yaml` | słowa, po których asystent rozumie wypowiedź: tak / nie / anuluj, czasowniki poleceń, kolory, barwy bieli, dni, słowa rodzinne, nazwy stanów czytane na głos, typowe błędy Whispera | tłumaczysz słowa; nazwy Home Assistanta zostają |
| `patterns.yaml` | wyrażenia regularne (słowa alarmu, „wszystkie”, początek pytania o wiedzę, słowa dni …), każde z przykładami `matches` i `not_matches` | najpierw tłumaczysz przykłady, potem poprawiasz wzorzec, aż je znajdzie |
| `grammar.py` | kilka funkcji, które budują zdania (przypadki, liczba mnoga, rodzaj, data czytana na głos), i wartości liczone z danych | tłumaczysz tekst w funkcjach i dopasowujesz gramatykę |

Komentarz nad każdym wpisem mówi, co to jest i kiedy się przydaje. Pakiet polski jest wzorcem: nowy
pakiet ma dokładnie te same nazwy.

### Zasady sprawdzane przez testy {#rules}

- **Nazwy zostają** (`CONFIRM_QUESTION`, `YES_WORDS` …) - kod je czyta.
- **`{pola}` zostają** - `MORE_ITEMS: "… i {count} więcej"` musi mieć `{count}`.
- **Nazwy Home Assistanta zostają**: intencje (`HassTurnOn`), domeny (`light`, `cover`), klasy
  urządzeń, stany (`on`, `off`), wartości kolorów (`red`, `white`), rodzaje mediów (`track`), kody
  dni (`today`, `monday`, `weekend`). W słowniku komentarz mówi, którą stronę się tłumaczy: w
  `COLORS` słowo się tłumaczy, a nazwa CSS zostaje; w `DOMAINS` klucz zostaje, a opis się tłumaczy.
- **Znaczniki zostają**: `!tuple`, `!set`, `!frozenset`, `!translate` tylko zachowują typ, którego
  oczekuje kod.
- **Słowa kluczy JSON zgadzają się z promptami**: jeśli `SENTENCES_KEY` to `vety`, prompty pokazujące
  `{"zdania": [...]}` muszą pokazywać `{"vety": [...]}`; `CHANGE_SET` / `CHANGE_MORE` / `CHANGE_LESS`
  to słowa, którymi odpowiada parser poleceń, a `control_prompt` bierze je z pakietu.
- **Każdy wzorzec znajduje swoje `matches` i żadnego z `not_matches`.**

Rdzenie słów są w porządku tam, gdzie język się odmienia („świat” obejmuje *światło, światła,
światłem*); w języku z małą odmianą lepsze są całe słowa.

## Krok po kroku (na przykładzie czeskiego) {#steps}

1. **Zacznij od szkicu.** Skopiuj `languages/pl/` do `languages/cs/` albo pozwól przetłumaczyć go
   trenerowi: `router-trainer language new cs` zapisuje sprawdzone tłumaczenie maszynowe tego pakietu
   (i pakietu trenera) z `REVIEW.md` - listą tego, co musi przejrzeć osoba znająca język. Zobacz
   przewodnik trenera, *Nowy język*.
2. **`texts.yaml`**: przetłumacz. Ustaw `CODE: cs` i `WIKIPEDIA_LANGUAGE: cs`.
3. **`words.yaml`**: przetłumacz listy słów. Dobrym źródłem właściwych czasowników i nazw kolorów są
   zdania samego Home Assistanta dla Twojego języka: repozytorium
   [home-assistant/intents](https://github.com/home-assistant/intents), katalog `sentences/cs/`.
4. **`patterns.yaml`**: przetłumacz przykłady `matches` / `not_matches`, potem wzorzec. Po każdym
   uruchom sprawdzenie.
5. **`grammar.py`**: przetłumacz zdania w funkcjach i dopasuj gramatykę - liczbę mnogą
   (`done_speech`), datę (`format_now`, `MONTHS_GENITIVE`), żeńskie formy odpowiedzi (`gendered`;
   język bez rodzaju gramatycznego zwraca tekst bez zmian).
6. **Sprawdź** - jedna linia na problem, nic, gdy pakiet jest gotowy:

    ```bash
    .venv/bin/python tools/check_language.py custom_components/assist_router/languages/cs
    make test     # te same kontrole dla każdego pakietu, razem z resztą testów
    ```

7. **Użyj**: pakiet wybiera się, gdy językiem Home Assistanta jest `cs`, albo przez `language: cs` w
   `router.yaml`. Opisy, przykłady i wzorce `match` w `router.yaml` napisz po czesku, wybierz model
   Ollamy, który dobrze pisze po czesku, i przetestuj `tools/model_benchmark.py` na czeskich pytaniach
   ([Testowanie i wybór modeli](good-practice.md#testing)).

Kody dni to słowa kluczowe, takie same w każdym języku: pakiet przypisuje do nich mówione słowa
(`WHEN_PATTERNS`, w kolejności - wygrywa pierwszy pasujący) i może dodać własne nazwy dla `days:` w
`router.yaml` (`DAY_ALIASES`).

!!! tip

    Nowe języki są mile widziane: wyślij katalog jako pull request do
    [repozytorium na GitHubie](https://github.com/witold-gren/home-assistant-assist-router). Wynik
    `tools/check_language.py` w opisie pull requesta ułatwia przegląd.
