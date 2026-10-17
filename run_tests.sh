#!/usr/bin/env sh
# Runs all unit/API tests with line coverage per backend area.
# Area -> module: fixtures=fixtures.py, scoring=scoring.py+sports.py, standings=standings.py,
# store=store.py, roster=roster.py, rbac=auth.py
set -e
cd "$(dirname "$0")"
python -m pip install -q pytest pytest-cov fastapi httpx "psycopg[binary]" redis >/dev/null
python -m pytest --cov=backend/app --cov-report=term "$@"
