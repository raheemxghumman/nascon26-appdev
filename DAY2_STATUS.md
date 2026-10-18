# Day 2 progress and takeover notes

Latest source handover: remaining non-APK changes are published on top of Raheem's `9661876`; his release APK is preserved. Read `DAY2_HANDOVER_AUDIT.md`, including its subsequent-source-handover update, for current limitations. The older pending-APK notes below are historical.

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

- Release APK built and installed; three real Appium tests passed (both native deep links plus browser-to-phone chat). Latest APK includes connection retry and foreground notifications.
- Real WHIP publication and WHEP playback passed with Chrome's synthetic 640x360 camera/microphone fixture; real media packets and decoded video verified. Physical phone camera, RTMP, key eviction timing and glass-to-glass latency still need checks.
- FFmpeg composition and abrupt host handoff while actual streams are active.
- Completed real recording segments uploaded to MinIO and indexed; full playback retrieval check pending.
- Recheck the optimized load profile on the independent clean GitHub runner.
- Selenium images use the previously required/cached 4.24.0; Day 2 example shows 4.25.0. Organizer clarification pending.
- Signed co-stream invitations, host control endpoints and foreground WebSocket notifications implemented and tested. UI controls and full background native push still need work.
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

## Push record

- `3e9a651`: foundation, confirmed pushed around 11:10 PKT.
- `d723cb4`: load optimizations and coverage, confirmed pushed around 11:31 PKT.
- Next checkpoint includes the release APK, real media probe, recording storage client and stream readiness fix. Do not count it as pushed until origin confirms.

Latest local checks: 141 backend tests passed before the additional signed invitation/notification test; all 23 Day 2 tests then passed. Six Grid tests passed again. Venue-secret scan passed against tracked source and every unpacked release APK entry.
