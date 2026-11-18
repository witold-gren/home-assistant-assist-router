# Response speed {#speed}

A few seconds pass from the moment you stop speaking to the first word of the answer. This page
shows where that time goes, what Assist Router already does to shorten it, and what you can set
yourself. All numbers were measured in one home: Jetson AGX Orin 64 GB, Ollama with Gemma 4 26B
as both router and answer model, Whisper `large-v3`, Piper, Home Assistant Voice satellites.

## Where the time goes {#stages}

The question "What will the weather be tomorrow?" (a topic with a daily and an hourly forecast),
before the changes on this page:

| Stage | Time | What it depends on |
|---|---|---|
| Detecting the end of speech | about 0.7 s of silence | the satellite's "Finished speaking detection" setting |
| Speech to text (Whisper) | 1.8–2.5 s | model, `beam_size`, length of the recording |
| Built-in HA agent and fetching data | 0.1 s | hardly anything |
| Choosing the topic (router) | 1.2–3.2 s | length of the router prompt and whether Ollama has it cached |
| Reading the answer prompt | 2.2–3.8 s | how much data goes to the answer model |
| Writing the answer | about 1.2 s | length of the answer (streamed, it overlaps with speech) |

The language model costs the most, and within it not writing but **reading the prompt**: Gemma 4
26B on the Orin reads about 750–1000 tokens per second. The router prompt has a few thousand
tokens (topic descriptions and examples), the answer prompt as many as the data from Home
Assistant.

Where to check it yourself:

- Settings → Voice assistants → ⋮ → **Debug**: the times of the stages of each run.
- The Ollama log (`docker logs ollama`): the time of each request; first the topic, then the
  answer.
- An Ollama answer with `"stream": false` gives `prompt_eval_count` and `prompt_eval_duration` -
  how many tokens it read and in what time.

## What Assist Router does itself {#built-in}

- **Streaming answers.** The answer model's answer, the Wikipedia summary and the fallback
  agent's answer go to text to speech while the model is still writing them
  ([Guide: pipelines](guide.md#pipelines)). A long answer is heard 1–2 s sooner.
- **Data as a table.** A list of items with plain fields (a forecast, events, lessons) goes to
  the model as a table: the field names once in the header, then one line per item. A 24-hour
  hourly forecast: 1855 → 1439 tokens, reading 0.3–0.5 s shorter, the same answer.
- **The same context.** When the router and the answer model are the same model, both requests
  use the same `num_ctx` (8192) - Ollama does not reload the model between them.

## Ollama settings {#ollama}

On the Ollama server (environment variables of the container):

| Variable | Value | Why |
|---|---|---|
| `OLLAMA_NUM_PARALLEL` | `2` | Two slots: the router prompt and the answer prompt do not push each other out of the cache. Choosing the topic took 1.2–3.2 s, after the change a steady 0.9–1.0 s. It costs a second cache (for Gemma 4 26B at 8192 tokens - about 1 GB). |
| `OLLAMA_FLASH_ATTENTION` | `1` | faster reading of long prompts |
| `OLLAMA_KV_CACHE_TYPE` | `q8_0` | a smaller cache, no visible loss of quality |
| `OLLAMA_KEEP_ALIVE` | long, e.g. `72h` | the model stays in memory between questions |

Everybody asking the same model must use **the same `num_ctx`** - the router, the fallback agent
in the Ollama integration, other apps. Another context reloads the model (about 25 s for 26B),
and that question and the next one wait. The same goes for your own tests with `curl`: pass
`"options": {"num_ctx": 8192}` and `"keep_alive": -1`.

## Less data for the answer model {#data}

Every 1000 tokens of data is about a second of waiting. In `router.yaml`:

- `limit:` on long lists - an hourly forecast for 12 hours instead of 24 is usually enough;
- `drop:` - fields nobody asks about (e.g. `pressure`, `dew_point`, `uv_index`);
- the day of the question ("tomorrow", "at the weekend") already trims lists with dates
  ([Data](data.md)), so do not add separate sources for every day.

## Speech to text {#speech}

- **Finished speaking detection** on the satellite: "Aggressive" ends the recording after a
  shorter silence (about 0.4 s sooner). With a longer pause in the middle of a sentence the
  satellite may cut it - try it on one satellite before changing all of them.
- **Whisper**: a comparison on 40 recordings from the home (the same GPU, the same prompt):

| Variant | Average | Longest | Other text than `large-v3`, beam 5 |
|---|---|---|---|
| `large-v3`, `beam_size` 5 | 1.11 s | 3.3 s | — |
| `large-v3`, `beam_size` 1 | 1.48 s | 17.3 s | 14 of 40, made-up sentences among them |
| `distil-whisper-large-v3-pl`, beam 5 | 0.97 s | 3.1 s | 25 of 40, cuts sentences |
| `distil-whisper-large-v3-pl`, beam 1 | 1.04 s | 3.7 s | 25 of 40, cuts sentences |

  A smaller `beam_size` is not faster (on noise the model falls into repeating itself), and the
  distilled Polish model is hardly faster and loses the ends of commands. `large-v3` with
  `beam_size` 5 stays. The model itself recognizes in about 1.1 s, while the speech stage of the
  pipeline takes 1.8–2.5 s - the rest is around it (the Speaker ID proxy, the prompt with entity
  names, transfer), which is where to look further.

## Choosing the topic {#classification}

The router prompt is the topic descriptions and all `examples` from `router.yaml` - with 29
topics and 123 examples about 3200 tokens. From the cache (the second Ollama slot) it is read
in 0.2–0.4 s, without it in about 3 s. What shortens the prompt works for longer:

- fewer but better examples - 3–5 per topic, the ones that really tell the topics apart;
- a smaller, fine-tuned router model from the
  [Assist Router trainer](https://github.com/witold-gren/home-assistant-assist-router-trainer):
  a short prompt and reading several times faster.

## Checklist {#checklist}

1. Streaming works: `stream_response: true` in the pipeline's Debug.
2. `OLLAMA_NUM_PARALLEL=2`, every client of the model with the same `num_ctx`.
3. Long lists in `router.yaml` have `limit:` and `drop:`.
4. "Aggressive" finished speaking detection on one satellite.
5. Whisper unchanged, unless another variant recognizes just as well for you, but faster
   (compare on your own recordings).
