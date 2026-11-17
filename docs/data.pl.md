# Skąd router bierze dane

## Skąd router bierze dane {#data}

Router nie potrzebuje specjalnych automatyzacji ani zdań Assist. Dane bierze wprost z Home
Assistanta, a w `router.yaml` opisujesz tylko, **które** encje i
usługi należą do tematu. Resztą zajmuje się kod: wybiera z danych to, o co pytano, usuwa
szum i podaje modelowi odpowiedzi zwięzłą listę faktów.

<div class="flow">
<svg aria-label="Schemat: pytanie, temat i osoba z dniem, źródła danych (entities, details, fetch), przycinanie, dane, model odpowiedzi" role="img" viewbox="0 0 900 470">
<defs><marker id="arrow2" markerheight="7" markerwidth="7" orient="auto-start-reverse" refx="9" refy="5" viewbox="0 0 10 10"><path d="M0,0 L10,5 L0,10 z"></path></marker></defs>
<rect class="box" height="66" rx="8" width="210" x="10" y="30"></rect>
<text text-anchor="middle" x="115" y="56">Pytanie</text>
<text class="small" text-anchor="middle" x="115" y="76">„Na którą Ola idzie jutro</text>
<text class="small" text-anchor="middle" x="115" y="89">do szkoły?”</text>
<rect class="box hot" height="52" rx="8" width="220" x="270" y="10"></rect>
<text text-anchor="middle" x="380" y="32">Router (model)</text>
<text class="small" text-anchor="middle" x="380" y="50">tylko temat: szkola</text>
<rect class="box" height="52" rx="8" width="220" x="270" y="72"></rect>
<text text-anchor="middle" x="380" y="94">Kod</text>
<text class="small" text-anchor="middle" x="380" y="112">osoba: ola · dzień: tomorrow (jutro)</text>
<rect class="box" height="62" rx="8" width="330" x="560" y="36"></rect>
<text text-anchor="middle" x="725" y="60">Temat w router.yaml</text>
<text class="small" text-anchor="middle" x="725" y="80">szkola: details, fetch, entities, days, drop</text>
<rect class="box" height="70" rx="8" width="270" x="10" y="160"></rect>
<text text-anchor="middle" x="145" y="184">entities</text>
<text class="small" text-anchor="middle" x="145" y="203">stany encji po polsku</text>
<text class="small" text-anchor="middle" x="145" y="218">„Okno salon: otwarte (od 12 min)”</text>
<rect class="box" height="70" rx="8" width="270" x="315" y="160"></rect>
<text text-anchor="middle" x="450" y="184">details</text>
<text class="small" text-anchor="middle" x="450" y="203">atrybuty encji</text>
<text class="small" text-anchor="middle" x="450" y="218">plan lekcji, saldo, odjazdy, adres</text>
<rect class="box" height="70" rx="8" width="270" x="620" y="160"></rect>
<text text-anchor="middle" x="755" y="184">fetch</text>
<text class="small" text-anchor="middle" x="755" y="203">usługi, które zwracają dane</text>
<text class="small" text-anchor="middle" x="755" y="218">calendar.get_events, weather.get_forecasts</text>
<rect class="box hot" height="78" rx="8" width="880" x="10" y="275"></rect>
<text text-anchor="middle" x="450" y="299">Przycinanie (kod, bez modelu)</text>
<text class="small" text-anchor="middle" x="450" y="320">osoba: tylko elementy z child/person pasującym do „Ola” · dzień: tylko date/datetime z jutra</text>
<text class="small" text-anchor="middle" x="450" y="338">bez szumu (html, awatary, kolory, false) · czas lokalny i dzień tygodnia · limity długości</text>
<rect class="box" height="62" rx="8" width="400" x="10" y="395"></rect>
<text text-anchor="middle" x="210" y="419">Dane dla modelu (zwięzły YAML)</text>
<text class="small" text-anchor="middle" x="210" y="439">zwykle kilkaset do kilku tysięcy znaków</text>
<rect class="box hot" height="62" rx="8" width="420" x="470" y="395"></rect>
<text text-anchor="middle" x="680" y="419">Model odpowiedzi</text>
<text class="small" text-anchor="middle" x="680" y="439">„Ola idzie jutro na 8:00, pierwsza jest matematyka.”</text>
<path class="arrow" d="M220,52 L268,38" style="marker-end:url(#arrow2)"></path>
<path class="arrow" d="M220,74 L268,96" style="marker-end:url(#arrow2)"></path>
<path class="arrow" d="M490,36 L558,58" style="marker-end:url(#arrow2)"></path>
<path class="arrow" d="M490,98 L558,80" style="marker-end:url(#arrow2)"></path>
<path class="arrow" d="M640,98 C560,130 250,120 160,158" style="marker-end:url(#arrow2)"></path>
<path class="arrow" d="M700,98 C640,130 470,130 455,158" style="marker-end:url(#arrow2)"></path>
<path class="arrow" d="M760,98 L758,158" style="marker-end:url(#arrow2)"></path>
<path class="arrow" d="M145,230 L145,273" style="marker-end:url(#arrow2)"></path>
<path class="arrow" d="M450,230 L450,273" style="marker-end:url(#arrow2)"></path>
<path class="arrow" d="M755,230 L755,273" style="marker-end:url(#arrow2)"></path>
<path class="arrow" d="M210,353 L210,393" style="marker-end:url(#arrow2)"></path>
<path class="arrow" d="M410,426 L468,426" style="marker-end:url(#arrow2)"></path>
</svg>
</div>

### Trzy źródła danych {#three-data-sources}

| Pole tematu | Co trafia do modelu | Typowe przykłady |
| --- | --- | --- |
| `entities` | Stan każdej pasującej encji, po polsku, z najważniejszymi atrybutami: jasność światła, pozycja rolety, temperatura termostatu, co gra, od kiedy czujnik jest otwarty. | okna i drzwi, światła, czujniki w pokojach, auto, osoby (`person.*`), ruch, alarm, pralka |
| `details` | Atrybuty encji, czyli dane, których nie widać w samym stanie: listy, plany, salda, adresy. | plan lekcji z dziennika, odjazdy z przystanku, adres telefonu (`*_geocoded_location`), konta kieszonkowego |
| `fetch` | Odpowiedź usługi HA, która zwraca dane. Zakres dni wynika z pytania. | kalendarze (`calendar.get_events`), prognoza (`weather.get_forecasts`) |

W jednym temacie możesz łączyć wszystkie trzy. Pogoda w przykładzie bierze bieżący odczyt z
czujników (`entities`) i prognozę z usługi (`fetch`).

### Jak kod przycina dane {#how-the-code-trims-data}

- **Osoba.** Element listy z kluczem `child` albo
  `person` zostaje tylko wtedy, gdy pasuje do osoby z pytania (wzorzec
  `match` z `people`, więc „Ola” trafia też w „Aleksandra”). Gdy osoby
  z pytania w ogóle nie ma w danych (tata pyta o konta dzieci), nic nie jest usuwane.
  Pytanie o „dzieci” albo bez imienia daje dane wszystkich.
- **Dzień.** Element z kluczem `date` albo `datetime`
  zostaje tylko wtedy, gdy wypada w dniu z pytania. Gdy pytanie nie podaje dnia, liczy się
  `days` tematu. Bez `days` dane nie są filtrowane po dniu. Gdy w danym
  dniu nic nie ma (lekcje w sobotę), model dostaje „brak” zamiast pustej listy. Filtr nie
  dotyczy samego korzenia atrybutów, bo tam `date` to zwykle data odczytu.
- **Szum.** Pomijane są: html, awatary, kolory, identyfikatory,
  `friendly_name`, wartości `false` („odwołana: nie”) i puste
  wartości oraz klucze z `drop`.
- **Czas.** Czasy ze strefą (prognozy są w UTC) są przeliczane na lokalne, a
  przy dacie pojawia się dzień tygodnia: `2026-10-24 12:00 (sobota)`. Model nie
  musi liczyć, który dzień to sobota.
- **Limity.** Najwyżej 80 encji w `entities` (w kolejności wzorców,
  więc najważniejsze wpisz pierwsze), 40 pozycji listy (`limit` w
  `fetch` zmienia to dla usługi) i 6000 znaków na jedno źródło.

### Dzień z pytania {#day-from-the-question}

Pakiet językowy rozpoznaje słowa o dniu w pytaniu i zamienia je na **kod dnia**
(`WHEN_PATTERNS`). Kody są angielskie i takie same w każdym języku - to je zawiera
zmienna `when` i je wpisuje się w `days:`. W `days:` działają też
polskie nazwy z kolumny „Alias”.

| W pytaniu | Kod dnia | Alias | Zakres dni |
| --- | --- | --- | --- |
| „dziś”, „dzisiaj”, „teraz” | `today` | `dzis` | dziś |
| „jutro”, „pojutrze” | `tomorrow`, `day_after_tomorrow` | `jutro`, `pojutrze` | ten jeden dzień |
| „w poniedziałek” … „w niedzielę” | `monday` … `sunday` | `poniedzialek` … `niedziela` | najbliższy taki dzień (dziś, jeśli to dziś) |
| „w weekend” | `weekend` | `weekend` | najbliższa sobota i niedziela |
| „w tym tygodniu” | `week` | `tydzien` | dziś i 6 kolejnych dni |
| nic | `days` tematu | | np. `today` (`dzis`) albo `"30"` (dziś i 29 kolejnych dni) |

### Przykład krok po kroku: plan lekcji {#step-by-step-example-school}

Pytanie: *„Na którą Ola idzie jutro do szkoły?”*. Router wybiera temat
`szkola`, a kod wyciąga osobę `ola` i dzień `tomorrow` (`jutro`). Temat ma
`details: [sensor.dziennik_plan_lekcji]`. Atrybuty tej encji to cały tydzień obojga
dzieci, kilkanaście tysięcy znaków:

```
{"friendly_name": "Plan lekcji", "week_start": "2026-10-19",
 "children": [
   {"child": "Aleksandra", "avatar": "https://…", "color": "#f5ec00",
    "days": [
      {"date": "2026-10-22", "lessons": [{"start": "08:00", "subject": "Matematyka", "canceled": false}, …]},
      {"date": "2026-10-23", "lessons": [{"start": "08:00", "subject": "Matematyka", "canceled": false},
                                         {"start": "08:55", "subject": "Przyroda", "canceled": true}, …]},
      …]},
   {"child": "Jakub", "days": […]}]}
```

Po przycięciu model dostaje tylko jutro Oli, bez awatarów, kolorów i
`canceled: false`:

```
Plan lekcji (stan: 2026-10-22):
week_start: 2026-10-19 (poniedziałek)
children:
- child: Aleksandra
  days:
  - date: 2026-10-23 (piątek)
    lessons:
    - start: 08:00
      subject: Matematyka
    - start: 08:55
      subject: Przyroda
      canceled: true
```

Odpowiedź modelu: *„Ola idzie jutro na 8:00, pierwsza jest matematyka. Przyroda o 8:55
jest odwołana.”* Model sam zauważył odwołaną lekcję, bo flaga `true` została w
danych.

### Przykład: kilka kalendarzy naraz {#example-several-calendars-at-once}

<div class="flow">
<svg aria-label="Schemat: cztery kalendarze, usługa calendar.get_events z zakresem dni, merge w jedną listę po godzinie" role="img" viewbox="0 0 900 210">
<defs><marker id="arrow3" markerheight="7" markerwidth="7" orient="auto-start-reverse" refx="9" refy="5" viewbox="0 0 10 10"><path d="M0,0 L10,5 L0,10 z"></path></marker></defs>
<rect class="box" height="40" rx="8" width="190" x="10" y="10"></rect>
<text text-anchor="middle" x="105" y="35">calendar.rodzina</text>
<rect class="box" height="40" rx="8" width="190" x="10" y="60"></rect>
<text text-anchor="middle" x="105" y="85">calendar.praca_tomka</text>
<rect class="box" height="40" rx="8" width="190" x="10" y="110"></rect>
<text text-anchor="middle" x="105" y="135">calendar.urodziny</text>
<rect class="box" height="40" rx="8" width="190" x="10" y="160"></rect>
<text text-anchor="middle" x="105" y="185">calendar.swieta_w_polsce</text>
<rect class="box" height="70" rx="8" width="250" x="260" y="70"></rect>
<text text-anchor="middle" x="385" y="94">calendar.get_events</text>
<text class="small" text-anchor="middle" x="385" y="113">„w piątek” → start: piątek 00:00</text>
<text class="small" text-anchor="middle" x="385" y="128">end: sobota 00:00</text>
<rect class="box hot" height="110" rx="8" width="320" x="570" y="50"></rect>
<text text-anchor="middle" x="730" y="74">merge: events</text>
<text class="small" text-anchor="middle" x="730" y="96">08:00 (piątek) Rodzina: wywiadówka</text>
<text class="small" text-anchor="middle" x="730" y="113">11:45 (piątek) Praca: spotkanie z klientem</text>
<text class="small" text-anchor="middle" x="730" y="130">16:30 (piątek) Rodzina: urodziny Franka</text>
<text class="small" text-anchor="middle" x="730" y="147">jedna lista po godzinie, ze źródłem</text>
<path class="arrow" d="M200,30 C230,30 240,80 258,92" style="marker-end:url(#arrow3)"></path>
<path class="arrow" d="M200,80 L258,98" style="marker-end:url(#arrow3)"></path>
<path class="arrow" d="M200,130 L258,114" style="marker-end:url(#arrow3)"></path>
<path class="arrow" d="M200,180 C230,180 240,130 258,122" style="marker-end:url(#arrow3)"></path>
<path class="arrow" d="M510,105 L568,105" style="marker-end:url(#arrow3)"></path>
</svg>
</div>

Bez `merge` każdy kalendarz byłby osobnym źródłem i model musiałby sam układać
wydarzenia w kolejności. Z `merge` pytanie „Co mamy w piątek?” dostaje gotowy plan
dnia, a „Kiedy są urodziny babci?” przeszukuje 30 dni (`days: "30"`).

**Bezpieczeństwo `fetch`.** Integracja wywołuje
tylko usługi, które *wyłącznie zwracają dane* (w HA: `SupportsResponse.ONLY`,
np. `calendar.get_events`, `weather.get_forecasts`,
`todo.get_items`). Wpis z usługą, która coś robi (`lock.unlock`, skrypt),
jest pomijany z ostrzeżeniem w logu. Pytanie nigdy niczego nie przełączy.

### A automatyzacje ze zdaniami? {#what-about-automations-with-sentences}

Nie są potrzebne. Jeśli już je masz, mogą zostać: HA sprawdza je *przed* routerem,
więc zdanie dokładnie pasujące do automatyzacji dostaje odpowiedź w ułamku sekundy, bez modelu.
Każde inne sformułowanie trafia do routera i odpowiada na nie model z danych. Starsze pole
`command` (wzorcowe pytanie do automatyzacji) nadal działa, ale nowe tematy lepiej
opisywać przez `entities`, `details` i `fetch`.

## Kto pyta: rozpoznany mówca (Assist Speaker ID) {#speaker}

Z integracją [Speaker
ID](https://github.com/witold-gren/home-assistant-assist-speaker-id) (zamiana mowy na tekst, która rozpoznaje też głos) router wie, kto zadał pytanie.
Wystarczy w pipeline'ach ustawić jej STT („Mowa na tekst z mówcą”). Agentem zostaje Assist
Router, który sam odczytuje mówcę z tego samego przebiegu pipeline'u.

- **Pytanie w 1. osobie bez imienia** („Jakie *mam* dzisiaj zajęcia?”,
  „Pokaż *moje* oceny”) dotyczy mówcy. `details` są przycinane do jego
  danych, jakby padło jego imię.
- **Imię w pytaniu wygrywa** („Jakie zajęcia ma Kuba?” od Oli to plan Kuby).
  Pytanie bez 1. osoby („Jaki jest plan lekcji?”) zostaje dla wszystkich.
  „Mamy” (my) nie jest 1. osobą liczby pojedynczej.
- **Model odpowiedzi dostaje linię „Pyta: Ola.”**, więc „mam” i „moje”
  rozumie jako tę osobę. Imię pochodzi z `people`, nie ze Assist Speaker ID.
- **Przypisanie głosu do osoby:** pole `speaker` przy osobie.
  Domyślnie jest to klucz osoby, więc wystarczy zapisać wzorce głosu pod tymi samymi
  identyfikatorami (`ola`, `kuba`…).
- **Mówca prawdopodobny** (Assist Speaker ID 0.2.0+): głos nie osiągnął progu
  osoby, ale najbardziej podobna osoba jest dość blisko (opcja „Prawdopodobny mówca od”). Tam,
  gdzie odpowiedź zależy od tego, kto pyta (1. osoba, tematy `personal`, określenia
  rodzinne, „w moim pokoju”), router używa tej osoby i mówi o tym na początku: „Wydaje mi się,
  że pyta Kasia. Dzisiaj masz…” (`probable_speaker` w pakiecie). Rozpoznanego mówcy
  nie wymienia; zgadywania, które niczego nie zmienia („Jaka jest pogoda?”, imię w pytaniu),
  nie mówi. Agent zapasowy nigdy nie dostaje imienia prawdopodobnego mówcy.
- **Mówca nieznany** (obcy głos, za krótka wypowiedź, tekst wpisany ręcznie)
  oznacza, że wszystko działa jak bez Assist Speaker ID.

**Encje i pokój osoby (`owns`, `labels`, `room`):**

- **`owns`** to wzorce encji należących do osoby, np. jej
  kalendarz albo lokalizacja jej telefonu. Gdy pytanie dotyczy konkretnej osoby (z imienia
  albo „mam”, „moje” od rozpoznanego mówcy), encje *innych* osób są pomijane w
  `details`, `fetch` i `entities`. Encje niczyje, np.
  kalendarz rodzinny, są zawsze brane. „Co mam jutro?” od Oli to więc kalendarz rodzinny
  i jej własny, bez kalendarza pracy taty. To jest potrzebne, bo wydarzenia kalendarza
  nie mają pola osoby, po którym dałoby się je przyciąć.
- **`labels`** robią to samo etykietami Home Assistanta: daj osobie
  `labels: [ola]` i oznacz jej encje etykietą „Ola” w *Ustawienia → Encje*
  (zaznacz encję → etykiety). Przydaje się przy kalendarzach z CalDAV albo Google Calendar,
  których Home Assistant nie łączy z osobą – nowy kalendarz przypisujesz w interfejsie, bez
  edycji `router.yaml`. `owns` i `labels` można łączyć. W
  temacie kalendarza ustaw `personal: true`, żeby rozpoznany mówca dostawał swoje i
  wspólne kalendarze także bez „mój” (rodzic – również kalendarze dzieci). Gdy osoba, o którą
  pytamy, nie ma własnego kalendarza, a inni mają, model odpowiedzi dostaje o tym informację i
  mówi to wprost, zamiast „nie ma żadnych wydarzeń”.
- **`room`** to pokój osoby. „Zgaś światło w moim pokoju” albo
  „u mnie w pokoju” od tej osoby oznacza ten obszar.
- **Określenia rodzinne względem mówcy** (sekcja `family`:
  `parents`, `children`, `men`). „Mój brat”, „moja
  siostra”, „rodzeństwo” od dziecka oraz „mój syn”, „moja córka”, „moje dzieci” od
  rodzica wskazują odpowiednie osoby, np. „moja córka” od taty to wszystkie córki.
  Dopisują się do imion z pytania („Czy mama i mój brat są w domu?”).
  „Mama”, „tata”, „żona” i „mąż” zostają stałymi imionami w `match`.
- **Agent zapasowy** też dostaje linię „Pyta: Ola.” w prompcie
  systemowym.
- **Zdania automatyzacji** HA obsługuje przed Assist Routerem, więc nie
  dostają mówcy wprost. Mogą go odczytać z sensora „Ostatni mówca” Assist Speaker ID, który jest
  świeży przez kilka sekund po rozpoznaniu, np. makrem `speaker()` (z README Assist Speaker ID) w
  `custom_templates`.

**Podsumowanie dnia i „dobranoc” dla osoby:** tematy z
`personal: true` zbierają dane mówcy. „Dzień dobry”, „Jak wygląda mój dzień?”, „Co
mnie dziś czeka?” od dziecka dają jego lekcje, sprawdziany, obowiązki i kalendarz. Od rodzica
dają jego kalendarz i pogodę oraz krótki skrót o dzieciach. Jak ułożyć odpowiedź, mówi
`answer_hint` tematu. Przykład: tematy `podsumowanie_dnia` i
`dobranoc` w `router.example.pl.yaml`. Sceny o tych nazwach uruchamia się
tylko jawnie („Uruchom scenę Dzień dobry”). Samo „Dzień dobry” jest powitaniem.

**Ogłoszenia (intercom):** zdanie zaczynające się od „ogłoszenie”,
„komunikat”, „do wszystkich” albo „intercom” („Ogłoszenie, dzieci proszę przyjść na
obiad”) nie trafia do HA ani do modeli. Assist Speaker ID odtwarza **nagranie mówcy**,
bez cięcia i bez zmian, na pozostałych głośnikach, a głośnik, który nagrał, mówi tylko
„Ogłoszenie wysłane.”. Odtwarzacze dodatkowe, np. HomePody, podajesz w
`router.yaml` jako `announce_players: [media_player.…]`; z Assist Speaker ID
0.1.1+ w pokoju gra jeden głośnik: dostępny odtwarzacz (np. HomePod) zamiast satelity, a pokój,
z którego pada ogłoszenie, nic nie dostaje. Bez nagrania
(tekst wpisany ręcznie albo brak Assist Speaker ID) zdanie idzie dalej zwykłą drogą: HA czyta je
syntezą mowy. Te słowa muszą być na początku zdania, więc „Jakie są ogłoszenia w Librusie?”
to zwykłe pytanie.

**Sprawdzenie rozpoznawania:** „Kto to mówi?”, „Kim jestem?”, „Jak mnie
rozpoznajesz?”, „Co to za głos?”. Asystent odpowiada od razu, bez HA i modeli, z wyniku tej
samej wypowiedzi, np. „Mówi Ola, podobieństwo 82 procent. Następna osoba: Kuba, 35 procent.”
Odpowiedź może też brzmieć „nie jestem pewien”, z dwoma
najbardziej podobnymi głosami, albo „nie rozpoznaję tego głosu” z najbliższą osobą, podobieństwem,
którego ta osoba potrzebuje (jej progiem), i następną osobą - np. „Najbliżej: Jan, 53 procent, a do
rozpoznania potrzeba 78 procent. Następna osoba: Kasia, 50 procent.” Wysoki próg zwykle oznacza, że
ktoś inny w domu ma podobny głos. Krótkie pytanie (poniżej 1 s mowy) daje prośbę o dłuższe
zdanie, np. „Powiedz mi, kto teraz do ciebie mówi”.

## Postać asystenta w potoku (personas) {#personas}

Każdy potok Assist może mieć własny głos i słowo wybudzające: „Hej Jarvis” z głosem Jarvisa,
Elza w pokoju córek, Optimus Prime u syna. Sekcja `personas` mówi modelom, kim jest
asystent w danym potoku. Bez niej, i w potokach, których nie wymienia, wszystko działa jak dotąd.

```
personas:
  jarvis:
    pipelines: [Hej Jarvis]          # fragment nazwy potoku albo jego identyfikator
    gender: male
    prompt: >-
      Jesteś Jarvisem, superinteligentnym systemem Tony'ego Starka z Iron Mana. Mówisz jako
      mężczyzna, uprzejmie i z lekką ironią.
  elza:
    voices: [pl_PL-elza-medium]      # głos TTS potoku - postać idzie za głosem
    gender: female
    prompt: Jesteś Elzą, królową z bajki Kraina lodu. Mówisz jako dziewczyna, ciepło i spokojnie.
```

- `prompt` - 1-2 zdania: kim jest postać i jak mówi. Trafia na koniec promptu modelu
  odpowiedzi (dane z HA), streszczeń Wikipedii i agenta zapasowego, ze wskazówką, by mówić stylem
  i w rodzaju gramatycznym postaci, ale fakty brać tylko z danych. Router tematów i rozbiór poleceń
  jej nie dostają, więc rozumienie poleceń się nie zmienia.
- `gender` (`male` / `female`, opcjonalnie) - stałe odpowiedzi
  asystenta w formie postaci: „Przepraszam, źle zrozumiałam”, „Nie znalazłam…”, „Nie jestem
  pewna…”.
- `voices` i `pipelines` - jak znaleźć potok (wystarczy jedno). Najpierw
  liczy się głos TTS potoku, potem fragment nazwy potoku albo jego identyfikator (bez znaczenia
  wielkość liter). Pierwsza pasująca postać wygrywa.

Potok jest rozpoznawany po przebiegu, który przekazał zdanie (satelity i okno Assist w
przeglądarce). Akcja `conversation.process` nie ma potoku, więc odpowiada zwykły asystent.
Zmiana działa od razu po zapisaniu pliku.
