# FAQ

## Edytor i router {#editor-faq}

| Komunikat albo objaw | Przyczyna i co zrobić |
| --- | --- |
| Nie ma „Edytor Assist Routera” w pasku bocznym | Panel pojawia się po restarcie HA po instalacji albo aktualizacji integracji i tylko dla administratorów. Po restarcie odśwież stronę (Ctrl+Shift+R). |
| „Router nie przeczyta tego tekstu: …” | Szkic ma błąd, który wyłączyłby router; okno podaje powód (np. persona bez promptu). Popraw go w formularzu albo w YAML; zapis czeka. |
| `expected ',' or ']', but got '?'` | Tekst ze znakiem `?` albo `:` w liście w nawiasach bez cudzysłowu: `[Czy będzie padać?]`. Napisz `["Czy będzie padać?"]`. Formularz robi to sam. |
| „W międzyczasie router.yaml zmienił się poza edytorem” | Ktoś zmienił plik (inny edytor, File editor, Samba) od początku szkicu. Różnice pokazuje okno zapisu; *Zapisz mimo to* nadpisze tamtą zmianę, a *Odrzuć szkic* wczyta plik od nowa. |
| „Podgląd czeka, aż router przeczyta tekst: …” | Podgląd źródeł liczy się na tekście, który router umie przeczytać. Popraw błąd podany po dwukropku. |
| „Tej zmiany nie wprowadzono: Tu nie da się nic dodać: rodzic nie jest mapą kluczy” | Sekcja, do której formularz dopisuje, jest tekstem albo listą (np. `people: brak`). Popraw ją w zakładce YAML na mapę (`people:` z osobami pod spodem). |
| „Ta usługa może coś zmienić: router nigdy nie wywoła jej z tematu” | W `fetch` działają tylko usługi, które wyłącznie zwracają dane (np. `calendar.get_events`). Wybierz taką z podpowiedzi. |
| „Usługa nic nie zwróciła (albo wystąpił błąd…)” | Usługa odpowiedziała pustą listą albo błędem; szczegóły są w logu HA (`Router fetch … failed`). Sprawdź jej encje i dane. |
| „router nie wypełni {who}” | Prompt w ustawieniach ma słowo w klamrach, którego router nie zna. Dozwolone są `{household}`, `{now}` i `{sentences}`; zwykłą klamrę zapisz podwójnie: `{{`, `}}`. |
| „Błąd: The Assist Router agent is not running” | Tester, nierozpoznane zdania i testy potrzebują działającej integracji. Sprawdź, czy Assist Router jest załadowany (Ustawienia → Urządzenia i usługi). |
| „Router nie ma ustawionego modelu” | W opcjach integracji brakuje adresu Ollamy albo modelu routera. |
| „Brak tematu (model nie odpowiedział albo odpowiedział źle)” | Ollama jest wyłączona, model nie zmieścił się w pamięci albo odpowiedział nie po swojemu. Spróbuj jeszcze raz; szczegóły są w logu HA. |
| „Home Assistant nie ma obsługi intencji …” | Zdanie trafia do intencji, której HA nie umie wykonać. Wybierz znaną intencję (np. `HassTurnOn`) albo dodaj `intent_script` o tej nazwie w `configuration.yaml`. |
| „Unable to find end of group”, „Unable to find end of optional” | W zdaniu brakuje zamknięcia `)` albo `]`. Plik nie zapisze się, dopóki zdanie jest błędne. |
| „router_tests.yaml nie jest zestawem testów: …” | Plik testów ma inny układ. Oczekiwany: `tests:` z listą, każdy element z `sentence` i `topic` albo `intent`. Popraw plik albo usuń go; edytor zrobi nowy. |

## Wypróbowanie i praca nad kodem {#make-faq}

| Komunikat albo objaw | Przyczyna i co zrobić |
| --- | --- |
| „Docker nie działa - uruchom Docker Desktop i spróbuj ponownie” / „Brak Dockera” | `make demo`, `make docs` i `make docs-serve` działają tylko w Dockerze. Zainstaluj i uruchom Docker Desktop, poczekaj, aż działa, powtórz polecenie; `make doctor` pokazuje, czego brakuje. |
| „Brak uv - zainstaluj: …” | Środowisko programisty (`make setup`, `make test`, `make lint`) robi uv, który sam pobiera Pythona 3.14. Zainstaluj uv poleceniem z komunikatu i otwórz nowy terminal. Do wypróbowania edytora uv nie jest potrzebny. |
| `make: *** No rule to make target 'ui'` | `make ui` było starą nazwą demo i zniknęło. Użyj `make demo`. |

## Przy budowaniu tematu {#problems}

| Co widzisz | Przyczyna | Co zrobić |
| --- | --- | --- |
| Liczba **0** przy wzorcu encji | Wzorzec nie pasuje do żadnej encji. | Sprawdź identyfikator encji w Home Assistant; w <b class="ui">Encje, których atrybuty idą do modelu</b> wpisuje się wzorce encji, nie nazwy atrybutów. |
| <b class="ui">Rodzaj tematu</b>: <b class="ui">Bez danych (rozmowa)</b> | Temat nie ma żadnego źródła danych. | Dodaj <b class="ui">Wzorce encji</b> albo usługę w części <b class="ui">Dane</b>. |
| Tester wybiera inny temat | Opis albo przykłady są podobne do innego tematu. | Dopisz słowa do <b class="ui">Na co odpowiada (dla modelu routera)</b> i prawdziwe pytania do <b class="ui">Przykładowe pytania</b>. |
| <b class="ui">Sprawdzenie</b>: „Router nie przeczyta tego tekstu:” | Tekst w zakładce YAML nie jest poprawnym YAML. | Popraw linię z komunikatu albo cofnij zmianę (<kbd>Ctrl</kbd>+<kbd>Z</kbd>). |
| „W międzyczasie router.yaml zmienił się poza edytorem.” | Plik zmieniono w innym miejscu po rozpoczęciu szkicu. | <b class="ui">Zapisz mimo to</b> nadpisze tamte zmiany; okno zapisu pokaże różnice. |
| „Home Assistant nie ma obsługi intencji …” | Intencja nie jest wbudowana ani nie ma `intent_script`. | Wybierz znaną intencję albo dodaj `intent_script`. |
| Przeglądarka ostrzega, że karta zużywa dużo energii lub pamięci | Do wersji 0.1.6 edytor czytał `router.yaml` od nowa przy każdej zmianie stanu w domu. | Zaktualizuj do 0.1.7 lub nowszej i wczytaj kartę od nowa. |
| Nie widać panelu w pasku bocznym | Konto nie jest administratorem albo panel jest ukryty. | Otwórz `/assist-router-editor` albo włącz <b class="ui">Pokazuj edytor w pasku bocznym</b>. |

Opis wszystkich pól i opcji: [Edytor na komputerze](editor.md#editor).
