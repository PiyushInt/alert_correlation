#!/bin/bash
set -e

echo "Running ruff format check..."
ruff format --check src/ tests/

echo "Running ruff check..."
ruff check src/ tests/

echo "Running mypy..."
mypy src/

echo "Running pytest..."
pytest

echo "All checks passed!"
