# Shippo Extras Discovery Suite - Makefile
# Development workflow automation with uv

.PHONY: help install install-dev test lint format typecheck quality clean \
        run-discovery run-comparative run-analyzer list-carriers list-extras

# Default target
help:
	@echo "Shippo Extras Discovery Suite"
	@echo ""
	@echo "Setup:"
	@echo "  make install        Install runtime dependencies"
	@echo "  make install-dev    Install with development dependencies"
	@echo "  make sync           Sync dependencies from lockfile"
	@echo ""
	@echo "Quality:"
	@echo "  make lint           Run ruff linter"
	@echo "  make format         Format code with ruff"
	@echo "  make typecheck      Run type checking (if pyre available)"
	@echo "  make test           Run test suite"
	@echo "  make quality        Run all quality checks"
	@echo ""
	@echo "Discovery Tests:"
	@echo "  make list-carriers  List connected carrier accounts"
	@echo "  make list-extras    List all testable extras"
	@echo "  make run-discovery  Run basic discovery tests"
	@echo "  make run-comparative Run comparative analysis"
	@echo "  make run-analyzer   Run service level analyzer"
	@echo ""
	@echo "Utilities:"
	@echo "  make clean          Remove generated files and caches"

# =============================================================================
# Setup
# =============================================================================

install:
	uv sync --no-dev

install-dev:
	uv sync

sync:
	uv sync

# =============================================================================
# Quality Assurance
# =============================================================================

lint:
	uv run ruff check src/ test/ analysis/

format:
	uv run ruff format src/ test/ analysis/
	uv run ruff check --fix src/ test/ analysis/

typecheck:
	@command -v pyre >/dev/null 2>&1 && pyre check || echo "Pyre not installed, skipping type check"

test:
	uv run pytest test/test_async_behavior.py -v

test-cov:
	uv run pytest test/test_async_behavior.py -v --cov=src --cov-report=term-missing

quality: lint test
	@echo "All quality checks passed!"

# =============================================================================
# Discovery Tests
# =============================================================================

# Ensure SHIPPO_API_KEY is set
check-api-key:
	@if [ -z "$$SHIPPO_API_KEY" ]; then \
		echo "Error: SHIPPO_API_KEY environment variable not set"; \
		echo "Run: export SHIPPO_API_KEY='shippo_test_xxxxx'"; \
		exit 1; \
	fi

list-carriers: check-api-key
	uv run python src/shippo_extras.py --list-carriers

list-extras:
	uv run python src/shippo_extras.py --list-extras

run-discovery: check-api-key
	uv run python src/shippo_extras.py

run-discovery-quick: check-api-key
	uv run python src/shippo_extras.py --max-tests 20

run-comparative: check-api-key
	uv run python src/comparative_runner.py

run-analyzer: check-api-key
	uv run python analysis/service_level_analyzer.py

# Run discovery for specific carrier
# Usage: make run-carrier CARRIER=usps
run-carrier: check-api-key
	uv run python src/shippo_extras.py -c $(CARRIER)

# Run with custom concurrency
# Usage: make run-fast CONCURRENCY=20
run-fast: check-api-key
	uv run python src/shippo_extras.py -j $(or $(CONCURRENCY),10)

# =============================================================================
# Utilities
# =============================================================================

clean:
	rm -rf __pycache__ */__pycache__ */*/__pycache__
	rm -rf .pytest_cache */.pytest_cache
	rm -rf .ruff_cache
	rm -rf htmlcov .coverage
	rm -rf *.egg-info
	rm -rf .venv
	find . -type f -name "*.pyc" -delete
