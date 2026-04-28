# AutoPoC Makefile
# -----------------
# Targets:
#   make build       - Build a single-file executable (shiv zipapp)
#   make image       - Build container image
#   make image-push  - Push container image to registry
#   make install     - pip install in editable mode with dev extras
#   make lock        - Regenerate requirements.lock from pyproject.toml
#   make test        - Run unit/integration tests
#   make test-e2e    - Run end-to-end tests (requires infra)
#   make lint        - Lint with ruff
#   make fmt         - Auto-format with ruff
#   make clean       - Remove build artifacts
#   make help        - Show this help

PYTHON         ?= python
PIP            ?= pip
SHIV           ?= shiv
CONTAINER_CMD  ?= podman
NAME            = autopoc
VERSION         = $(shell $(PYTHON) -c "from autopoc import __version__; print(__version__)" 2>/dev/null || echo 0.1.0)
DIST_DIR        = dist
BINARY          = $(DIST_DIR)/$(NAME)

# Container image settings
IMAGE_REGISTRY ?= quay.io
IMAGE_ORG      ?= autopoc
IMAGE_NAME     ?= autopoc
IMAGE_TAG      ?= latest
IMAGE           = $(IMAGE_REGISTRY)/$(IMAGE_ORG)/$(IMAGE_NAME):$(IMAGE_TAG)

.DEFAULT_GOAL := help

# ---------- build ----------

.PHONY: build
build: $(BINARY) ## Build single-file executable with shiv

$(BINARY): pyproject.toml src/autopoc/**/*.py src/autopoc/prompts/*.md src/autopoc/templates/*.j2
	@mkdir -p $(DIST_DIR)
	$(SHIV) \
		--console-script $(NAME) \
		--output-file $(BINARY) \
		--python "/usr/bin/env python3" \
		--compressed \
		".[checkpoint]"
	@chmod +x $(BINARY)
	@echo ""
	@echo "Built: $(BINARY) ($(shell du -h $(BINARY) | cut -f1))"
	@echo "Run:   ./$(BINARY) --help"

# ---------- image ----------

.PHONY: image
image: ## Build container image
	$(CONTAINER_CMD) build -t $(IMAGE) .

.PHONY: image-push
image-push: ## Push container image to registry
	$(CONTAINER_CMD) push $(IMAGE)

# ---------- dev ----------

.PHONY: install
install: ## Install in editable mode with dev extras
	$(PIP) install -r requirements.lock
	$(PIP) install -e ".[dev,checkpoint]" --no-deps

.PHONY: lock
lock: ## Regenerate requirements.lock from pyproject.toml
	pip-compile --generate-hashes --output-file=requirements.lock pyproject.toml

.PHONY: test
test: ## Run unit and integration tests
	$(PYTHON) -m pytest tests/ --ignore=tests/e2e -q

.PHONY: test-e2e
test-e2e: ## Run end-to-end tests (requires local infra)
	$(PYTHON) -m pytest tests/e2e/ --e2e -v

.PHONY: lint
lint: ## Lint with ruff
	ruff check src/ tests/

.PHONY: fmt
fmt: ## Auto-format with ruff
	ruff format src/ tests/
	ruff check --fix src/ tests/

# ---------- clean ----------

.PHONY: clean
clean: ## Remove build artifacts
	rm -rf $(DIST_DIR) build/ *.egg-info src/*.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true

# ---------- help ----------

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'
