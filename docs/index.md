# Assist Router

A Home Assistant voice assistant that understands ordinary questions and commands, even when they do not match any sentence template. Everything runs locally.

!!! note

    **Language:** everything Assist Router says, recognizes or sends to the
    models lives in a **language pack**. The integration ships the **Polish** pack,
    so today it understands and answers Polish. Example sentences below are written in English for
    readability; where a behavior depends on the words of the pack (inflection, yes/no replies, keywords),
    the Polish words of the bundled pack are shown with a translation. The rest - topics in router.yaml, data from entities, control, speaker
    recognition - is language-neutral, and a new pack is a single file: see
    [Adding a language](languages.md). The configuration examples use
    English names; the same example in Polish is `router.example.pl.yaml`.

!!! note

    Setting up the whole voice stack from scratch (satellites, Whisper, Piper, Ollama,
    speaker recognition)? Start with [the step-by-step guide (GUIDE.md)](https://github.com/witold-gren/home-assistant-assist-router/blob/main/GUIDE.md), which
    walks you through it step by step and refers back here for the details.

## What it is {#what}

The built-in Home Assistant assistant recognizes sentences using templates: HA intents, your own
sentences in `custom_sentences` and automations with a sentence trigger. It is fast and
reliable, but as soon as you phrase something differently (“What time does Olivia go to school
tomorrow?” instead of “When do Olivia's lessons start?”), you hear “Sorry, I couldn't understand
that”. Adding more and more
sentence variants never ends.

**Assist Router** is a conversation agent layered on top of the built-in HA agent.
Everything HA understands keeps working unchanged. When HA does not recognize a sentence:

- a small language model (e.g. Gemma 4 E4B in Ollama) **only recognizes the topic**
  of the question, e.g. “school” or “car”. This takes about half a second;
- the integration fetches **real data from HA** for that topic: entity states,
  their attributes (e.g. a school timetable) and service responses (calendars, forecast), trimmed
  to the person and day mentioned in the question. You do not need to write any automations for this;
- the answer model **writes an answer to the question asked** based solely on
  that data: “Olivia finishes at 12:40 today, so she is at school for 5 hours and 10 minutes”;
- general knowledge questions (“Who was Copernicus?”) get a 3–4 sentence
  summary of a Wikipedia article;
- **commands** that HA does not know literally (“make it brighter in the living
  room”, “lower the blind halfway”) are parsed into an HA intent and executed. When the assistant is
  not sure, it asks first (“Should I turn off the kitchen light?”);
- everything else (chit-chat, jokes) is handled by the fallback agent of your choice;
- every unrecognized sentence is written to a CSV file. It shows what was said, what the
  assistant answered and which path the router took.

## How it works {#how}

<div class="flow">
<svg aria-label="Diagram: speech, Whisper, HA agent, router, data, control, Wikipedia, answer model, Piper" role="img" viewbox="0 0 900 430">
<defs><marker id="arrow" markerheight="7" markerwidth="7" orient="auto-start-reverse" refx="9" refy="5" viewbox="0 0 10 10"><path d="M0,0 L10,5 L0,10 z"></path></marker></defs>
<rect class="box" height="56" rx="8" width="140" x="10" y="20"></rect>
<text text-anchor="middle" x="80" y="44">Speech</text>
<text class="small" text-anchor="middle" x="80" y="62">Whisper (STT)</text>
<rect class="box" height="56" rx="8" width="230" x="190" y="20"></rect>
<text text-anchor="middle" x="305" y="44">HA agent</text>
<text class="small" text-anchor="middle" x="305" y="62">intents, custom_sentences, automations</text>
<rect class="box" height="56" rx="8" width="170" x="470" y="20"></rect>
<text text-anchor="middle" x="555" y="44">Recognized</text>
<text class="small" text-anchor="middle" x="555" y="62">answer unchanged</text>
<rect class="box" height="56" rx="8" width="150" x="740" y="180"></rect>
<text text-anchor="middle" x="815" y="204">Speaker</text>
<text class="small" text-anchor="middle" x="815" y="222">Piper (TTS)</text>
<rect class="box hot" height="56" rx="8" width="230" x="190" y="120"></rect>
<text text-anchor="middle" x="305" y="144">Router (small model)</text>
<text class="small" text-anchor="middle" x="305" y="162">topic only: {"topic": "school"}</text>
<rect class="box" height="66" rx="8" width="200" x="10" y="240"></rect>
<text text-anchor="middle" x="110" y="264">Topic data</text>
<text class="small" text-anchor="middle" x="110" y="282">entities, attributes, services</text>
<text class="small" text-anchor="middle" x="110" y="296">trimmed to person and day</text>
<rect class="box hot" height="66" rx="8" width="175" x="225" y="240"></rect>
<text text-anchor="middle" x="312" y="264">Control</text>
<text class="small" text-anchor="middle" x="312" y="282">parse -&gt; HA intent</text>
<text class="small" text-anchor="middle" x="312" y="296">confirm, intent.async_handle</text>
<rect class="box" height="66" rx="8" width="140" x="415" y="240"></rect>
<text text-anchor="middle" x="485" y="264">Wikipedia</text>
<text class="small" text-anchor="middle" x="485" y="282">knowledge questions</text>
<rect class="box" height="66" rx="8" width="140" x="570" y="240"></rect>
<text text-anchor="middle" x="640" y="264">Fallback</text>
<text class="small" text-anchor="middle" x="640" y="282">agent (chit-chat)</text>
<rect class="box hot" height="56" rx="8" width="545" x="10" y="350"></rect>
<text text-anchor="middle" x="282" y="374">Answer model</text>
<text class="small" text-anchor="middle" x="282" y="392">answers the question from the data only; summarizes the article</text>
<path class="arrow" d="M150,48 L188,48"></path>
<path class="arrow" d="M420,48 L468,48"></path>
<path class="arrow" d="M640,48 C720,48 800,110 815,178"></path>
<path class="arrow" d="M305,76 L305,118"></path>
<text class="small" x="313" y="102">not recognized</text>
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

### Why the router returns only the topic {#why-the-router-returns-only}

Small models make mistakes when they have to pick the topic, the person and the day and call a
tool all at once. That is why the work is split like this:

- The **router model** returns a single field in schema-constrained JSON: a topic
  from the list. It cannot make up a value that is not on the list.
- The **code** extracts from the question the people (names including inflected
  forms - in Polish „Oli”, „Olą” for „Ola”), the day (“tomorrow”, “the day after tomorrow”, “at the
  weekend”; the words come from the language pack) and the Wikipedia search term. This is reliable and
  instant.
- **Home Assistant** supplies the data, and the **answer model**
  only reads, calculates and compares it.

As a result, answers are not made up, and a small model is enough for most tasks. The same split
applies to home control: the model picks the intent and parameters from lists, the code matches the
device, and HA executes the action.

### Knowledge questions (Wikipedia) {#knowledge-questions}

1. **Search term.** The code strips the beginning of the question (“who was”, “what
   is”, “who is currently”, “who wrote / invented / won”, “where is”…; the phrases come from the
   language pack), so only the term itself is sent to the search: “Who wrote Pan Tadeusz?” → “Pan
   Tadeusz”.
2. **Typos.** When the search returns nothing (a misspelled word), the integration
   takes Wikipedia's spelling suggestion and searches again.
3. **Matching article.** The article title must contain a word from the search term -
   the search engine always finds something, even for gibberish, and we do not read such an article.
4. **Several articles.** The model gets the first article (up to 4000 characters) and
   the introductions of the next two matching ones (1000 each). For “Who is the current world
   champion…” the first result is the upcoming tournament,
   while the answer is in the article about the most recent one.
5. **Answer.** The model answers the question from these texts in 3–4 sentences.
