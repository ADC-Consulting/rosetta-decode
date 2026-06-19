.PHONY: help install test test-fast test-reconciliation lint format check coverage clean \
        dev dev-down dev-logs run-local run-backend run-frontend frontend-lint frontend-build tsc-check docker-build test-file \
        tf-init tf-plan tf-apply tf-destroy tf-fmt tf-validate tf-bootstrap tf-bootstrap-destroy tf-nuke

SHELL := bash
.SHELLFLAGS := -eu -o pipefail -c

# Pytest: quiet, no header, no warnings, short tracebacks, only failure summary
PYTEST_FLAGS := --no-header -q -p no:cacheprovider -W ignore --disable-warnings \
                --tb=short -rN --no-summary
# npm: kill progress/funding/audit/notice noise
NPM_FLAGS := --silent --no-fund --no-audit --no-update-notifier --loglevel=error
# Docker: quiet build
DOCKER_BUILD_FLAGS := --quiet

# Helper: run a command, print only on failure; on success emit one-line OK
define run_quiet
	@out=$$(mktemp); \
	if $(1) >$$out 2>&1; then \
	    echo "✓ $(2)"; rm -f $$out; \
	else \
	    ec=$$?; cat $$out; rm -f $$out; exit $$ec; \
	fi
endef

help: ## Show available commands
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-26s %s\n", $$1, $$2}'

install: ## Install all dependencies
	$(call run_quiet,uv sync --extra dev --quiet,install)

# ── Tests ─────────────────────────────────────────────────────────────────────

test: ## Run full suite (incl. coverage)
	$(call run_quiet,uv run ruff check src tests --quiet,ruff-check)
	$(call run_quiet,uv run ruff format --check src tests --quiet,ruff-format)
	$(call run_quiet,uv run mypy src --no-error-summary --no-pretty --hide-error-context --hide-error-codes,mypy)
	$(call run_quiet,uv run pytest $(PYTEST_FLAGS) --cov=src --cov-fail-under=82 --cov-report=html --cov-report=,pytest+coverage)
	@$(MAKE) -s tsc-check
	@$(MAKE) -s frontend-lint
	@$(MAKE) -s frontend-build
	@echo "Coverage: htmlcov/index.html"

test-file: ## make test-file FILE=tests/test_foo.py
	$(call run_quiet,uv run pytest $(PYTEST_FLAGS) $(FILE),pytest $(FILE))

test-fast: ## Skip slow test markers
	$(call run_quiet,uv run pytest $(PYTEST_FLAGS) -m "not reconciliation and not cloud and not integration",pytest-fast)

test-reconciliation: ## Reconciliation tests only
	$(call run_quiet,uv run pytest $(PYTEST_FLAGS) -m reconciliation,pytest-reconciliation)

coverage: ## HTML coverage report (verbose)
	@uv run pytest $(PYTEST_FLAGS) --cov=src --cov-report=html --cov-report=term:skip-covered
	@echo "Report: htmlcov/index.html"

# ── Code quality ──────────────────────────────────────────────────────────────

lint:
	$(call run_quiet,uv run ruff check src tests --quiet,lint)

format:
	$(call run_quiet,uv run ruff format src tests --quiet,format)

check:
	$(call run_quiet,uv run ruff check src tests --quiet,ruff-check)
	$(call run_quiet,uv run ruff format --check src tests --quiet,ruff-format)
	$(call run_quiet,uv run mypy src --no-error-summary --no-pretty --hide-error-context --hide-error-codes,mypy)

# ── Docker ────────────────────────────────────────────────────────────────────

docker-build:
	$(call run_quiet,docker build $(DOCKER_BUILD_FLAGS) -f src/backend/Dockerfile  -t rosetta-backend:dev  .,docker-backend)
	$(call run_quiet,docker build $(DOCKER_BUILD_FLAGS) -f src/worker/Dockerfile   -t rosetta-worker:dev   .,docker-worker)
	$(call run_quiet,docker build $(DOCKER_BUILD_FLAGS) -f src/frontend/Dockerfile -t rosetta-frontend:dev src/frontend,docker-frontend)

# ── Frontend ──────────────────────────────────────────────────────────────────

tsc-check:
	$(call run_quiet,cd src/frontend && ./node_modules/.bin/tsc --noEmit,tsc)

frontend-lint:
	$(call run_quiet,cd src/frontend && npm run lint,frontend-lint)

frontend-build:
	$(call run_quiet,cd src/frontend && npm run build,frontend-build)

# ── Run (interactive — leave verbose) ─────────────────────────────────────────

run-backend:
	uv run uvicorn src.backend.main:app --reload --port 8000 --log-level warning

run-frontend:
	cd src/frontend && npm run dev -- $(NPM_FLAGS)

run-local:
	@echo "Run 'make run-backend' and 'make run-frontend' in separate terminals."

dev:
	docker compose up --build

dev-down:
	@docker compose down >/dev/null 2>&1 && echo "✓ dev-down"

dev-logs:
	docker compose logs -f

clean:
	@find . -type d $$$ -name __pycache__ -o -name .pytest_cache -o -name .mypy_cache -o -name .ruff_cache -o -name htmlcov $$$ -exec rm -rf {} + 2>/dev/null; \
	find . -name ".coverage*" -delete 2>/dev/null; echo "✓ clean"

# ── Infra (Terraform — same config, per-env tfvars + state) ───────────────────
# Usage: make tf-plan ENV=dev   |   make tf-apply ENV=prd
# Same root config for every env; values come from env/<env>.tfvars, state from
# env/<env>.backend.hcl. plan/apply re-init the backend for the selected env.

TF_DIR     := infra
VALID_ENVS := dev prd

define _tf_guard
	@case " $(VALID_ENVS) " in *" $(ENV) "*) : ;; \
	  *) echo "ENV must be one of: $(VALID_ENVS) (got '$(ENV)'). e.g. make $@ ENV=dev"; exit 1 ;; esac
endef

# Re-init the backend for the selected env, then run the given terraform command
# with that env's var-file.
define _tf_in_env
	cd $(TF_DIR) && \
	  terraform init -reconfigure -backend-config=backend.hcl -backend-config=env/$(ENV).backend.hcl -input=false >/dev/null && \
	  terraform $(1) -var-file=env/common.tfvars -var-file=env/$(ENV).tfvars
endef

tf-init: ## Init backend for an env: make tf-init ENV=dev
	$(_tf_guard)
	@cd $(TF_DIR) && terraform init -reconfigure -backend-config=backend.hcl -backend-config=env/$(ENV).backend.hcl -input=false

tf-fmt: ## Format all Terraform files
	@cd $(TF_DIR) && terraform fmt -recursive

tf-validate: ## Validate config: make tf-validate
	@cd $(TF_DIR) && terraform init -backend=false -input=false >/dev/null && terraform validate

tf-plan: ## Plan changes for an env: make tf-plan ENV=dev
	$(_tf_guard)
	@$(call _tf_in_env,plan -input=false)

tf-apply: ## Apply changes for an env: make tf-apply ENV=dev
	$(_tf_guard)
	@$(call _tf_in_env,apply -input=false)

tf-destroy: ## Destroy an env: make tf-destroy ENV=dev
	$(_tf_guard)
	@$(call _tf_in_env,destroy -input=false)

tf-bootstrap: ## Create the remote-state backend (one-time, az cli)
	@$(TF_DIR)/scripts/bootstrap-backend.sh create

tf-bootstrap-destroy: ## Delete the remote-state backend (DESTROYS ALL STATE)
	@$(TF_DIR)/scripts/bootstrap-backend.sh destroy

tf-nuke: ## Tear EVERYTHING down: destroy dev + prd infra, then the backend
	@echo ">> Destroying dev infra..."   && $(MAKE) -s tf-destroy ENV=dev
	@echo ">> Destroying prd infra..."   && $(MAKE) -s tf-destroy ENV=prd
	@echo ">> Removing state backend..." && $(MAKE) -s tf-bootstrap-destroy