# Assist Router

Asystent głosowy Home Assistant, który rozumie pytania po polsku także wtedy, gdy nie pasują do żadnego zdania. Wszystko działa lokalnie.

!!! note

    **Język:** wszystko, co Assist Router mówi, rozpoznaje albo wysyła do
    modeli, jest w **pakiecie językowym**. Integracja ma wbudowany pakiet
    **polski**. Pakiet jest wybierany przy starcie: język HA, jeśli jest dla niego pakiet,
    inaczej polski; `router.yaml` może wskazać go wprost (`language: pl`). Inne
    języki można dodać jednym plikiem: [Dodanie języka](languages.md).

!!! note

    Konfigurujesz cały głosowy zestaw od zera (satelity, Whisper, Piper, Ollama,
    rozpoznawanie mówcy)? Zacznij od [PRZEWODNIK.md](https://github.com/witold-gren/home-assistant-assist-router/blob/main/PRZEWODNIK.md), który
    prowadzi krok po kroku i odsyła tutaj po szczegóły.

## Co to jest {#what}

Wbudowany asystent Home Assistant rozpoznaje zdania według szablonów: intencje HA, własne
zdania w `custom_sentences` i automatyzacje z wyzwalaczem zdaniowym. Jest szybki i
pewny, ale wystarczy powiedzieć coś inaczej („Na którą Ola idzie jutro do szkoły?” zamiast
„O której Ola zaczyna lekcje?”) i słyszymy „Nie rozumiem”. Dopisywanie kolejnych wariantów
zdań nie ma końca.

**Assist Router** to agent rozmowy, który nakłada się na wbudowanego agenta
HA. Wszystko, co HA rozumie, działa bez zmian. Gdy HA nie rozpozna zdania:

- mały model językowy (np. Gemma 4 E4B w Ollamie) **rozpoznaje tylko temat**
  pytania, np. „lekcje” albo „samochód”. To trwa ok. pół sekundy;
- integracja pobiera **prawdziwe dane z HA** dla tego tematu: stany encji,
  ich atrybuty (np. plan lekcji) i odpowiedzi usług (kalendarze, prognoza), przycięte do
  osoby i dnia z pytania. Nie trzeba pisać do tego żadnych automatyzacji;
- model odpowiedzi **pisze odpowiedź na zadane pytanie** wyłącznie na
  podstawie tych danych: „Ola kończy dziś o 12:40, czyli jest w szkole 5 godzin i 10 minut”;
- pytania o wiedzę ogólną („Kim był Kopernik?”) dostają streszczenie artykułu z
  Wikipedii w 3–4 zdaniach;
- **polecenia**, których HA nie zna dosłownie („zrób jaśniej w salonie”,
  „opuść roletę do połowy”), są rozbierane na intencję HA i wykonywane. Gdy asystent nie
  jest pewien, najpierw pyta („Czy wyłączyć światło w kuchni?”);
- resztą (rozmowa, żarty) zajmuje się wybrany agent zapasowy;
- każde nierozpoznane zdanie trafia do pliku CSV. Widać w nim, co powiedziano, co
  odpowiedział asystent i jaką drogę wybrał router.

## Jak działa {#how}

<div class="flow">
<svg aria-label="Schemat: mowa, Whisper, agent HA, router, dane, sterowanie, Wikipedia, model odpowiedzi, Piper" role="img" viewbox="0 0 900 430">
<defs><marker id="arrow" markerheight="7" markerwidth="7" orient="auto-start-reverse" refx="9" refy="5" viewbox="0 0 10 10"><path d="M0,0 L10,5 L0,10 z"></path></marker></defs>
<rect class="box" height="56" rx="8" width="140" x="10" y="20"></rect>
<text text-anchor="middle" x="80" y="44">Mowa</text>
<text class="small" text-anchor="middle" x="80" y="62">Whisper (STT)</text>
<rect class="box" height="56" rx="8" width="230" x="190" y="20"></rect>
<text text-anchor="middle" x="305" y="44">Agent HA</text>
<text class="small" text-anchor="middle" x="305" y="62">intencje, custom_sentences, automatyzacje</text>
<rect class="box" height="56" rx="8" width="170" x="470" y="20"></rect>
<text text-anchor="middle" x="555" y="44">Rozpoznane</text>
<text class="small" text-anchor="middle" x="555" y="62">odpowiedź bez zmian</text>
<rect class="box" height="56" rx="8" width="150" x="740" y="180"></rect>
<text text-anchor="middle" x="815" y="204">Głośnik</text>
<text class="small" text-anchor="middle" x="815" y="222">Piper (TTS)</text>
<rect class="box hot" height="56" rx="8" width="230" x="190" y="120"></rect>
<text text-anchor="middle" x="305" y="144">Router (mały model)</text>
<text class="small" text-anchor="middle" x="305" y="162">tylko temat: {"temat": "lekcje"}</text>
<rect class="box" height="66" rx="8" width="200" x="10" y="240"></rect>
<text text-anchor="middle" x="110" y="264">Dane tematu</text>
<text class="small" text-anchor="middle" x="110" y="282">encje, atrybuty, usługi</text>
<text class="small" text-anchor="middle" x="110" y="296">przycięte do osoby i dnia</text>
<rect class="box hot" height="66" rx="8" width="175" x="225" y="240"></rect>
<text text-anchor="middle" x="312" y="264">Sterowanie</text>
<text class="small" text-anchor="middle" x="312" y="282">rozbiór -&gt; intencja HA</text>
<text class="small" text-anchor="middle" x="312" y="296">dopytanie, intent.async_handle</text>
<rect class="box" height="66" rx="8" width="140" x="415" y="240"></rect>
<text text-anchor="middle" x="485" y="264">Wikipedia</text>
<text class="small" text-anchor="middle" x="485" y="282">pytania o wiedzę</text>
<rect class="box" height="66" rx="8" width="140" x="570" y="240"></rect>
<text text-anchor="middle" x="640" y="264">Agent</text>
<text class="small" text-anchor="middle" x="640" y="282">zapasowy (rozmowa)</text>
<rect class="box hot" height="56" rx="8" width="545" x="10" y="350"></rect>
<text text-anchor="middle" x="282" y="374">Model odpowiedzi</text>
<text class="small" text-anchor="middle" x="282" y="392">odpowiada na pytanie tylko z danych; streszcza artykuł</text>
<path class="arrow" d="M150,48 L188,48"></path>
<path class="arrow" d="M420,48 L468,48"></path>
<path class="arrow" d="M640,48 C720,48 800,110 815,178"></path>
<path class="arrow" d="M305,76 L305,118"></path>
<text class="small" x="313" y="102">nie rozpoznano</text>
<path class="arrow" d="M240,176 L130,238"></path>
<path class="arrow" d="M305,176 L310,238"></path>
<path class="arrow" d="M370,176 L470,238"></path>
<path class="arrow" d="M420,150 C560,150 630,190 640,238"></path>
<path class="arrow" d="M110,306 L150,348"></path>
<path class="arrow" d="M485,306 L440,348"></path>
<path class="arrow" d="M400,280 C700,300 790,280 805,238"></path>
<path class="arrow" d="M555,378 C700,378 800,300 815,238"></path>
<path class="arrow" d="M710,272 C740,262 770,250 790,238"></path>
</svg>
</div>

### Dlaczego router zwraca tylko temat {#why-the-router-returns-only}

Małe modele mylą się, gdy mają jednocześnie wybrać temat, osobę, dzień i wywołać narzędzie.
Dlatego podział pracy wygląda tak:

- **Model routera** zwraca jedno pole w formacie JSON wymuszonym schematem:
  temat z listy. Zmyślenie wartości spoza listy nie jest możliwe.
- **Kod** wyciąga z pytania osoby (imiona z odmianą: „Oli”, „Olą”), dzień
  („jutro”, „pojutrze”, „w weekend”) i hasło do Wikipedii. Jest to pewne i natychmiastowe.
- **Home Assistant** dostarcza dane, a **model odpowiedzi**
  tylko je czyta, liczy i porównuje.

Dzięki temu odpowiedzi nie są zmyślone, a mały model wystarcza do większości zadań. Ten sam
podział obowiązuje przy sterowaniu: model wskazuje intencję i parametry z list, kod dopasowuje
urządzenie, a wykonuje HA.

### Pytania o wiedzę (Wikipedia) {#knowledge-questions}

1. **Hasło.** Kod wycina początek pytania („kim był”, „co to jest”, „kto jest
   obecnie”, „kto napisał / wynalazł / wygrał”, „gdzie leży”…), więc do wyszukiwarki trafia
   samo hasło: „Kto napisał Pana Tadeusza?” → „Pana Tadeusza”.
2. **Literówki.** Gdy wyszukiwanie nic nie da („…w piłce norznej”), integracja
   bierze podpowiedź pisowni Wikipedii („…w piłce nożnej”) i szuka jeszcze raz.
3. **Pasujący artykuł.** Artykuł musi mieć w tytule słowo z hasła - wyszukiwarka
   zawsze coś znajdzie, także dla bełkotu, a takiego artykułu nie czytamy.
4. **Kilka artykułów.** Model dostaje pierwszy artykuł (do 4000 znaków) i wstępy
   dwóch kolejnych pasujących (po 1000). Przy „Kto jest obecnie mistrzem świata…” pierwszy
   wynik to przyszły turniej, a odpowiedź jest w artykule o ostatnim.
5. **Odpowiedź.** Model odpowiada na pytanie z tych tekstów w 3–4 zdaniach.
