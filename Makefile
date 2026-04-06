.PHONY: help install install-dev test test-unit test-integration test-e2e test-all lint format clean build docs

# Default target
help:
	@echo "Available targets:"
	@echo "  install       - Install package"
	@echo "  install-dev   - Install package with dev dependencies"
	@echo "  test          - Run all tests"
	@echo "  test-unit     - Run unit tests only"
	@echo "  test-integration - Run integration tests"
	@echo "  test-tools    - Run tool tests"
	@echo "  test-cov      - Run tests with coverage"
	@echo "  lint          - Run linters (ruff, black, mypy)"
	@echo "  format        - Format code with black and ruff"
	@echo "  clean         - Clean build artifacts"
	@echo "  build         - Build package"
	@echo "  run           - Run the application"

# Installation
install:
	pip install -e .

install-dev:
	pip install -e ".[dev]"
	pre-commit install

# Testing
test: test-unit

test-unit:
	pytest tests/unit -v -m "not integration and not e2e and not network and not slow"

test-integration:
	pytest tests/integration -v -m "integration"

test-e2e:
	pytest tests/e2e -v -m "e2e"

test-tools:
	pytest tests/unit/tools -v
	python test_all_tools.py

test-network:
	pytest tests/ -v -m "network"

test-all:
	pytest tests/ -v

test-cov:
	pytest tests/unit -v --cov=pilotcode --cov-report=html --cov-report=term-missing
	@echo "Coverage report: htmlcov/index.html"

# Linting and formatting
lint:
	ruff check src/pilotcode tests
	black --check src/pilotcode tests
	mypy src/pilotcode --ignore-missing-imports || true

format:
	black src/pilotcode tests
	ruff check --fix src/pilotcode tests

# Cleaning
clean:
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	rm -rf htmlcov/
	rm -rf .coverage
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/
	rm -rf .ruff_cache/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete

# Building
build: clean
	python -m build

twine-check: build
	twine check dist/*

# Running
run:
	python -m pilotcode

run-dev:
	PYTHONPATH=src python -m pilotcode

# Development helpers
setup-git:
	git config --local user.email "dev@pilotcode.local"
	git config --local user.name "PilotCode Developer"

# Documentation
docs:
	@echo "Documentation target not implemented yet"
