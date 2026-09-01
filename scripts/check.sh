#!/bin/bash
set -e

if [ -z "${CI}" ]; then
    # Prevent local tests from leaking into the developer's default database.
    # Tests MUST mock dependencies or use the db_session fixture.
    export DATABASE_URL="postgresql+psycopg://ace_user:ace_password@localhost:5433/ace_db_must_be_mocked_in_tests"
    export REDIS_URL="redis://localhost:6380/15"

    # Ensure local environment strictly matches pyproject.toml to catch missing deps.
    if command -v uv >/dev/null 2>&1; then
        echo "Syncing dependencies with uv..."
        uv sync --all-extras
    fi
fi

echo "Checking for destructive database commands..."
if git ls-files | grep -E '^(scripts/|eval/|src/|[^/]+$)' | grep -vE '^(AGENTS\.md|\.pre-commit-config\.yaml|scripts/check\.sh)$' | xargs git grep -E 'downgrade base|TRUNCATE|DROP TABLE' -- > /dev/null 2>&1; then
    echo "ERROR: Destructive database commands found in executable code."
    exit 1
fi

echo "Running ruff format check..."
ruff format --check src/ tests/

echo "Running ruff check..."
ruff check src/ tests/

echo "Running mypy..."
mypy src/
mypy --strict --explicit-package-bases eval/matcher.py tests/eval/test_matcher.py

echo "Running pytest..."
pytest

echo "All checks passed!"
