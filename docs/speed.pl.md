# Szybkość odpowiedzi {#speed}

Od chwili, gdy skończysz mówić, do pierwszego słowa odpowiedzi mija kilka sekund. Ta strona
pokazuje, gdzie ten czas idzie, co Assist Router już robi, żeby go skrócić, i co możesz ustawić
sam. Wszystkie liczby zmierzono w jednym domu: Jetson AGX Orin 64 GB, Ollama z Gemma 4 26B jako
router i model odpowiedzi, Whisper `large-v3`, Piper, satelity Home Assistant Voice.

## Gdzie idzie czas {#stages}

Pytanie „Jaka będzie jutro pogoda?” (temat z prognozą dzienną i godzinową), przed zmianami
z tej strony:

| Etap | Czas | Od czego zależy |
|---|---|---|
| Wykrycie końca mówienia | ok. 0,7 s ciszy | ustawienie satelity „Wykrywanie zakończenia mówienia” |
| Rozpoznanie mowy (Whisper) | 1,8–2,5 s | model, `beam_size`, długość nagrania |
| Wbudowany agent HA i pobranie danych | 0,1 s | prawie nic |
| Wybór tematu (router) | 1,2–3,2 s | długość promptu routera i to, czy Ollama ma go w pamięci podręcznej |
| Wczytanie promptu odpowiedzi | 2,2–3,8 s | ile danych idzie do modelu odpowiedzi |
| Pisanie odpowiedzi | ok. 1,2 s | długość odpowiedzi (strumieniowana, nakłada się na mowę) |

Najwięcej kosztuje model językowy, a w nim nie pisanie, tylko **wczytanie promptu**: Gemma 4
26B na Orinie czyta około 750–1000 tokenów na sekundę. Prompt routera ma kilka tysięcy tokenów
(opisy tematów i przykłady), a prompt odpowiedzi tyle, ile danych z Home Assistanta.

Gdzie sprawdzić to u siebie:

- Ustawienia → Asystenci głosowi → ⋮ → **Debug**: czasy etapów każdego przebiegu.
- Dziennik Ollamy (`docker logs ollama`): czas każdego zapytania; najpierw wybór tematu, potem
  odpowiedź.
- Odpowiedź Ollamy z `"stream": false` podaje `prompt_eval_count` i `prompt_eval_duration` -
  ile tokenów wczytał i w jakim czasie.

## Co Assist Router robi sam {#built-in}

- **Strumieniowanie odpowiedzi.** Odpowiedź modelu odpowiedzi, streszczenie z Wikipedii
  i odpowiedź agenta zapasowego idą do zamiany tekstu na mowę, gdy model jeszcze je pisze
  ([Przewodnik: potoki](guide.md#pipelines)). Długą odpowiedź słychać 1–2 s wcześniej.
- **Dane jako tabela.** Lista elementów z prostymi polami (prognoza, wydarzenia, lekcje) trafia
  do modelu jako tabela: nazwy pól raz w nagłówku, potem jeden wiersz na element. Prognoza
  godzinowa na 24 godziny: 1855 → 1439 tokenów, wczytanie o 0,3–0,5 s krótsze, odpowiedź taka
  sama.
- **Ten sam kontekst.** Gdy router i model odpowiedzi to ten sam model, oba zapytania mają ten
  sam `num_ctx` (8192) - Ollama nie przeładowuje modelu między nimi.

## Ustawienia Ollamy {#ollama}

Na serwerze Ollamy (zmienne środowiska kontenera):

| Zmienna | Wartość | Dlaczego |
|---|---|---|
| `OLLAMA_NUM_PARALLEL` | `2` | Dwa sloty: prompt routera i prompt odpowiedzi nie wypychają się nawzajem z pamięci podręcznej. Wybór tematu trwał 1,2–3,2 s, po zmianie stale 0,9–1,0 s. Kosztuje to drugą pamięć podręczną (dla Gemma 4 26B przy 8192 tokenach - około 1 GB). |
| `OLLAMA_FLASH_ATTENTION` | `1` | szybsze wczytywanie długich promptów |
| `OLLAMA_KV_CACHE_TYPE` | `q8_0` | mniejsza pamięć podręczna, bez widocznej straty jakości |
| `OLLAMA_KEEP_ALIVE` | długi, np. `72h` | model nie znika z pamięci między pytaniami |

Każdy, kto pyta ten sam model, musi używać **tego samego `num_ctx`** - router, agent zapasowy
w integracji Ollama, inne aplikacje. Inny kontekst przeładowuje model (z 26B około 25 s) i to
pytanie, i następne, czekają. To samo dotyczy własnych testów z `curl`: podaj
`"options": {"num_ctx": 8192}` i `"keep_alive": -1`.

## Mniej danych dla modelu odpowiedzi {#data}

Każde 1000 tokenów danych to około sekundy czekania. W `router.yaml`:

- `limit:` przy długich listach - prognoza godzinowa na 12 godzin zamiast 24 zwykle wystarcza;
- `drop:` - pola, których nikt nie pyta (np. `pressure`, `dew_point`, `uv_index`);
- dzień z pytania („jutro”, „w weekend”) już sam przycina listy z datami
  ([Dane](data.md)), więc nie dokładaj osobnych źródeł na każdy dzień.

## Rozpoznanie mowy {#speech}

- **Wykrywanie zakończenia mówienia** na satelicie: „Agresywne” kończy nagrywanie po krótszej
  ciszy (około 0,4 s szybciej). Przy dłuższej pauzie w środku zdania satelita może je uciąć -
  spróbuj na jednej satelicie, zanim zmienisz wszystkie.
- **Whisper**: porównanie na 40 nagraniach z domu (ten sam GPU, ta sama podpowiedź):

| Wariant | Średnio | Najdłużej | Inny tekst niż `large-v3`, beam 5 |
|---|---|---|---|
| `large-v3`, `beam_size` 5 | 1,11 s | 3,3 s | — |
| `large-v3`, `beam_size` 1 | 1,48 s | 17,3 s | 14 z 40, w tym zmyślone zdania |
| `distil-whisper-large-v3-pl`, beam 5 | 0,97 s | 3,1 s | 25 z 40, ucina zdania |
| `distil-whisper-large-v3-pl`, beam 1 | 1,04 s | 3,7 s | 25 z 40, ucina zdania |

  Mniejszy `beam_size` nie przyspiesza (przy szumie model wpada w powtórzenia), a destylowany
  polski model jest niewiele szybszy i gubi końce poleceń. `large-v3` z `beam_size` 5 zostaje.
  Sam model rozpoznaje w około 1,1 s, a etap mowy w potoku trwa 1,8–2,5 s - reszta to otoczka
  (pośrednik Speaker ID, podpowiedź z nazwami encji, przesyłanie), tam warto szukać dalej.

## Wybór tematu {#classification}

Prompt routera to opisy tematów i wszystkie `examples` z `router.yaml` - przy 29 tematach
i 123 przykładach około 3200 tokenów. Z pamięci podręcznej (drugi slot Ollamy) czyta się go
w 0,2–0,4 s, bez niej w około 3 s. Dłużej działa to, co skraca prompt:

- mniej, ale lepszych przykładów - po 3–5 na temat, takich, które naprawdę różnią tematy;
- mniejszy, douczony model routera z
  [Trenera Assist Routera](https://github.com/witold-gren/home-assistant-assist-router-trainer):
  krótki prompt i kilka razy szybsze wczytanie.

## Lista kontrolna {#checklist}

1. Strumieniowanie działa: w Debug potoku `stream_response: true`.
2. `OLLAMA_NUM_PARALLEL=2`, wszyscy klienci modelu z tym samym `num_ctx`.
3. Długie listy w `router.yaml` mają `limit:` i `drop:`.
4. Na jednej satelicie „Agresywne” wykrywanie zakończenia mówienia.
5. Whisper bez zmian, chyba że inny wariant rozpoznaje u Ciebie tak samo dobrze, a szybciej
   (porównaj na własnych nagraniach).
