# Instalacja

## Wypróbuj na Macu {#try-on-a-mac}

- **Potrzebne:** tylko [Docker Desktop](https://www.docker.com/products/docker-desktop/), uruchomiony. Bez Pythona,
  bez Home Assistant, bez Ollamy, bez GPU.
- **Uruchom:** `make demo` (pierwsza budowa małego obrazu trwa poniżej minuty).
- **Otwórz:** <http://127.0.0.1:8767/dev/editor-demo.html> (po angielsku: dopisz `?lang=en`), bez logowania.
- **Udawane:** przykładowy `router.example.pl.yaml` w zmyślonym domu, w kontenerze; nic się nie zapisuje i nic nie
  trafia do prawdziwego Home Assistant. Ctrl+C zatrzymuje i usuwa kontener, `make demo-clean` usuwa obraz.
- **Dokumentacja i dla programisty:** `make docs` buduje tę dokumentację w Dockerze i ją otwiera. `make test`
  i `make test-browser` potrzebują `make setup` (uv, który sam pobiera Pythona 3.14; Chrome do testów
  w przeglądarce); `make demo-local` podaje tę samą stronę bez Dockera.

## Wymagania i modele {#requirements}

- Home Assistant 2026.x (testowane na 2026.10) z polskim Assistem (Whisper i Piper albo
  inne STT/TTS).
- Serwer [Ollama](https://ollama.com) w sieci lokalnej. Może to być inny
  komputer niż HA.
- Opcjonalnie agent zapasowy, np. integracja Ollama z modelem do swobodnej rozmowy.

!!! tip

    **Sprawdzone w praktyce:** cały zestaw działa na co dzień w domu autora
    na **NVIDIA Jetson AGX Orin 64 GB**: Ollama (Gemma 4 26B jako router i model odpowiedzi),
    faster-whisper i Assist Speaker ID. Działa bardzo dobrze: router odpowiada w ok. 0,7 s, a odpowiedź
    z danych (router i model odpowiedzi) zajmuje ok. 2 s. 64 GB wspólnej pamięci mieści model razem z Whisperem.

Przykładowe wyniki z NVIDIA Jetson AGX Orin 64 GB. Test obejmował 96 pytań do routera, 34
pytania o prawdziwe dane z HA i 8 streszczeń z Wikipedii:

| Rola | Model | Trafność | Czas |
| --- | --- | --- | --- |
| Router | Gemma 4 26B (ten sam model co odpowiedzi, w pamięci raz) | 153/153 (z akcjami i bełkotem) | 0,7 s |
| Router (mniejszy) | Gemma 4 E4B | 92/96 | 0,5 s |
| Model odpowiedzi | Gemma 4 26B (MoE, 4B aktywnych) | 34/34 dane, 8/8 streszczeń | 1,2 s / 5,5 s |
| Rozbiór poleceń sterowania | Gemma 4 26B (`control_model: answer`) | 67/67 polecenia (z akcjami) | 2,7 s |
| Zgadywanie zdania po bełkocie | Gemma 4 26B | z 10 przykładów: 6 trafnych, 3× „nie wiem” (prośba o powtórzenie), 1 śmiała propozycja | 1,6 s |
| Wersja oszczędna | Gemma 4 E4B we wszystkich rolach | 29/34 dane, 8/8 streszczeń, 26/32 polecenia | 0,8 s / 3,8 s / 1,7 s |

**[Pełne porównanie kilkunastu modeli](models.md)** (Gemma 4, Bielik, PLLuM,
Qwen 3.5, Ministral): trafność i czas w każdej roli, wnioski, typowe błędy i wyniki douczania.
Test można powtórzyć na własnym sprzęcie: [Test i wybór modeli](good-practice.md#testing).

**Pamięć modeli.** Ollama ładuje model z kontekstem podanym w
zapytaniu. Integracja używa stałego kontekstu: 4096 dla routera i 8192 dla modelu odpowiedzi.
Jeśli agent zapasowy w integracji Ollama używa *tego samego* modelu co model odpowiedzi,
ustaw mu też kontekst 8192. Inaczej Ollama będzie przeładowywać model przy każdym pytaniu.

## Instalacja {#installation}

1. Skopiuj `custom_components/assist_router` do katalogu
   `/config/custom_components/`. Możesz też dodać repozytorium w HACS jako
   repozytorium niestandardowe typu „Integracja”.
2. Zrestartuj Home Assistant.
3. **Ustawienia → Urządzenia i usługi → Dodaj integrację → Assist Router.**
4. **Ustawienia → Asystenci głosowi:** w każdym potoku zmień agenta rozmowy na
   **„Assist Router”** (encja `conversation.assist_router`) i
   **wyłącz „Preferuj obsługę poleceń lokalnie”**. Przy włączonej opcji HA
   rozpoznaje wbudowane intencje przed Assist Routerem: „Ogłoszenie, …” poszłoby syntezą,
   a „Kto to mówi?” i nagrywanie wzorca głosu nie miałyby pierwszeństwa. Assist Router i tak
   najpierw przekazuje każde zdanie wbudowanemu agentowi, więc nic się nie traci.
5. Skopiuj `router.example.pl.yaml` z repozytorium do
   `/config/assist/router.yaml` i dopasuj encje do swojego domu (opis pliku:
   [Przykładowy router.yaml](router-yaml.md#example)). `router.example.yaml` to ten sam plik z
   angielskimi nazwami.
6. W opcjach integracji podaj adres Ollamy i wybierz modele ([Opcje integracji](#options)).
7. Opcjonalnie: [Speaker
   ID](https://github.com/witold-gren/home-assistant-assist-speaker-id), żeby asystent wiedział, kto pyta ([Kto pyta: rozpoznany mówca (Assist Speaker ID)](data.md#speaker)).
   Assist Router odczytuje mówcę sam, wystarczy zmienić w potokach zamianę mowy na tekst.

## Opcje integracji {#options}

**Ustawienia → Urządzenia i usługi → Assist Router → Konfiguruj** otwiera menu:

| Pozycja | Co robi |
| --- | --- |
| Ustawienia | Dwa kroki opisane niżej. |
| Plik routera (router.yaml) | Edycja `/config/assist/router.yaml` wprost w HA. Przed zapisem plik jest sprawdzany (zły YAML albo błąd konfiguracji pokazuje komunikat i nic nie zapisuje), a poprzednia wersja zostaje jako `router.yaml.bak`. Router czyta zmiany od następnego pytania, bez restartu. |
| Przykładowe komendy | Podgląd zdań, które działają w tym domu, i ich generowanie (patrz niżej). |
| Nierozpoznane komendy | Tabela ostatnich 30 wpisów dziennika (od najnowszych) i opcja „Wyczyść dziennik”; poprzednia treść zostaje jako `unrecognized_commands.csv.bak`. |

### Przykładowe komendy dla Twojego domu {#examples}

Akcja `assist_router.generate_examples` albo pozycja menu „Przykładowe
komendy” działa tak:

1. Dla każdego tematu z `router.yaml` model odpowiedzi układa zdania z
   prawdziwymi nazwami: encjami tematu, urządzeniami i pokojami (sterowanie) oraz domownikami.
2. **Każde zdanie przechodzi przez prawdziwy router.** Zostaje tylko wtedy,
   gdy trafi do swojego tematu.
3. Polecenia sterowania przechodzą też rozbiór i plan polecenia, **bez
   wykonania**.

Wynik:

- plik `/config/assist/router_examples.yaml`: dla każdego tematu
  `description` (opis), `working` (zdania działające) i
  `rejected` (odrzucone: `sentence` i dokąd trafiło - `topic`, albo
  `control` z powodem, dla którego polecenie by nie zadziałało), co jest wskazówką, który
  opis tematu albo przykład poprawić. Pliki ze starszych wersji z kluczami `dzialaja` /
  `odrzucone` nadal są czytane;
- sensor **„Przykładowe komendy”**: stan to liczba działających zdań, w
  atrybucie `topics` są zdania tematów;
- podgląd w opcjach.

Generowanie trwa kilka minut, bo każde zdanie to osobne zapytanie do routera. Opcje
akcji: `per_topic` (ile zdań na temat, domyślnie 5) i `topics` (tylko
wybrane tematy). Tematy bełkotu (`unclear: true`) są pomijane. Odpowiedź akcji podaje
liczby `working` i `rejected` dla każdego tematu.

Akcja `assist_router.clear_log` czyści dziennik nierozpoznanych. Sensor
**„Nierozpoznane komendy”** pokazuje liczbę wpisów, a w atrybucie
`last` ostatnie 20, co przydaje się do karty Markdown na dashboardzie.

**Ustawienia**, krok pierwszy:

| Opcja | Co robi |
| --- | --- |
| Zapisuj nierozpoznane komendy | Dopisuje każde nierozpoznane zdanie do `/config/assist/unrecognized_commands.csv` i wysyła zdarzenie `assist_router_unrecognized`. |
| Agent zapasowy | Agent rozmowy dla pytań, którym router nie dał danych (temat „inne”, błąd). Puste = komunikat „Powiedziałeś: …”. |
| Czas na odpowiedź agenta zapasowego | Po tym czasie słychać „Powiedziałeś: …”. |
| Adres Ollamy | Np. `http://localhost:11434`. Puste = router wyłączony. |

Krok drugi pojawia się, gdy podasz adres Ollamy. Lista modeli jest pobierana z serwera:

| Opcja | Co robi |
| --- | --- |
| Model routera | Wybiera temat. Wystarczy mały i szybki model. |
| Model odpowiedzi | Opcjonalny, ale potrzebny do odpowiedzi z danych. Pisze odpowiedź z danych tematu i streszcza Wikipedię. Bez niego pytania z danymi trafiają do agenta zapasowego, a z Wikipedii czytany jest początek artykułu. |
| Czas na odpowiedź routera / modelu | Domyślnie 8 s i 15 s. Ten sam limit routera dotyczy też wyszukiwania w Wikipedii. |
| Trzymaj model w pamięci | Minuty od ostatniego pytania. `-1` = zawsze w pamięci, najszybsza odpowiedź. Oba modele są ładowane przy starcie integracji. |
