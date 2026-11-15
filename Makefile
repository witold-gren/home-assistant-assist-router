# home-assistant-assist-router - Assist with a question router on a local LLM (Ollama).
#
#   make help    the steps in order (Polish or English, from $LANG; HELP_LANG=en|pl)
#
# Targets that need the Python environment create it first, so any target can be the first one.

PYTHON ?= python3.13
HA_CONFIG ?= /Volumes/config
UI_PORT ?= 8766

VENV := .venv
HELP_LANG ?= $(if $(filter pl%,$(LANG)),pl,en)

.DEFAULT_GOAL := help
.PHONY: help setup doctor ui test test-browser test-all lint deploy docs clean screenshots

##@ Start | Start

help: ## This list | Ta lista
	@awk -v lang=$(HELP_LANG) 'BEGIN { FS = ":.*## " } \
	  /^##@ / { split(substr($$0, 5), t, " \\| "); printf "\n\033[1m%s\033[0m\n", (lang == "pl" && t[2] != "") ? t[2] : t[1]; next } \
	  /^[a-zA-Z0-9_-]+:.*## / { split($$2, d, " \\| "); printf "  \033[36m%-14s\033[0m %s\n", $$1, (lang == "pl" && d[2] != "") ? d[2] : d[1] }' \
	  $(MAKEFILE_LIST)
	@echo
	@if [ "$(HELP_LANG)" = "pl" ]; then \
	  echo "Środowisko: $(VENV) $$(test -x $(VENV)/bin/pytest && echo '- gotowe' || echo '- powstanie przy pierwszym poleceniu')"; \
	else \
	  echo "Environment: $(VENV) $$(test -x $(VENV)/bin/pytest && echo '- ready' || echo '- created by the first command')"; \
	fi

##@ 1. Setup | 1. Instalacja

$(VENV)/bin/pytest: requirements_test.txt
	@echo "==> Python environment in $(VENV) ($(PYTHON))"
	@command -v $(PYTHON) >/dev/null || { echo "$(PYTHON) not found - macOS: brew install python@3.13"; exit 1; }
	@test -d $(VENV) || $(PYTHON) -m venv $(VENV)
	@$(VENV)/bin/pip install -q --upgrade pip
	@$(VENV)/bin/pip install -q -r requirements_test.txt
	@touch $@

setup: $(VENV)/bin/pytest ## Create the test environment (.venv) | Utwórz środowisko testów (.venv)

doctor: setup ## Check Chrome and the config share | Sprawdź Chrome i udział z konfiguracją
	@if [ -d "/Applications/Google Chrome.app" ] || command -v google-chrome >/dev/null; then echo "ok       Google Chrome"; \
	  else echo "MISSING  Google Chrome - browser tests are skipped"; fi
	@if [ -d "$(HA_CONFIG)/custom_components" ]; then echo "ok       $(HA_CONFIG)"; \
	  else echo "MISSING  $(HA_CONFIG) - config share not mounted"; fi
	@if [ -f "$(HA_CONFIG)/assist/router.yaml" ]; then echo "ok       $(HA_CONFIG)/assist/router.yaml"; \
	  else echo "MISSING  $(HA_CONFIG)/assist/router.yaml - copy router.example.yaml there"; fi

##@ 2. Try it | 2. Wypróbuj

ui: ## The editor on the example router.yaml, nothing saved (http://127.0.0.1:8766/dev/editor-demo.html) | Edytor na przykładowym router.yaml, nic się nie zapisuje (http://127.0.0.1:8766/dev/editor-demo.html)
	@echo "==> http://127.0.0.1:$(UI_PORT)/dev/editor-demo.html$(if $(filter en,$(HELP_LANG)),?lang=en,)  (Ctrl+C stops)"
	@(sleep 1; open "http://127.0.0.1:$(UI_PORT)/dev/editor-demo.html$(if $(filter en,$(HELP_LANG)),?lang=en,)" 2>/dev/null) &
	@$(PYTHON) -m http.server $(UI_PORT) --bind 127.0.0.1

##@ 3. Home Assistant | 3. Home Assistant

deploy: ## Copy the integration to HA (restart HA yourself) | Skopiuj integrację do HA (restart HA zrób sam)
	@HA_CONFIG="$(HA_CONFIG)" scripts/deploy.sh

##@ 4. Development | 4. Rozwój

test: setup ## Tests of the integration | Testy integracji
	$(VENV)/bin/python -m pytest tests --ignore=tests/browser -q -p no:cacheprovider -n auto

test-browser: setup ## Tests of the editor in Google Chrome | Testy edytora w Google Chrome
	$(VENV)/bin/python -m pytest tests/browser -q -p no:homeassistant -p no:cacheprovider -n auto

screenshots: setup ## Pictures of the editor guide on the demo (docs/assets/editor) | Zrzuty przewodnika po edytorze na demie (docs/assets/editor)
	$(VENV)/bin/python dev/screenshots.py

test-all: test test-browser lint ## All tests and the linter | Wszystkie testy i linter

lint: setup ## Check the Python code | Sprawdź kod Pythona
	$(VENV)/bin/ruff check custom_components tests tools dev
	$(VENV)/bin/ruff format --check custom_components tests tools dev

docs: ## Open the README | Otwórz README
	@open README$(if $(filter pl,$(HELP_LANG)),.pl,).md 2>/dev/null || xdg-open README.md

clean: ## Remove caches (keeps the environment) | Usuń pliki tymczasowe (środowisko zostaje)
	find . -name __pycache__ -type d -prune -not -path "./.venv*" -exec rm -rf {} +
	rm -rf .pytest_cache .ruff_cache tests/browser/output
