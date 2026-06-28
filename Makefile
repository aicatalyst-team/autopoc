# AutoPoC Makefile (OpenCode harness)
# ------------------------------------
# Targets:
#   make image       - Build both container images (opencode + recorder)
#   make image-push  - Push both container images to registry
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
CONTAINER_CMD  ?= podman
NAME            = autopoc
VERSION         = $(shell $(PYTHON) -c "from autopoc import __version__; print(__version__)" 2>/dev/null || echo 0.1.0)

# Container image settings
IMAGE_REGISTRY ?= quay.io
IMAGE_ORG      ?= autopoc
IMAGE_TAG      ?= latest
IMAGE_OPENCODE = $(IMAGE_REGISTRY)/$(IMAGE_ORG)/autopoc-opencode:$(IMAGE_TAG)
IMAGE_RECORDER = $(IMAGE_REGISTRY)/$(IMAGE_ORG)/autopoc-recorder:$(IMAGE_TAG)

.DEFAULT_GOAL := help

# ---------- image ----------

.PHONY: image
image: ## Build both container images (opencode + recorder)
	$(CONTAINER_CMD) build -t $(IMAGE_OPENCODE) .
	$(CONTAINER_CMD) build -f Dockerfile.record-demo -t $(IMAGE_RECORDER) .

.PHONY: image-push
image-push: ## Push both container images to registry
	$(CONTAINER_CMD) push $(IMAGE_OPENCODE)
	$(CONTAINER_CMD) push $(IMAGE_RECORDER)

# ---------- ogx image ----------

OGX_VERSION ?=

.PHONY: ogx-image
ogx-image: ## Build OGX (LlamaStack) UBI9 container image
	CONTAINER_CMD=$(CONTAINER_CMD) IMAGE_REGISTRY=$(IMAGE_REGISTRY) IMAGE_ORG=$(IMAGE_ORG) \
		OGX_VERSION=$(OGX_VERSION) ./deploy/build-ogx.sh

.PHONY: ogx-image-push
ogx-image-push: ## Build and push OGX UBI9 container image
	CONTAINER_CMD=$(CONTAINER_CMD) IMAGE_REGISTRY=$(IMAGE_REGISTRY) IMAGE_ORG=$(IMAGE_ORG) \
		OGX_VERSION=$(OGX_VERSION) ./deploy/build-ogx.sh --push

# ---------- dev ----------

.PHONY: install
install: ## Install in editable mode with dev extras
	$(PIP) install -r requirements.lock
	$(PIP) install -e ".[dev]" --no-deps

.PHONY: lock
lock: ## Regenerate requirements.lock from pyproject.toml
	pip-compile --upgrade --generate-hashes --output-file=requirements.lock pyproject.toml

.PHONY: test
test: ## Run unit and integration tests with coverage
	$(PYTHON) -m pytest tests/ --ignore=tests/e2e -q --cov --cov-report=term-missing

.PHONY: test-e2e
test-e2e: ## Run end-to-end tests (requires local infra)
	$(PYTHON) -m pytest tests/e2e/ --e2e -v

.PHONY: typecheck
typecheck: ## Type-check with pyright
	pyright src/

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
	rm -rf build/ *.egg-info src/*.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true

# ---------- help ----------

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'
