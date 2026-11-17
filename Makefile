# home-assistant-assist-router - Assist with a question router on a local LLM (Ollama).
#
#   make help    the steps in order (Polish or English, from $LANG; HELP_LANG=en|pl)
#
# "1. Start" needs only Docker Desktop. "3. Development" makes its Python environment with uv (uv fetches the
# Python of PYTHON_VERSION itself), so any target there can be the first one.

PYTHON_VERSION ?= 3.14
HA_CONFIG ?= /Volumes/config
UI_PORT ?= 8767
DEMO_IMAGE ?= assist-router-demo
DOCS_IMAGE ?= assist-router-docs
DOCS_PORT ?= 9767
DOCKERFILE := dev/docker/Dockerfile
DEMO_URL = http://127.0.0.1:$(UI_PORT)/dev/editor-demo.html$(if $(filter en,$(HELP_LANG)),?lang=en,)

VENV := .venv
HELP_LANG ?= $(if $(filter pl%,$(LANG)),pl,en)

.DEFAULT_GOAL := help
.PHONY: help demo demo-clean docs docs-serve doctor deploy setup demo-local test test-browser test-docker test-all \
	lint format docs-build screenshots clean docker-check uv-check

##@ 1. Start | 1. Start

help: ## This list | Ta lista
	@awk -v lang=$(HELP_LANG) 'BEGIN { FS = ":.*## " } \
	  /^##@ / { split(substr($$0, 5), t, " \\| "); printf "\n\033[1m%s\033[0m\n", (lang == "pl" && t[2] != "") ? t[2] : t[1]; next } \
	  /^[a-zA-Z0-9_-]+:.*## / { split($$2, d, " \\| "); printf "  \033[36m%-14s\033[0m %s\n", $$1, (lang == "pl" && d[2] != "") ? d[2] : d[1] }' \
	  $(MAKEFILE_LIST)
	@echo

demo: docker-check ## Try it: the editor on the example router.yaml in Docker, nothing saved (http://127.0.0.1:8767/dev/editor-demo.html) | Wypróbuj: edytor na przykładowym router.yaml w Dockerze, nic się nie zapisuje (http://127.0.0.1:8767/dev/editor-demo.html)
	docker build -f $(DOCKERFILE) --target demo -t $(DEMO_IMAGE) .
	@(sleep 2; open "$(DEMO_URL)" 2>/dev/null) &
	docker run --rm --init $$( [ -t 0 ] && echo -it ) -p 127.0.0.1:$(UI_PORT):$(UI_PORT) $(DEMO_IMAGE)

demo-clean: ## Remove the demo and documentation images of Docker | Usuń obrazy demo i dokumentacji z Dockera
	@docker image rm -f $(DEMO_IMAGE) $(DOCS_IMAGE) >/dev/null 2>&1 || true
	@echo "==> removed | usunięte: $(DEMO_IMAGE) $(DOCS_IMAGE)"

docs: docs-build ## Build the documentation in Docker and open it | Zbuduj dokumentację w Dockerze i ją otwórz
	@open site/$(if $(filter pl,$(HELP_LANG)),pl/,)index.html 2>/dev/null || xdg-open site/index.html

docs-serve: docker-check ## Live preview of the documentation in Docker (http://127.0.0.1:9767/home-assistant-assist-router/) | Podgląd dokumentacji na żywo w Dockerze (http://127.0.0.1:9767/home-assistant-assist-router/)
	docker build -q -f $(DOCKERFILE) --target docs-tools -t $(DOCS_IMAGE) .
	docker run --rm --init $$( [ -t 0 ] && echo -it ) -p 127.0.0.1:$(DOCS_PORT):$(DOCS_PORT) -v "$(CURDIR)":/src $(DOCS_IMAGE) \
	  mkdocs serve --dev-addr 0.0.0.0:$(DOCS_PORT)

doctor: ## Check Docker, Chrome, uv and the Home Assistant share (installs nothing) | Sprawdź Dockera, Chrome, uv i udział Home Assistant (nic nie instaluje)
	@if docker info >/dev/null 2>&1; then echo "ok       Docker"; \
	  else echo "MISSING  Docker Desktop (installed and running) - needed by demo and docs | Docker Desktop - potrzebny do demo i dokumentacji"; fi
	@if [ -d "/Applications/Google Chrome.app" ] || command -v google-chrome >/dev/null; then echo "ok       Google Chrome"; \
	  else echo "MISSING  Google Chrome - only for test-browser and screenshots | tylko do test-browser i screenshots"; fi
	@if command -v uv >/dev/null 2>&1; then echo "ok       uv $$(uv --version | cut -d' ' -f2)"; \
	  else echo "MISSING  uv - only for development: curl -LsSf https://astral.sh/uv/install.sh | sh"; fi
	@if [ -d "$(HA_CONFIG)/custom_components" ]; then echo "ok       $(HA_CONFIG)"; \
	  else echo "MISSING  $(HA_CONFIG) - Home Assistant config share not mounted (only for deploy)"; fi
	@if [ -f "$(HA_CONFIG)/assist/router.yaml" ]; then echo "ok       $(HA_CONFIG)/assist/router.yaml"; \
	  else echo "MISSING  $(HA_CONFIG)/assist/router.yaml - copy router.example.yaml there"; fi

##@ 2. Home Assistant | 2. Home Assistant

deploy: ## Copy the integration to HA (restart HA yourself) | Skopiuj integrację do HA (restart HA zrób sam)
	@HA_CONFIG="$(HA_CONFIG)" scripts/deploy.sh

##@ 3. Development | 3. Rozwój

$(VENV)/bin/pytest: requirements_test.txt | uv-check
	@echo "==> Python $(PYTHON_VERSION) environment in $(VENV) (uv)"
	@test -x $(VENV)/bin/python || uv venv -q --python $(PYTHON_VERSION) $(VENV)
	@uv pip install -q --python $(VENV)/bin/python -r requirements_test.txt
	@touch $@

setup: $(VENV)/bin/pytest ## Create the test environment (.venv, uv) | Utwórz środowisko testów (.venv, uv)

demo-local: setup ## The demo page from .venv, without Docker (for tests and screenshots) | Strona demo z .venv, bez Dockera (do testów i zrzutów)
	@echo "==> $(DEMO_URL)  (Ctrl+C stops)"
	@(sleep 1; open "$(DEMO_URL)" 2>/dev/null) &
	@$(VENV)/bin/python -m http.server $(UI_PORT) --bind 127.0.0.1

test: setup ## Tests of the integration, no Docker images | Testy integracji, bez obrazów Dockera
	$(VENV)/bin/python -m pytest tests --ignore=tests/browser -m "not docker" -q -p no:cacheprovider -n auto

test-browser: setup ## Tests of the editor in Google Chrome | Testy edytora w Google Chrome
	$(VENV)/bin/python -m pytest tests/browser -q -p no:homeassistant -p no:cacheprovider -n auto

test-docker: setup docker-check ## Build and run the demo image: HTTP, every file of the page, no container left | Zbuduj i uruchom obraz demo: HTTP, każdy plik strony, żaden kontener nie zostaje
	$(VENV)/bin/python -m pytest tests --ignore=tests/browser -m docker -q -p no:cacheprovider

test-all: lint test test-browser test-docker ## lint + test + test-browser + test-docker | lint + test + test-browser + test-docker

lint: setup ## Check the Python code and its format | Sprawdź kod Pythona i jego format
	$(VENV)/bin/ruff check custom_components tests tools dev
	$(VENV)/bin/ruff format --check custom_components tests tools dev

format: setup ## Fix what ruff can and format the Python code | Popraw, co ruff umie, i sformatuj kod Pythona
	$(VENV)/bin/ruff check --fix custom_components tests tools dev
	$(VENV)/bin/ruff format custom_components tests tools dev

docs-build: docker-check ## Build the documentation site into site/ in Docker (GitHub Pages, docs-hub) | Zbuduj stronę dokumentacji do site/ w Dockerze (GitHub Pages, docs-hub)
	@rm -rf site
	docker build -q -f $(DOCKERFILE) --target docs-site --output type=local,dest=site .
	@# Docker writes the folder for its owner only; the web server of docs-hub must read it.
	@chmod -R u+rwX,go+rX site

screenshots: setup ## Pictures of the editor for the documentation, on the demo (docs/assets/screens/{pl,en}) | Zrzuty edytora do dokumentacji, na demie (docs/assets/screens/{pl,en})
	$(VENV)/bin/python dev/screenshots.py

clean: ## Remove the environments, site/ and caches | Usuń środowiska, site/ i pamięci podręczne
	find . -name __pycache__ -type d -prune -not -path "./.venv*" -exec rm -rf {} +
	rm -rf .venv .venv-docs .pytest_cache .ruff_cache tests/browser/output site

# Helpers (not in the list) -----------------------------------------------------------------------------------------

docker-check:
	@command -v docker >/dev/null 2>&1 || { echo "Docker not found - install and start Docker Desktop: https://www.docker.com/products/docker-desktop/ | Brak Dockera - zainstaluj i uruchom Docker Desktop"; exit 1; }
	@docker info >/dev/null 2>&1 || { echo "Docker is not running - start Docker Desktop and try again | Docker nie działa - uruchom Docker Desktop i spróbuj ponownie"; exit 1; }

uv-check:
	@command -v uv >/dev/null 2>&1 || { echo "uv not found - install it: curl -LsSf https://astral.sh/uv/install.sh | sh | Brak uv - zainstaluj: curl -LsSf https://astral.sh/uv/install.sh | sh"; exit 1; }
