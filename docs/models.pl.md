# Porównanie modeli językowych

Które modele w Ollamie najlepiej sprawdzają się w Assist Routerze po polsku: trafność i czas w każdej roli. Test z 26.10.2026 (runda 3) na NVIDIA Jetson AGX Orin 64 GB.

!!! note

    Zestawienie jest tylko po polsku, bo test prowadzono wyłącznie na polskich
    pytaniach i polskich danych. W innym języku wyniki mogą wyglądać inaczej.

## Co było testowane {#tested}

Każdy z 16 modeli przeszedł ten sam zestaw 669 przypadków, w pięciu rolach, które model pełni
w Assist Routerze. Przypadki powstały z prawdziwej konfiguracji domu (28 tematów, obszary,
urządzenia, skrypty i sceny) i z pytań, których Home Assistant sam nie zrozumiał:

| Część testu | Co sprawdza | Liczba przypadków |
| --- | --- | --- |
| Router (temat) | czy model wybiera właściwy temat z `router.yaml` dla swobodnego pytania, także z błędami rozpoznania mowy i bełkotem; przy pytaniach pasujących do dwóch tematów każdy z nich jest dobry | 379 |
| Sterowanie (rozbiór) | czy z polecenia powstaje właściwy zamiar HA, obszar, urządzenie, wartość i decyzja „czy dopytać”: światła, kolor i barwa, rolety, klimat, muzyka (Music Assistant, wykonawca, radio), głośność, odkurzacz, listy, skrypty i sceny | 155 |
| Odpowiedzi: dane wpisane | odpowiedź z gotowych danych: liczenie godzin i kwot, „za ile minut”, „pojutrze”, brak danych, prośba o sterowanie | 34 |
| Odpowiedzi: dane z HA | odpowiedź z migawki danych domu, zbudowanych dokładnie tak jak w integracji (encje, `details`, `fetch`, osoba i dzień z pytania, ten sam prompt i limit tokenów): plan lekcji, sprawdziany, kalendarze, obowiązki, leki, samochód, czujniki, okna, niedostępne urządzenia, listy, odkurzacz, podsumowanie dnia | 86 |
| Streszczenia z Wikipedii | streszczenie artykułu promptem integracji: 2–5 zdań, z kluczowym faktem | 15 |

Odpowiedź jest trafiona, gdy zawiera oczekiwane fakty (np. godzinę albo kwotę) i nie zawiera
zakazanych (np. wydarzenia z innego dnia). Czas to średni czas jednej odpowiedzi; modele były
ładowane i zwalniane po kolei, więc nie konkurowały o pamięć. Migawka danych zamraża stan domu,
więc każdy model dostał te same fakty.

Kolory: ≥ 95%≥ 85%poniżej 85%
Kolejność: średnia trafność ze wszystkich pięciu części.

## Wyniki {#results}

| Model rozmiar pliku | Router (temat) | Sterowanie (rozbiór) | Odpowiedzi: dane wpisane | Odpowiedzi: dane z HA | Streszczenia z Wikipedii |
| --- | --- | --- | --- | --- | --- |
| gemma4:26b 18.7 GB | **376/379** 0.85 s | **152/155** 3.27 s | **33/34** 0.95 s | **83/86** 2.28 s | **14/15** 4.75 s |
| gemma4:12b 8.0 GB | **369/379** 1.01 s | **148/155** 4.53 s | **34/34** 1.20 s | **77/86** 3.93 s | **15/15** 7.71 s |
| gemma4:e4b 6.6 GB | **359/379** 0.54 s | **139/155** 2.43 s | **34/34** 0.68 s | **72/86** 1.71 s | **14/15** 3.64 s |
| qwen3.5:9b 6.6 GB | **357/379** 1.72 s | **130/155** 8.93 s | **29/34** 2.04 s | **71/86** 4.58 s | **14/15** 9.19 s |
| qwen3.5:4b 3.3 GB | **348/379** 1.33 s | **135/155** 5.92 s | **26/34** 1.60 s | **68/86** 3.04 s | **14/15** 7.10 s |
| gemma4:e2b 4.6 GB | **336/379** 0.49 s | **128/155** 2.47 s | **28/34** 0.51 s | **67/86** 1.11 s | **14/15** 2.13 s |
| ministral-3:8b 6.0 GB | **338/379** 0.72 s | **136/155** 6.04 s | **31/34** 1.11 s | **75/86** 3.42 s | **8/15** 11.39 s |
| bielik-minitron-7B-v3.0-instruct:Q4_K_M 4.5 GB | **280/379** 1.02 s | **128/155** 5.88 s | **29/34** 2.19 s | **70/86** 6.56 s | **9/15** 14.65 s |
| bielik-11b-v3.0-instruct:Q6_K 9.2 GB | **293/379** 1.66 s | **134/155** 10.35 s | **31/34** 4.08 s | **63/86** 15.12 s | **7/15** 31.47 s |
| Llama-PLLuM-8B-instruct-2512-GGUF:Q4_K_M 4.9 GB | **312/379** 0.86 s | **124/155** 5.02 s | **26/34** 0.77 s | **64/86** 2.18 s | **9/15** 5.51 s |
| PLLuM-12B-chat-2512-GGUF:Q4_K_M 7.5 GB | **332/379** 1.10 s | **134/155** 8.02 s | **25/34** 1.12 s | **69/86** 4.90 s | **6/15** 13.47 s |
| bielik-11b-v3.0-instruct:Q4_K_M 6.7 GB | **296/379** 1.43 s | **131/155** 8.83 s | **31/34** 3.32 s | **63/86** 11.47 s | **6/15** 25.08 s |
| ministral-3:3b 3.0 GB | **324/379** 0.61 s | **120/155** 3.64 s | **23/34** 0.62 s | **70/86** 1.77 s | **6/15** 5.78 s |
| qwen3.5:2b 2.7 GB | **314/379** 0.74 s | **114/155** 4.37 s | **18/34** 0.99 s | **59/86** 2.80 s | **8/15** 13.73 s |
| PLLuM-4B-instruct-2512-GGUF:Q4_K_M 2.5 GB | **299/379** 0.77 s | **115/155** 4.40 s | **14/34** 0.82 s | **56/86** 2.06 s | **1/15** 3.23 s |
| qwen3.5:0.8b 1.3 GB | **259/379** 1.06 s | **40/155** 6.99 s | **14/34** 1.16 s | **42/86** 2.28 s | **9/15** 6.61 s |
| Gemma 4 E4B douczona router, QLoRA 8.0 GB | **100/101** (przed ponownym douczeniem) 0.62 s | – | – | – | – |
| Gemma 4 E2B douczona router, LoRA 5.0 GB | **88/96** (przed ponownym douczeniem) 0.41 s | – | – | – | – |

Rozmiar to rozmiar pliku modelu; na Jetsonie pamięć jest wspólna dla CPU i GPU.
Douczone Gemmy mają wyniki z wcześniejszego, mniejszego zestawu (96 i 101 pytań): zostaną
douczone na nowo na obecnych 28 tematach i sprawdzone tym samym zestawem. Modele PLLuM
działały z szablonem czatu, który Hugging Face dobiera przy `ollama pull`
(w stylu Granite) – z natywnym szablonem mogą wypaść lepiej.

## Wnioski {#conclusions}

- **Najlepszy we wszystkich rolach: Gemma 4 26B** (MoE, liczy ok. 4B parametrów
  naraz): router 376/379 w 0,85 s, sterowanie 152/155, dane z HA 83/86 w 2,3 s – najlepszy
  wynik w routerze, sterowaniu i na danych z HA, a przy tym szybszy od gęstych Gemmy 4 12B i
  Qwena 3.5 9B. Jeden model w obu rolach trzyma w pamięci tylko jeden model; tak działa to u
  autora.
- **Gemma 4 12B** jest tuż za nią (369/379, 15/15 streszczeń, 34/34 na danych
  wpisanych), ale 1,2–1,7× wolniejsza i słabsza na danych z HA (77/86).
- **Wersja oszczędna: Gemma 4 E4B** (6,6 GB) – najszybszy dobry router
  (359/379 w 0,54 s), 34/34 na danych wpisanych, ale słabsza w sterowaniu (139/155) i na
  danych z HA (72/86). Gemma 4 E2B jest jeszcze szybsza (0,49 s), ale wyraźnie mniej dokładna.
- **Qwen 3.5 9B i 4B** dobrze rozpoznają tematy (357 i 348/379) i streszczają
  (14/15), ale wolniej sterują (6–9 s) i słabiej liczą na danych.
- **Ministral 3 8B** dobrze odpowiada z danych z HA (75/86), ale streszczenia
  są za długie (8/15), a odpowiedzi często zawierają markdown.
- **Polskie modele** (Bielik, PLLuM) wypadły słabiej, niż sugerowały wcześniejsze,
  mniejsze rundy: Bielik rozpoznaje 74–78% tematów, streszcza za długo i jest wolny (Bielik 11B Q6:
  15 s na odpowiedź z danych z HA); PLLuM 12B ma 332/379 w routerze, ale tylko 6/15 streszczeń.
  Dobrze radzą sobie z danymi wpisanymi (Bielik 31/34).
- **Małe modele** (Qwen 3.5 0,8B–2B, PLLuM 4B, Ministral 3 3B) nie nadają się do
  sterowania ani do odpowiedzi; Qwen 3.5 0,8B rozbiera poprawnie tylko 40/155 poleceń.

## Typowe błędy modeli {#errors}

- **Arytmetyka:** sumy kwot, liczba godzin („5 i pół godziny”), „za ile minut”
  do najbliższego spotkania – najczęstsze potknięcia nawet dużych modeli.
- **Dni tygodnia:** „pojutrze”, „w przyszłym tygodniu” – wydarzenia z
  niewłaściwego dnia albo pominięte.
- **Pomylone tematy:** najczęściej polecenie sterowania odczytane jako pytanie
  o muzykę, alarm albo światła (np. „włącz serial”), bełkot uznany za zwykłe pytanie, a pytanie o
  urządzenia za pytanie o czujniki.
- **Sterowanie:** najwięcej błędów to wybór urządzenia (np. „ledy w korytarzu”,
  „kolorowe lampy”, roleta wewnętrzna zamiast zewnętrznej) i zamiaru (kalibracja i ustawienia
  rolet, sceny w rodzaju „zrób klimat”, „włącz telewizor”).
- **Zmyślanie:** dopisywanie wydarzeń spoza danych albo „nie wiem”, choć dane
  zawierały odpowiedź.
- **Streszczenia:** 6–11 zdań zamiast najwyżej 5 (Bielik, Ministral, PLLuM)
  albo brak kluczowego faktu.
- **Forma:** markdown (`**`) i znaczniki końca tekstu w odpowiedzi,
  która ma być przeczytana na głos – głównie Ministral 3 (ponad 50 odpowiedzi) i PLLuM 12B.

## Douczanie routera {#fine-tuning}

- **Pierwszy przebieg:** Gemma 4 E2B douczona (LoRA) na 15 tys. zdań
  wygenerowanych z szablonów hassil, 80 minut na RTX 4090. Na zdaniach z szablonów 298/300, ale
  na swobodnych pytaniach 88/96 – model nauczył się szablonów zamiast uogólniać.
- **Drugi przebieg:** Gemma 4 E4B (QLoRA), 14 tys. przykładów, w tym 7,7 tys.
  parafraz napisanych przez Gemmę 4 26B. Na 101 pytaniach spoza nauki 100/101 w 0,62 s
  (bazowa Gemma 4 E4B: 97/101 w 0,55 s); walidacja 290/300 wobec 272/300.
- **Wniosek:** parafrazy napisane większym modelem są kluczowe. Jak douczyć
  router na własnych tematach: [Douczanie routera (opcjonalnie)](good-practice.md#fine-tuning).

## Jak powtórzyć test u siebie {#repeat}

Narzędzia są w katalogu `tools/` repozytorium: `snapshot_data.py`
(migawka danych), `model_benchmark.py` (test modeli) i `model_report.py`
(taka tabela jako HTML i CSV). Opis: [Test i wybór modeli](good-practice.md#testing).
