# Alert Correlation Engine

An intelligent engine that normalizes, deduplicates, and correlates alerts from disparate monitoring tools to reduce alert noise and identify root causes.

## Getting Started

1. Clone the repository.
2. Ensure you have Python 3.12 installed.
3. Set up the virtual environment: `python3.12 -m venv .venv && source .venv/bin/activate`
4. Install dependencies: `pip install -e ".[dev]"`
5. Start local infrastructure: `docker compose -f docker-compose.services.yml up -d`
6. Run the application: `./scripts/dev.sh`
