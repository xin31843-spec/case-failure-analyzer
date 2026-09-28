PYTHON ?= python3
FIXTURE_JOB := tests/fixtures/regressions/mixed-job-success-trial/job
DEV_OUT := failure-analysis/dev

.PHONY: help test test-pytest test-one compile smoke dev dev-min clean

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

smoke: ## End-to-end CLI run against the committed 2-trial fixture
	$(PYTHON) scripts/analyze_case.py --job $(FIXTURE_JOB) --output $(DEV_OUT)
	@echo "--- job_summary.json ---"
	@cat $(DEV_OUT)/job_summary.json

dev: ## Install dev extras (pytest) into the active interpreter
	$(PYTHON) -m pip install -e ".[dev]"

dev-min: ## Fallback if the editable install misbehaves: install pytest only
	$(PYTHON) -m pip install pytest

clean: ## Remove bytecode caches and pytest state
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
	rm -rf .pytest_cache