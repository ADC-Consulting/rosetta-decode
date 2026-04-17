.PHONY: help install test test-fast test-reconciliation lint format check coverage clean \
        run-local run-backend run-frontend frontend-lint frontend-test frontend-build

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-24s %s\n", $$1, $$2}'

install: ## Install all dependencies (dev + core)
	uv sync --extra dev

test: ## Run full test suite with coverage
	uv run pytest

test-fast: ## Run tests excluding slow reconciliation and cloud tests
	uv run pytest -m "not reconciliation and not cloud and not integration"

test-reconciliation: ## Run reconciliation tests only
	uv run pytest -m reconciliation

lint: ## Run ruff linter
	uv run ruff check src tests

format: ## Run ruff formatter
	uv run ruff format src tests

check: ## Run linter + type checker
	uv run ruff check src tests && uv run mypy src

coverage: ## Show coverage report
	uv run pytest --cov=src/sas_migrator --cov-report=html

clean: ## Remove build artifacts and caches
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; \
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null; \
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null; \
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null; \
	find . -type d -name htmlcov -exec rm -rf {} + 2>/dev/null; \
	find . -name ".coverage*" -delete 2>/dev/null; true

run-backend: ## Start FastAPI dev server
	uv run uvicorn sas_migrator.api.main:app --reload --port 8000

run-frontend: ## Start Vite dev server
	cd src/frontend && npm run dev

run-local: ## Start backend + frontend (requires two terminals)
	@echo "Run 'make run-backend' and 'make run-frontend' in separate terminals"

frontend-lint: ## Run ESLint on frontend
	cd src/frontend && npm run lint

frontend-test: ## Run frontend tests
	cd src/frontend && npm run test

frontend-build: ## Build frontend for production
	cd src/frontend && npm run build
