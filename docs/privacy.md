# Privacy and security {#privacy}

- **Everything runs locally:** HA, Ollama, Whisper and Piper. The only thing sent to
  the internet is the search term from knowledge questions (e.g. “Nicolaus Copernicus”), sent to the
  Wikipedia API.
- **Only the data of the topic asked about goes to the model:** the entities,
  attributes and service responses listed in `router.yaml`, trimmed to the person and day.
  With `only_exposed: true` these are exclusively entities exposed to Assist.
- **A question never switches anything.** `fetch` only calls services that
  only return data. Control goes exclusively through the `control: true` topic and HA
  intents, which check whether entities are exposed. Uncertain commands, locks, gates and devices in
  `confirm_entities` require confirmation.
- The CSV file contains what household members said. If you do not need it, turn logging off in
  the options.
