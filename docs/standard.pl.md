# Jeden standard {#standard}

Edytor Assist Router jest jedną z kilku aplikacji domu: Edytor Home Dashboard, studio słów budzących, Trener
Assist Routera, Piper Voice Cloner. Wszystkie stosują **wspólny standard** (`gpu-studio.md`). Edytor jest panelem
Home Assistanta, a nie studiem na maszynie z GPU, więc obowiązuje go ta część standardu, która dotyczy paneli HA.
Dzięki temu aplikacje mają:

- te same polecenia;
- ten sam wygląd i zachowanie;
- dokumentację budowaną tak samo;
- te same zasady testów.

Ta strona zbiera wszystko, co w edytorze i jego repozytorium zmieniło się, żeby spełnić standard (listopad 2026).
Szczegóły każdej zmiany są w ostatnim rozdziale, „Lista zmian”.

## W skrócie {#summary}

| Obszar | Przed | Po |
|---|---|---|
| Dokumentacja | statyczne strony HTML (`docs/pl/…html`, `docs/en/…html`) | MkDocs Material, PL i EN z tymi samymi kotwicami; stare adresy prowadzą na nowe miejsca |
| Pomoc w edytorze | **?** w pasku otwiera przewodnik | **?** w pasku otwiera przewodnik, a **?** każdej kolumny i okna otwiera małe okienko z linkiem do rozdziału |
| Adres | zawsze otwiera się początek | wybrany węzeł jest w adresie (`#/topics/weather`) |
| Menu Home Assistanta | widoczne obok edytora | schowane po otwarciu edytora, przycisk w lewym górnym rogu |
| Wolny Home Assistant | edytor mógł czekać bez końca | każde pytanie ma limit czasu i czytelny komunikat |
| Wypróbowanie | `make ui` z Pythonem na Macu | `make demo`, tylko Docker Desktop |
| Polecenia | własne nazwy (`ui`, `.venv-docs`) | wspólne nazwy i grupy `make help` |
| Python programisty | z brew | z uv (`PYTHON_VERSION ?= 3.14`) |
| Testy | bez testów dokumentacji, Dockera i wydajności | 809, w tym testy dokumentacji, przeglądarki, wydajności i obrazu demo |

## Wygląd i zachowanie edytora {#editor}

To samo co w studiach i w Edytorze Home Dashboard:

- **Pasek górny:** ikona edytora przy jego nazwie. **?** otwiera przewodnik po polsku, gdy Home Assistant jest po
  polsku, a w przeciwnym razie po angielsku.
- **Pomoc w okienkach:**
  - drzewo, środkowa i prawa kolumna mają własne **?**, tak samo okna zapisu i historii;
  - **?** otwiera małe okienko z opisem części i linkiem do jej rozdziału;
  - tylko **?** w pasku otwiera od razu cały przewodnik.
- **Adres:** wybrany węzeł jest w adresie, więc link albo przeładowanie otwiera edytor na nim, gdy plik się wczyta.
- **Menu Home Assistanta** chowa się po otwarciu edytora, a przycisk w lewym górnym rogu je pokazuje i chowa.
  - Na każdej innej stronie HA menu wraca.
  - Do chowania służy tryb kiosku HA, który nie jest nigdzie zapisywany, więc ustawienie menu użytkownika zostaje
    bez zmian.
- **Przeglądarka, która nic nie zapamiętuje** (okno prywatne, zablokowane dane stron), nie psuje już edytora.
- **Kolumny** mają przesuwane podziałki, a ich szerokość jest zapamiętywana. Motyw: Auto, Jasny albo Ciemny.

## Wydajność {#performance}

- Ten sam tekst `router.yaml` jest czytany raz, a nie przy każdej zmianie stanu w domu. Wcześniej zajmowało to
  ok. 4% głównego wątku przez cały dzień, teraz poniżej 1%. Ostrzeżenie przeglądarki o dużym zużyciu energii
  zniknęło (opisane w FAQ).
- **Limity czasu:** każde pytanie do Home Assistanta ma limit (60 s, a tester 180 s) i kończy się czytelnym
  komunikatem.
- **Szkic** zapisuje się jeden naraz. Zmiany z tego czasu idą z następnym zapisem.
- **Test wydajności** przechodzi przez duży `router.yaml` (150 tematów) i nie dopuszcza zadania strony dłuższego
  niż 500 ms.

## Dokumentacja {#docs}

- **Przewodnik od nowa w MkDocs Material**, angielski i polski, z tymi samymi kotwicami. Rozdziały:
  - Start, Przewodnik od zera, Instalacja, Edytor;
  - Plik router.yaml, [Przepisy](recipes.md#recipes), Dane, Sterowanie domem;
  - Jak robić to dobrze (wszystkie wartości domyślne z kodu), Modele, Prywatność, Dodanie języka;
  - FAQ, ta strona, Lista zmian.
- **Stare adresy** (`przewodnik-edytora.html`, `editor-guide.html`) prowadzą na nowe miejsca.
- **Zrzuty** z dema w obu językach (`make screenshots`), więc nazwy w przewodniku są nazwami z ekranu.
- **„Wypróbuj na Macu”:** ta sama krótka sekcja w obu README i na stronie [Instalacja](installation.md#try-on-a-mac).
- **Sprawdzanie:**
  - budowa z `--strict`;
  - każdy nagłówek ma kotwicę, a kotwice są takie same w obu językach;
  - każda nazwa przycisku lub pola w tekście jest na ekranie edytora;
  - każde **?** edytora prowadzi do istniejącego rozdziału.
- Przewodnik trafia też na wspólną stronę dokumentacji domu, z zerem martwych linków.

## Polecenia make {#make}

Te same nazwy i grupy we wszystkich aplikacjach (`make help` po polsku albo angielsku):

| Grupa | Polecenia | Czego potrzebuje |
|---|---|---|
| 1. Start | `help`, `demo`, `demo-clean`, `docs`, `docs-serve`, `doctor` | tylko Docker Desktop |
| 2. Home Assistant | `deploy` (kopia integracji do HA; restart HA robisz sam) | udział z konfiguracją HA |
| 3. Rozwój | `setup`, `demo-local`, `test`, `test-browser`, `test-docker`, `test-all`, `lint`, `format`, `docs-build`, `screenshots`, `clean` | uv (sam pobiera Pythona `PYTHON_VERSION`) |

- **`make demo`** buduje mały obraz ze stroną demo edytora i uruchamia go na porcie 8767. Port 8766 ma demo studia
  słów budzących, więc oba mogą działać naraz. Ctrl+C usuwa kontener, `make demo-clean` usuwa obrazy, a
  `make demo-local` podaje tę samą stronę z Pythona.
- **`make docs`, `docs-build`, `docs-serve`** działają w Dockerze. Podgląd na żywo jest na porcie 9767.
  `.venv-docs` zniknęło. Po budowie `site/` dostaje prawa do odczytu dla serwera strony dokumentacji.
- **`make doctor`** sprawdza Dockera, Chrome, uv i udział Home Assistanta. Niczego nie instaluje.
- **Testy:**
  - `make test` nigdy nie buduje obrazów, a `make test-docker` buduje;
  - `make test-all` = lint, test, test-browser i test-docker;
  - `make lint` sprawdza też format, a `make format` poprawia to, co umie ruff.
- **Zmienione nazwy:** `make ui` zniknęło, zamiast niego jest `make demo`.
- **`scripts/deploy.sh`** odczytuje wersję przez sed, więc wdrożenie nie potrzebuje Pythona.

## Integracja i trener {#trainer}

- Doszła komenda `assist_router/training/export`. Działa tylko dla administratora i tylko odczytuje. Zwraca:
  - `router.yaml`;
  - dziennik nierozpoznanych zdań;
  - pliki testu;
  - automatyzacje z wyzwalaczem rozmowy, także z `packages/`;
  - pliki `custom_sentences`.
- Dzięki niej Trener Assist Routera potrzebuje tylko adresu Home Assistanta i tokenu, bez udziału z plikami.
  Komenda jest od wersji 0.1.8.

## Testy {#tests}

- **Razem 809 testów:** 807 w `make test` i `make test-browser` oraz 2 w `make test-docker`.
- **Testy nie łączą się z niczym poza 127.0.0.1** (`tests/network_guard.py`, z własnymi testami).
- **Testy przeglądarki** (Playwright, Chrome) sprawdzają:
  - adres z węzłem, kolumny, okienka pomocy i rozdziały przewodnika;
  - pola i formularze, menu Home Assistanta;
  - wydajność: 500 ms na zadanie strony przy 150 tematach.
- **Testy Makefile:** grupy i ich kolejność, oba opisy każdego celu, cele Start bez `setup`, brak aliasów.
- **Test „Wypróbuj na Macu”:** sekcja w obu README i obu językach dokumentacji, z portem i poleceniami zgodnymi z
  `Makefile`.
- **Test z Dockerem** buduje obraz demo, wczytuje każdy plik strony i sprawdza, że po zatrzymaniu nie zostaje
  żaden kontener.

## Co jeszcze zostało {#left}

Nic: wszystko z tej strony weszło do wersji 0.1.8 (17 listopada 2026).
