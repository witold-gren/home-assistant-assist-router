# Jak robić to dobrze

Ta strona zbiera dobre praktyki i wszystkie ustawienia z wartościami domyślnymi z kodu integracji. Opis
każdego pola jest w [Plik router.yaml](router-yaml.md#router), a działanie krok po kroku w
[Edytor krok po kroku](editor.md).

## Zasady {#rules}

- **Zaczynaj od tego, o co domownicy już pytali.** Nowe tematy buduj z [dziennika nierozpoznanych](#log)
  (w edytorze <b class="ui">Nauka</b> → <b class="ui">Nierozpoznane zdania</b>), a nie z wymyślonych pytań.
- **Opisy tematów nie mogą się pokrywać.** `description` to słowa i zwroty, po których router wybiera temat. Dwa
  tematy z podobnym opisem to najczęstsza przyczyna złego wyboru.
- **2–4 prawdziwe przykłady na temat**, szczególnie sformułowania z pogranicza dwóch tematów.
- **Wskazuj dane wąsko.** Wzorce encji w kolejności ważności (najwyżej 80 encji trafia do modelu), `!wzorzec` wyklucza
  zbędne, `drop` pomija klucze atrybutów. Mniej danych to szybsza i pewniejsza odpowiedź.
- **`details` i `fetch` zamiast `command`.** Starsze pole `command` wymaga osobnej automatyzacji Assist; dane z encji
  i usług nie wymagają niczego więcej.
- **Każdą zmianę sprawdź testerem i zestawem testów** przed zapisem (<b class="ui">Tester</b>,
  <b class="ui">Zestaw testów</b>). Zdanie, które raz trafiło źle, dopisz do testów.
- **Po zmianie modelu powtórz [test modeli](#testing).** Wyniki z [Porównania modeli](models.md) dotyczą
  testowego domu; w Twoim liczy się Twój zestaw testów.

## Opcje integracji: wartości domyślne {#integration-defaults}

Ustawienia → Urządzenia i usługi → Assist Router → Konfiguruj (nazwy pól jak w Home Assistant).

| Opcja | Domyślnie | Na co wpływa |
| --- | --- | --- |
| <b class="ui">Adres Ollamy (router pytań)</b> | brak | Bez adresu router nie działa; zostaje agent HA i agent zapasowy. |
| <b class="ui">Model routera</b> | brak | Mały model wybierający temat; musi odpowiadać szybko (ok. 0,5 s). |
| <b class="ui">Czas na odpowiedź routera</b> | 8 s | Ile czekać na wybór tematu. Za krótko: wolny model nie zdąży. |
| <b class="ui">Trzymaj model w pamięci</b> | -1 (zawsze) | Minuty trzymania modelu w Ollamie. Mniej zwalnia pamięć, ale pierwsze pytanie po zwolnieniu czeka na wczytanie modelu. |
| <b class="ui">Model odpowiedzi</b> | brak | Pisze odpowiedzi z danych domu i streszczenia z Wikipedii. Bez niego pytania z danymi trafiają do agenta zapasowego, a z Wikipedii czytany jest początek artykułu. |
| <b class="ui">Czas na odpowiedź modelu</b> | 15 s | Ile czekać na odpowiedź modelu odpowiedzi (także przy Wikipedii). |
| <b class="ui">Agent zapasowy</b> | brak | Agent rozmowy dla pytań bez danych (rozmowa, żarty). |
| <b class="ui">Czas na odpowiedź agenta zapasowego</b> | 30 s | Po tym czasie asystent przestaje czekać na agenta zapasowego. |
| <b class="ui">Zapisuj nierozpoznane komendy</b> | włączone | Zapis do `/config/assist/unrecognized_commands.csv` i zdarzenie `assist_router_unrecognized`. |
| <b class="ui">Pokazuj edytor w pasku bocznym</b> | włączone | Wyłączone chowa panel; edytor dalej otwiera się pod `/assist-router-editor`. |

Kontekst modeli w Ollamie jest stały: router 4096, model odpowiedzi 8192 tokenów. Agent rozmowy Ollama w HA
z tym samym modelem co model odpowiedzi powinien mieć ten sam kontekst, inaczej Ollama wczytuje model od nowa.

## router.yaml: pola główne {#file-defaults}

| Pole | Domyślnie | Na co wpływa |
| --- | --- | --- |
| `language` | język HA, jeśli jest dla niego pakiet, inaczej `pl` | Pakiet językowy: słowa, prompty, nazwy dni. |
| `household` | pusty | Kto mieszka w domu; trafia do promptu routera i modelu odpowiedzi. |
| `people` | brak osób | Osoby w pytaniach. `name` = klucz, `match` = pierwsze 4 litery imienia, `speaker` = klucz. |
| `family` | brak | Rodzice i dzieci: kto widzi czyje dane w tematach `personal`. |
| `sentences` | 4 | Liczba zdań streszczenia z Wikipedii. |
| `wikipedia_language` | z pakietu (`pl`) | Wikipedia, z której pochodzą artykuły. |
| `answer_prompt`, `summary_prompt` | prompty z pakietu | Własny prompt modelu odpowiedzi i streszczeń. |
| `only_exposed` | `false` | `true`: encje tematów tylko spośród udostępnionych Assistowi. |
| `control_model` | `router` | Który model rozbiera polecenia sterowania: `router` albo `answer`. |
| `confirm_entities` | brak | Urządzenia, przy których asystent zawsze dopytuje (zamki, bramy i drzwi garażowe dopytuje zawsze). |
| `music_players` | brak | „Puść …”: pokój → odtwarzacze, pierwszy dostępny. |
| `announce_players` | brak | Głośniki ogłoszeń zamiast satelity. |
| `personas` | brak | Postać asystenta w potoku (prompt, płeć, potoki albo głosy). |

## Pola tematu: wartości domyślne {#topic-defaults}

| Pole | Domyślnie | Na co wpływa |
| --- | --- | --- |
| `entities` | brak | Stany encji; najwyżej 80, w kolejności wzorców. |
| `unavailable` | `false` | `true`: niedostępne encje trafiają do danych jako „niedostępne” zamiast być pomijane. |
| `only_exposed` | z pola głównego | Nadpisuje `only_exposed` dla tego tematu. |
| `details` | brak | Atrybuty encji, przycięte do osoby i dnia z pytania. |
| `fetch` → `limit` | 40 | Najwięcej pozycji z jednej usługi; jedno źródło to najwyżej 6000 znaków, usługa ma 10 s. |
| `frigate` | `labels: person`, `days: 7`, `limit: 30`, `summaries: 10`, `gap: 120` | Ile dni wstecz, ile pobytów i opisów, ile sekund łączy zdarzenia w jeden pobyt. |
| `days` | brak | Dzień, gdy pytanie go nie podaje. |
| `answer_tokens` | 0 = 160 tokenów | Dłuższa odpowiedź, np. 360 dla podsumowania dnia. |
| `personal`, `verbatim`, `control`, `unclear` | `false` | Zob. [Pola tematu](router-yaml.md#topic-fields). |

Sterowanie: polecenie dla 8 i więcej urządzeń naraz bez „wszystkie” albo „cały” asystent najpierw potwierdza;
„jaśniej”, „wyżej” zmieniają o 25%, „cieplej” o 1°; pytanie o potwierdzenie czeka 30 s.

## Dziennik nierozpoznanych {#log}

`/config/assist/unrecognized_commands.csv` (UTF-8, separator `;`)
otwiera się w Numbers i Excelu. Kolumny:

| Kolumna | Treść |
| --- | --- |
| `timestamp`, `area`, `device` | kiedy i na którym głośniku |
| `kind` | `no_intent_match` (HA nic nie rozpoznało) albo `no_valid_targets` (rozpoznało polecenie dla nieistniejącego obszaru lub urządzenia, np. „…w szkole”) |
| `text` | co usłyszał Whisper |
| `response` | co odpowiedział asystent |
| `route` | droga routera: temat, liczba encji i źródeł (`details`, `fetch`), „+ odpowiedź” / „+ streszczenie”, a przy sterowaniu intencja i parametry |
| `speaker` | rozpoznany mówca (Assist Speaker ID), puste = nieznany |

Przeglądaj go co jakiś czas. Pytania z pustym `route` albo złą odpowiedzią
pokazują, który temat poprawić. Częste zdania warto dopisać jako zwykłe zdania HA, bo te
działają natychmiast.

- **Podgląd w HA:** opcje integracji → „Nierozpoznane komendy” pokazują
  tabelę 30 ostatnich wpisów, od najnowszych.
- **Sensor** `sensor.assist_router_unrecognized_commands` (takie samo id w każdym
  języku HA; dawne `sensor.assist_router_nierozpoznane_komendy` zmienia się samo) podaje
  liczbę wpisów, a w atrybucie `last` ostatnie 20. Przydaje się do karty
  Markdown na dashboardzie.
- **Czyszczenie:** akcja `assist_router.clear_log` albo
  „Wyczyść dziennik” w opcjach. Nagłówek zostaje, a poprzednia treść ląduje w
  `unrecognized_commands.csv.bak`.
- Kolumna `speaker` zawiera rozpoznanego mówcę (Assist Speaker ID).

## Test i wybór modeli {#testing}

W katalogu `tools/` jest pięć narzędzi (Python, uruchamiane z dowolnego
komputera z dostępem do Ollamy):

- `snapshot_data.py` zapisuje migawkę prawdziwych danych: artykuły z Wikipedii
  i, dla przypadków z tematem (`topic`, pytanie, mówca), dane tematu dokładnie
  tak, jak buduje je integracja: encje, `details` i `fetch`, z osobą i
  dniem z pytania (potrzebuje `--router-config`). Zapisuje też chwilę migawki,
  którą model dostaje jako „teraz”, więc oczekiwane fakty w teście się nie zmieniają.
- `model_benchmark.py` testuje modele po kolei:
  - router, z tym samym promptem co integracja;
  - odpowiedzi z danych;
  - streszczenia.

  Ocena jest automatyczna: wymagane i zakazane fragmenty oraz długość. Sekcja
  `control` sprawdza rozbiór poleceń na obrazie domu z migawki, niczego nie
  wykonując. Odtwarza całą decyzję integracji: zabezpieczenie alarmu, samą odpowiedź
  „tak/nie”, nazwę skryptu bez modelu i rozbiór z listą akcji (skrypty z opisami, sceny).
  Sprawdza intencję, obszar, dopasowane urządzenie lub akcję i to, czy asystent by dopytał.
  `snapshot_data.py --only-home` odświeża sam obraz domu, np. po zmianie opisów
  albo aliasów. Same testy kodu (`pytest`) sprawdzają sterowanie od zdania do
  wywołanej usługi na sztucznym domu (`tests/test_actions.py`). Opcja
  `--rescore` ocenia zapisane odpowiedzi ponownie po poprawkach testu.
  Sekcja bez własnego `system` używa promptów integracji: odpowiedzi z danymi
  tematu z mówcą i podpowiedzią, a streszczenia (`prompt: summary`) promptem
  streszczenia. W routerze dwuznaczne pytanie może mieć listę równie dobrych tematów.
  Przy dłuższym teście wielu modeli: `--pull` pobiera brakujące modele (następny
  już w tle), `--delete-after` usuwa je po teście (nigdy modeli zainstalowanych
  przed startem; `--keep` chroni kolejne), a `--resume` pomija modele,
  które mają już komplet wyników, więc przerwany test można wznowić.
- `model_report.py` tworzy raport HTML i dopisuje historię do CSV, więc nowe
  modele można porównać ze starymi.
- `compare_sources.py` to test zgodności przy zmianie źródła danych tematu.
  Dla każdego pytania z listy liczy dane po staremu i po nowemu (dwa pliki router.yaml), np.
  zdania automatyzacji kontra `details`/`fetch`, na żywych danych z HA.
  Odpowiedzi modelu zapisuje obok siebie. Tylko odczyt.
- `check_sentences.py` sprawdza Twoje automatyzacje ze zdaniami. Z każdego wzorca
  wyzwalacza `conversation` generuje kilka zdań i pyta HA (tryb debug, nic nie
  jest wykonywane), co by je obsłużyło. Zgłasza zdania, które trafiają w inną automatyzację
  albo intencję HA, nie pasują do niczego, oraz automatyzacje wyłączone. Uruchamiaj po
  każdej zmianie zdań.

```
.venv/bin/python tools/model_benchmark.py --ollama http://localhost:11434 \
  --router-config /config/assist/router.yaml --cases model_test.yaml \
  --data model_test_data.yaml --router gemma4:e4b --answer gemma4:26b --pull --out wyniki.json
.venv/bin/python tools/model_report.py wyniki.json --label "test" \
  --html result.html --csv model_results.csv --answers-csv model_answers.csv
.venv/bin/python tools/compare_sources.py --ha http://homeassistant.local:8123 \
  --token-file ~/.ha_token --ollama http://localhost:11434 \
  --old router.yaml --new router.new.yaml --questions pytania.txt --out porownanie.json
.venv/bin/python tools/check_sentences.py --ha http://homeassistant.local:8123 \
  --token-file ~/.ha_token --config /config --per-template 5
```

Plik przypadków testowych (YAML) zawiera pytania z oczekiwanym tematem oraz dane z pytaniem i
oczekiwanymi faktami. Format opisuje początek pliku `tools/model_benchmark.py`. Trzymaj
go poza repozytorium, bo zawiera dane Twojego domu.

## Douczanie routera (opcjonalnie) {#fine-tuning}

Ogólny mały model rozpoznaje tematy dobrze, ale można go douczyć na danych własnego domu.
Służy do tego osobny zestaw skryptów, które w przyszłości trafią do osobnego repozytorium.
Do nauki potrzebna jest karta graficzna (np. RTX 4090), a model po douczeniu działa w Ollamie
jak każdy inny. Kroki:

1. pobranie z HA obszarów, encji z aliasami i osób oraz plików ze zdaniami;
2. zbiór danych:
   - zdania z Twoich szablonów hassil, z tematem przypisanym przez wzorcowe pytania z
     `router.yaml`;
   - wbudowane intencje HA z Twoimi nazwami;
   - pytania o wiedzę;
   - zakłócenia w stylu Whispera.
3. LoRA (Unsloth) z dokładnie tym samym promptem, którego używa integracja;
4. eksport do Ollamy;
5. test na pytaniach, które nie były w nauce.

Po zmianie listy tematów douczony model trzeba douczyć ponownie.

**Doświadczenie z pierwszej próby:** Gemma 4 E2B douczona na samych zdaniach z
szablonów rozpoznawała je w 99%, ale na swobodnych pytaniach z dziennika wypadła gorzej od
zwykłej Gemmy 4 E4B (88/96 wobec 93/96). Nauczyła się stylu szablonów, a nie języka.
Dlatego drugi przebieg łączy szablony z parafrazami, które pisze duży model (Gemma 4 26B):
naturalne pytania z imionami, pokojami i błędami Whispera. Bazą jest E4B.
