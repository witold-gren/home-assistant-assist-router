# Sterowanie domem {#control}

Temat z `control: true` obsługuje polecenia, których HA nie rozpoznał. Zdania hassil
i automatyzacje zawsze mają pierwszeństwo.

1. **Poprawki Whispera.** Pewne poprawki są stosowane od razu („czystkę” →
   „wszystkie”), a niepewne (np. „jaś” → „zgaś”) oznaczają dopytanie. Listę zawiera
   `WHISPER_FIXES` w pakiecie językowym (`languages/pl.py`).
2. **Rozbiór.** Model zwraca JSON wymuszony schematem. Pole
   `intencja` to intencja HA: `HassTurnOn`/`Off`,
   `HassLightSet`, `HassSetPosition`,
   `HassClimateSetTemperature`, `HassSetVolume`/`Relative`,
   sterowanie mediami, `HassMediaSearchAndPlay` („puść …”), odkurzacz lub
   `HassListAddItem`. Pola
   `domena`, `obszar` i `pietro` to wybór z list Twojego
   HA. Do tego dochodzą `nazwa` (fragment wypowiedzi), `wszystkie`,
   `wartosc` i `zmiana` (więcej / mniej), a dla światła
   `kolor` (np. czerwony) i `barwa` (ciepła 2700 K, neutralna 4000 K,
   zimna 6500 K), dla muzyki `szukaj` i `rodzaj` (utwór, album,
   wykonawca, playlista, gatunek, podcast).
3. **Dopasowanie w kodzie.**
   - Fragment nazwy jest porównywany z nazwami i aliasami encji udostępnionych Assistowi.
     Pod uwagę idą rdzenie słów, więc odmiana nie przeszkadza.
   - Gdy fragment jest słaby, wygrywa urządzenie, którego wszystkie słowa nazwy padły w
     poleceniu.
   - Obszar, którego nie było w wypowiedzi, jest pomijany. Model potrafi pomylić
     „garderobie” z „Garaż”.
   - Zmiany względne („jaśniej”, „wyżej”, „cieplej”) są liczone z bieżącego stanu: o 25%
     albo o 1°.
4. **Dopytanie** („Czy wyłączyć Oświetlenie garderoby?”, rozmowa zostaje
   otwarta przez 30 s) następuje, gdy:
   - poprawka Whispera była niepewna;
   - w poleceniu nie ma żadnego znanego czasownika;
   - pasuje kilka urządzeń (ale nie encje-bliźniaki - patrz niżej);
   - chodzi o zamek, bramę albo drzwi garażowe;
   - urządzenie jest na liście `confirm_entities` (także w poleceniu
     zbiorczym, np. „wyłącz wszystkie przełączniki”).

   Przy kilku podobnie pasujących urządzeniach („roletą wewnętrzną okno” - mała i duża)
   asystent pyta, zamiast podmieniać je na inne urządzenie, którego słowa akurat padły w
   poleceniu (roleta zewnętrzna okna). Wygrywa tylko urządzenie z większą liczbą słów z
   polecenia („lampę w garderobie” → Garderoba Lampa).
   Pytanie ma dwie formy. Przy niepewności („Czy dobrze rozumiem, że mam uruchomić Ekspres -
   zrób kawę?”) samo „nie” znaczy „źle zrozumiałeś”: asystent przeprasza, prosi o powtórzenie
   i słucha dalej, a „anuluj”, „nie trzeba” albo „koniec” kończą rozmowę. Przy urządzeniach
   wrażliwych („Czy otworzyć drzwi wejściowe?”) „nie” znaczy po prostu „nic nie rób”.
   Odpowiedzi działają tak samo przy każdym pytaniu asystenta: **zgoda** – „tak”, „dokładnie (tak)”, „o to (mi) chodzi”, „działaj”, „zrób”, „wykonaj”, „dawaj”; **powtórzenie** – „nie”, „o coś innego”, „nie o to chodzi”, „jeszcze raz”, „(może) powtórzę” – asystent przeprasza i słucha dalej; **koniec** – „anuluj”, „koniec”, „nieważne”, „zostaw (to)”, „nic nie rób”, „daj (sobie z tym) spokój”, „olej to”. Przy pytaniach o rzeczy wrażliwe („Czy otworzyć drzwi?”) samo „nie” znaczy „nie rób tego” i kończy rozmowę.
   Odpowiedź czasownikiem jest oceniana w kontekście pytania: na „Czy włączyć…?” samo
   „włącz” to tak, a „wyłącz” to nie. Dla zamków i rolet kod używa ich własnych czasowników
   (w HA `HassTurnOn` dla zamka = zarygluj). Inna wypowiedź unieważnia pytanie.
   **Poprawienie pytania:** „nie” i od razu polecenie to poprawione pytanie –
   „nie, wyłącz światło w łazience” albo „nie, pytałem czy możesz…”. Asystent zdejmuje
   początkowe „nie” (i zwroty w rodzaju „pytałem czy”, „chodziło mi o” – `REPHRASE_LEADS`
   w pakiecie językowym) i obsługuje resztę od początku: agent HA, router, modele. Gdy znów
   skończy się pytaniem, można poprawiać dalej, do skutku – poprawki nie liczą się jako prośby o
   powtórzenie. Fraza anulowania na początku („nie chcę”, „nie rób”) nadal kończy rozmowę. Tak samo
   działa to po „Przepraszam, źle zrozumiałem. Powtórz, proszę.” W dzienniku nierozpoznanych
   komend takie polecenie ma dopisek „(poprawione: …)” z oryginalną odpowiedzią.
5. **Kilka poleceń w jednym zdaniu** – „wyłącz światło w kuchni oraz łazience”,
   „zamknij rolety w salonie i włącz ekspres do kawy”, „zgaś wszystkie światła oraz włącz alarm”.
   Agent HA dostaje najpierw całe zdanie, jak zawsze. Dopiero gdy go nie zrozumie, a zdanie jest
   poleceniem (znany czasownik) ze spójnikiem („i”, „oraz”, „potem”, „następnie”, przecinek –
   `CONJUNCTIONS` w pakiecie językowym), model sterowania rozpisuje je na osobne, pełne
   polecenia, powtarzając wspólny czasownik albo rzecz (`split_prompt`). Pytania nie są
   dzielone („co mają jutro Kasia i Jan” to jedno pytanie o dwie osoby), tytuły też nie („Simon i
   Garfunkel”). Każde polecenie idzie potem całą zwykłą drogą – intencje HA, Twoje automatyzacje ze
   zdaniami (np. „włącz alarm”), router – a odpowiedzi są łączone. Polecenie, które wymaga pytania,
   zatrzymuje kolejkę: asystent mówi, co już zrobił, i pyta; pozostałe polecenia czekają na
   odpowiedź i wykonują się po „tak” albo poprawce, „anuluj” je porzuca. W dzienniku nierozpoznanych
   komend zdanie ma jeden wiersz: „kilka poleceń → …”.
6. **Wykonanie** przez `intent.async_handle` (HA):
   - **Encje-bliźniaki.** Jedno urządzenie bywa widoczne w dwóch integracjach
     pod tą samą nazwą i w tym samym pokoju, np. HomePod z integracji Apple TV i z Music
     Assistanta („Łazienka HomePod” ×2). Intencja HA odrzuca taką nazwę
     (`DUPLICATE_NAME`) i nic nie robi, a nie da się w niej wskazać
     `entity_id`. Integracja nie pyta więc o „kilka pasujących urządzeń”, tylko
     wywołuje usługę na każdej z tych encji (`media_player.volume_set`,
     `homeassistant.turn_on`, `light.turn_on` …); pauza i następny
     utwór - tylko na tej, która gra. Nazwa podana przez model razem z pokojem
     („Łazienka HomePod”) jest porównywana bez słowa pokoju.
   - sprawdza, czy encja jest udostępniona Assistowi;
   - jako domyślny bierze pokój głośnika („włącz światło” bez pokoju);
   - w odpowiedzi wymienia, co zostało przełączone: „Wyłączono: …”.
7. **Akcje: skrypty i sceny.** Model dostaje listę udostępnionych skryptów z
   ich *opisami* oraz scen z listą tego, co ustawiają (HA nie ma pola opisu sceny).
   Polecenie, które nie pasuje do żadnego urządzenia, może więc trafić w akcję robiącą to, o
   co proszono, nawet przy przekręconym słowie („zapasz kawę” → „Ekspres - zrób kawę”,
   „przewietrzmy mieszkanie” → scena wietrzenia). Skrypt jest uruchamiany wprost; jego pola z
   wyborem satelity Assist dostają głośnik, z którego padło polecenie.
   - **Dlaczego opis, a nie zdania:** automatyzacja ze zdaniami rozumie
     tylko wpisane słowa, a opis mówi modelowi, *co* skrypt robi, więc pasuje do
     dowolnego sformułowania. Kroki (włącz ekspres, poczekaj, zaparz) i tak są w skrypcie.
   - **Jak pisać opis:** zacznij od prostego zdania o efekcie („Parzy kawę:
     …”, „Zamyka wszystkie rolety zewnętrzne: …”) - model widzi pierwsze 160 znaków.
     Szczegóły techniczne dopisz dalej.
   - **Co udostępniać:** tylko akcje do uruchamiania głosem. Skryptów
     technicznych (powiadomienia, aktualizacje) i alarmu nie udostępniaj - model mógłby je
     wybrać przez pomyłkę. Akcje, przy których asystent ma zawsze pytać, dopisz do
     `confirm_entities`.
   - **Automatyzacji się nie udostępnia:** „włącz automatyzację” w HA znaczy
     „włącz jej działanie”, a nie „uruchom ją teraz”. Czynność, którą chcesz wywoływać
     głosem, przenieś do skryptu.
8. **Bełkot z rozpoznawania mowy.** Whisper czasem przekręca całe zdanie
   („Głup nastrój w pisarowie” zamiast „Włącz nastrój w salonie”). Temat z
   `unclear: true` łapie zdania, w których słowa do siebie nie pasują. Model
   odgaduje, co powiedziano - zna nazwy pomieszczeń i akcji - a asystent pyta: „Nie jestem
   pewien, czy dobrze usłyszałem. Czy chodziło o: włącz nastrój w salonie?”. Na „tak”
   poprawione zdanie przechodzi całą zwykłą drogę (zdania HA, automatyzacje, router); na
   „nie” asystent prosi o powtórzenie, „anuluj” kończy. Gdy nie da się zgadnąć - od razu
   „Nie zrozumiałem. Powtórz, proszę.” W opisie tematu warto napisać wprost, co tu
   *nie* należy: pytania i polecenia z jednym przekręconym słowem, gdy sens jest jasny,
   pytania o wiedzę, rozmowa. Nic nie jest wykonywane bez potwierdzenia. Asystent prosi o powtórzenie najwyżej raz z rzędu. Gdy drugi raz nie zrozumie (znów bełkot albo znów „nie” na jego propozycję), mówi „Przepraszam, nie rozumiem. Jeśli będziesz czegoś potrzebować, poproś mnie jeszcze raz.” i kończy rozmowę - mikrofon się zamyka. Każde zrozumiane polecenie albo pytanie zeruje licznik; liczy się każda rozmowa (głośnik) osobno.
9. **Zabezpieczenia.**
   - **Alarm tylko zdaniami.** Polecenie ze słowami „alarm”, „czuwanie”,
     „ochrona”, „syrena”, „uzbrój”, „rozbrój” (także przekręconymi, np. „halaryn”), którego
     nie złapała automatyzacja ze
     zdaniami, nie idzie do modelu - asystent odpowiada podpowiedzią („Alarmem steruję tylko
     konkretnymi zdaniami, na przykład: wyłącz alarm…”). Test pokazał, że model potrafił
     wtedy wybrać scenę „Dzień dobry”.
   - **Bez pomieszczenia - pokój głośnika.** HA przy poleceniu bez obszaru i
     bez nazwy („wyłącz światło”) bierze *wszystkie* urządzenia tego rodzaju w domu.
     Integracja dopisuje więc pomieszczenie głośnika, z którego padło polecenie; bez znanego
     głośnika pyta „W którym pomieszczeniu?”. (22.10.2026 przekręcone „wyłącz alarm” zgasiło
     w ten sposób 64 światła.)
   - **Duży zasięg.** Więcej niż 8 urządzeń naraz bez „wszystkie”, „cały”,
     „każdy” w poleceniu - najpierw pytanie.
   - **Zgadnięty rodzaj urządzenia.** Gdy model wybrał np. światło, a w
     poleceniu nie ma ani nazwy urządzenia, ani słowa, które na światło wskazuje
     („wyłącz kalafiora w kuchni”) - pytanie „Czy dobrze rozumiem…?”.
   - **Urządzenie nie odpowiada.** Gdy nazwane urządzenie (albo wszystko
     w nazwanym pokoju) jest niedostępne, nic nie jest wykonywane, a odpowiedź mówi dlaczego:
     „Urządzenie Skrzynka pocztowa nie odpowiada (jest niedostępne), więc nic nie zmieniłem.”
     Tak samo przy pytaniu o stan, na które odpowiada HA: zamiast „Nie, … jest unavailable” -
     „…nie odpowiada (jest niedostępne), więc nie wiem, jaki ma teraz stan.” Gdy nie odpowiada
     tylko część urządzeń, polecenie działa na pozostałych.
   - **Samo „tak” bez pytania** („tak, zrób to”, „nie rób”) nie jest poleceniem
     i niczego nie uruchamia; „zrób jaśniej w salonie” jest poleceniem, choć zaczyna się od
     „zrób”.
   - **Akcja zawsze jest uruchamiana.** „Wyłącz telewizor i kino domowe” może
     trafić w skrypt „Telewizor - wyłącz” - a „wyłącz” na skrypcie w HA by go zatrzymał.
     Skrypt i scenę model może też pomylić - nazwy szuka się w obu.
   - **Nazwa skryptu bez modelu.** Wypowiedziana dokładnie nazwa skryptu albo
     sceny (min. 3 słowa, np. „Opuść rolety wewnętrzne w salonie”) uruchamia ją od razu, bez
     rozbioru przez model.
10. **„Puść …”** idzie inaczej. Na odtwarzaczu Music Assistanta:
    `music_assistant.play_media` - wyszukiwanie MA z rodzajem (utwór, album, wykonawca,
    playlista, podcast), wykonawcą („puść Małomiasteczkowy Dawida Podsiadło”) i trybem radia
    („puść coś w stylu …” - podobna muzyka bez końca). Na innych odtwarzaczach, dla gatunku albo
    gdy MA zgłosi błąd: wyszukanie (`media_player.search_media`) i odtworzenie
    pierwszego wyniku. Pusta lista albo niedostępne odtwarzacze pokoju - odpowiedź, że nie ma na
    czym puścić muzyki. Odtwarzacz wybiera kod:
    z `music_players` (pierwszy dostępny), bez wpisu odtwarzacz z wyszukiwaniem w
    tym obszarze albo z nazwą pokoju w nazwie, a bez pokoju w poleceniu pokój satelity.
    Światło bez obsługi koloru lub barwy dostaje komunikat zamiast błędu.
11. **Muzyka bez tytułu** („włącz muzykę”, „puść coś w kuchni”, „wznów muzykę”)
    wznawia kolejkę odtwarzacza pokoju z `music_players` (albo pokoju satelity). Gdy
    `music_players` jest ustawione, muzyka gra tylko na tych odtwarzaczach - głośnik
    satelity wskazany w poleceniu jest pomijany.
12. **„Wyłącz muzykę [w …]”** wstrzymuje odtwarzacze, które grają w tym pokoju
    (`HassMediaPause`), zamiast wyłączać urządzenia: odtwarzacza Music Assistanta nie da
    się wyłączyć, a wyłączenie HomePoda (integracja Apple TV) albo głośnika satelity nie zatrzymuje
    muzyki. „Wyłącz telewizor” nadal wyłącza. Słowa o muzyce to `MUSIC_WORDS` w pakiecie
    językowym.

**Zakres.** Router steruje wszystkim, co jest udostępnione
Assistowi. Urządzenia, których nie chcesz przełączać bez pytania (serwery, lodówka), wpisz do
`confirm_entities`, a tych, których nie chcesz przełączać głosem wcale, nie
udostępniaj.
