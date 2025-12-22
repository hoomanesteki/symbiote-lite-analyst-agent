# ============================================================
# Symbiote Lite - Makefile
# ============================================================
# Usage: make <target>
# Run 'make help' to see all available commands
# ============================================================

.PHONY: help install install-dev setup clean test test-cov test-mcp lint format typecheck run server db docker-build docker-run docker-test docker-clean all

# Default target
.DEFAULT_GOAL := help

# ============================================================
# Variables
# ============================================================
PYTHON := python
PIP := pip
CONDA := conda
PYTEST := pytest
DOCKER := docker
DOCKER_COMPOSE := docker-compose

PROJECT_NAME := symbiote-lite
DOCKER_IMAGE := symbiote-lite
DOCKER_TAG := latest

# Colors for terminal output
BLUE := \033[0;34m
GREEN := \033[0;32m
YELLOW := \033[0;33m
RED := \033[0;31m
NC := \033[0m # No Color

# ============================================================
# Help
# ============================================================
help: ## Show this help message
	@echo ""
	@echo "$(BLUE)Symbiote Lite - Available Commands$(NC)"
	@echo "============================================================"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "$(GREEN)%-20s$(NC) %s\n", $$1, $$2}'
	@echo ""

# ============================================================
# Environment Setup
# ============================================================
install: ## Install production dependencies
	@echo "$(BLUE)Installing production dependencies...$(NC)"
	$(PIP) install pandas numpy python-dotenv mcp

install-dev: ## Install development dependencies
	@echo "$(BLUE)Installing development dependencies...$(NC)"
	$(PIP) install pandas numpy python-dotenv mcp openai pytest pytest-cov mypy ruff

install-all: install install-dev ## Install all dependencies
	@echo "$(GREEN)All dependencies installed!$(NC)"

setup: ## Full setup: install deps + create sample database
	@echo "$(BLUE)Running full setup...$(NC)"
	$(MAKE) install-dev
	$(MAKE) db
	@echo "$(GREEN)Setup complete! Run 'make run' to start the agent.$(NC)"

conda-create: ## Create conda environment from environment.yml
	@echo "$(BLUE)Creating conda environment...$(NC)"
	$(CONDA) env create -f environment.yml

conda-update: ## Update conda environment
	@echo "$(BLUE)Updating conda environment...$(NC)"
	$(CONDA) env update -f environment.yml --prune

conda-lock: ## Create conda-lock file for all platforms
	@echo "$(BLUE)Creating conda-lock files...$(NC)"
	conda-lock -f environment.yml -p osx-64 -p osx-arm64 -p linux-64 -p win-64
	@echo "$(GREEN)Lock file created: conda-lock.yml$(NC)"

# ============================================================
# Database
# ============================================================
db: ## Create sample database
	@echo "$(BLUE)Creating sample database...$(NC)"
	$(PYTHON) -m scripts.create_sample_db
	@echo "$(GREEN)Database created at data/taxi_trips.sqlite$(NC)"

db-clean: ## Remove database
	@echo "$(YELLOW)Removing database...$(NC)"
	rm -f data/taxi_trips.sqlite

db-reset: db-clean db ## Reset database (delete and recreate)

# ============================================================
# Running the Application
# ============================================================
run: ## Run the interactive agent
	@echo "$(BLUE)Starting Symbiote Lite Agent...$(NC)"
	$(PYTHON) -m scripts.run_agent

server: ## Start the MCP server
	@echo "$(BLUE)Starting MCP Server...$(NC)"
	$(PYTHON) -m scripts.mcp_server

# ============================================================
# Testing
# ============================================================
test: ## Run all tests
	@echo "$(BLUE)Running tests...$(NC)"
	$(PYTEST) tests/ -v

test-fast: ## Run tests without slow markers
	@echo "$(BLUE)Running fast tests...$(NC)"
	$(PYTEST) tests/ -v -m "not slow"

test-cov: ## Run tests with coverage report
	@echo "$(BLUE)Running tests with coverage...$(NC)"
	$(PYTEST) tests/ -v --cov=symbiote_lite --cov-report=html --cov-report=term-missing
	@echo "$(GREEN)Coverage report: htmlcov/index.html$(NC)"

test-mcp: ## Run MCP integration tests
	@echo "$(BLUE)Running MCP integration tests...$(NC)"
	$(PYTHON) -m scripts.test_mcp_integration

test-all: test test-mcp ## Run all tests including MCP integration
	@echo "$(GREEN)All tests completed!$(NC)"

# ============================================================
# Code Quality
# ============================================================
lint: ## Run linter (ruff)
	@echo "$(BLUE)Running linter...$(NC)"
	ruff check symbiote_lite/ scripts/ tests/

lint-fix: ## Run linter and fix issues
	@echo "$(BLUE)Running linter with auto-fix...$(NC)"
	ruff check --fix symbiote_lite/ scripts/ tests/

format: ## Format code (ruff)
	@echo "$(BLUE)Formatting code...$(NC)"
	ruff format symbiote_lite/ scripts/ tests/

typecheck: ## Run type checker (mypy)
	@echo "$(BLUE)Running type checker...$(NC)"
	mypy symbiote_lite/ --ignore-missing-imports

check: lint typecheck ## Run all code quality checks
	@echo "$(GREEN)All checks passed!$(NC)"

# ============================================================
# Docker
# ============================================================
docker-build: ## Build Docker image
	@echo "$(BLUE)Building Docker image...$(NC)"
	$(DOCKER) build -t $(DOCKER_IMAGE):$(DOCKER_TAG) .
	@echo "$(GREEN)Image built: $(DOCKER_IMAGE):$(DOCKER_TAG)$(NC)"

docker-run: ## Run agent in Docker container
	@echo "$(BLUE)Running agent in Docker...$(NC)"
	$(DOCKER) run -it --rm \
		-v $(PWD)/data:/app/data \
		$(DOCKER_IMAGE):$(DOCKER_TAG)

docker-server: ## Run MCP server in Docker container
	@echo "$(BLUE)Running MCP server in Docker...$(NC)"
	$(DOCKER) run -it --rm \
		-p 8000:8000 \
		-v $(PWD)/data:/app/data \
		$(DOCKER_IMAGE):$(DOCKER_TAG) \
		python -m scripts.mcp_server

docker-test: ## Run tests in Docker container
	@echo "$(BLUE)Running tests in Docker...$(NC)"
	$(DOCKER) run --rm \
		-v $(PWD)/data:/app/data \
		$(DOCKER_IMAGE):$(DOCKER_TAG) \
		python -m pytest tests/ -v

docker-shell: ## Open shell in Docker container
	@echo "$(BLUE)Opening shell in Docker container...$(NC)"
	$(DOCKER) run -it --rm \
		-v $(PWD)/data:/app/data \
		$(DOCKER_IMAGE):$(DOCKER_TAG) \
		/bin/bash

docker-clean: ## Remove Docker image
	@echo "$(YELLOW)Removing Docker image...$(NC)"
	$(DOCKER) rmi $(DOCKER_IMAGE):$(DOCKER_TAG) || true

# Docker Compose commands
dc-up: ## Start services with docker-compose
	@echo "$(BLUE)Starting services...$(NC)"
	$(DOCKER_COMPOSE) up -d

dc-down: ## Stop services with docker-compose
	@echo "$(YELLOW)Stopping services...$(NC)"
	$(DOCKER_COMPOSE) down

dc-logs: ## View docker-compose logs
	$(DOCKER_COMPOSE) logs -f

dc-build: ## Build with docker-compose
	@echo "$(BLUE)Building with docker-compose...$(NC)"
	$(DOCKER_COMPOSE) build

# ============================================================
# Cleaning
# ============================================================
clean: ## Remove Python cache files
	@echo "$(YELLOW)Cleaning Python cache...$(NC)"
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type f -name "*.pyo" -delete 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name ".coverage" -delete 2>/dev/null || true
	@echo "$(GREEN)Cleaned!$(NC)"

clean-all: clean db-clean docker-clean ## Remove all generated files
	@echo "$(GREEN)All cleaned!$(NC)"

# ============================================================
# Development Workflow
# ============================================================
dev: ## Start development mode (run tests on file change)
	@echo "$(BLUE)Starting development mode...$(NC)"
	@echo "$(YELLOW)Install 'pytest-watch' for auto-reload: pip install pytest-watch$(NC)"
	ptw tests/ -- -v

pre-commit: format lint test ## Run before committing (format, lint, test)
	@echo "$(GREEN)Pre-commit checks passed!$(NC)"

# ============================================================
# Release
# ============================================================
build: ## Build package
	@echo "$(BLUE)Building package...$(NC)"
	$(PYTHON) -m build
	@echo "$(GREEN)Package built in dist/$(NC)"

publish-test: ## Publish to TestPyPI
	@echo "$(BLUE)Publishing to TestPyPI...$(NC)"
	$(PYTHON) -m twine upload --repository testpypi dist/*

publish: ## Publish to PyPI
	@echo "$(BLUE)Publishing to PyPI...$(NC)"
	$(PYTHON) -m twine upload dist/*

# ============================================================
# Quick Start
# ============================================================
all: setup test run ## Complete setup, test, and run
