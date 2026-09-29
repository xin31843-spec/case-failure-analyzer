PYTHON ?= python3
RUFF ?= $(shell command -v ruff 2>/dev/null || (command -v uv >/dev/null 2>&1 && echo "uv tool run ruff") || echo "$(PYTHON) -m ruff")
FIXTURE_JOB := tests/fixtures/regressions/mixed-job-success-trial/job
DEV_OUT := failure-analysis/dev

.PHONY: help test test-pytest test-one compile smoke dev dev-min clean lint lint-fix format format-check

help: ## List available targets
	@grep -E '^[a-z][a-z-]*:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-14s %s\n", $$1, $$2}'

test: ## Canonical zero-dependency test run (unittest, no install needed)
	$(PYTHON) -m unittest discover -s tests -t . -v

test-pytest: ## Optional pytest run (requires `make dev`)
	$(PYTHON) -m pytest -q

test-one: ## Run one test module: make test-one T=tests.test_attribution_decision_table
	$(PYTHON) -m unittest -v $(T)

compile: ## Zero-dependency syntax check over scripts/ and tests/
	$(PYTHON) -m compileall -q scripts tests

lint: ## Check codebase with ruff (syntax, dead code, and anti-patterns)
	$(RUFF) check .

lint-fix: ## Automatically fix safe lint issues (unused imports, etc.)
	$(RUFF) check --fix .

format: ## Format codebase with ruff
	$(RUFF) format .

format-check: ## Check codebase formatting with ruff without writing changes
	$(RUFF) format --check .

smoke: ## End-to-end CLI run against the committed 2-trial fixture
	$(PYTHON) scripts/analyze_case.py --job $(FIXTURE_JOB) --output $(DEV_OUT)
	@echo "--- job_summary.json ---"
	@cat $(DEV_OUT)/job_summary.json

dev: ## Install dev extras (pytest, ruff) into the active interpreter
	$(PYTHON) -m pip install -e ".[dev]"

dev-min: ## Fallback if the editable install misbehaves: install pytest and ruff only
	$(PYTHON) -m pip install pytest ruff

clean: ## Remove bytecode caches and pytest state
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
	rm -rf .pytest_cache .ruff_cache