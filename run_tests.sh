#!/usr/bin/env sh
# Runs the unit tests with line coverage. Usage: ./run_tests.sh
set -e
cd "$(dirname "$0")"
python -m pip install -q pytest pytest-cov fastapi "psycopg[binary]" redis httpx >/dev/null
python -m pytest --cov=backend/app --cov-report=term-missing "$@"
