# Day 2 progress and takeover notes

Continue from locked Day 1 commit `ef195aa`. No history was rewritten.

## Verified at the first checkpoint

- 140 backend tests passed, including the Day 1 suite and new Day 2 contract/security/concurrency tests.
- Six real Selenium tests passed across Chrome and Firefox using the three-node Grid.
- Database, Redis, MinIO, MediaMTX, API and Selenium Hub reported healthy locally.
- Mobile TypeScript, lint and six mobile queue/data tests passed.
- Required 550-VU/15-second k6 profile passed on the direct Docker network: 0 failed requests, all checks passed, 622.71ms p95. Windows forwarding runs previously failed; their report is retained separately.
- 25-client WebSocket score probe passed locally at 78ms p95.
- Measured coverage exceeds 85% in all five Phase II modules (see COVERAGE_DAY2.json).
- Both venue salts are stored only in ignored local `.env`; never copy that file into Git.

## Implementation

- Day 2 signed stream keys, revocation guard and MediaMTX publisher eviction.
- Ordered co-stream handoff, idempotent creation and socket disconnect handling.
- Dynamic QR routes, real SVG/PNG/PDF exports and aggregate-only scan counters.
- Guest web page, native deep-link routes, QR scanner and WebView camera broadcast surface.
- Server guest-write guard and transactional/idempotent guest cart merges.
- Durable SQLite moderation decisions, deduplicated kick/mute sets, retries and dead-letter records.
- WebSocket score/chat delivery, metrics, privacy endpoint, required k6 profile and CI workflow.

## Still needs verification/work

- New release APK build, installation, real deep-link Appium run and cross-surface report.
- Real camera/RTMP publish and playback, key eviction timing and glass-to-glass latency.
- FFmpeg composition and abrupt host handoff while actual streams are active.
- Upload completed real recording segments to MinIO and verify indexed playback.
- Recheck the optimized load profile on the independent clean GitHub runner.
- Selenium images use the previously required/cached 4.24.0; Day 2 example shows 4.25.0. Organizer clarification pending.
- Full background native push, signed co-stream invitations and host media controls are not complete.
- Day 1 state remains in memory. Day 2 records persist in `/data/day2.sqlite3`.

## Local commands

Activate tools: `. E:\NASCON-Preparation\Start-Environment.ps1`

Run stack: `docker compose --project-name nascon-local-demo up -d --build`

Phone USB: `adb reverse tcp:8080 tcp:8080`; repeat for 8889 and 8189 for media testing.

Guest page: http://localhost:8080/q/m1-live

Unit/contracts: `python -m pytest tests/test_*.py`

Grid: `python -m pytest -n 3 tests/selenium/ --junitxml=tests/reports/selenium-report.xml`

Appium: `python -m pytest tests/appium/ --junitxml=tests/reports/appium-report.xml`

Build log: `E:\NASCON-Preparation\logs\day2-android-build-retry.log`.
