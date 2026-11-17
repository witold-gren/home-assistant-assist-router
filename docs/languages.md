# Adding a language {#adding-a-language}

Everything that depends on a language lives in one **language pack**: a Python module in
`custom_components/assist_router/languages/` named after the language code. The integration
ships the Polish pack, `pl.py`. It holds:

- the spoken replies (confirmations, errors, “Did you mean…?”, announcement and speaker messages);
- the words and patterns used to understand commands and questions: day words (mapped to day
  codes), yes / no / cancel replies and correction lead-ins („pytałem czy” – REPHRASE_LEADS), verbs, colors, first-person words, family terms, announcement and
  alarm keywords, Whisper corrections, the beginnings of knowledge questions;
- the LLM prompts (router, answer, summary, control, guessing, example sentences) and the JSON key
  names they ask for (`TOPIC_KEY`, `CONTROL_KEYS`…);
- the sentence about the assistant's character (`PERSONA`) and the female forms of the
  fixed replies (`FEMININE_FORMS`, `gendered()`; a language without grammatical
  gender returns the text unchanged);
- log labels, state names and a few functions that build sentences (they depend on grammar),
  plus `CODE` and the default `WIKIPEDIA_LANGUAGE`.

To add, for example, Czech:

1. Copy `languages/pl.py` to `languages/cs.py`.
2. Translate all phrases, patterns, prompts and replies. Keep the same names of constants and
   functions (and their arguments) - the code reads them through `LANG`. JSON key names can
   be translated too (optional; a model fills in keys in its own language more reliably). Set
   `CODE = "cs"` and `WIKIPEDIA_LANGUAGE = "cs"`.
3. **Day codes stay the same.** The codes used in `days:` and in the
   `when` variable (`today`, `tomorrow`,
   `day_after_tomorrow`, `weekend`, `week`, `monday` …
   `sunday`, a number of days) are keywords and the same in every language. The new pack
   maps the spoken Czech words to them (`WHEN_PATTERNS`) and may add its own names for
   `days:` (`DAY_ALIASES`, like Polish `dzis`, `jutro`);
   the alias of `when` in `COMMAND_VARIABLE_ALIASES` (Polish
   `kiedy`) then gets those names.
4. The pack is used when Home Assistant's language is `cs`, or when
   `router.yaml` has `language: cs`. The conversation agent then also lists
   Czech among its supported languages. An unknown code in `language:` disables the router
   with an error in the log.
5. Choose an Ollama model that understands and writes the language well - the router, the answers
   and command parsing all happen in that language.
6. Write `router.yaml` descriptions, examples and `match` patterns in Czech, and
   test with `tools/model_benchmark.py` using Czech test questions
   ([Testing and choosing models](good-practice.md#testing)).

!!! tip

    Contributions are welcome: send the new pack as a pull request to the
    [GitHub repository](https://github.com/witold-gren/home-assistant-assist-router).
