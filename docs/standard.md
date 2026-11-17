# One standard {#standard}

The Assist Router editor is one of several apps of the house: the Home Dashboard editor, the wake word studio, the
Assist Router trainer and Piper Voice Cloner. They all follow **one shared standard** (`gpu-studio.md`). The editor
is a Home Assistant panel, not a studio on the GPU machine, so the part of the standard for HA panels applies to it.
This gives the apps:

- the same commands;
- the same look and behaviour;
- documentation built the same way;
- the same rules for tests.

This page lists everything that changed in the editor and its repository to meet the standard (November 2026).
The details of each change are in the last chapter, "Changelog".

## In short {#summary}

| Area | Before | After |
|---|---|---|
| Documentation | static HTML pages (`docs/pl/…html`, `docs/en/…html`) | MkDocs Material, PL and EN with the same anchors; the old addresses lead to the new places |
| Help in the editor | the top bar's **?** opens the guide | the top bar's **?** opens the guide; the **?** of each column and window opens a small window with a link to its chapter |
| Address | always opens at the start | the chosen node is in the address (`#/topics/weather`) |
| Home Assistant menu | shown next to the editor | hidden when the editor opens, a button at the top left |
| A slow Home Assistant | the editor could wait for ever | every question has a time limit and a clear message |
| Trying it | `make ui` with Python on the Mac | `make demo`, only Docker Desktop |
| Commands | its own names (`ui`, `.venv-docs`) | the shared names and groups of `make help` |
| Developer's Python | from brew | from uv (`PYTHON_VERSION ?= 3.14`) |
| Tests | no tests of the docs, Docker or speed | 809, including tests of the docs, the browser, speed and the demo image |

## How the editor looks and behaves {#editor}

The same as the studios and the Home Dashboard editor:

- **The top bar:** the editor's icon next to its name. **?** opens the guide in Polish when Home Assistant is in
  Polish, otherwise in English.
- **Help in small windows:**
  - the tree, the middle and the right column each have their own **?**, and so do the save and history windows;
  - **?** opens a small window saying what the part does, with a link to its chapter;
  - only the top bar's **?** opens the whole guide at once.
- **Address:** the chosen node is in the address, so a link or a reload opens the editor on it once the file has
  loaded.
- **The Home Assistant menu** is hidden when the editor opens, and the button at the top left shows and hides it.
  - It comes back on any other page of HA.
  - Hiding uses HA's kiosk mode, which is never saved, so the user's own place of the menu stays as it was.
- **A browser that keeps nothing** (a private window, blocked site data) no longer breaks the editor.
- **Columns** have movable dividers, and their widths are remembered. Theme: Auto, Light or Dark.

## Speed {#performance}

- The same text of `router.yaml` is read once, not on every change of a state in the home. Before, that took about
  4% of the main thread all day; now it is under 1%. The browser's warning about high energy use is gone (described
  in the FAQ).
- **Time limits:** every question to Home Assistant has one (60 s, the tester 180 s) and ends in a clear message.
- **The draft** is saved one save at a time. Changes made meanwhile go with the next save.
- **A speed test** goes through a big `router.yaml` (150 topics) and allows no task of the page longer than
  500 ms.

## Documentation {#docs}

- **The guide, rewritten in MkDocs Material**, in English and Polish with the same anchors. Chapters:
  - Start, Guide from scratch, Installation, The editor;
  - The router.yaml file, [Recipes](recipes.md#recipes), Data, Home control;
  - Doing it well (every default from the code), Models, Privacy, Adding a language;
  - FAQ, this page, Changelog.
- **The old addresses** (`przewodnik-edytora.html`, `editor-guide.html`) lead to the new places.
- **Pictures** from the demo in both languages (`make screenshots`), so the names in the guide are the names on the
  screen.
- **"Try it on a Mac":** the same short section in both READMEs and on the
  [Installation](installation.md#try-on-a-mac) page.
- **Checks:**
  - the build runs with `--strict`;
  - every heading has an anchor, and the anchors are the same in both languages;
  - every button or field name in the text is on the editor's screen;
  - every **?** of the editor leads to a chapter that is there.
- The guide is also on the shared documentation site of the house, with zero dead links.

## Make commands {#make}

The same names and groups in every app (`make help` in Polish or English):

| Group | Commands | Needs |
|---|---|---|
| 1. Start | `help`, `demo`, `demo-clean`, `docs`, `docs-serve`, `doctor` | only Docker Desktop |
| 2. Home Assistant | `deploy` (copies the integration to HA; you restart HA) | the share with HA's configuration |
| 3. Development | `setup`, `demo-local`, `test`, `test-browser`, `test-docker`, `test-all`, `lint`, `format`, `docs-build`, `screenshots`, `clean` | uv (it brings the Python of `PYTHON_VERSION` itself) |

- **`make demo`** builds a small image with the editor's demo page and runs it on port 8767. Port 8766 is the demo of
  the wake word studio, so both can run at once. Ctrl+C removes the container, `make demo-clean` the images, and
  `make demo-local` serves the same page from Python.
- **`make docs`, `docs-build` and `docs-serve` run in Docker.** The live preview is on port 9767. `.venv-docs` is
  gone. After the build, `site/` is made readable for the web server of the documentation site.
- **`make doctor`** checks Docker, Chrome, uv and the Home Assistant share. It installs nothing.
- **Tests:**
  - `make test` never builds images; `make test-docker` does;
  - `make test-all` = lint, test, test-browser and test-docker;
  - `make lint` also checks the format, and `make format` fixes what ruff can.
- **Renamed:** `make ui` is gone; use `make demo`.
- **`scripts/deploy.sh`** reads the version with sed, so deploying needs no Python.

## The integration and the trainer {#trainer}

- The command `assist_router/training/export` was added: administrators only, read-only. It returns:
  - `router.yaml`;
  - the log of unrecognized sentences;
  - the test files;
  - the automations with a conversation trigger, also those from `packages/`;
  - the `custom_sentences` files.
- With it the Assist Router trainer needs only the address of Home Assistant and a token, no file share. The
  command is there since version 0.1.8.

## Tests {#tests}

- **809 tests in all:** 807 in `make test` and `make test-browser`, and 2 in `make test-docker`.
- **Tests connect to nothing but 127.0.0.1** (`tests/network_guard.py`, with its own tests).
- **Browser tests** (Playwright, Chrome) check:
  - the address with the node, the columns, the help windows and the guide's chapters;
  - fields and forms, and the Home Assistant menu;
  - speed: 500 ms per task of the page with 150 topics.
- **Makefile tests:** the groups and their order, both descriptions of every target, Start targets without
  `setup`, no aliases.
- **The "Try it on a Mac" test:** the section in both READMEs and both languages of the docs, with the port and
  commands matching the `Makefile`.
- **The Docker test** builds the demo image, loads every file of the page and checks that no container is left
  after stopping.

## What is left {#left}

Nothing: everything on this page went into version 0.1.8 (17 November 2026).
