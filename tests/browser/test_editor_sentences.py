"""Commands of Home Assistant in the editor: files of custom_sentences in a form or as YAML, saved by themselves and
reloaded, with what Home Assistant recognizes now; a new file, an intent without a handler, a conflict."""

from __future__ import annotations

import re

from playwright.sync_api import Page, expect
import yaml

from .test_editor_app import answer

ROUTER = "household: Tom\ntopics:\n  weather:\n    description: the weather\n"
LIGHTS = """language: pl
# lights of the living room
intents:
  HassTurnOn:
    data:
      - sentences:
          - "rozbudź {name}"   # the lamp
        requires_context:
          area:
            slot: true
"""


def open_editor(page: Page, **options) -> None:
    page.evaluate(
        "(options) => window.editor.open(options)",
        {
            "file": ROUTER,
            "sentences": [{"language": "pl", "name": "lampy.yaml", "text": LIGHTS}],
            **options,
        },
    )


def server_text(page: Page, name: str = "lampy.yaml") -> str:
    return page.evaluate(
        "(name) => window.editor.server.state.sentences.find((file) => file.name === name)?.text ?? null",
        name,
    )


def pane_text(page: Page) -> str:
    return page.evaluate(
        "() => { const app = window.editor.app; const key = app._selected.join('/');"
        " return app._sentenceEdits[key] ?? app._sentenceFile(app._selected).text; }"
    )


def choose(page: Page, name: str = "lampy.yaml") -> None:
    page.locator(f"[data-node='@sentences/pl/{name}']").click()


def test_the_files_are_in_the_tree_and_open_in_a_form(page: Page) -> None:
    open_editor(page)
    expect(page.locator("[data-group='commands']")).to_contain_text("Komendy Home Assistanta")
    choose(page)
    expect(page.locator("[data-sentences-file='pl/lampy.yaml']")).to_be_visible()
    expect(page.locator("[data-intent='HassTurnOn'] [data-sentence-input]")).to_have_value(
        "rozbudź {name}"
    )
    expect(page.locator("[data-intent='HassTurnOn']")).to_contain_text("requires_context")
    expect(page.locator("[data-intent-unhandled]")).to_have_count(0)
    expect(page.locator("[data-sentences-state]")).to_have_text("Zapisany")


def test_a_sentence_is_added_and_saved_with_a_reload(page: Page) -> None:
    open_editor(page)
    choose(page)
    add = page.locator("[data-intent='HassTurnOn'] [data-add-sentence]")
    add.fill("obudź {name}")
    add.press("Enter")
    expect(page.locator("[data-sentences-state]")).to_have_text("Niezapisane zmiany")
    expect(page.locator("[data-node='@sentences/pl/lampy.yaml']")).to_contain_text("•")
    # the comments of the file and the other keys of the group stay
    text = pane_text(page)
    assert text.startswith("language: pl\n# lights of the living room\n")
    group = yaml.safe_load(text)["intents"]["HassTurnOn"]["data"][0]
    assert group["sentences"] == ["rozbudź {name}", "obudź {name}"]
    assert group["requires_context"] == {"area": {"slot": True}}
    page.locator("[data-sentences-save]").click()
    expect(page.locator("[data-notice='ok']")).to_contain_text("przeładował")
    assert server_text(page) == text
    assert page.evaluate("() => window.editor.server.state.reloads") == 1
    # the router.yaml draft is not touched
    assert page.evaluate("() => window.editor.app._text") == ROUTER


def test_what_home_assistant_recognizes(page: Page) -> None:
    open_editor(page, haKnows=["włącz światło"])
    choose(page)
    page.locator("[data-sentences-sample]").fill("rozbudź {name}\nwłącz światło\nzaśpiewaj")
    page.locator("[data-sentences-run]").click()
    results = page.locator("[data-sentence-result]")
    expect(results).to_have_count(3)
    expect(results.nth(0)).to_contain_text("pl/lampy.yaml")
    expect(results.nth(1)).to_contain_text("wbudowane zdania")
    expect(results.nth(2)).to_have_attribute("data-sentence-result", "none")


def test_an_intent_is_added_answered_renamed_and_removed(page: Page) -> None:
    open_editor(page)
    choose(page)
    page.locator("[data-new-intent]").fill("PlayRadio")
    page.locator("[data-add-intent] button").click()
    expect(page.locator("[data-intent='PlayRadio'] [data-intent-unhandled]")).to_contain_text(
        "intent_script"
    )
    page.locator("[data-intent='PlayRadio'] [data-add-sentence]").fill("puść radio")
    page.locator("[data-intent='PlayRadio'] [data-add-sentence]").press("Enter")
    page.locator("[data-intent='PlayRadio'] [data-response]").fill("Już gra.")
    page.locator("[data-intent='PlayRadio'] [data-response]").press("Enter")
    data = yaml.safe_load(pane_text(page))
    assert data["intents"]["PlayRadio"]["data"] == [{"sentences": ["puść radio"]}]
    assert data["responses"]["intents"]["PlayRadio"]["default"] == "Już gra."
    name = page.locator("[data-intent='PlayRadio'] [data-intent-name]")
    name.fill("HassTurnOff")
    name.press("Enter")
    data = yaml.safe_load(pane_text(page))
    assert "HassTurnOff" in data["intents"] and "HassTurnOff" in data["responses"]["intents"]
    page.locator("[data-intent='HassTurnOff'] [data-remove-intent]").click()
    data = yaml.safe_load(pane_text(page))
    assert list(data["intents"]) == ["HassTurnOn"] and "responses" not in data


def test_a_new_file_is_made_saved_and_deleted(page: Page) -> None:
    open_editor(page, sentences=[])
    page.locator("[data-add-sentences]").click()
    answer(page, value="radio")
    expect(page.locator("[data-node='@sentences/pl/radio.yaml']")).to_have_class(
        re.compile(r"\bsel\b")
    )
    expect(page.locator("[data-sentences-state]")).to_have_text("Nowy, niezapisany")
    page.locator("[data-new-intent]").fill("HassTurnOn")
    page.locator("[data-add-intent] button").click()
    page.locator("[data-sentences-save]").click()
    expect(page.locator("[data-sentences-state]")).to_have_text("Zapisany")
    assert yaml.safe_load(server_text(page, "radio.yaml"))["intents"] == {
        "HassTurnOn": {"data": [{"sentences": []}]}
    }
    page.locator("[data-sentences-delete]").click()
    answer(page)
    expect(page.locator("[data-node='@sentences/pl/radio.yaml']")).to_have_count(0)
    assert server_text(page, "radio.yaml") is None


def test_a_bad_name_or_a_taken_one_is_refused(page: Page) -> None:
    open_editor(page)
    page.locator("[data-add-sentences]").click()
    answer(page, value="../zle")
    expect(page.locator("[data-node^='@sentences/']")).to_have_count(1)
    page.locator("[data-add-sentences]").click()
    answer(page, value="lampy.yaml")
    expect(page.locator("[data-notice='error']")).to_contain_text("już istnieje")


def test_the_yaml_tab_and_a_mistake_in_it(page: Page) -> None:
    open_editor(page)
    choose(page)
    page.locator("[data-sentences-view='yaml']").click()
    area = page.locator("[data-sentences-yaml]")
    expect(area).to_have_value(LIGHTS)
    area.fill(LIGHTS.replace("rozbudź {name}", "rozbudź (to|tamto"))
    page.locator("[data-sentences-save]").click()
    expect(page.locator("[data-sentences-error]")).to_contain_text("end of group")
    area.fill("intents: [a")
    expect(page.locator("[data-sentences-yaml-error]")).to_be_visible()
    expect(page.locator("[data-sentences-save]")).to_be_disabled()
    page.locator("[data-sentences-discard]").click()
    expect(area).to_have_value(LIGHTS)


def test_a_file_changed_elsewhere_is_saved_only_when_asked(page: Page) -> None:
    open_editor(page)
    choose(page)
    page.evaluate("() => { window.editor.server.state.sentences[0].text += '# elsewhere\\n'; }")
    add = page.locator("[data-intent='HassTurnOn'] [data-add-sentence]")
    add.fill("obudź {name}")
    add.press("Enter")
    page.locator("[data-sentences-save]").click()
    expect(page.locator("[data-sentences-error]")).to_contain_text("poza edytorem")
    page.locator("[data-sentences-force]").click()
    expect(page.locator("[data-sentences-state]")).to_have_text("Zapisany")
    assert "obudź {name}" in server_text(page)


def test_helpers_of_sentences(page: Page) -> None:
    result = page.evaluate(
        """async () => {
          const s = await import("/custom_components/assist_router/www/editor/sentences.js");
          return [s.sentencesFileName("radio"), s.sentencesFileName("a b"), s.sentencesFileName("x.yaml"),
                  s.newSentencesFile("pl"), s.readSentences("intents: [a").error !== null];
        }"""
    )
    assert result == ["radio.yaml", None, "x.yaml", "language: pl\nintents: {}\n", True]


def test_a_file_of_sentences_has_only_its_own_tabs(page: Page) -> None:
    open_editor(page)
    page.locator("[data-node='topics/weather']").click()
    page.locator("[data-tab='file']").click()
    choose(page)
    expect(page.locator("[data-tab='file']")).to_be_hidden()
    expect(page.locator("[data-sentences-file='pl/lampy.yaml']")).to_be_visible()


def test_the_demo_server_matches_templates_of_home_assistant(page: Page) -> None:
    """The made-up Home Assistant of the demo and of these tests: a slot takes words, (a|b) one of them, [a] may go."""
    found = page.evaluate("""async () => {
        const m = await import('/tests/js/mock-editor.js');
        return [m.templateSlots('zaświeć {name}', 'Zaświeć salon'),
                m.templateSlots('zapal (lampę|światło) {name}', 'zapal światło w kuchni'),
                m.templateSlots('[proszę] włącz {name}', 'włącz salon'),
                m.templateSlots('rozbudź {name}', 'zgaś salon')];
    }""")
    assert found == [{"name": "salon"}, {"name": "w kuchni"}, {"name": "salon"}, None]


def test_the_name_of_a_new_file_is_asked_in_a_window_of_the_editor(page: Page) -> None:
    open_editor(page, sentences=[])
    page.locator("[data-add-sentences]").click()
    expect(page.locator("[data-ask-title]")).to_have_text("Nowy plik komend")
    expect(page.locator("[data-ask-ok]")).to_have_text("Utwórz")
    field = page.locator("[data-ask-input]")
    # The usual name, focused and selected: typing replaces it
    expect(field).to_have_value("moje_komendy.yaml")
    expect(field).to_be_focused()
    assert page.evaluate(
        """() => {
          const field = window.editor.app.shadowRoot.querySelector('assist-router-ask')
            .shadowRoot.querySelector('[data-ask-input]');
          return [field.selectionStart, field.selectionEnd];
        }"""
    ) == [0, len("moje_komendy.yaml")]
    # An empty name cannot be confirmed
    field.fill("  ")
    expect(page.locator("[data-ask-ok]")).to_be_disabled()
    # Esc: no file
    page.keyboard.press("Escape")
    expect(page.locator("[data-ask]")).to_have_count(0)
    expect(page.locator("[data-node^='@sentences/']")).to_have_count(0)
    # Enter confirms the typed name
    page.locator("[data-add-sentences]").click()
    page.keyboard.type("salon")
    page.keyboard.press("Enter")
    expect(page.locator("[data-ask]")).to_have_count(0)
    expect(page.locator("[data-node='@sentences/pl/salon.yaml']")).to_have_class(
        re.compile(r"\bsel\b")
    )


def test_deleting_a_file_of_commands_asks_with_the_focus_on_cancel(page: Page) -> None:
    open_editor(page)
    choose(page)
    page.locator("[data-sentences-delete]").click()
    expect(page.locator("[data-ask-title]")).to_have_text("Usuwanie pliku komend")
    expect(page.locator("[data-ask-ok]")).to_have_class("danger")
    expect(page.locator("[data-ask-cancel]")).to_be_focused()
    page.keyboard.press("Escape")
    expect(page.locator("[data-ask]")).to_have_count(0)
    assert server_text(page, "lampy.yaml") is not None
    expect(page.locator("[data-node='@sentences/pl/lampy.yaml']")).to_be_visible()
