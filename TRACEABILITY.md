# Traceability Matrix

| ID | Requirement | Source | Tests | Status |
|---|---|---|---|---|
| FR-1.1 | Multi-sport taxonomy, event-sourced scoring, signed compensations | backend/app/signing.py | tests/test_signing.py | In progress |
| FR-1.2 | League and tournament setup | | | Not started |
| FR-1.3 | Fixture scheduling (RR, Swiss, SE, DE), conflicts, status machine | | | Not started |
| FR-1.4 | Standings, tie-breakers, H2H, qualification | backend/app/signing.py (draw_lots) | tests/test_signing.py::test_draw_lots_vector_2 | In progress |
| FR-2.1 | Club profiles and tenant isolation | | | Not started |
| FR-2.2 | Roster, transfers, loans, audit trail | | | Not started |
| FR-2.3 | Merchandise store, concurrency-safe checkout, PDF receipt | | | Not started |
| FR-5.1 | Five-tier RBAC | | | Not started |
| NFR-3 | Concurrency correctness (no overselling) | | | Not started |
| NFR-4 | Offline tolerance (mobile queue + sync) | | | Not started |
| NFR-5 | Security (JWT, rate limit, validation, 413) | backend/app/main.py, backend/app/errors.py | | In progress |
| NFR-7 | Reproducibility (one-command compose) | docker-compose.yml | | In progress |
