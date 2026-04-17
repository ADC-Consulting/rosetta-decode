.PHONY: help install test test-fast test-reconciliation lint format check coverage clean \
        dev dev-down dev-logs run-local run-backend run-frontend frontend-lint frontend-build

help: ## Show available commands
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-26s %s\n", $$1, $$2}'

install: ## Install all dependencies (dev + core)
	uv sync --extra dev

# ── Tests ──────────────────────────────────────────────────────────────────────

test: ## Run full test suite with coverage
	uv run pytest

test-fast: ## Skip reconciliation, cloud, and integration tests (quick feedback loop)
	uv run pytest -m "not reconciliation and not cloud and not integration"

test-reconciliation: ## Run reconciliation tests only (requires Postgres running)
	uv run pytest -m reconciliation

coverage: ## Generate HTML coverage report (opens htmlcov/index.html)
	uv run pytest --cov=src --cov-report=html
	@echo "Coverage report: htmlcov/index.html"

# ── Code quality ───────────────────────────────────────────────────────────────

lint: ## Run ruff linter
	uv run ruff check src tests

format: ## Run ruff auto-formatter
	uv run ruff format src tests

check: ## Run linter + mypy type check
	uv run ruff check src tests && uv run mypy src

# ── Docker stack ───────────────────────────────────────────────────────────────

dev: ## Build and start all four services (postgres, backend, worker, frontend)
	docker compose up --build

dev-down: ## Stop all Docker containers
	docker compose down

dev-logs: ## Tail logs from all Docker containers
	docker compose logs -f

# ── Local (no Docker) ──────────────────────────────────────────────────────────

run-backend: ## Start FastAPI dev server locally (no Docker)
	uv run uvicorn src.backend.main:app --reload --port 8000

run-frontend: ## Start Vite dev server locally (no Docker)
	cd src/frontend && npm run dev

run-local: ## Reminder: run backend + frontend in separate terminals
	@echo "Run 'make run-backend' and 'make run-frontend' in separate terminals."

# ── Frontend ───────────────────────────────────────────────────────────────────

frontend-lint: ## Run ESLint on frontend source
	cd src/frontend && npm run lint

frontend-build: ## Build frontend for production
	cd src/frontend && npm run build

# ── Housekeeping ───────────────────────────────────────────────────────────────

clean: ## Remove build artefacts and caches
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; \
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null; \
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null; \
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null; \
	find . -type d -name htmlcov -exec rm -rf {} + 2>/dev/null; \
	find . -name ".coverage*" -delete 2>/dev/null; true
