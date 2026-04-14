# ai-harness — common dev operations
#
# Run `make help` to discover targets.

.DEFAULT_GOAL := help
.PHONY: help install test test-py test-web test-e2e lint fmt typecheck dev-api dev-web docker clean ci status doctor verify pause resume

help: ## Show available targets
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Install all dependencies (Python + JS) and pre-commit hooks
	uv sync --group dev --all-packages
	pnpm install
	uv run pre-commit install

test: test-py test-web ## Run all unit tests

test-py: ## Run Python tests (apps/api + agents)
	uv run pytest apps/api agents -v

test-web: ## Run web unit tests (vitest)
	pnpm --filter web test

test-e2e: ## Run Playwright e2e tests (auto-starts api)
	pnpm --filter web e2e

lint: ## Run ruff + tsc
	uv run ruff check .
	pnpm --filter web typecheck

fmt: ## Auto-format with ruff
	uv run ruff check --fix .
	uv run ruff format .

typecheck: ## Type-check Python + TypeScript
	uv run mypy apps/api/src agents/src
	pnpm --filter web typecheck

dev-api: ## Run FastAPI in dev mode (localhost:8080)
	uv run uvicorn api.main:app --reload --port 8080

dev-web: ## Run Vite dev server (localhost:5173)
	pnpm --filter web dev

docker: ## Build the production Docker image locally
	docker build -t ai-harness:local .

clean: ## Remove build artifacts + caches
	rm -rf apps/web/dist apps/web/node_modules .venv .ruff_cache .mypy_cache .pytest_cache
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

ci: lint typecheck test ## Run everything CI runs locally

# ─── harness CLI shortcuts ──────────────────────────────────────────────

status: ## harness status
	uv run harness status

doctor: ## harness doctor (env health check)
	uv run harness doctor

verify: ## harness verify (live integration check)
	uv run harness verify

pause: ## Halt all agent workflows
	uv run harness pause

resume: ## Resume agent workflows
	uv run harness resume
