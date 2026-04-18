.PHONY: help install test test-fast test-reconciliation lint format check coverage clean \
        dev dev-down dev-logs run-local run-backend run-frontend frontend-lint frontend-build

# Silence pytest warnings + disable plugin autoload chatter + quieter output
PYTEST_FLAGS := --no-header -q -p no:cacheprovider -W ignore --disable-warnings
# Silence npm's progress/funding/audit noise
NPM_FLAGS := --silent --no-fund --no-audit --loglevel=error
# Quiet Docker buildkit plain logs
DOCKER_BUILD_FLAGS := --quiet

help: ## Show available commands
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-26s %s\n", $$1, $$2}'

install: ## Install all dependencies (dev + core)
	@uv sync --extra dev --quiet

# ── Tests ──────────────────────────────────────────────────────────────────────

test: ## Run full test suite with coverage
	@uv run pytest $(PYTEST_FLAGS)

test-fast: ## Skip reconciliation, cloud, and integration tests (quick feedback loop)
	@uv run pytest $(PYTEST_FLAGS) -m "not reconciliation and not cloud and not integration"

test-reconciliation: ## Run reconciliation tests only (requires Postgres running)
	@uv run pytest $(PYTEST_FLAGS) -m reconciliation

coverage: ## Generate HTML coverage report (open htmlcov/index.html)
	@uv run pytest $(PYTEST_FLAGS) --cov=src --cov-report=html --cov-report=term-missing:skip-covered
	@echo "Report: htmlcov/index.html"

# ── Code quality ───────────────────────────────────────────────────────────────

lint: ## Run ruff linter
	@uv run ruff check src tests --quiet

format: ## Run ruff auto-formatter
	@uv run ruff format src tests --quiet

check: ## Run linter + mypy type check
	@uv run ruff check src tests --quiet && uv run mypy src --no-error-summary --no-pretty --hide-error-context --hide-error-codes

# ── Docker stack ───────────────────────────────────────────────────────────────

docker-build: ## Build all Docker images without starting containers (validates Dockerfiles)
	@docker build $(DOCKER_BUILD_FLAGS) -f src/backend/Dockerfile  -t rosetta-backend:dev  .
	@docker build $(DOCKER_BUILD_FLAGS) -f src/worker/Dockerfile   -t rosetta-worker:dev   .
	@docker build $(DOCKER_BUILD_FLAGS) -f src/frontend/Dockerfile -t rosetta-frontend:dev src/frontend

dev: ## Build and start all four services (postgres, backend, worker, frontend)
	docker compose up --build

dev-down: ## Stop all Docker containers
	@docker compose down

dev-logs: ## Tail logs from all Docker containers
	docker compose logs -f

# ── Local (no Docker) ──────────────────────────────────────────────────────────

run-backend: ## Start FastAPI dev server locally (no Docker)
	uv run uvicorn src.backend.main:app --reload --port 8000 --log-level warning

run-frontend: ## Start Vite dev server locally (no Docker)
	cd src/frontend && npm run dev $(NPM_FLAGS)

run-local: ## Reminder: run backend + frontend in separate terminals
	@echo "Run 'make run-backend' and 'make run-frontend' in separate terminals."

# ── Frontend ───────────────────────────────────────────────────────────────────

frontend-lint: ## Run ESLint on frontend source
	@cd src/frontend && npm run lint --silent $(NPM_FLAGS)

frontend-build: ## Build frontend for production
	@cd src/frontend && npm run build --silent $(NPM_FLAGS)

# ── Housekeeping ───────────────────────────────────────────────────────────────

clean: ## Remove build artefacts and caches
	@find . -type d $$$ -name __pycache__ -o -name .pytest_cache -o -name .mypy_cache -o -name .ruff_cache -o -name htmlcov $$$ -exec rm -rf {} + 2>/dev/null; \
	find . -name ".coverage*" -delete 2>/dev/null; true