# Dodanie języka {#adding-a-language}

Wszystko, co zależy od języka, jest w jednym **pakiecie językowym**: module Pythona w
`custom_components/assist_router/languages/`, nazwanym kodem języka. Integracja ma
wbudowany pakiet polski, `pl.py`. Są w nim:

- odpowiedzi mówione (potwierdzenia, błędy, „Czy chodziło o…?”, komunikaty ogłoszeń i mówcy);
- słowa i wzorce do rozumienia poleceń i pytań: słowa dni (zamieniane na kody dni), odpowiedzi
  tak / nie / anuluj i zwroty poprawek („pytałem czy” – REPHRASE_LEADS), czasowniki, kolory, słowa 1. osoby, określenia rodzinne, słowa ogłoszeń
  i alarmu, poprawki Whispera, początki pytań o wiedzę;
- prompty dla modeli (router, odpowiedź, streszczenie, sterowanie, zgadywanie, przykładowe
  zdania) i nazwy kluczy JSON, o które proszą (`TOPIC_KEY`, `CONTROL_KEYS`…);
- zdanie o postaci asystenta (`PERSONA`) i formy żeńskie stałych odpowiedzi
  (`FEMININE_FORMS`, `gendered()`; język bez rodzaju zwraca tekst bez zmian);
- etykiety dziennika, nazwy stanów i kilka funkcji składających zdania (zależą od gramatyki)
  oraz `CODE` i domyślny `WIKIPEDIA_LANGUAGE`.

Żeby dodać np. czeski:

1. Skopiuj `languages/pl.py` do `languages/cs.py`.
2. Przetłumacz wszystkie zwroty, wzorce, prompty i odpowiedzi. Zostaw te same nazwy stałych
   i funkcji (i ich argumentów) - kod czyta je przez `LANG`. Nazwy kluczy JSON też możesz
   przetłumaczyć (opcjonalnie; model pewniej wypełnia klucze w swoim języku). Ustaw
   `CODE = "cs"` i `WIKIPEDIA_LANGUAGE = "cs"`.
3. **Kody dni się nie zmieniają.** Kody w `days:` i w zmiennej
   `when` (`today`, `tomorrow`, `day_after_tomorrow`,
   `weekend`, `week`, `monday` … `sunday`, liczba dni) to
   słowa kluczowe, takie same w każdym języku. Nowy pakiet mapuje na nie czeskie słowa
   (`WHEN_PATTERNS`) i może dodać własne nazwy dla `days:`
   (`DAY_ALIASES`, jak polskie `dzis`, `jutro`); te nazwy dostaje
   też alias zmiennej `when` z `COMMAND_VARIABLE_ALIASES` (po polsku
   `kiedy`).
4. Pakiet działa, gdy język Home Assistanta to `cs` albo gdy `router.yaml`
   ma `language: cs`. Agent konwersacji podaje wtedy czeski wśród obsługiwanych języków.
   Nieznany kod w `language:` wyłącza router z błędem w logu.
5. Wybierz model w Ollamie, który dobrze rozumie i pisze w tym języku - router, odpowiedzi
   i rozbiór poleceń dzieją się w tym języku.
6. Opisy, przykłady i wzorce `match` w `router.yaml` napisz po czesku,
   a całość sprawdź narzędziem `tools/model_benchmark.py` z czeskimi pytaniami testowymi
   ([Test i wybór modeli](good-practice.md#testing)).

!!! tip

    Nowe pakiety są mile widziane: wyślij go jako pull request do
    [repozytorium na GitHubie](https://github.com/witold-gren/home-assistant-assist-router).
