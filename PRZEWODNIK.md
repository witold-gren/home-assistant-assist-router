# Asystent głosowy po polsku w Home Assistant: przewodnik od zera

[English](GUIDE.md) · **Polski**

Ten przewodnik prowadzi krok po kroku od Home Assistanta bez asystenta do domu, w którym
można zapytać zwykłym zdaniem:

- „Na którą Ola idzie jutro do szkoły?”
- „Zgaś lampę w garderobie.”
- „Co mam jutro w kalendarzu?” (asystent wie, **kto** pyta)
- „Kim był Mikołaj Kopernik?”

Każdy krok mówi, **co** zrobić i **po co**, a szczegóły zostawia dokumentacji
poszczególnych części (linki w ramkach „Więcej”). Przykłady używają fikcyjnego domu:
Tomek (tata), Ania (mama), dzieci Ola i Kuba, jak w
[router.example.pl.yaml](router.example.pl.yaml).

> **Język:** Assist Router trzyma wszystko, co zależy od języka, w pakiecie językowym.
> Wbudowany jest pakiet polski i to on działa, gdy HA jest po polsku. Inne języki można
> dodać: zob. [Dodanie języka](README.pl.md#dodanie-języka).

> Nie musisz robić wszystkiego naraz. Kroki 1–5 dają działającego asystenta, a krok 6
> (rozpoznawanie mówcy) i krok 7 (własne automatyzacje) są dodatkiem.

---

## 0. Jak to działa w jednym obrazku

```
 Ty: „Co mam jutro?”
   │
   ▼
 satelita (głośnik z mikrofonem, np. Home Assistant Voice)
   │ dźwięk
   ▼
 Home Assistant: potok Assist (pipeline)
   ├─ 1. mowa → tekst        Whisper              (krok 2)
   │      └─ (opcjonalnie) kto mówi?  Assist Speaker ID   (krok 6)
   ├─ 2. tekst → odpowiedź   Assist Router        (krok 4)
   │      ├─ zdania HA i automatyzacje             (krok 7)
   │      └─ router pytań + modele w Ollamie       (krok 3)
   └─ 3. odpowiedź → mowa    Piper                (krok 2)
   │
   ▼
 satelita: „Jutro o 16:00 masz basen.”
```

| Element | Co robi | Gdzie działa | Więcej |
|---|---|---|---|
| **Satelita** | mikrofon i głośnik w pokoju, słowo wybudzające („Okay Nabu”, „Hey Jarvis”) | ESPHome, np. Home Assistant Voice PE | [dokumentacja HA: Voice](https://www.home-assistant.io/voice_control/) |
| **Whisper** | zamienia mowę na tekst | dodatek HA albo kontener (Wyoming, port 10300) | [Wyoming](https://www.home-assistant.io/integrations/wyoming/) |
| **Piper** | czyta odpowiedzi głosem | dodatek HA albo kontener (Wyoming, port 10200) | jw. |
| **Ollama** | uruchamia modele językowe lokalnie | ten sam albo inny komputer (port 11434) | [ollama.com](https://ollama.com) |
| **Assist Router** | rozumie zwykłe zdania: router pytań, sterowanie, Wikipedia | integracja HA (to repozytorium) | [dokumentacja](https://witold-gren.github.io/home-assistant-assist-router/pl/) |
| **Assist Speaker ID** | rozpoznaje, kto mówi | dodatek HA albo kontener + integracja HA | [home-assistant-assist-speaker-id](https://github.com/witold-gren/home-assistant-assist-speaker-id) |

**Sprzęt.** Whisper i modele językowe najlepiej działają na komputerze z kartą graficzną
albo na urządzeniu w rodzaju NVIDIA Jetson. Na samym procesorze też działają, ale
wolniej; wybierz wtedy mniejsze modele. Raspberry Pi wystarczy dla samego Home
Assistanta, na Whispera i modele językowe jest za słabe. Jakie modele wybrać i jak je
porównać: [dokumentacja, rozdział 3 (Wymagania i modele)](https://witold-gren.github.io/home-assistant-assist-router/pl/#wymagania).

---

## 1. Home Assistant i satelita

1. Zainstaluj Home Assistanta (najprościej Home Assistant OS) i ustaw **język polski**
   (Ustawienia → System → Ogólne).
2. Utwórz **obszary** dla pokojów: Ustawienia → Obszary. Nazwy obszarów są potem częścią
   zdań („w kuchni”, „w salonie”), więc nazywaj je tak, jak mówisz.
3. Podłącz satelitę: Home Assistant Voice PE pojawi się sam jako urządzenie ESPHome.
   Przypisz go do obszaru. Dzięki temu „włącz światło” bez pokoju działa w pokoju,
   w którym stoi głośnik.
4. Udostępnij Assistowi urządzenia, którymi chcesz sterować głosem: Ustawienia →
   Asystenci głosowi → Udostępnij.

---

## 2. Mowa na tekst i tekst na mowę: Whisper i Piper

Obie usługi mówią protokołem **Wyoming**, który Home Assistant obsługuje wbudowaną
integracją Wyoming.

**Wariant A: dodatki HA** (wszystko na jednym komputerze). Ustawienia → Dodatki → Sklep:
zainstaluj **Whisper** i **Piper**.
- Whisper: język `pl`, model jak największy, na jaki pozwala sprzęt. Mniejsze modele
  częściej przekręcają polskie słowa.
- Piper: polski głos, np. `pl_PL-gosia-medium` albo `pl_PL-darkman-medium`.

**Wariant B: kontenery na mocniejszym komputerze** (np. z kartą graficzną). Przykład
`docker-compose.yaml`:

```yaml
services:
  whisper:
    image: rhasspy/wyoming-whisper
    command: --model small-int8 --language pl
    ports: ["10300:10300"]
    volumes: ["./whisper:/data"]
    restart: unless-stopped
  piper:
    image: rhasspy/wyoming-piper
    command: --voice pl_PL-gosia-medium
    ports: ["10200:10200"]
    volumes: ["./piper:/data"]
    restart: unless-stopped
```

Potem w HA: Ustawienia → Urządzenia i usługi → Dodaj → **Wyoming Protocol**, osobno dla
Whispera (host, port 10300) i Pipera (host, port 10200).

**Sprawdzenie:** Ustawienia → Asystenci głosowi → (dowolny asystent) → przycisk mikrofonu
w oknie Assist. Powiedziane zdanie powinno pojawić się jako tekst.

---

## 3. Modele językowe: Ollama

Assist Router używa dwóch ról modeli. Mogą to być ten sam model albo dwa różne:

| Rola | Zadanie | Wymagania |
|---|---|---|
| **router** | wybiera **temat** pytania z listy (zwraca tylko nazwę tematu) | szybki; mały model wystarczy, większy myli się rzadziej |
| **model odpowiedzi** | pisze krótką odpowiedź z danych HA, rozbiera polecenia sterowania, streszcza Wikipedię | większy, dobrze piszący po polsku |

1. Zainstaluj [Ollamę](https://ollama.com) na komputerze z kartą graficzną (albo na tym
   samym co HA, jeśli jest dość mocny) i pobierz model: `ollama pull <model>`.
2. Sprawdź, że HA go widzi: `curl http://<host>:11434/api/tags` z sieci HA.

Który model wybrać: [dokumentacja, rozdział 3](https://witold-gren.github.io/home-assistant-assist-router/pl/#wymagania). Jak porównać modele
na pytaniach z Twojego domu: [rozdział 12 (Test i wybór modeli)](https://witold-gren.github.io/home-assistant-assist-router/pl/#test).
U autora router i odpowiedzi to ten sam model na Jetsonie AGX Orin 64 GB.

---

## 4. Assist Router

1. **Instalacja:** skopiuj `custom_components/assist_router` do
   `/config/custom_components/` (albo HACS → repozytorium niestandardowe, typ
   „Integracja”), zrestartuj HA i dodaj integrację **Assist Router** (Ustawienia →
   Urządzenia i usługi → Dodaj).
2. **Opcje** (Konfiguruj → Ustawienia):
   - adres Ollamy (`http://<host>:11434`);
   - w drugim kroku: model routera i model odpowiedzi;
   - opcjonalnie agent zapasowy: dowolny agent LLM dla pytań, na które router nie ma
     danych.

   Opis wszystkich pól: [dokumentacja, rozdział 5](https://witold-gren.github.io/home-assistant-assist-router/pl/#opcje).
3. **router.yaml:** skopiuj [router.example.pl.yaml](router.example.pl.yaml) do
   `/config/assist/router.yaml` ([router.example.yaml](router.example.yaml) to ten sam plik
   z angielskimi nazwami). Najważniejsze części:
   - `household`: kto mieszka w domu (model wie, że „mama” to Ania);
   - `people`: osoby i początki ich imion w odmianie (`match`); opcjonalnie `owns` (ich
     encje, np. kalendarz pracy), `labels` (etykiety HA na ich encjach), `room` (ich pokój) i `speaker` (głos, krok 6);
   - `family`: rodzice, dzieci, kto jest mężczyzną (do „mój brat”, „moja córka”);
   - `topics`: tematy pytań. Każdy ma opis i przykłady (dla routera) oraz źródło danych:
     `entities` (stany encji), `details` (atrybuty encji), `fetch` (usługi, np.
     `calendar.get_events`);
   - opcjonalnie `language`: pakiet językowy (domyślnie język HA, jeśli jest dla niego
     pakiet, inaczej `pl`);
   - w starszym polu `command` (szablon) zmienne nazywają się teraz `who`, `person`, `people`,
     `when`, `text`; polskie `kto`, `osoba`, `osoby`, `kiedy`, `tekst` nadal działają
     (`when` to angielski kod dnia, np. `tomorrow`, a `kiedy` - polska nazwa, np. `jutro`,
     więc `{{ 'jutro' if kiedy == 'jutro' else 'dzisiaj' }}` działa bez zmian);
   - kody dni w `days:` są teraz angielskie (`today`, `tomorrow`, `day_after_tomorrow`,
     `weekend`, `week`, `monday` … `sunday` albo liczba dni), ale polskie nazwy (`dzis`, `jutro`,
     `pojutrze`, `tydzien`, `poniedzialek` … `niedziela`) działają dalej jako aliasy. Nieznana
     wartość wyłącza router z błędem w logu.

   Plik edytujesz też w samym HA: opcje integracji → **Plik routera**. Przed zapisem plik
   jest sprawdzany, a poprzednia wersja zostaje jako `.bak`. Działa od razu, bez restartu.
   Opis pól i przykłady: [dokumentacja, rozdziały 6–9](https://witold-gren.github.io/home-assistant-assist-router/pl/#router).
4. **Sprawdzenie, co działa w Twoim domu:** opcje integracji → **Przykładowe komendy** →
   „Wygeneruj” (kilka minut). Model układa zdania z nazwami Twoich encji, a każde
   sprawdza prawdziwy router (polecenia sterowania tylko na sucho, nic się nie wykonuje).
   Wynik: `/config/assist/router_examples.yaml` (dla każdego tematu: `description`,
   `working` - zdania działające i `rejected` - odrzucone) i sensor „Przykładowe komendy”.
   Odrzucone zdania pokazują, który opis tematu warto poprawić.

---

## 5. Potoki Assist: łączymy wszystko

Ustawienia → Asystenci głosowi → **Dodaj asystenta** (najlepiej jeden na pokój, np.
„Kuchnia”):

| Pole | Wartość |
|---|---|
| Język | polski |
| Agent rozmowy | **Assist Router** |
| Zamiana mowy na tekst | Whisper (z kroku 2), a po kroku 6 **„Mowa na tekst z mówcą”** |
| Zamiana tekstu na mowę | Piper, polski głos |
| **Preferuj obsługę poleceń lokalnie** | **wyłączone** |

Ostatnie pole jest ważne. Gdy jest włączone, HA rozpoznaje wbudowane intencje jeszcze
**przed** Assist Routerem. „Ogłoszenie, …” rozgłosi wtedy tekst syntezą zamiast nagrania,
a „Kto to mówi?” i nagrywanie wzorca głosu nie dostaną pierwszeństwa. Nic nie tracisz:
Assist Router i tak najpierw przekazuje każde zdanie wbudowanemu agentowi HA.

Potem w ustawieniach satelity (urządzenie ESPHome → „Asystent”) wybierz potok tego pokoju.

**Sprawdzenie:** powiedz do satelity „Jaka będzie jutro pogoda?” i „Zgaś światło w
kuchni”. Szczegóły każdego zapytania pokazuje Ustawienia → Asystenci głosowi → ⋮ →
**Debugowanie**. Widać tam usłyszany tekst, wybrany temat i odpowiedź. Zdania, których
asystent nie zrozumiał, trafiają do dziennika: opcje Assist Routera → **Nierozpoznane
komendy** ([dokumentacja, rozdział 11](https://witold-gren.github.io/home-assistant-assist-router/pl/#dziennik)).

---

## 6. (Opcjonalnie) Kto mówi: Assist Speaker ID

Dzięki temu „Co mam jutro?” od Oli dotyczy jej kalendarza, a „Gdzie jest mój telefon?”
dzwoni na właściwy telefon. Dokumentacja:
[home-assistant-assist-speaker-id](https://github.com/witold-gren/home-assistant-assist-speaker-id).

**Jak to działa.** Usługa stoi między HA a Whisperem: dźwięk przekazuje bez zmian, a w tym
czasie zamienia głos na „odcisk” (wektor liczb) i porównuje go z zapisanymi wzorcami
domowników. Nie dodaje opóźnienia i nie zapisuje nagrań.

1. **Usługa:**
   - jako dodatek HA: dodaj repozytorium dodatków
     `https://github.com/witold-gren/home-assistant-assist-speaker-id`, zainstaluj **Speaker
     ID** i ustaw serwer zamiany mowy na tekst (np. `tcp://core-whisper:10300`);
   - albo jako kontener obok Whispera: README repozytorium, rozdział
     [„Usługa jako kontener”](https://github.com/witold-gren/home-assistant-assist-speaker-id/blob/main/README.pl.md#usługa-jako-kontener-np-obok-whispera-na-innym-komputerze).
2. **Integracja Assist Speaker ID** (HACS, repozytorium niestandardowe, typ „Integracja”). Dodatek
   HA zgłosi się sam; dla kontenera podaj host i porty 10350 i 10351.
3. **Potoki:** w każdym zmień zamianę mowy na tekst na **„Mowa na tekst z mówcą”**. Tekst
   jest ten sam co z Whispera, więc niczego to nie psuje.
4. **Wzorce głosu**, osobno dla każdej osoby. Narzędzia deweloperskie → Akcje:

   ```yaml
   action: speaker_id.start_enrollment
   data:
     speaker: ola          # ten sam klucz co w people w router.yaml
     name: Ola
     count: 10
     satellite: assist_satellite.kuchnia_assist_satellite
   ```

   Głośnik sam prosi o kolejne zdania („Nagrano 3 z 10. Kolejne zdanie.”), bez słowa
   wybudzającego. W tym czasie polecenia się nie wykonują. Mów zwykłe zdania po kilka słów,
   z typowej odległości.
5. **Kalibracja** po nagraniu wszystkich osób: akcja `speaker_id.calibrate` z
   `apply: true`. Każda osoba dostaje wtedy własny próg. Progi możesz też ustawić ręcznie:
   opcje integracji Assist Speaker ID → **Progi rozpoznawania**. Co oznaczają liczby i jak
   kalibrować podobne głosy (rodzeństwo): README Assist Speaker ID, rozdział „Jak czytać wyniki i
   progi”.
6. **Ogłoszenia:** „Ogłoszenie, dzieci proszę przyjść na obiad” (także „komunikat”, „do
   wszystkich”, „intercom” na początku zdania) odtwarza Twoje nagranie na pozostałych
   głośnikach zamiast syntezy. Dodatkowe odtwarzacze: `announce_players` w `router.yaml`
   (z Assist Speaker ID 0.1.1+ jeden głośnik w pokoju: dostępny odtwarzacz, np. HomePod,
   zamiast satelity w tym pokoju).
7. **Sprawdzenie:** zapytaj „Powiedz mi, kto teraz do ciebie mówi”. Asystent poda imię,
   podobieństwo w procentach i następną osobę w kolejce.

Co Assist Router robi z mówcą (1. osoba, `owns`, `room`, `family`, agent zapasowy):
[dokumentacja, rozdział 7, „Kto pyta”](https://witold-gren.github.io/home-assistant-assist-router/pl/#mowca).

---

## 7. Twoje automatyzacje ze zdaniami

Automatyzacje z wyzwalaczem „Zdanie” (conversation) działają jak dotąd i mają
pierwszeństwo przed routerem: HA sprawdza je, zanim zapyta Assist Router. Dwie zasady:

- **Pytania, które mają odpowiadać z danych, lepiej opisać jako temat w router.yaml niż
  jako automatyzację.** Temat rozumie dowolne sformułowanie, osobę, dzień i mówcę. Zdanie
  automatyzacji musi pasować dokładnie.
- **Mówca w automatyzacji:** zdania automatyzacji nie dostają mówcy wprost. Sensor „Ostatni
  mówca” zmienia się jednak w tym samym poleceniu. Makro `speaker()` z README Assist Speaker ID
  (rozdział „Użycie”, punkt 3) zwraca mówcę bieżącego zdania, np. żeby „gdzie jest mój
  telefon” dzwoniło na telefon tej osoby.

---

## 8. Gdy coś nie działa

| Objaw | Gdzie patrzeć |
|---|---|
| Asystent źle usłyszał zdanie | Debugowanie potoku → tekst z Whispera; większy model Whispera, wyraźniej, bliżej mikrofonu |
| „Nie rozumiem” albo zła odpowiedź na pytanie | dziennik Nierozpoznane komendy (kolumna `route`: który temat wybrał router); popraw `description` i `examples` tematu; „Przykładowe komendy” pokażą, co trafia gdzie indziej |
| Pytanie o dane, a odpowiedź „nie wiem” | czy encje tematu istnieją (Narzędzia deweloperskie → Stany); `only_exposed`; urządzenie jest niedostępne (dodaj `unavailable: true` do tematu); inna nazwa - dodaj alias encji; [dokumentacja, rozdział 7](https://witold-gren.github.io/home-assistant-assist-router/pl/#dane) |
| Polecenie sterowania nie działa | czy urządzenie jest udostępnione Assistowi; [dokumentacja, rozdział 10](https://witold-gren.github.io/home-assistant-assist-router/pl/#sterowanie) |
| Mówca „nieznany” | czy potok używa „Mowa na tekst z mówcą”; zdanie dłuższe niż 1 s; kalibracja i progi (README Assist Speaker ID) |
| Pomyłki między rodzeństwem | więcej próbek, większy margines (README Assist Speaker ID, „Jak kalibrować podobne głosy”) |

---

## 9. Prywatność

Wszystko działa lokalnie: mowa, modele, rozpoznawanie głosu. Wzorzec głosu to dane
biometryczne: Assist Speaker ID zapisuje tylko wektory, bez nagrań, a `speaker_id.delete_speaker`
usuwa wzorzec osoby. Domownicy powinni wiedzieć o rozpoznawaniu głosu.

Opcja `debug_recording_dir` w sekcji `assist_pipeline` w `configuration.yaml` zapisuje
dźwięk **każdego** polecenia na dysk. Włączaj ją tylko na czas diagnozy.

Więcej: [dokumentacja, rozdział 14](https://witold-gren.github.io/home-assistant-assist-router/pl/#prywatnosc) i README Assist Speaker ID, rozdział
„Prywatność”.

---

## Mapa dokumentacji

| Temat | Dokument |
|---|---|
| Assist Router: jak działa, router.yaml, źródła danych, sterowanie, mówca, dziennik, modele | [dokumentacja](https://witold-gren.github.io/home-assistant-assist-router/pl/) |
| Przykładowa konfiguracja routera z komentarzami | [router.example.pl.yaml](router.example.pl.yaml) (z angielskimi nazwami: [router.example.yaml](router.example.yaml)) |
| Porównanie modeli LLM | [modele](https://witold-gren.github.io/home-assistant-assist-router/pl/modele.html) |
| Dodanie języka | [README: Dodanie języka](README.pl.md#dodanie-języka) |
| Zmiany Assist Routera | [CHANGELOG.md](CHANGELOG.md) |
| Assist Speaker ID: instalacja, użycie, wzorce, progi i kalibracja, prywatność | [README Assist Speaker ID](https://github.com/witold-gren/home-assistant-assist-speaker-id#readme) |
| Dodatek Assist Speaker ID (opcje dodatku) | [speaker_id/DOCS.md](https://github.com/witold-gren/home-assistant-assist-speaker-id/blob/main/speaker_id/DOCS.md) |
| Asystent głosowy w Home Assistancie (oficjalnie) | [home-assistant.io/voice_control](https://www.home-assistant.io/voice_control/) |
