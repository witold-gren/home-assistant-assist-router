# Assist Router

[English](README.md) · **Polski**

<img src="custom_components/assist_router/brand/icon.png" width="96" align="right" alt="">

Agent konwersacji dla Home Assistanta (domena `assist_router`, encja
`conversation.assist_router`), który sprawia, że Assist rozumie zwykłe pytania i polecenia
po polsku, a nie tylko wyuczone zdania.

> **Język:** wszystko, co zależy od języka (słowa kluczowe, wbudowane zwroty, prompty,
> odpowiedzi mówione), jest w pakiecie językowym. Wbudowany jest pakiet **polski**; kolejne
> można dodać - zob. [Dodanie języka](#dodanie-języka).

**Nowy zestaw głosowy od zera** (satelity, Whisper, Piper, Ollama, rozpoznawanie mówcy)?
Zacznij od **[PRZEWODNIK.md](PRZEWODNIK.md)**.

## Co robi

Każde zdanie trafia najpierw do wbudowanego agenta HA. Intencje, `custom_sentences`
i automatyzacje ze zdaniami działają bez zmian. Gdy HA nie rozpozna zdania:

| Co | Jak |
|---|---|
| **Router pytań** | Model w Ollamie wybiera temat z `/config/assist/router.yaml` (kalendarz, lekcje, pogoda, czujniki…). Kod zbiera dane tematu z encji, atrybutów i usług, przycięte do osoby i dnia z pytania. Model odpowiedzi odpowiada krótko z tych danych. |
| **Sterowanie** | „Zgaś lampę w garderobie”, „zrób cieplej”, „puść jazz w salonie” zamienia na intencje HA. Przy niepewności albo wrażliwych urządzeniach pyta „Czy dobrze rozumiem…?”. |
| **Wiedza** | Pytania ogólne („Kim był Kopernik?”) odpowiada streszczeniem z Wikipedii. |
| **Kto pyta** | Z integracją [Assist Speaker ID](https://github.com/witold-gren/home-assistant-assist-speaker-id) pytanie w 1. osobie („Co mam jutro?”) dotyczy mówcy. Działają też określenia rodzinne („mój brat”), pokój mówcy („w moim pokoju”) i pytanie „Kto to mówi?”. |
| **Ogłoszenia (intercom)** | „Ogłoszenie, dzieci proszę przyjść na obiad” odtwarza **Twoje nagranie** na pozostałych głośnikach zamiast syntezy (Assist Speaker ID). |
| **Bełkot** | Źle rozpoznane zdanie kończy się pytaniem „Czy chodziło o …?”. Po dwóch nieporozumieniach z rzędu Assist przeprasza i kończy rozmowę. |
| **Agent zapasowy** | Gdy router nie ma danych, pytanie przejmuje wybrany agent LLM. |
| **Dziennik** | Nierozpoznane zdania trafiają do `/config/assist/unrecognized_commands.csv`, z podglądem w opcjach, sensorem i akcją czyszczenia. |
| **Przykładowe komendy** | Akcja `assist_router.generate_examples` układa zdania z Twoich encji i sprawdza je prawdziwym routerem. Wynik ląduje w `assist/router_examples.yaml`. |
| **Edycja router.yaml w HA** | Opcje integracji → „Plik routera”, ze sprawdzeniem przed zapisem i kopią `.bak`. |

**Sprawdzone w praktyce:** u autora wszystko działa na co dzień na **NVIDIA Jetson AGX Orin 64 GB**
(Ollama z Gemma 4 26B, faster-whisper, Assist Speaker ID) i działa bardzo dobrze: router odpowiada
w ok. 0,7 s, odpowiedź z danych (router i model odpowiedzi) w ok. 2 s.

## Instalacja

1. Skopiuj `custom_components/assist_router` do `/config/custom_components/` (albo HACS:
   repozytorium niestandardowe, typ „Integracja”) i zrestartuj HA.
2. **Ustawienia → Urządzenia i usługi → Dodaj integrację → Assist Router.**
3. Skopiuj [router.example.pl.yaml](router.example.pl.yaml) do `/config/assist/router.yaml`
   i dopasuj encje oraz osoby ([router.example.yaml](router.example.yaml) to ten sam plik
   z angielskimi nazwami).
4. W opcjach integracji podaj adres Ollamy i wybierz modele.
5. **Ustawienia → Asystenci głosowi:** w każdym potoku ustaw agenta rozmowy
   **„Assist Router”** i **wyłącz „Preferuj obsługę poleceń lokalnie”**. Inaczej
   wbudowane intencje HA wyprzedzą ogłoszenia, „Kto to mówi?” i nagrywanie wzorca głosu.

## Usługi w docker compose (bez dodatków HA)

Assist Router to integracja HA. Usługi, z których korzysta (Whisper, Piper, Ollama
i opcjonalnie [Assist Speaker ID](https://github.com/witold-gren/home-assistant-assist-speaker-id)),
nie muszą być dodatkami. Mogą działać jako kontenery na innym komputerze, np. z kartą
graficzną. Tak działa to u autora, na Jetsonie AGX Orin 64 GB. Przykładowy
`docker-compose.yaml`:

```yaml
services:
  whisper:                      # mowa na tekst (Wyoming, port 10300)
    image: rhasspy/wyoming-whisper
    command: --model medium-int8 --language pl
    ports: ["10300:10300"]
    volumes: ["./whisper:/data"]
    restart: unless-stopped

  piper:                        # tekst na mowę (Wyoming, port 10200)
    image: rhasspy/wyoming-piper
    command: --voice pl_PL-gosia-medium
    ports: ["10200:10200"]
    volumes: ["./piper:/data"]
    restart: unless-stopped

  ollama:                       # modele językowe routera i odpowiedzi (port 11434)
    image: ollama/ollama
    ports: ["11434:11434"]
    volumes: ["./ollama:/root/.ollama"]
    environment:
      OLLAMA_FLASH_ATTENTION: "1"
      OLLAMA_MAX_LOADED_MODELS: "2"
    restart: unless-stopped
    deploy:                     # karta NVIDIA (wymaga NVIDIA Container Toolkit)
      resources:
        reservations:
          devices: [{ driver: nvidia, count: all, capabilities: [gpu] }]

  speaker-id:                   # opcjonalnie: kto mówi (przed Whisperem, porty 10350/10351)
    build: ./home-assistant-assist-speaker-id/speaker_id   # git clone obok tego pliku
    depends_on: [whisper]
    ports: ["10350:10350", "10351:10351"]
    volumes: ["./speaker-id:/data"]
    environment:
      SPEAKER_ID_UPSTREAM: tcp://whisper:10300
      SPEAKER_ID_API_TOKEN: ${SPEAKER_ID_API_TOKEN}       # z pliku .env obok
    restart: unless-stopped
```

1. Uruchom: `docker compose up -d`, potem pobierz model:
   `docker compose exec ollama ollama pull gemma4:26b` (albo mniejszy, np. `gemma4:e4b`).
2. W HA: Ustawienia → Urządzenia i usługi → Dodaj → **Wyoming Protocol** dla Pipera
   (`192.168.1.10`, port 10200) i Whispera (port 10300). Z Assist Speaker ID zamiast
   Whispera dodaj integrację **Assist Speaker ID** (porty 10350 i 10351, token z `.env`).
3. W opcjach Assist Routera ustaw adres Ollamy: `http://192.168.1.10:11434`.
4. W asystencie głosowym: zamiana mowy na tekst Whisper (albo „Mowa na tekst z mówcą”),
   agent **Assist Router**, tekst na mowę Piper.

**Uwagi:**
- **Whisper:** obraz `rhasspy/wyoming-whisper` liczy na procesorze. Na karcie graficznej
  (np. `large-v3`) użyj obrazu z CUDA, np. `lscr.io/linuxserver/faster-whisper:gpu`
  (zmienne `WHISPER_MODEL`, `WHISPER_LANG`).
- **Jetson:** zamiast sekcji `deploy` daj `runtime: nvidia`. Oficjalny obraz
  `ollama/ollama` sam wykrywa GPU Orina. Whisper i Piper na GPU Jetsona wymagają obrazów
  zbudowanych pod JetPack (np. z projektu `dusty-nv/jetson-containers`).
- **Bez GPU:** Ollama działa też na procesorze, ale wtedy wybierz mały model (np.
  `gemma4:e4b`) i licz się z dłuższymi odpowiedziami.
- **Adres usług:** `192.168.1.10` to przykładowy adres komputera z kontenerami. Porty
  wystawiaj tylko w sieci domowej.

### Sama Ollama w docker compose

Gdy Whisper i Piper działają już jako dodatki HA, wystarczy sama Ollama na komputerze
z kartą graficzną:

```yaml
services:
  ollama:
    image: ollama/ollama
    container_name: ollama
    command: serve
    ports: ["11434:11434"]
    volumes: ["./ollama:/root/.ollama"]   # pobrane modele (kilkanaście GB)
    environment:
      OLLAMA_HOST: 0.0.0.0
      OLLAMA_KEEP_ALIVE: "72h"            # model zostaje w pamięci, bez ładowania przy pytaniu
      OLLAMA_NUM_PARALLEL: "1"
      OLLAMA_MAX_LOADED_MODELS: "2"       # router i model odpowiedzi naraz, jeśli są różne
      OLLAMA_FLASH_ATTENTION: "1"
      OLLAMA_KV_CACHE_TYPE: "q8_0"        # mniejsza pamięć kontekstu
    restart: unless-stopped
    deploy:                               # karta NVIDIA (NVIDIA Container Toolkit)
      resources:
        reservations:
          devices: [{ driver: nvidia, count: all, capabilities: [gpu] }]
```

- **Jetson (JetPack 6):** usuń `deploy` i dodaj `runtime: nvidia`. Oficjalny obraz
  `ollama/ollama` ma wersję arm64 i sam wykrywa GPU Orina; tak działa to u autora na AGX Orin
  64 GB.
- **Bez GPU:** usuń `deploy` i wybierz mały model, np. `gemma4:e4b`.
- **Karta AMD:** obraz `ollama/ollama:rocm` z urządzeniami `/dev/kfd` i `/dev/dri`.

Uruchomienie i modele:

```sh
docker compose up -d ollama
docker compose exec ollama ollama pull gemma4:26b   # router i odpowiedzi (18 GB, karta 24 GB)
docker compose exec ollama ollama pull gemma4:e4b   # mniejszy (ok. 8 GB): router albo wersja oszczędna
curl http://192.168.1.10:11434/api/tags              # z komputera HA: lista modeli
```

W opcjach Assist Routera podaj adres `http://192.168.1.10:11434` i wybierz modele z listy.
Opcja „Trzymaj model w pamięci” (`-1` = zawsze) sprawia, że tylko pierwsze pytanie po
starcie Ollamy czeka na załadowanie modelu.

## Dokumentacja

- [PRZEWODNIK.md](PRZEWODNIK.md): cały zestaw krok po kroku, dla początkujących;
- **pełna dokumentacja ze schematami:** jak działa router, pola `router.yaml`, źródła danych,
  sterowanie, mówca, dziennik, testy modeli, prywatność.
  Po polsku: [docs/pl](https://witold-gren.github.io/home-assistant-assist-router/pl/),
  in English: [docs/en](https://witold-gren.github.io/home-assistant-assist-router/en/)
  (pliki źródłowe: [docs/](docs/));
- [porównanie modeli LLM](https://witold-gren.github.io/home-assistant-assist-router/pl/modele.html):
  Gemma 4, Bielik, PLLuM, Qwen 3.5, Ministral na Jetsonie AGX Orin 64 GB, trafność i czas
  w każdej roli, wnioski i douczanie;
- [router.example.pl.yaml](router.example.pl.yaml): przykładowa konfiguracja z komentarzami
  (fikcyjny dom: Tomek, Ania, Ola, Kuba); wersja angielska:
  [router.example.yaml](router.example.yaml);
- [CHANGELOG.md](CHANGELOG.md): zmiany w kolejnych wersjach.

## Rozwój

```bash
python3.13 -m venv .venv && .venv/bin/pip install -r requirements_test.txt
.venv/bin/pytest -q && .venv/bin/ruff check . && .venv/bin/ruff format --check .
scripts/deploy.sh            # kopiuje integrację do udziału z konfiguracją HA (custom_components)
```

Wersja jest w `manifest.json`, zmiany opisuje `CHANGELOG.md`, a wydanie to tag `vX.Y.Z`.
Narzędzia do testu modeli i zdań są w `tools/` (`model_benchmark.py`, `check_sentences.py`,
`compare_sources.py`, `snapshot_data.py`; opis: dokumentacja, rozdział 12).

## Dodanie języka

Integracja ma wbudowany pakiet polski. Wszystko, co zależy od języka, jest w
`custom_components/assist_router/languages/<kod>.py`: odpowiedzi mówione, słowa i wzorce
(dni, odpowiedzi tak/nie, czasowniki, kolory…), prompty dla modeli i klucze JSON, o które
proszą, etykiety dziennika i funkcje składające zdania. Żeby dodać np. czeski:

1. Skopiuj `languages/pl.py` do `languages/cs.py`.
2. Przetłumacz wszystkie zwroty, wzorce, prompty i odpowiedzi, opcjonalnie też nazwy kluczy
   JSON. Zostaw te same nazwy stałych i funkcji - kod czyta je przez `LANG`.
3. Pakiet działa, gdy język HA to `cs` albo gdy `router.yaml` ma `language: cs` (nieznany
   kod wyłącza router z błędem w logu).
4. Kody dni są angielskie i takie same w każdym języku (`today`, `tomorrow`,
   `day_after_tomorrow`, `weekend`, `week`, `monday` … `sunday`, liczba dni) - przyjmuje je
   `days:` i zawiera je zmienna `when`. Pakiet mapuje na nie wypowiadane słowa
   (`WHEN_PATTERNS`) i może dodać własne nazwy dla `days:` (`DAY_ALIASES`, np. polskie `dzis`,
   `jutro`, `tydzien`).
5. Wybierz model w Ollamie, który rozumie ten język, napisz w nim opisy i przykłady
   w `router.yaml` i sprawdź całość narzędziem `tools/model_benchmark.py`.

Szczegóły: [dokumentacja, rozdział 15](https://witold-gren.github.io/home-assistant-assist-router/pl/#jezyk).
Nowe pakiety są mile widziane jako pull request.
