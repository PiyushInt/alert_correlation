#!/bin/bash
set -e

# Prevent local tests from leaking into the developer's default database.
# Tests MUST mock dependencies or use the db_session fixture.
export DATABASE_URL="postgresql+psycopg://ace_user:ace_password@localhost:5433/ace_db_must_be_mocked_in_tests"
export REDIS_URL="redis://localhost:6380/15"

# Ensure local environment strictly matches pyproject.toml to catch missing deps.
if command -v uv >/dev/null 2>&1; then
    echo "Syncing dependencies with uv..."
    uv sync --all-extras
fi

echo "Running ruff format check..."
ruff format --check src/ tests/

echo "Running ruff check..."
ruff check src/ tests/

echo "Running mypy..."
mypy src/

echo "Running pytest..."
pytest

echo "All checks passed!"
