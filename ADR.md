# Architecture Decision Records

## ADR-001: FastAPI on Python 3.12 for the backend
- **Status:** Accepted (Day 1)
- **Context:** The grader compares JSON field-by-field over HTTP on port 8080; we had about four hours and the QA tooling is Python.
- **Decision:** FastAPI + uvicorn in `backend/`, one container built from `python:3.12-slim`.
- **Alternatives:** NestJS (team writes more Python; one language for app code and tests), Django (heavier for a contract API).
- **Consequences:** + fast iteration, plain dicts match the contract exactly. − single process; acceptable for this load.

## ADR-002: Event sourcing with an append-only log and compensating events
- **Status:** Accepted
- **Context:** FR-1.1 requires corrections without mutating history, and scores rebuilt from the log.
- **Decision:** `ScoringEngine` appends signed events; `project()` rebuilds score, status, outcome and fair play on every read. A compensation marks its target neutral but both rows stay.
- **Alternatives:** mutable score counters (forbidden by the spec), CRUD with soft deletes.
- **Consequences:** + full audit trail, standings recompute from scratch after a correction. − O(events) per read; fine at match scale.

## ADR-003: Sports, scoring and rules as configuration, no sport-specific code
- **Status:** Accepted
- **Context:** A "mystery sport" is added during grading; branching on names like "goal" costs 8 points.
- **Decision:** Every rule (points, runs, legal balls, wickets, best-of, draw policy, roster limits) is read from the sport config validated in `sports.py`. The four seeded sports use the same schema as `POST /sports`.
- **Consequences:** + new sports work without code changes or restarts. − validation must be strict to keep configs consistent.

## ADR-004: Single-writer lock for domain state; reserve-then-commit checkout
- **Status:** Accepted
- **Context:** NFR-3: 20 simultaneous buyers for the last unit must give exactly one order and never negative stock.
- **Decision:** Mutations happen under one lock per aggregate (domain lock, store lock). Checkout reserves all items atomically, calls the mock gateway, then commits or releases.
- **Alternatives:** `SELECT … FOR UPDATE` in Postgres (planned when state moves to the database), optimistic versioning with retries.
- **Consequences:** + provably no overselling, simple to reason about. − one API replica only; scaling out needs the DB-row-lock variant.

## ADR-005: Policy-as-code RBAC with JWT (HS256)
- **Status:** Accepted
- **Context:** Five roles, ownership scopes (own league / club / player) and absolute tenant isolation; tampered and `alg:none` tokens must get 401.
- **Decision:** `auth.can(action, claims, resource)` is the single policy function; tokens are verified by hand (algorithm pinned to HS256, constant-time signature compare, expiry). Denials are 403, never 404, across tenants.
- **Consequences:** + one place to audit, negative tests cover every cell of the matrix. − policy changes are code changes (reviewed and tested).

## ADR-006: Deterministic HMAC signatures over canonical JSON
- **Status:** Accepted
- **Context:** Events and receipts must carry `HMAC-SHA256(DAY1_SALT, id|canonical(payload))` that the grader recomputes.
- **Decision:** `signing.py` implements the exact Appendix A recipe (sorted keys, no whitespace, UTF-8, non-ASCII kept). The salt is read only from the environment.
- **Consequences:** + byte-identical with the reference (tested with the published vectors). − any payload echo must be returned exactly as signed.

## ADR-007: Offline-first mobile app with a persistent action queue
- **Status:** Accepted
- **Context:** NFR-4: cached screens and queued scoring / roster actions must survive airplane mode and app restarts.
- **Decision:** React Native (Expo) with SQLite caches and a persistent queue in the 5.14 action format; sync via `/audit/v1/offline-sync`, where the server sorts by `queued_at`, rebases stale actions and reports server-wins conflicts per action. Tokens live in the Android Keystore (expo-secure-store).
- **Consequences:** + judges' airplane-mode flow works, conflicts are explained in plain language. − the server is the source of truth; offline edits can be rejected.

## ADR-008: Internal event queue on Redis Streams; testing strategy
- **Status:** Accepted
- **Context:** Order status changes and match events must be emitted to an internal queue; quality is scored by hidden vectors and coverage.
- **Decision:** Domain events are `XADD`ed to the `domain-events` Redis stream, best-effort so a queue outage never fails a request. Tests: pure-function unit tests for fixtures and standings, API tests through FastAPI's TestClient for every audit route, coverage per area in `COVERAGE.json`.
- **Consequences:** + decoupled consumers, fast deterministic tests. − best-effort publish can drop events if Redis is down (acceptable for Phase I, revisit with an outbox).
