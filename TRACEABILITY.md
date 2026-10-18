# Traceability Matrix (Phase I)

Tests run with `./run_tests.sh`. Audit routes are wired in `backend/app/main.py`.

| ID | Requirement | Source | Automated tests | Status |
|---|---|---|---|---|
| FR-1.1 | Multi-sport taxonomy as data; mystery sport via JSON; event / innings / round models | `backend/app/sports.py` (`validate_sport`, `create_sport`, `BASELINE_SPORTS`) | `tests/test_api.py::test_mystery_sport_create_duplicate_and_validation`, `::test_mystery_sport_usable_in_events` | Done |
| FR-1.1 | Event-sourced scoring, append-only log, signed compensating events, config-driven limits | `backend/app/scoring.py` (`ScoringEngine.append`, `project`), `backend/app/signing.py` | `tests/test_api.py::test_event_flow_signature_compensation_and_idempotency`, `::test_tie_not_allowed_and_tiebreak_winner`, `::test_innings_and_round_limits`, `tests/test_signing.py` | Done |
| FR-1.2 | League setup scoped to sport, points config, tie-break order, qualification spots | `backend/app/main.py` (`register_league`) | `tests/test_api.py::test_league_registration_and_standings` | Done (single-stage); multi-division/hybrid via fixtures formats |
| FR-1.3 | Fixture generation: round robin (circle method, byes, withdrawals), Swiss (Buchholz, optimal rematch-free pairing), single and double elimination (seeding, byes, bracket reset) | `backend/app/fixtures.py` (`generate`) | `tests/test_fixtures.py` (64 tests) | Done |
| FR-1.3 | Match status state machine, illegal transitions rejected | `backend/app/scoring.py` (`append`: match_start / match_end) | `tests/test_api.py::test_event_flow_signature_compensation_and_idempotency` | Done (upcoming / in_progress / completed) |
| FR-1.4 | Standings: points config, recursive tie-breakers incl. 3-way H2H mini-league, NRR, draw of lots, clinched / eliminated | `backend/app/standings.py` (`compute_standings`) | `tests/test_standings.py` (16 tests), `tests/test_api.py::test_league_registration_and_standings` | Done |
| FR-2.1 | Clubs and white-label tenants, tenant isolation | `backend/app/auth.py` (`TENANTS`, `CLUBS`, `can`), `backend/app/main.py` (`app_club`) | `tests/test_api.py::test_rbac_matrix_every_cell` | Done |
| FR-2.2 | Roster transfers / loans / releases, windows, squad size, positions, loan auto-return, immutable audit trail | `backend/app/roster.py` (`RosterService`) | `tests/test_roster.py` (20 tests) | Done |
| FR-2.3 | Store: variants, discount code, mock gateway (authorize / capture / decline), order events to queue, PDF receipt | `backend/app/store.py` (`Store.checkout`, `render_receipt_pdf`), `backend/app/events_bus.py` | `tests/test_api.py::test_checkout_receipt_signature_pdf_discount_and_replay`, `::test_payment_failures_release_stock_and_errors` | Done |
| FR-5.1 | Five-tier RBAC as policy-as-code with negative tests for every boundary | `backend/app/auth.py` (`can`, `authorize`, `verify_token`) | `tests/test_api.py::test_rbac_matrix_every_cell`, `::test_tampered_none_and_missing_tokens` | Done |
| NFR-3 | Concurrency: 20 buyers on the last unit yield exactly one order, no negative stock | `backend/app/store.py` (lock-guarded reserve / commit / release) | `tests/test_api.py::test_twenty_concurrent_buyers_last_unit` | Done |
| NFR-4 | Offline tolerance: local cache + persistent action queue + sync with conflict resolution | `backend/app/main.py` (`offline_sync`, `_sync_one`); `mobile/src/storage.ts`, `mobile/src/state.tsx` | `tests/test_api.py::test_offline_sync_conflicts_and_replay`, `mobile/tests/domain.test.mjs` | Done |
| NFR-5 | Security: JWT HS256 (alg none / tamper / expiry rejected), rate limit with Retry-After, input validation, 413 body limit, secure token storage on device | `backend/app/auth.py`, `backend/app/main.py` (`guards`, `read_json`), `mobile/src/storage.ts` (expo-secure-store) | `tests/test_api.py::test_tampered_none_and_missing_tokens`, `::test_rate_limit_and_body_limit`, `::test_login_route` | Done |
| NFR-7 | Reproducibility: one command brings up and seeds the backend | `docker-compose.yml`, `backend/Dockerfile`, `backend/app/main.py` (`reset_state` at startup) | `tests/test_api.py::test_reset_contract_and_repeatable` | Done |
# Phase II additions

| Requirement | Source | Verification |
|---|---|---|
| FR-3.1 profiles/follows | `backend/app/day2.py` | Additional integration verification pending |
| FR-3.2 key lifecycle/media | `streaming.py`, `backend/media/`, `mobile/src/live.tsx` | `tests/test_day2.py`; actual-media timing pending |
| FR-3.3 co-stream/handoff | `costream.py`, `day2.py`, `backend/media/compositor.py` | contract tests pass; composed-media handoff pending |
| FR-4.1 dynamic QR/export | `qr_guest.py`, `mobile/src/app/scan.tsx` | contract/export tests and real Grid tests pass; native scan pending |
| FR-4.2 guest web | `backend/app/web/`, `day2.py` | six Grid cases pass |
| FR-4.3 guest boundary | `main.py`, `qr_guest.py` | direct-write rejection tests pass |
| FR-4.4 cart merge | `qr_guest.py` | concurrent replay and stock tests pass |
| FR-5.2 retry/DLQ | `moderation_dlq.py` | failure-simulation contract tests pass; background push incomplete |
| FR-5.3 moderation | `moderation_dlq.py` | exact examples, obfuscation and concurrency tests pass |
| NFR-1 score latency | `day2.py`, `web/guest.js` | Grid DOM updates tested within 500ms; 25-viewer probe pending |
| NFR-2 load | `tests/k6_load.js` | required profile written; full run pending |
| NFR-6 metrics | `observability.py` | contract test passes |
| NFR-8 accessibility | `web/guest.html`, `web/guest.css` | semantic labels, keyboard controls, 48px targets; partial Grid inspection |
| NFR-9 privacy | `qr_guest.py`, `observability.py` | aggregate telemetry only; erasure needs broader verification |
