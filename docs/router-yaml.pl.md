# Plik router.yaml

## Plik router.yaml {#router}

`/config/assist/router.yaml` opisuje Twój dom. Kod integracji jest wspólny dla
wszystkich użytkowników. Zmiany w pliku działają od razu, bez restartu HA. Brak pliku
wyłącza router. Poniżej szkielet z najważniejszymi polami; pełny przykład domu z
kilkunastoma tematami jest w [Przykładowy router.yaml](#example), a to, jak kod zbiera i
przycina dane, opisuje [Skąd router bierze dane](data.md#data).

```
# language: pl            # pakiet językowy (domyślnie język HA, jeśli jest pakiet, inaczej pl)

# Kto mieszka w domu - trafia do promptu routera i modelu odpowiedzi
household: "Domownicy: Tomek (tata), Ania (mama), dzieci: Ola, Kuba."

# Osoby w pytaniach: match = początki słów (regex), żeby złapać odmianę
people:
  ola:  {name: Ola,  match: "ola|oli|olą|olę|aleksandr"}
  kuba: {name: Kuba, match: "kub|jakub"}
  tomek: {name: Tomek, match: "tom|tat(a|y|o|ą)\\b"}
  # family: {parents: [tomek, ania], children: [ola, kuba], men: [tomek, kuba]}
  # speaker: identyfikator głosu w Assist Speaker ID (domyślnie klucz osoby, tu „ola”, „kuba”)
  # owns: [calendar.kalendarz_oli] - encje tej osoby; room: Pokój Oli - jej pokój

sentences: 4              # ile zdań w streszczeniu z Wikipedii
wikipedia_language: pl
only_exposed: false       # true = encje tematów tylko spośród udostępnionych Assistowi
control_model: answer     # kto rozbiera polecenia sterowania: router albo answer
confirm_entities:         # zawsze dopytaj (wzorce entity_id albo nazwy)
  - switch.kuchnia_lodowka_przelacznik
  - switch.*_enabled
music_players:            # „puść …”: pokój -> odtwarzacze, pierwszy dostępny
  Salon: [media_player.salon_homepod, media_player.salon_home_assistant_voice]
# personas:               # kim jest asystent w potoku - postacie
#   jarvis: {pipelines: [Hej Jarvis], gender: male, prompt: "Jesteś Jarvisem z Iron Mana."}

topics:
  lekcje:
    description: szkoła, plan lekcji, zajęcia dodatkowe, o której kończy lekcje
    examples: ["Na którą Ola idzie jutro do szkoły?"]
    details: [sensor.plan_lekcji]    # atrybuty encji, przycięte do osoby i dnia z pytania
    days: dzis                       # bez dnia w pytaniu - dziś
    drop: [teacher, classroom]       # pomijane klucze

  kalendarz:
    description: plany, wydarzenia, spotkania, urodziny
    examples: ["Co mamy w weekend?"]
    days: "14"                       # bez dnia w pytaniu - 14 dni od dziś
    fetch:                           # usługa z odpowiedzią
      - action: calendar.get_events
        entities: [calendar.rodzina, calendar.praca]
        data: {start_date_time: "{start}", end_date_time: "{end}"}
        merge: events                # jedna lista ze wszystkich kalendarzy, po kolei
        title: Wydarzenia w kalendarzach

  samochod:
    description: auto - paliwo, zasięg, przebieg, czy zamknięte, gdzie stoi
    examples: ["Ile paliwa ma auto?", "Czy zamknąłem samochód?"]
    entities: [sensor.moje_auto_*, binary_sensor.moje_auto_*, lock.moje_auto_*]

  swiatla:
    description: które światła są włączone
    entities: [light.*, "!light.ipad_*"]   # „!” = wykluczenie
    skip_states: ["off"]

  sterowanie:
    description: polecenia - włącz, wyłącz, ustaw, przyciemnij, rolety, cieplej, głośniej
    examples: ["Zrób jaśniej w salonie.", "Opuść rolety do połowy."]
    control: true

  wiedza:
    description: pytanie o wiedzę ogólną - kim był, co to jest, historia, geografia
    examples: ["Kim był Mikołaj Kopernik?"]
    search: wikipedia

  inne:
    description: wszystko inne - rozmowa, żart, polecenia
    examples: ["Opowiedz coś ciekawego."]
```

### Pola tematu {#topic-fields}

| Pole | Znaczenie |
| --- | --- |
| `description` | Krótki opis dla routera: o czym są pytania z tego tematu. Opisy tematów nie powinny się pokrywać. |
| `examples` | 2–4 przykładowe pytania. Najbardziej pomagają przy sformułowaniach z pogranicza dwóch tematów. |
| `entities` | Wzorce `entity_id` (`*` = dowolny ciąg, `|klasa1,klasa2` = tylko te rodzaje czujników, `!wzorzec` = wykluczenie). Ich stany trafiają do danych po polsku: okno „otwarte”, zamek „zamknięty”. Pomijane są `unknown`/`unavailable`, najwyżej 80 encji, w kolejności wzorców (ważniejsze pierwsze). |
| `details` | Wzorce encji, których **atrybuty** idą do modelu (np. plan lekcji, saldo kont, odjazdy tramwajów). Listy są przycinane do osoby z pytania (klucz `child` albo `person`) i do dnia (klucz `date` albo `datetime`); szum (html, awatary, kolory, wartości `false`) jest pomijany, czasy są lokalne i z dniem tygodnia. |
| `fetch` | Usługi z odpowiedzią: `action`, `entities`, `data` (`{start}` i `{end}` = zakres dni z pytania), opcjonalnie `merge` (lista do połączenia z wszystkich encji), `past` (pozycje, których czas już minął: `drop` je pomija, więc podsumowanie dnia o 16:00 nie wspomni spotkania z południa; `mark` zostawia je z dopiskiem `już_było: true`, więc „ile miałem dziś spotkań” dalej się zgadza), `title` i `limit` (najwięcej pozycji, domyślnie 40). Np. kalendarze (`calendar.get_events`) albo prognoza (`weather.get_forecasts`). |
| `frigate` | Kogo, gdzie i kiedy widziały kamery **Frigate**: `url` (adres Frigate, port 5000 bez logowania), opcjonalnie `cameras` (kamera → nazwa do mówienia, np. `salon: Salon`; pytane są tylko te), `labels` (domyślnie `person`), `days` (ile dni wstecz, gdy pytanie nie podaje dnia, domyślnie 7), `limit` (najwięcej pobytów, 30), `summaries` (najwięcej opisów GenAI z przeglądów, 10; 0 = bez) i `gap` (sekundy, które jeszcze łączą zdarzenia w jeden pobyt, 120). Osoby z pytania to imiona twarzy we Frigate (`sub_label`), więc twarze w Face Library nazwij tak jak w `people`. Dni liczone są wstecz: dzień tygodnia to ostatni taki dzień, a „wczoraj” jest czytane z pytania. Bez wywoływania narzędzi - głosem nic we Frigate się nie przełączy. |
| `days` | Dzień, gdy pytanie go nie podaje, jako kod dnia. Kody są angielskie i takie same w każdym języku: `today`, `tomorrow`, `day_after_tomorrow`, `weekend`, `week` (ten tydzień), `monday` … `sunday` albo liczba dni (`"14"` = dziś i 13 kolejnych). Polski pakiet przyjmuje też polskie nazwy jako aliasy: `dzis`, `jutro`, `pojutrze`, `tydzien`, `poniedzialek` … `niedziela` (tak jak w przykładach), więc starsze pliki działają bez zmian. Nieznana wartość wyłącza router z błędem w logu. Bez tego pola dane nie są filtrowane po dniu. |
| `drop` | Klucze atrybutów pomijane w tym temacie. |
| `personal` | `true`: temat dla osoby, która pyta, także bez „mam” i „moje” („Dzień dobry”). Rodzic (`family.parents`) dostaje swoje dane i dane dzieci, a dziecko tylko swoje. Mówca nieznany oznacza dane wszystkich. Imię w pytaniu zawsze wygrywa. |
| `answer_hint` | Dodatkowa instrukcja dla modelu odpowiedzi w tym temacie, np. jak ułożyć podsumowanie dnia i co powiedzieć rodzicowi, a co dziecku. |
| `verbatim` | `true`: odpowiedź HA na wzorcowe zdanie z `command` jest czytana dosłownie, bez modelu odpowiedzi. Kilka zdań oddzielonych `;` daje wszystkie odpowiedzi po kolei. Przydaje się, gdy automatyzacja ma stały układ odpowiedzi, np. wiadomości dnia: „Dzisiejsze wiadomości z Polski: Pierwsza wiadomość…”. |
| `answer_hints` | Instrukcje zależne od tego, kto pyta. Klucze, po kolei: osoba (np. `ola`), `girl`/`boy` (dzieci), `child`/`parent`, `unknown` (mówca nierozpoznany). Brak pasującego klucza oznacza `answer_hint`. Prosta instrukcja dla jednej osoby działa pewniej niż jedna długa z warunkami. |
| `answer_tokens` | Dłuższa odpowiedź niż domyślne 160 tokenów, np. 360 dla podsumowania dnia. |
| `command` | (starsze) Szablon HA (Jinja) z wzorcowym pytaniem do Twojego HA, np. zdaniem automatyzacji. Kilka pytań rozdziel znakiem `;`. Zamiast tego lepiej użyć `details` i `fetch` - bez osobnych automatyzacji Assist. |
| `search: wikipedia` | Temat wiedzy: hasło jest brane z pytania, artykuł streszczany. |
| `control: true` | Temat poleceń sterowania ([Sterowanie domem](control.md)). |
| `unclear: true` | Temat bełkotu z rozpoznawania mowy: model odgaduje, co powiedziano, a asystent pyta „Czy chodziło o…?”; bez propozycji prosi o powtórzenie ([Sterowanie domem](control.md)). |
| *brak danych i search* | Pytanie idzie do agenta zapasowego. |

### Zmienne w szablonie `command` (starsze pole) {#variables-in-the-command-template}

| Zmienna | Polska nazwa (alias) | Wartość |
| --- | --- | --- |
| `person` | `osoba` | pierwsze imię z pytania (forma z `people.name`) albo brak |
| `people` | `osoby` | wszystkie imiona z pytania, po kolei: „Ola i Kuba” → `['Ola', 'Kuba']` |
| `who` | `kto` | klucz pierwszej osoby z `people` (np. `ola`) |
| `when` | `kiedy` | `when`: kod dnia (`today`, `tomorrow`, `day_after_tomorrow`, `weekend`, `week`, `monday` … `sunday`, liczba dni) albo brak; `kiedy`: polska nazwa dnia (`dzis`, `jutro`, `pojutrze`, `tydzien`, `poniedzialek` … `niedziela`), więc np. `{{ 'jutro' if kiedy == 'jutro' else 'dzisiaj' }}` działa bez zmian |
| `text` | `tekst` | pełne pytanie, np. do wyciągnięcia numeru linii tramwaju |

Udokumentowane są nazwy angielskie; polskie działają dalej (aliasy z pakietu językowego,
`COMMAND_VARIABLE_ALIASES`), więc starsze pliki `router.yaml` nie wymagają
zmian.

### Prompty modelu odpowiedzi {#answer-model-prompts}

Domyślne prompty są wbudowane w integrację. Możesz je nadpisać w `router.yaml`
polami `answer_prompt` (odpowiedź z danych) i `summary_prompt`
(streszczenie). W tekście możesz użyć pól `{household}`, `{now}` (data i
godzina po polsku) i `{sentences}`.

## Jak dodać nowy temat (krok po kroku) {#new-topic}

Przykład: pytania o pralkę i suszarkę, np. „Ile jeszcze będzie prać?” albo „Czy mogę wyjąć
pranie?”.

1. **Znajdź encje.** *Narzędzia deweloperskie → Stany*, wyszukaj np.
   `pralka`. Zwróć uwagę, czy potrzebna informacja jest w *stanie* (np.
   „czas do końca: 25 min”) - wtedy wystarczy `entities`, czy w
   *atrybutach* (listy, plany) - wtedy `details`.
2. **Jeśli dane daje usługa** (kalendarz, prognoza), sprawdź ją w
   *Narzędzia deweloperskie → Akcje* z zaznaczonym „Zwróć odpowiedź”. Ta sama akcja z
   tymi samymi danymi trafia do `fetch`; zamiast dat wpisz `{start}` i
   `{end}`.
3. **Dopisz temat:**

   ```
     pranie:
       description: pralka, suszarka, czy pranie się skończyło, ile jeszcze potrwa
       examples: ["Czy suszarka skończyła?", "Ile jeszcze będzie prać?"]
       entities: [sensor.pralka_*, sensor.suszarka_*]
   ```
4. **Zapisz i zapytaj** swobodnie. W pliku CSV, w kolumnie `route`,
   zobaczysz np. `pranie + 12 encji + odpowiedź`, a dla `details` i
   `fetch` `szkola + 1 źródeł + odpowiedź`.
5. **Jeśli router wybiera zły temat**, popraw `description` i dodaj
   pytanie z dziennika do `examples`.
6. **Jeśli odpowiedź jest zła, a temat dobry**, zobacz, co model dostał: dane
   są za długie (dodaj `drop`, `days`, `limit`), brakuje w nich
   odpowiedzi (dodaj encję) albo zawierają podobne, mylące encje (wyklucz je
   `!wzorzec`). Pomaga `tools/compare_sources.py` ([Test i wybór modeli](good-practice.md#testing)).

**Dobre praktyki**

- Mniej tematów, ale wyraźnie różnych, działa lepiej niż wiele podobnych. Lepiej jeden temat
  „samochód” z wszystkimi czujnikami auta niż trzy osobne.
- Daj modelowi pełne dane, np. plan lekcji z godzinami każdej lekcji. Wtedy odpowie też na
  pytania, których nie przewidziałeś („Ile godzin Ola jest w szkole?”).
- Dla danych z datami ustaw `days`, żeby pytanie bez dnia nie ściągało całego
  tygodnia.
- Najważniejsze wzorce wpisuj pierwsze: limit 80 encji odcina od końca.

Gotowe przykłady pytań i poleceń krok po kroku (granie, kamery, tryb prywatny, ogrzewanie, podcasty) są w
[Przepisy](recipes.md#recipes).

## Przykładowy router.yaml {#example}

Plik `router.example.pl.yaml` w repozytorium opisuje zmyślony dom: Tomek, Ania i
dwoje dzieci, Ola i Kuba. Encje mają nazwy, jakie zwykle tworzą popularne integracje:
aplikacja mobilna HA (lokalizacja telefonów), Frigate (kamery), Met.no (pogoda), kalendarze,
auto, odkurzacz, pralka i listy zakupów. Wystarczy podmienić nazwy encji na swoje
(*Narzędzia deweloperskie → Stany*). Ten sam dom z angielskimi nazwami tematów, osób i
pomieszczeń (wzór dla dokumentacji po angielsku) jest w `router.example.yaml`.

| Temat | Skąd dane | Co pokazuje |
| --- | --- | --- |
| `kalendarz` | `fetch`: `calendar.get_events`, `merge` | kilka kalendarzy w jednej liście, dzień z pytania, bez dnia 30 dni |
| `szkola` | `details` albo `fetch` | plan lekcji przycięty do dziecka i dnia; dwa warianty dziennika |
| `pogoda` | `entities` + 2 × `fetch` | odczyt z czujnika i prognoza dzienna oraz godzinowa (`limit: 24`) |
| `czujniki` | `entities` z `|klasa` | czujniki według `device_class`, tylko udostępnione |
| `okna_drzwi` | `entities` | okna, drzwi, garaż i rolety z czasem „od kiedy” |
| `osoby` | `entities` + `details` | domownicy, kamery Frigate, ruch, adres z telefonu; kolejność wzorców |
| `samochod` | `entities` | wszystkie czujniki auta - model wybiera |
| `swiatla` | `entities`, `skip_states`, `!` | tylko świecące, bez ekranu tabletu |
| `media` | `entities`, `skip_states` | tylko odtwarzacze, które coś grają |
| `listy` | `entities: [todo.*]` | pozycje list (integracja sama woła `todo.get_items`) |
| `komunikacja` | `details` | odjazdy z przystanków z atrybutów |
| `niezrozumiale` | `unclear: true` | bełkot z rozpoznawania mowy: propozycja „Czy chodziło o…?” albo prośba o powtórzenie |
| `sterowanie`, `wiedza`, `inne` | - | polecenia, Wikipedia, agent zapasowy |

```
# Przykładowy router.yaml dla Assist Routera - skopiuj do /config/assist/router.yaml
# i dopasuj encje do swojego domu (Narzędzia deweloperskie → Stany).
# Ten sam plik z angielskimi nazwami (dokumentacja po angielsku): router.example.yaml.
#
# Dom z przykładu: Tomek (tata), Ania (mama), dzieci Ola i Kuba. Encje mają nazwy, jakie
# zwykle tworzą popularne integracje: aplikacja mobilna HA (lokalizacja telefonów),
# Frigate (kamery), Met.no (pogoda), kalendarze Google/CalDAV, integracja auta, odkurzacza
# i pralki. Wszystkie nazwy encji są przykładowe.
#
# Jak router używa tego pliku:
#   1. Model routera wybiera JEDEN temat z `topics` (na podstawie description i examples).
#   2. Kod wyciąga z pytania osoby (`people`) i dzień („jutro”, „w piątek”).
#   3. Temat zbiera dane: stany encji (entities), atrybuty encji (details) i odpowiedzi
#      usług (fetch) - przycięte do osoby i dnia z pytania.
#   4. Model odpowiedzi odpowiada na pytanie wyłącznie z tych danych.
# Zmiany w pliku działają od razu, bez restartu HA.

# --- Ustawienia ogólne ---------------------------------------------------------------

# language: pl              # pakiet językowy; domyślnie język HA, jeśli jest dla niego pakiet,
#                           # inaczej pl. Nieznany kod wyłącza router (błąd w logu).

# Kto mieszka w domu - trafia do promptów (model wie, że „mama” to Ania, a „dzieci” to
# Ola i Kuba).
household: >-
  Domownicy: Tomek (tata, najczęściej pyta), Ania (mama), dzieci: Ola (Aleksandra, 10 lat)
  i Kuba (Jakub, 7 lat).

# Osoby w pytaniach. `match` to początki słów (regex), żeby złapać odmianę: „Oli”, „Olą”,
# „Kubie”, „taty”. Osoba z pytania przycina dane, które mają klucz `child` albo `person`
# (np. plan lekcji tylko Oli). Pytanie bez imienia („dzieci”) - dane wszystkich.
# Z rozpoznawaniem mówcy (integracja Assist Speaker ID) pytanie w 1. osobie („Co mam jutro?”)
# dotyczy tego, kto mówi. Dodatkowe pola osoby:
#   speaker - identyfikator jej głosu w Assist Speaker ID (domyślnie klucz osoby, np. „ola”),
#   owns    - jej encje (np. kalendarz pracy, telefon): w pytaniu o inną osobę są pomijane,
#             encje niczyje (kalendarz rodziny) - zawsze,
#   labels  - to samo etykietami Home Assistanta (Ustawienia -> Encje): encje z jedną z tych
#             etykiet należą do osoby (np. kalendarz z CalDAV albo Google),
#   room    - jej pokój: „zgaś światło w moim pokoju” od tej osoby = ten obszar.
people:
  tomek:
    name: Tomek
    match: "tom|tat(a|y|o|ą|ę)\\b"
    owns: [calendar.praca_tomka, sensor.telefon_tomka_*]
    labels: [tomek]
  ania:
    name: Ania
    match: "ani|anna|anny|mam(a|y|ie|ą|ę)\\b"
    owns: [sensor.telefon_ani_*]
  ola:
    name: Ola
    match: "ol(a|i|ą|ę|u)\\b|olk|aleksandr"
    room: Pokój Oli
  kuba:
    name: Kuba
    match: "kub|jakub"
    room: Pokój Kuby

# Określenia rodzinne względem mówcy: „mój brat” od Oli = Kuba, „moja córka” od Tomka =
# Ola, „moje dzieci” od Ani = Ola i Kuba. „mama”/„tata” to stałe imiona (match wyżej).
family:
  parents: [tomek, ania]
  children: [ola, kuba]
  men: [tomek, kuba]

sentences: 4                # ile zdań w streszczeniu z Wikipedii
wikipedia_language: pl
only_exposed: false         # true = encje tematów tylko spośród udostępnionych Assistowi
control_model: answer       # rozbiór poleceń sterowania: router albo answer (większy model)

# Sterowanie: przy tych urządzeniach asystent zawsze pyta „Czy wyłączyć…?” - także gdy
# trafią do polecenia zbiorczego („wyłącz wszystkie przełączniki”).
confirm_entities:
  - switch.lodowka
  - switch.serwer_*
  - switch.*_kamera_enabled     # włączniki kamer (Frigate)
  - Router Wi-Fi                # można też podać nazwę urządzenia

# „Puść …”: pokój -> odtwarzacze w kolejności (pierwszy dostępny). Odtwarzacze Music
# Assistanta często nie mają pokoju - stąd ta lista. Bez pokoju w poleceniu: pokój
# głośnika, do którego mówisz. Pusta lista albo niedostępne odtwarzacze = odpowiedź, że w tym
# pokoju nie ma na czym puścić muzyki (asystent nie wybiera wtedy innego głośnika).
music_players:
  Salon: [media_player.salon_glosnik, media_player.salon_telewizor]
  Sypialnia: [media_player.sypialnia_glosnik]
  Kuchnia: [media_player.kuchnia_glosnik]

# --- Tematy ---------------------------------------------------------------------------
#
# Źródła danych tematu (można łączyć):
#   entities  - wzorce entity_id; do modelu idzie stan po polsku („otwarte”, „w domu”).
#               `*` = dowolny ciąg, `|klasa1,klasa2` = tylko te device_class,
#               `!wzorzec` = wykluczenie. Kolejność ma znaczenie (limit 80 encji).
#   details   - wzorce encji, których ATRYBUTY idą do modelu (listy, plany, salda).
#   fetch     - usługi, które zwracają dane (calendar.get_events, weather.get_forecasts…).
#               `{start}` i `{end}` = zakres dni z pytania.
#   days      - dzień, gdy pytanie go nie podaje. Kody dni (angielskie, te same w każdym języku):
#               today, tomorrow, day_after_tomorrow, weekend, week (ten tydzień), monday … sunday
#               albo liczba dni ("14" = dziś i 13 kolejnych). Działają też polskie nazwy (aliasy):
#               dzis, jutro, pojutrze, weekend, tydzien, poniedzialek … niedziela.
#   drop      - klucze atrybutów do pominięcia (szum, którego model nie potrzebuje).
#   skip_states - stany pomijane (np. wyłączone światła - zostają tylko świecące).
#   unavailable - true = niedostępne encje trafiają do modelu jako „niedostępne” (zamiast
#               pominięcia; model nie odpowie wtedy „nie mam informacji”).

topics:
  # Podsumowania dla osoby, która pyta (wymaga Assist Speaker ID; bez niego - dla całej rodziny).
  # personal: bez imienia w pytaniu dane mówcy, a rodzica także dzieci.
  podsumowanie_dnia:
    description: dzień dobry, podsumowanie dnia, jak wygląda mój dzień, co mnie dziś czeka, plan na resztę dnia
    examples: ["Dzień dobry", "Jak wygląda mój dzisiejszy dzień?", "Co mnie dzisiaj czeka?"]
    personal: true
    days: dzis
    answer_tokens: 360
    answer_hint: >-
      To podsumowanie dnia na głos. Mów do osoby z „Pyta:”, po imieniu, zwykłymi zdaniami.
      Najpierw pogoda, potem jej plan (lekcje, wydarzenia, obowiązki). Rodzicowi dodaj
      jedno lub dwa zdania o najważniejszych sprawach dzieci. Do 6 zdań.
    details: [sensor.plan_lekcji, sensor.obowiazki]
    fetch:
      - action: calendar.get_events
        entities: [calendar.rodzina, calendar.praca_tomka]
        data: {start_date_time: "{start}", end_date_time: "{end}"}
        merge: events
      - action: weather.get_forecasts
        entities: [weather.dom]
        data: {type: daily}

  dobranoc:
    description: dobranoc, idę spać, co mnie czeka jutro
    examples: ["Dobranoc", "Idę spać", "Co mnie jutro czeka?"]
    personal: true
    days: jutro
    # instrukcja zależna od mówcy: osoba, girl/boy, child/parent, unknown
    answer_hints:
      girl: >-
        Jednym-dwoma zdaniami powiedz, co ją czeka jutro (bez domu i pogody), potem czule,
        bajkowo życz dobrej nocy po imieniu, jak księżniczce.
      boy: >-
        Jednym-dwoma zdaniami powiedz, co go czeka jutro (bez domu i pogody), potem na wesoło
        życz dobrej nocy po imieniu (np. ładowanie baterii superbohatera).
      parent: >-
        Co go czeka jutro i pogoda rano, co w domu zostało otwarte lub włączone, jedno
        zdanie o jutrze dzieci. Zakończ „Dobranoc”. Do 5 zdań.
      unknown: >-
        Krótko dla całej rodziny, bez imion: co jutro i co otwarte lub włączone w domu.
    details: [sensor.plan_lekcji]
    fetch:
      - action: calendar.get_events
        entities: [calendar.rodzina, calendar.praca_tomka]
        data: {start_date_time: "{start}", end_date_time: "{end}"}
        merge: events
    entities: [binary_sensor.*_okno, light.*]

  # Kalendarze: wydarzenia ze wszystkich kalendarzy w jednej liście, po kolei.
  # „Co mamy w piątek?” -> tylko piątek; „Kiedy są urodziny babci?” -> 30 dni od dziś.
  kalendarz:
    description: plany, wydarzenia, spotkania, urodziny, imieniny, święta, co mamy zaplanowane, terminy
    examples:
      - Co mamy w weekend?
      - Ile mam jutro spotkań w pracy?
      - Kiedy są urodziny babci?
      - Czy w czwartek coś się dzieje?
    days: "30"
    drop: [description]           # opisy spotkań (linki do wideorozmów) tylko zajmują miejsce
    fetch:
      - action: calendar.get_events
        entities: [calendar.rodzina, calendar.praca_tomka, calendar.urodziny, calendar.swieta_w_polsce]
        data: {start_date_time: "{start}", end_date_time: "{end}"}
        merge: events             # jedna lista ze wszystkich kalendarzy, posortowana po godzinie
        title: Wydarzenia w kalendarzach (po kolei)
        limit: 60

  # Szkoła z dziennika elektronicznego. Dwa typowe warianty - wybierz pasujący:
  #  a) integracja daje encję z atrybutami (dzieci -> dni -> lekcje): `details`;
  #  b) integracja daje kalendarz lekcji dla każdego dziecka: `fetch` jak w kalendarzu.
  szkola:
    description: szkoła, plan lekcji, o której zaczyna lub kończy lekcje, kiedy wraca ze szkoły, zastępstwa, odwołane lekcje
    examples:
      - Na którą Ola idzie jutro do szkoły?
      - Czy Kuba ma jutro WF?
      - O której dzieci kończą dziś lekcje?
    details: [sensor.dziennik_plan_lekcji]      # wariant a)
    days: dzis                                  # bez dnia w pytaniu - dziś
    drop: [teacher_id, classroom_id]
    # fetch:                                    # wariant b)
    #   - action: calendar.get_events
    #     entities: [calendar.lekcje_ola, calendar.lekcje_kuba]
    #     data: {start_date_time: "{start}", end_date_time: "{end}"}
    #     merge: events

  # Pogoda: teraz z czujników na balkonie, prognoza z usługi (dzienna i godzinowa).
  pogoda:
    description: pogoda na zewnątrz teraz i prognoza, deszcz, wiatr, czy wziąć parasol, jak się ubrać, temperatura na dworze
    examples:
      - Czy jutro będzie padać?
      - Czy wziąć parasol?
      - Jak się ubrać na weekend?
      - Ile jest stopni na dworze?
    entities:
      - sensor.balkon_temperatura
      - sensor.balkon_wilgotnosc
      - sensor.deszczomierz_*
    drop: [wind_bearing, uv_index, cloud_coverage, dew_point, pressure]
    fetch:
      - action: weather.get_forecasts
        entities: [weather.dom]
        data: {type: daily}
        title: Prognoza na kolejne dni
      - action: weather.get_forecasts
        entities: [weather.dom]
        data: {type: hourly}
        title: Prognoza godzinowa
        limit: 24                 # najwyżej doba - więcej tylko spowalnia odpowiedź

  # Klimat w pokojach: czujniki według rodzaju (device_class) i termostaty.
  czujniki:
    description: temperatura, wilgotność, CO2, jakość powietrza w pokojach, ogrzewanie, termostaty, czy jest duszno
    examples:
      - Ile stopni jest w pokoju Oli?
      - Gdzie jest najwyższe CO2?
      - Na ile jest ustawione ogrzewanie w salonie?
    only_exposed: true            # tylko czujniki udostępnione Assistowi (bez technicznych)
    entities:
      - sensor.*|temperature,humidity,carbon_dioxide,pm25,volatile_organic_compounds
      - climate.*

  # Okna, drzwi i rolety: czujniki otwarcia i pozycja rolet.
  okna_drzwi:
    description: które okna lub drzwi są otwarte, czy wszystko zamknięte, drzwi wejściowe, balkon, garaż, rolety
    examples:
      - Które okna są otwarte?
      - Czy zamknąłem drzwi balkonowe?
      - Od kiedy jest otwarte okno w sypialni?
    entities:
      - binary_sensor.*|door,window,opening,garage_door
      - cover.*

  # Kto jest w domu i gdzie: domownicy (person), adres z telefonu (aplikacja mobilna HA),
  # kamery Frigate (liczba osób), czujniki ruchu. Kolejność: najważniejsze najpierw.
  osoby:
    description: kto jest w domu, gdzie ktoś jest, czy ktoś jest w pokoju, gdzie był ruch, ile osób widzą kamery
    examples:
      - Gdzie jest mama?
      - Czy Kuba jest już w domu?
      - Czy ktoś jest w salonie?
      - Ile osób widzi kamera w ogrodzie?
    entities:
      - person.*
      - sensor.*_person_count                    # Frigate: liczba osób w kadrze
      - binary_sensor.*|motion,occupancy,presence
    details: [sensor.telefon_*_geocoded_location] # adres telefonu (atrybuty: ulica, miasto)
    drop: [Location, Country, ISO Country Code, Postal Code, Time Zone, Areas Of Interest,
           Administrative Area, Sub Administrative Area, Ocean, Inland Water]

  # Samochód: wszystkie czujniki auta - model wybierze, o co pytano.
  samochod:
    description: samochód - paliwo, zasięg, przebieg, spalanie, serwis, czy zamknięty, okna, opony, gdzie stoi
    examples:
      - Czy muszę zatankować?
      - Czy zamknąłem auto?
      - Gdzie zaparkowałem?
      - Kiedy przegląd?
    entities:
      - sensor.moje_auto_*
      - binary_sensor.moje_auto_*
      - lock.moje_auto_*
      - device_tracker.moje_auto_*

  # Światła: tylko świecące (skip_states), bez ekranu tabletu i podświetleń głośników.
  swiatla:
    description: które światła są włączone, gdzie się świeci, czy zostało zapalone światło, jasność lamp
    examples:
      - Czy zostawiłem gdzieś zapalone światło?
      - Które lampy świecą w kuchni?
    only_exposed: true
    entities:
      - light.*
      - "!light.*_ekran"
      - "!light.*_led_ring"
    skip_states: ["off"]

  # Co gra: tylko odtwarzacze, które coś robią.
  media:
    description: co teraz gra, muzyka, telewizor, głośniki, jaka głośność, czy telewizor jest włączony
    examples:
      - Co teraz gra w salonie?
      - Czy telewizor jest włączony?
    only_exposed: true
    entities:
      - media_player.*
    skip_states: ["off", "idle", "standby"]

  # Odkurzacz, pralka - stan i czas do końca.
  odkurzacz:
    description: odkurzacz, robot sprzątający, czy skończył, bateria, filtr, szczotki
    examples: ["Czy odkurzacz skończył?", "Ile baterii ma robot?"]
    entities: [vacuum.*, sensor.odkurzacz_*]

  pranie:
    description: pralka, suszarka, czy pranie się skończyło, ile zostało do końca
    examples: ["Czy pralka skończyła?", "Ile jeszcze będzie suszyć?"]
    entities: [sensor.pralka_*, sensor.suszarka_*]

  # Listy (todo): zawartość list, nie tylko liczba pozycji (todo.get_items).
  listy:
    description: lista zakupów, co trzeba kupić, przypomnienia, rzeczy do zrobienia
    examples: ["Co jest na liście zakupów?", "Czy mamy na liście mleko?"]
    entities: [todo.*]

  # Alarm i bezpieczeństwo - tylko odczyt (włączanie alarmu zostaw automatyzacjom).
  alarm:
    description: alarm, czy alarm jest włączony, tryb ochrony, zalanie, dym, gaz, czy gdzieś cieknie woda
    examples: ["Czy alarm jest włączony?", "Czy czujnik dymu coś wykrył?"]
    entities:
      - alarm_control_panel.*
      - binary_sensor.*|moisture,smoke,gas,carbon_monoxide

  # Komunikacja miejska: odjazdy z przystanków (integracje MPK/ZTM mają listę odjazdów
  # w atrybutach). Bez dnia - wszystko, co jest w danych.
  komunikacja:
    description: tramwaj, autobus, odjazdy z przystanku, za ile jest tramwaj
    examples: ["Za ile mam tramwaj 8?", "Kiedy jedzie autobus z Parkowej?"]
    details: [sensor.przystanek_*]
    drop: [html, original_departure]

  # Stan pozostałych urządzeń (gniazdka, przełączniki).
  urzadzenia:
    description: czy urządzenie jest włączone - gniazdka, przełączniki, ładowarki, akwarium
    examples: ["Czy akwarium jest włączone?", "Czy ładowarka w garażu działa?"]
    only_exposed: true
    unavailable: true             # niedostępne też - „Lustro jest niedostępne”
    entities: [switch.*]

  # Polecenia, których HA nie rozpoznał: rozbiór na intencję HA i wykonanie
  # (z dopytaniem przy wątpliwościach). Szczegóły: dokumentacja, rozdział „Sterowanie domem”.
  sterowanie:
    description: polecenia - włącz, wyłącz, zgaś, zapal, ustaw, przyciemnij, kolor światła, rolety, cieplej, głośniej, puść muzykę, odkurz, dopisz do listy
    examples:
      - Zrób ciepłe światło w sypialni.
      - Opuść rolety do połowy.
      - Puść jazz w kuchni.
      - Dopisz mleko do listy zakupów.
    control: true

  # Wiedza ogólna: streszczenie artykułu z Wikipedii (3–4 zdania).
  wiedza:
    description: pytanie o wiedzę ogólną - kim był, co to jest, historia, geografia, nauka
    examples: ["Kim był Mikołaj Kopernik?", "Co to jest fotosynteza?"]
    search: wikipedia

  # Bełkot z rozpoznawania mowy: słowa do siebie nie pasują. Asystent zgaduje, co powiedziano
  # („Czy chodziło o: włącz nastrój w salonie?”) albo prosi o powtórzenie. W opisie napisz
  # wprost, co tu NIE należy - inaczej router wrzuci tu też dziwne, ale sensowne pytania.
  niezrozumiale:
    description: zdanie bez sensu - słowa do siebie nie pasują i nie da się z nich zrozumieć ani pytania, ani polecenia; wygląda na przekręcone przez rozpoznawanie mowy. Tu NIE należą pytania i polecenia z jednym przekręconym słowem, gdy sens jest jasny, ani pytania o wiedzę, rozmowa i żarty
    examples:
      - Głup nastrój w pisarowie.
      - Szuflada wieczór gazeta kuchni.
    unclear: true

  # Wszystko inne - agent zapasowy (rozmowa, żarty).
  inne:
    description: wszystko inne - rozmowa, żart, prośby, pytania bez danych w domu
    examples: ["Opowiedz coś ciekawego.", "Jak się masz?"]
```
