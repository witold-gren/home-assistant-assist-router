# Przepisy: od pytania do odpowiedzi {#recipes}

Ta strona pokazuje na gotowych przykładach, jak dodać własne pytanie albo polecenie. Każdy przepis ma te same
części: **co powiesz**, **co musi być w Home Assistancie**, **co wpisać w edytorze** i **co usłyszysz**.
Przykłady dotyczą domu z tej dokumentacji (Tomek, Ania, Ola, Kuba); nazwy encji zamień na swoje
(*Narzędzia deweloperskie → Stany*).

## Dwie drogi {#two-roads}

Każda prośba do asystenta idzie jedną z dwóch dróg:

| Droga | Przykład | Co robi asystent | Co dodajesz |
| --- | --- | --- | --- |
| **Pytanie → odpowiedź** | „Jak długo Kuba dzisiaj grał?” | czyta dane z HA i odpowiada; niczego nie zmienia | temat z danymi w `router.yaml` (<b class="ui">Rodzaj tematu</b>: <b class="ui">Odpowiedź</b>) |
| **Pytanie → akcja → odpowiedź** | „Włącz tryb prywatny” | wykonuje coś w domu i mówi, co zrobił | skrypt albo urządzenie udostępnione Assistowi; `router.yaml` zwykle bez zmian |

Jak wybrać:

| Chcesz… | Zrób… | Przepis |
| --- | --- | --- |
| zapytać o coś, co HA już wie (stan, czas, licznik) | temat z <b class="ui">Encje</b> | [Granie](#gaming) |
| zapytać o coś, czego HA jeszcze nie liczy | najpierw pomocnik HA (statystyki historii, szablon), potem temat | [Granie](#gaming) |
| zapytać o zdarzenia z kamer | temat ze źródłem Frigate | [Ruch na kamerach](#motion) |
| uruchomić kilka czynności jednym zdaniem | skrypt z opisem | [Tryb prywatny](#private-mode) |
| włączyć albo wyłączyć jedno urządzenie | nic, wystarczy nazwa i obszar w HA | [Ogrzewanie](#heating) |
| usłyszeć po akcji własne zdanie | automatyzacja ze zdaniem i odpowiedzią | [Własna odpowiedź po akcji](#own-answer) |
| najpierw coś zrobić (odświeżyć), potem odpowiedzieć z wyniku | automatyzacja + temat z komendą | [Nowe podcasty](#podcasts) |

## Jak sprawdzić każdy przepis {#check}

Zawsze tak samo, zanim cokolwiek zapiszesz:

1. Wpisz zdanie w prawej kolumnie, w <b class="ui">Tester</b>, i kliknij <b class="ui">Sprawdź</b>. Tester niczego nie
   wykonuje w domu.
2. Zobacz, gdzie zdanie trafiło:
    - <b class="ui">1. Home Assistant</b> – HA rozpoznał je sam (wbudowane zdania albo Twoja automatyzacja);
    - <b class="ui">2. Router</b> – wybrany temat; zły temat poprawiasz w <b class="ui">Na co odpowiada (dla modelu routera)</b>
      albo dopisując pytanie do <b class="ui">Przykładowe pytania</b>;
    - <b class="ui">4. Sterowanie (plan)</b> – co zostałoby włączone lub uruchomione;
    - <b class="ui">5. Odpowiedź</b> – co usłyszysz.
3. Działa? <b class="ui">Dodaj do testów</b>, potem <b class="ui">Zapisz…</b>. Router czyta plik od razu, bez restartu.

## Pytanie → odpowiedź {#question-answer}

Asystent odpowiada **tylko z danych, które temat mu wskaże**. Dlatego najważniejsze pytanie brzmi: *czy HA
już ma tę informację w jakiejś encji?* Jeśli tak – wystarczy temat. Jeśli nie – najpierw pomocnik w HA, który ją
policzy, a model niech tylko ją przeczyta. Model słabo liczy; HA liczy dokładnie.

### Granie: ile dziś i ile zostało w tygodniu {#gaming}

**Co powiesz:** „Jak długo Kuba dzisiaj grał?”, „Ile Kuba może jeszcze grać w tym tygodniu?”

Oba pytania są o tym samym, więc to **jeden temat** z dwoma pytaniami. Mniej, ale wyraźnych tematów działa
lepiej niż wiele podobnych.

**1. Co musi być w HA.** Czas grania liczy pomocnik **Statystyki historii** (*Ustawienia → Urządzenia i usługi →
Pomocnicy → Utwórz pomocnika → Statystyki historii*): ile czasu encja konsoli była włączona. Potrzebne są dwa –
na dziś i na ten tydzień – oraz tygodniowy limit i to, co z niego zostało. To samo w YAML (np. w `packages/`):

```yaml
input_number:
  kuba_limit_grania:               # limit na tydzień, zmieniasz go w HA
    name: Kuba limit grania
    min: 0
    max: 40
    step: 0.5
    unit_of_measurement: h

sensor:
  - platform: history_stats
    name: Kuba granie dzisiaj
    entity_id: switch.konsola_kuby # encja, która jest „on”, gdy konsola działa
    state: "on"
    type: time
    start: "{{ today_at() }}"
    end: "{{ now() }}"
  - platform: history_stats
    name: Kuba granie w tygodniu
    entity_id: switch.konsola_kuby
    state: "on"
    type: time
    start: "{{ today_at() - timedelta(days=now().weekday()) }}"   # od poniedziałku
    end: "{{ now() }}"

template:
  - sensor:
      - name: Kuba granie zostało w tygodniu
        unit_of_measurement: h
        state: >
          {{ [states('input_number.kuba_limit_grania') | float(0)
              - states('sensor.kuba_granie_w_tygodniu') | float(0), 0] | max | round(2) }}
```

Sprawdź w *Narzędzia deweloperskie → Stany*, że `sensor.kuba_granie_dzisiaj` ma sensowną wartość, np. `1.75`
(godziny).

**2. Co wpisać w edytorze.** <b class="ui">Tematy pytań</b> → <b class="ui">+</b>:

- <b class="ui">Nazwa tematu</b>: `granie`;
- <b class="ui">Na co odpowiada (dla modelu routera)</b>: „granie, konsola, gry, komputer, jak długo grał, ile może
  grać, limit grania, czas przed ekranem”;
- <b class="ui">Przykładowe pytania</b>: oba zdania z góry i np. „Czy Kuba dużo dziś grał?”;
- <b class="ui">Encje</b> → <b class="ui">Wzorce encji</b>: `sensor.kuba_granie_*` i `input_number.kuba_limit_grania`
  – przy każdym wzorcu zielona liczba powinna być większa od zera;
- <b class="ui">Wskazówka dla modelu odpowiedzi</b>: „Czas podawaj w godzinach i minutach: 1.75 h to 1 godzina
  45 minut. Tydzień liczy się od poniedziałku.”

W pliku wygląda to tak:

```yaml
topics:
  granie:
    description: granie, konsola, gry, komputer, jak długo grał, ile może grać, limit grania, czas przed ekranem
    examples:
      - Jak długo Kuba dzisiaj grał?
      - Ile Kuba może jeszcze grać w tym tygodniu?
    entities: [sensor.kuba_granie_*, input_number.kuba_limit_grania]
    answer_hint: >-
      Czas podawaj w godzinach i minutach: 1.75 h to 1 godzina 45 minut.
      Tydzień liczy się od poniedziałku.
```

**3. Co usłyszysz:** „Kuba grał dzisiaj 1 godzinę 45 minut.” / „W tym tygodniu Kuba może jeszcze grać 3 godziny
i 30 minut.”

!!! tip "Gdy gra więcej dzieci"
    Dodaj takie same pomocniki dla Oli i wzorzec `sensor.*_granie_*`. Żeby pytanie o Kubę nie dostawało danych Oli,
    przypisz encje osobom polem `owns` w `people` (np. `owns: [sensor.kuba_granie_*]`) – wtedy pytanie z imieniem,
    a z rozpoznawaniem mówcy także „ile mogę jeszcze grać?”, widzi tylko dane tej osoby.

### Ruch na kamerach w ostatnich 24 godzinach {#motion}

**Co powiesz:** „Czy wykryto jakiś ruch na kamerze w ostatnich 24 godzinach?”, „Kto był wczoraj przed domem?”

**1. Co musi być w HA.** Kamery we **Frigate** (z wykrywaniem osób). Router pyta Frigate wprost o zdarzenia, więc
nie potrzebujesz żadnych pomocników.

**2. Co wpisać w edytorze.** Nowy temat jak wyżej (`kamery`, opis: „kamery, ruch, czy ktoś był, kto przechodził,
co widziały kamery, przed domem, w ogrodzie”, przykłady). Źródło Frigate wpisujesz w zakładce <b class="ui">YAML</b>
tematu:

```yaml
topics:
  kamery:
    description: kamery, ruch, czy ktoś był, kto przechodził, co widziały kamery, przed domem, w ogrodzie
    examples:
      - Czy wykryto jakiś ruch na kamerze w ostatnich 24 godzinach?
      - Kto był wczoraj przed domem?
    frigate:
      url: http://192.168.1.20:5000          # adres Frigate, port 5000 bez logowania
      cameras: {wejscie: Wejście, ogrod: Ogród}   # kamera → nazwa do mówienia
      labels: [person, car, dog, cat]        # co liczy się jako ruch (domyślnie tylko person)
      days: 2                                # pytanie bez dnia: wczoraj i dziś
    answer_hint: >-
      „Ostatnie 24 godziny” to od tej godziny wczoraj do teraz – wcześniejszych zdarzeń nie licz.
      Gdy nic nie było, powiedz to wprost.
```

`days: 2` bierze wczoraj i dziś – to obejmuje całe 24 godziny, a wskazówka mówi modelowi, gdzie je uciąć.

**3. Co usłyszysz:** „Tak, w ostatnich 24 godzinach kamera Wejście widziała osobę dwa razy: wczoraj o 18:40 i
dziś o 7:55.”

!!! note "Bez Frigate"
    Czujnik ruchu w HA pamięta tylko stan teraz. Żeby odpowiedzieć o ostatniej dobie, policz zdarzenia pomocnikiem
    **Statystyki historii** z `type: count`, `start: "{{ now() - timedelta(hours=24) }}"`, `end: "{{ now() }}"`
    i daj ten licznik do <b class="ui">Encje</b> tematu.

## Pytanie → akcja → odpowiedź {#question-action-answer}

Polecenia wykonuje temat z <b class="ui">Rodzaj tematu</b> <b class="ui">Sterowanie</b> (w przykładowym `router.yaml`
jest to `sterowanie`). Jeśli go masz, **w `router.yaml` nic nie dopisujesz** – router sam znajduje urządzenie albo
akcję po nazwie, obszarze i opisie. Twoja praca jest w Home Assistancie. Szczegóły: [Sterowanie domem](control.md#control).

### Tryb prywatny: kilka czynności jednym zdaniem {#private-mode}

**Co powiesz:** „Uruchom tryb prywatny”, „Włącz prywatność”, „Chcę mieć prywatność”.

**1. Co musi być w HA.** **Skrypt**, który robi wszystkie kroki, z **opisem** – model wybiera akcję po opisie,
więc działa każde sformułowanie, nie tylko wpisane słowa:

```yaml
script:
  tryb_prywatny:
    alias: Tryb prywatny
    description: >-
      Włącza tryb prywatny (prywatność): wyłącza kamery w domu i ich nagrywanie.
    sequence:
      - action: switch.turn_off
        target: {entity_id: [switch.kamera_salon, switch.kamera_kuchnia]}
      - action: input_boolean.turn_on
        target: {entity_id: input_boolean.tryb_prywatny}
```

Potem:

- udostępnij skrypt Assistowi (*Ustawienia → Asystenci głosowi → Udostępnij*);
- dodaj mu alias „Prywatność” (w tym samym oknie) – „włącz prywatność” trafi wtedy w nazwę wprost;
- pierwsze zdanie opisu ma mówić o efekcie – model widzi pierwsze 160 znaków.

**2. Co wpisać w edytorze:** nic. Sprawdź tylko w <b class="ui">Tester</b>: <b class="ui">4. Sterowanie (plan)</b> powinno
pokazać uruchomienie `script.tryb_prywatny`. Jeśli asystent ma zawsze pytać przed uruchomieniem, dopisz skrypt w
<b class="ui">Ustawienia</b> → <b class="ui">Potwierdzanie</b> → <b class="ui">Encje i urządzenia</b>.

**3. Co usłyszysz:** „Uruchomiono: Tryb prywatny.”

!!! warning "Wyłączenie trybu to osobny skrypt"
    Router zawsze **uruchamia** akcję – „wyłącz tryb prywatny” uruchomiłoby ten sam skrypt jeszcze raz. Zrób drugi
    skrypt, np. „Tryb prywatny – wyłącz”, z opisem „Wyłącza tryb prywatny: włącza z powrotem kamery…”.

### Ogrzewanie w łazience: jedno urządzenie {#heating}

**Co powiesz:** „Wyłącz ogrzewanie w łazience”, „Zrób cieplej w łazience”.

**1. Co musi być w HA.**

- termostat (np. `climate.lazienka`) w obszarze **Łazienka**;
- udostępniony Assistowi;
- jeśli nazywa się inaczej niż mówisz („Grzejnik łazienka”), alias „ogrzewanie”.

Ogrzewanie podłogowe na przełączniku (`switch.*`) wymaga tego samego.

**2. Co wpisać w edytorze:** nic. W <b class="ui">Tester</b> zobaczysz zwykle <b class="ui">1. Home Assistant</b>: HA rozpoznał
polecenie sam (wbudowane zdanie „wyłącz {nazwa} w {obszar}”). Gdy powiesz to inaczej („zakręć grzanie w
łazience”), zadziała temat sterowania – „cieplej” podniesie temperaturę o 1°.

**3. Co usłyszysz:** odpowiedź HA, np. „Wyłączono ogrzewanie.”, albo routera: „Wyłączono: Łazienka ogrzewanie.”

### Własna odpowiedź po akcji {#own-answer}

Po skrypcie router mówi krótko: „Uruchomiono: Tryb prywatny.” Jeśli chcesz usłyszeć coś więcej – np. ile kamer
wyłączono – zrób **automatyzację ze zdaniem**, która wykona akcję i ustawi odpowiedź:

```yaml
automation:
  - alias: Asystent – tryb prywatny
    triggers:
      - trigger: conversation
        command:
          - "(uruchom|włącz) (tryb prywatny|prywatność)"
    actions:
      - action: script.tryb_prywatny
      - set_conversation_response: >-
          Tryb prywatny włączony. Kamery w salonie i kuchni nie nagrywają.
```

HA sprawdza automatyzacje **przed** routerem, więc te zdania dostaną tę odpowiedź od razu, bez modelu.
`(a|b)` to jedno ze słów, `[a]` słowo opcjonalne. Inne sformułowanie („chcę mieć prywatność”) i tak trafi do
routera i uruchomi skrypt – tylko z krótką odpowiedzią.

### Nowe podcasty: najpierw akcja, potem odpowiedź z wyniku {#podcasts}

**Co powiesz:** „Czy są jakieś nowe podcasty?”, „Co nowego w podcastach?”

Tu asystent ma **najpierw coś zrobić** (odświeżyć kanały), a **potem odpowiedzieć z wyniku**. Służy do tego
temat z **komendą**: router rozpoznaje temat po dowolnym sformułowaniu, wysyła do HA zdanie z komendy, a
automatyzacja wykonuje akcję i zwraca dane, z których model układa odpowiedź.

**1. Co musi być w HA.** Kanały podcastów jako czujniki, np. z integracji **Feedparser** (HACS): `sensor.podcast_*`,
z odcinkami w atrybucie `entries`. Automatyzacja odświeża je i zwraca najnowszy odcinek każdego kanału:

```yaml
automation:
  - alias: Asystent – nowe podcasty
    triggers:
      - trigger: conversation
        command: "sprawdź nowe podcasty"
    actions:
      - action: homeassistant.update_entity
        target: {entity_id: [sensor.podcast_kawa_i_nauka, sensor.podcast_historia]}
      - delay: 3
      - set_conversation_response: >-
          {% for s in ['sensor.podcast_kawa_i_nauka', 'sensor.podcast_historia'] %}
          {%- set e = (state_attr(s, 'entries') or [{}])[0] %}
          {{ state_attr(s, 'friendly_name') }}: {{ e.title | default('brak odcinków') }}, {{ e.published | default('') }}.
          {% endfor %}
```

**2. Co wpisać w edytorze.** Temat `podcasty` (opis: „podcasty, nowe odcinki, co nowego w podcastach,
audycje”, przykłady) i w zakładce <b class="ui">YAML</b> komenda – zdanie automatyzacji:

```yaml
topics:
  podcasty:
    description: podcasty, nowe odcinki, co nowego w podcastach, audycje
    examples:
      - Czy są jakieś nowe podcasty?
      - Co nowego w podcastach?
    command: "sprawdź nowe podcasty"
    answer_hint: >-
      Nowy odcinek to taki z ostatnich 7 dni (porównaj datę z dzisiejszą). Wymień nowe: nazwa podcastu
      i tytuł. Gdy żadnego nie ma, powiedz to krótko.
```

<b class="ui">Czytaj odpowiedź HA bez zmian</b> zostaw wyłączone: wtedy model dostaje listę z automatyzacji jako dane
i sam ocenia, co jest nowe. Włącz je, gdy automatyzacja zwraca już gotowe zdanie do przeczytania.

**3. Co usłyszysz:** „Tak, są dwa nowe odcinki: w Kawie i nauce »Jak śpią delfiny« z wczoraj, a w Historii
»Bitwa pod Grunwaldem« z poniedziałku.”

!!! tip "Kiedy komenda, a kiedy dane"
    Jeśli kanały odświeżają się same (np. co godzinę), komenda nie jest potrzebna: wystarczy temat z
    <b class="ui">Atrybuty</b> → <b class="ui">Encje, których atrybuty idą do modelu</b>: `sensor.podcast_*` i ta sama wskazówka.
    Komenda jest dla pytań, przed którymi trzeba coś **zrobić**.

## Gdy przepis nie działa {#troubleshooting}

| Co widzisz w testerze | Co zrobić |
| --- | --- |
| <b class="ui">2. Router</b> wybrał inny temat | dopisz słowa z pytania do <b class="ui">Na co odpowiada (dla modelu routera)</b> i samo pytanie do <b class="ui">Przykładowe pytania</b> |
| temat dobry, ale odpowiedź „nie mam informacji” | rozwiń dane modelu w <b class="ui">4. Dane</b>: brak encji (wzorzec z liczbą 0) albo wartość `unknown` |
| odpowiedź liczy źle (czas, różnice) | policz to w HA pomocnikiem (szablon, statystyki historii), modelowi daj gotową liczbę |
| <b class="ui">4. Sterowanie (plan)</b> wybiera złe urządzenie | popraw nazwę lub alias w HA, sprawdź obszar; skryptowi dopisz wyraźniejszy opis |
| polecenie nic nie robi | encja lub skrypt nieudostępnione Assistowi |
| automatyzacja się nie uruchamia | zdanie musi pasować dokładnie; sprawdź je w <b class="ui">Komendy Home Assistanta</b> → <b class="ui">Co rozpozna Home Assistant</b> |

Więcej o polach tematu: [Plik router.yaml](router-yaml.md#topic-fields), o danych: [Skąd router bierze dane](data.md#data),
o poleceniach: [Sterowanie domem](control.md#control).
