# Home control {#control}

A topic with `control: true` handles commands that HA did not recognize. hassil
sentences and automations always take priority.

!!! note

    The verbs, Whisper corrections, yes/no replies, alarm words and the JSON field names
    below belong to the language pack. The examples are in English; the Polish words of the bundled pack
    (`languages/pl/`) are given in brackets where the behavior depends on them.

1. **Whisper corrections.** Certain corrections of words speech recognition often
   garbles are applied immediately (Polish: „czystkę” → „wszystkie”, “all”), while uncertain ones
   (e.g. „jaś” → „zgaś”, “turn off”) trigger a confirmation question. The list is
   `WHISPER_FIXES` in the language pack.
2. **Parsing.** The model returns schema-constrained JSON. The *intent* field is
   an HA intent: `HassTurnOn`/`Off`, `HassLightSet`,
   `HassSetPosition`, `HassClimateSetTemperature`,
   `HassSetVolume`/`Relative`, media control,
   `HassMediaSearchAndPlay` (“play …”), vacuum or `HassListAddItem`. The
   *domain*, *area* and *floor* fields are chosen from your HA's lists. On top
   of that come *name* (a fragment of the utterance), *all*, *value* and
   *change* (set / more / less), for lights *color* (e.g. red) and *white*
   (color temperature: warm 2700 K, neutral 4000 K, cool 6500 K), and for music *query*,
   *media class* (track, album, artist, playlist, genre, podcast), *artist* and
   *radio*. The key names the model is asked for come from the pack
   (`CONTROL_KEYS`; Polish: `intencja`, `domena`,
   `obszar`, `pietro`, `nazwa`, `wszystkie`,
   `wartosc`, `zmiana`, `kolor`, `barwa`,
   `szukaj`, `rodzaj`, `wykonawca`, `radio`), because a
   model fills in fields named in its own language more reliably.
3. **Matching in code.**
   - The name fragment is compared with the names and aliases of entities exposed to Assist.
     Word stems are used, so inflection is not a problem.
   - When the fragment is weak, the device whose name words were all said in the command wins.
   - An area that was not in the utterance is ignored. The model can confuse “in the walk-in
     closet” with “Garage” (in Polish „garderobie” and „Garaż” look alike).
   - Relative changes (“brighter”, “higher”, “warmer”) are calculated from the current state: by
     25% or by 1°.
4. **A confirmation question** (“Turn off the closet lighting?”; the conversation
   stays open for 30 s) is asked when:
   - the Whisper correction was uncertain;
   - the command contains no known verb;
   - several devices match (but not twin entities - see below);
   - it concerns a lock, a gate or a garage door;
   - the device is on the `confirm_entities` list (also in a group command, e.g.
     “turn off all switches”).

   With several similarly matching devices (“inner window blind” - small and large) the assistant
   asks, instead of swapping in another device whose words happened to be said in the command (the
   outer window blind). Only a device with more words from the command wins (“the lamp in the
   closet” → Closet Lamp).
   The question comes in two forms. When uncertain (“Do I understand correctly that I should run
   Coffee machine - make coffee?”), a plain “no” means “you misunderstood”: the assistant apologizes,
   asks you to repeat and keeps listening, while “cancel”, “no need” or “stop” end the conversation.
   For sensitive devices (“Open the front door?”) “no” simply means “do nothing”.
   Replies work the same way for every question from the assistant. In the Polish pack:
   **yes** – „tak” (yes), „dokładnie (tak)” (exactly), „o to (mi) chodzi” (that's what I
   mean), „działaj” (go ahead), „zrób” (do it), „wykonaj” (execute), „dawaj” (go on);
   **repeat** – „nie” (no), „o coś innego” (something else), „nie o to chodzi” (that's
   not it), „jeszcze raz” (once more), „(może) powtórzę” (let me repeat) – the assistant apologizes
   and keeps listening; **stop** – „anuluj” (cancel), „koniec” (stop), „nieważne” (never
   mind), „zostaw (to)” (leave it), „nic nie rób” (do nothing), „daj (sobie z tym) spokój” (forget
   it), „olej to” (skip it). For questions about sensitive things (“Open the door?”) a plain “no”
   means “don't do it” and ends the conversation.
   A reply with a verb is judged in the context of the question: to “Turn on…?” a plain “turn on”
   means yes, and “turn off” means no. For locks and blinds the code uses their own verbs (in HA,
   `HassTurnOn` for a lock = lock it). Any other utterance cancels the question.
   **Correcting the question:** “no” followed by a command is a corrected
   question – „nie, wyłącz światło w łazience” (no, turn off the bathroom light) or „nie, pytałem
   czy możesz…” (no, I asked whether you can…). The assistant drops the leading “no” (and lead-ins
   such as „pytałem czy”, „chodziło mi o” – `REPHRASE_LEADS` in the language pack) and
   handles the rest from the start: the HA agent, the router, the models. If that ends with a
   question again, you can correct it again, as many times as needed – corrections do not count as
   requests to repeat. A cancel phrase at the start („nie chcę”, „nie rób”) still cancels. The same
   works after “Sorry, I misunderstood. Please repeat.” The log of unrecognized commands marks such a
   command with „(poprawione: …)” and the original reply.
5. **Several commands in one sentence** – „wyłącz światło w kuchni oraz
   łazience” (turn off the light in the kitchen and the bathroom), „zamknij rolety w salonie i
   włącz ekspres do kawy”, „zgaś wszystkie światła oraz włącz alarm”. The HA agent gets the whole
   sentence first, as always. Only when it does not understand it, and the sentence is a command
   (a known verb) with a conjunction („i”, „oraz”, „potem”, „następnie”, a comma –
   `CONJUNCTIONS` in the language pack), the control model splits it into separate,
   complete commands, repeating a shared verb or object (`split_prompt`). Questions are
   not split („co mają jutro Kasia i Jan” stays one question about two people), nor titles
   („Simon i Garfunkel”). Each command then takes the whole usual path – HA intents, your sentence
   automations (e.g. „włącz alarm”), the router – and the replies are joined. A command that needs a
   question stops there: the assistant says what it has done and asks; the remaining commands wait
   for the answer and run after „tak” or a correction, „anuluj” drops them. The log of unrecognized
   commands has one row for the sentence: „kilka poleceń → …”.
6. **Execution** via `intent.async_handle` (HA):
   - **Twin entities.** A single device is sometimes visible through two integrations
     under the same name and in the same room, e.g. a HomePod from the Apple TV integration and from
     Music Assistant (“Bathroom HomePod” ×2). The HA intent rejects such a name
     (`DUPLICATE_NAME`) and does nothing, and there is no way to specify an
     `entity_id` in it. So the integration does not ask about “several matching devices”;
     instead it calls the service on each of these entities (`media_player.volume_set`,
     `homeassistant.turn_on`, `light.turn_on` …); pause and next track - only on
     the one that is playing. A name given by the model together with the room (“Bathroom HomePod”)
     is compared without the room word.
   - it checks whether the entity is exposed to Assist;
   - it uses the speaker's room as the default (“turn on the light” without a room);
   - the reply lists what was switched: “Turned off: …”.
7. **Actions: scripts and scenes.** The model gets a list of exposed scripts with their
   *descriptions*, and of scenes with a list of what they set (HA has no description field for
   scenes). So a command that does not match any device can still hit an action that does what was
   asked, even with a garbled word (“make me a coffee” → “Coffee machine - make coffee”, “let's air
   the flat” → the airing scene). The script is run directly; its fields that select an Assist
   satellite receive the speaker the command came from.
   - **Why a description and not sentences:** an automation with sentences only
     understands the words typed in, while a description tells the model *what* the script
     does, so it matches any phrasing. The steps (turn on the coffee machine, wait, brew) are in
     the script anyway.
   - **How to write the description:** start with a simple sentence about the effect
     (“Brews coffee: …”, “Closes all outer blinds: …”) - the model sees the first 160 characters.
     Add technical details after that.
   - **What to expose:** only actions meant to be run by voice. Do not expose technical
     scripts (notifications, updates) or the alarm - the model could pick them by mistake. Add
     actions the assistant should always ask about to `confirm_entities`.
   - **Automations are not exposed:** in HA, “turn on the automation” means “enable
     it”, not “run it now”. Move an action you want to trigger by voice into a script.
8. **Speech recognition gibberish.** Whisper sometimes garbles a whole sentence
   (Polish: „Głup nastrój w pisarowie” instead of „Włącz nastrój w salonie”, “Turn on the mood scene
   in the living room”). A topic with `unclear: true` catches sentences whose words do not
   fit together. The model guesses what was said - it knows the names of rooms and actions - and the
   assistant asks: “I'm not sure I heard you right. Did you mean: turn on the mood scene in the living
   room?”. On “yes” the corrected sentence goes through the whole normal path (HA sentences,
   automations, router); on “no” the assistant asks you to repeat, and “cancel” ends the
   conversation. When no guess is possible, it says straight away “I didn't understand. Please
   repeat.” In the topic description it is worth stating explicitly what does *not* belong
   here: questions and commands with one garbled word when the meaning is clear, knowledge questions,
   chit-chat. Nothing is executed without confirmation. The assistant asks you to repeat at most once
   in a row. If it fails to understand a second time (gibberish again, or “no” to its suggestion
   again), it says “Sorry, I don't understand. If you need anything, just ask me again.” and ends the
   conversation - the microphone closes. Every command or question that is understood resets the
   counter; each conversation (speaker) is counted separately.
9. **Safeguards.**
   - **Alarm only via sentences.** A command with alarm words (Polish pack:
     „alarm”, „czuwanie”, „ochrona”, „syrena”, „uzbrój”, „rozbrój”, also garbled, e.g. „halaryn”)
     that was not caught by an automation with sentences does not go to the model - the assistant
     replies with a hint (“I only control the alarm with specific sentences, for example: turn off
     the alarm…”). Testing showed that the model could otherwise pick the “Good morning” scene.
   - **No room - the speaker's room.** For a command without an area and without a
     name (“turn off the light”), HA takes *all* devices of that kind in the home. So the
     integration adds the room of the speaker the command came from; if the speaker is unknown, it
     asks “In which room?”. (In testing, a garbled “turn off the alarm” once turned off 64 lights
     this way.)
   - **Large scope.** More than 8 devices at once without “all”, “whole”, “every” in
     the command - a question first.
   - **Guessed device type.** When the model chose e.g. a light, but the command has
     neither a device name nor a word that points to a light (“turn off the cauliflower in the
     kitchen”) - the question “Do I understand correctly…?”.
   - **A device that does not respond.** When the named device (or everything
     in the named room) is unavailable, nothing runs and the reply says why: “Urządzenie
     Skrzynka pocztowa nie odpowiada (jest niedostępne), więc nic nie zmieniłem.” (“The mailbox
     does not respond (unavailable), so I changed nothing.”). The same for a state question HA
     answers: instead of “Nie, … jest unavailable” - “…does not respond, so I don't know its
     state”. When only some devices do not respond, the command works on the others.
   - **A plain “yes” with no question pending** (“yes, do it”, “don't”) is not a
     command and does not run anything; “make it brighter in the living room” is a command, even
     though it starts with “make”.
   - **An action is always run.** “Turn off the TV and home cinema” may hit the script
     “TV - turn off” - and “turn off” on a script in HA would stop it. The model may also confuse a
     script and a scene - the name is looked up in both.
   - **Script name without the model.** Saying the exact name of a script or scene
     (at least 3 words, e.g. “Lower the inner blinds in the living room”) runs it immediately,
     without parsing by the model.
10. **“Play …”** works differently. On a Music Assistant player:
    `music_assistant.play_media` - MA's own search with the media type (track, album, artist,
    playlist, podcast), the artist (“play Bohemian Rhapsody by Queen”) and radio mode (“play something
    like …”, endless similar music). On other players, for a genre, or when MA reports an error: a
    search (`media_player.search_media`) and playback of the first result. An empty list or
    unavailable players in the room - a reply that there is nothing to play on.
    The code chooses the player: from `music_players` (first available); without an entry, a
    player with search support in that area or with the room name in its name; and with no room in the
    command, the satellite's room. A light without color or color temperature support gets a message
    instead of an error.
11. **Music without a title** (“turn on the music”, “play something in the
    kitchen”, “resume the music”) resumes the queue of the room's player from `music_players`
    (or the satellite's room). With `music_players` set, music plays only on those players - a
    satellite's own speaker named in the command is ignored.
12. **“Turn off the music [in …]”** pauses the players that are playing in that room
    (`HassMediaPause`) instead of turning devices off: a Music Assistant player cannot be
    turned off, and turning off a HomePod (Apple TV integration) or a satellite's speaker does not stop
    the music. “Turn off the TV” still turns it off. The music words are `MUSIC_WORDS` in the
    language pack.

**Scope.** The router controls everything that is exposed to Assist.
Put devices you do not want switched without a question (servers, the fridge) in
`confirm_entities`, and do not expose those you never want controlled by voice.
