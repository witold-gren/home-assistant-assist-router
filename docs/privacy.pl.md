# Prywatność i bezpieczeństwo {#privacy}

- **Wszystko działa lokalnie:** HA, Ollama, Whisper i Piper. Do internetu
  trafia tylko hasło z pytań o wiedzę (np. „Mikołaj Kopernik”), wysyłane do API Wikipedii.
- **Do modelu trafiają tylko dane tematu, o który pytano:** encje, atrybuty i
  odpowiedzi usług wskazane w `router.yaml`, przycięte do osoby i dnia. Z
  `only_exposed: true` są to wyłącznie encje udostępnione Assistowi.
- **Pytanie nigdy niczego nie przełącza.** `fetch` wywołuje tylko
  usługi, które wyłącznie zwracają dane. Sterowanie przechodzi wyłącznie przez temat
  `control: true` i intencje HA, które sprawdzają udostępnienie encji. Niepewne
  polecenia, zamki, bramy i urządzenia z `confirm_entities` wymagają
  potwierdzenia.
- Plik CSV zawiera wypowiedzi domowników. Gdy go nie potrzebujesz, wyłącz zapis w opcjach.
