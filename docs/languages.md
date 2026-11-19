# Adding a language {#adding-a-language}

Everything Assist Router says, recognizes or sends to the language model in one language lives in a
**language pack**: a folder in `custom_components/assist_router/languages/` named after the language
code. The integration ships Polish, `pl/`. You do not need to know Python to translate most of it -
three of the four files are plain YAML, and the tests tell you exactly what is still wrong.

## What is in a pack {#pack}

| File | What it holds | What you do |
|---|---|---|
| `texts.yaml` | everything the assistant says aloud (confirmations, errors, “Did you mean…?”), log lines, the prompts sent to the model, the JSON key words the prompts ask for (`TOPIC_KEY`, `SENTENCES_KEY` …) | translate the values; keep every `{field}` |
| `words.yaml` | words used to understand what was said: yes / no / cancel, command verbs, colours, shades of white, days, family words, state names read aloud, Whisper's usual mistakes | translate the words; Home Assistant names stay |
| `patterns.yaml` | regular expressions (alarm words, “all”, the start of a knowledge question, day words …), each with `matches` and `not_matches` examples | translate the examples first, then fix the pattern until it finds them |
| `grammar.py` | the few functions that build sentences (cases, plural forms, gender, the date read aloud) and the values derived from the data | translate the text inside the functions and adapt the grammar |

A comment above every entry says what it is and when it is used. The Polish pack is the reference: a
new pack has exactly the same names.

### The rules the tests check {#rules}

- **Names stay** (`CONFIRM_QUESTION`, `YES_WORDS` …) - the code reads them.
- **`{fields}` stay** - `MORE_ITEMS: "… and {count} more"` must keep `{count}`.
- **Home Assistant names stay**: intents (`HassTurnOn`), domains (`light`, `cover`), device classes,
  states (`on`, `off`), colour values (`red`, `white`), media classes (`track`), day codes (`today`,
  `monday`, `weekend`). In a dictionary the comment says which side you translate: in `COLORS` the
  word is translated and the CSS name stays; in `DOMAINS` the key stays and the description is
  translated.
- **Tags stay**: `!tuple`, `!set`, `!frozenset`, `!translate` only keep the type the code expects.
- **JSON key words agree with the prompts**: if `SENTENCES_KEY` becomes `vety`, the prompts that show
  `{"zdania": [...]}` must show `{"vety": [...]}`; `CHANGE_SET` / `CHANGE_MORE` / `CHANGE_LESS` are
  the words the command parser answers with, and `control_prompt` takes them from the pack.
- **Every pattern finds its `matches` and none of its `not_matches`.**

Word stems are fine where the language inflects (`„świat”` covers *światło, światła, światłem*); in a
language with little inflection whole words are better.

## Step by step (Czech as the example) {#steps}

1. **Start from a draft.** Either copy `languages/pl/` to `languages/cs/`, or let the trainer translate
   it: `router-trainer language new cs` writes a checked machine translation of this pack (and of the
   trainer's) with a `REVIEW.md` of what needs a speaker - see the trainer's guide, *A new language*.
2. **`texts.yaml`**: translate. Set `CODE: cs` and `WIKIPEDIA_LANGUAGE: cs`.
3. **`words.yaml`**: translate the word lists. Home Assistant's own sentences for your language are a
   good source of the right verbs and colour words: the
   [home-assistant/intents](https://github.com/home-assistant/intents) repository, folder
   `sentences/cs/`.
4. **`patterns.yaml`**: translate the `matches` / `not_matches` examples, then the pattern. Run the
   check after each one.
5. **`grammar.py`**: translate the sentences inside the functions and adapt the grammar - plural
   forms (`done_speech`), the date (`format_now`, `MONTHS_GENITIVE`), the female forms of the replies
   (`gendered`; a language without grammatical gender returns the text unchanged).
6. **Check** - one line per problem, nothing when the pack is ready:

    ```bash
    .venv/bin/python tools/check_language.py custom_components/assist_router/languages/cs
    make test     # the same checks run for every pack, with the rest of the tests
    ```

7. **Use it**: the pack is chosen when Home Assistant's language is `cs`, or by `language: cs` in
   `router.yaml`. Write `router.yaml` descriptions, examples and `match` patterns in Czech, choose an
   Ollama model that writes Czech well, and test with `tools/model_benchmark.py` on Czech questions
   ([Testing and choosing models](good-practice.md#testing)).

Day codes are keywords and the same in every language: the pack maps the spoken words to them
(`WHEN_PATTERNS`, in order - the first that matches wins) and may add its own names for `days:` in
`router.yaml` (`DAY_ALIASES`).

!!! tip

    Contributions are welcome: send the new folder as a pull request to the
    [GitHub repository](https://github.com/witold-gren/home-assistant-assist-router). The check output
    of `tools/check_language.py` in the pull request helps the review.
