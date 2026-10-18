# LeagueDesk Day 2 — Technical Audit and Handover for Abdul Raheem

## Subsequent source handover

This update supersedes the pending-push details in the original 13:15 audit below:

- The remaining non-APK changes in this commit form one source-only handover on top of Raheem's `9661876`, preserving his settings fixes and his release APK byte for byte. Do not merge the earlier local APK integration history or `codex/apk-transfer` into submission `main`.
- Included: FFmpeg image/Python startup fix; authenticated co-stream creation/state routes; recording-list/VOD links; co-stream invitation and host control screens; H264 preference and labelled camera-only fallback; invitation/notification erasure; Appium idle-wait correction; updated tests/reports and coverage.
- The new FFmpeg container built successfully and reports healthy. This establishes runtime startup, not successful composed-media playback or handoff.
- Web JavaScript syntax checks pass; the final source-handover backend run passed all 142 tests in 29.71 seconds, including authenticated session creation/state and invitation/notification erasure. All five measured modules remain above 85%. Appium, Grid and media evidence below retain their individual scope and timestamps; full physical-camera/composite/background-push gaps remain open.
- There are no new native source edits in this handover. Raheem should build the final APK from the resulting remote `main` and run the final device checks there. Web assets require rebuilding/restarting the API service.

## Checkpoint and overall status

Prepared on **18 October 2026, approximately 13:15 PKT**, from `E:\NASCON App Dev`. This is a checkpoint audit, not a claim that every Day 2 requirement is finished.

The Day 1 base `ef195aa` remains in ancestry. No history was force-pushed or rewritten. Day 2 backend contracts, guest web flows, QR generation, moderation, mobile deep links and real solo WebRTC media have working implementations and local evidence. The biggest unfinished area is **real composed co-stream media and its failure/handoff behaviour**, followed by physical-phone media validation and background push.

At document preparation:

- Remote `main` was last independently fetched as **`0391da2`**, containing the Day 2 source checkpoint and Raheem's three fixes described below.
- Local integrated `main` was **`f0fb308`**, containing the new Day 2 release APK and both Raheem commits. Upload of this integrated history was still running; do not infer success from a local commit or from a failed push printing `Everything up-to-date`.
- The complete APK blob was uploaded successfully on temporary branch `codex/apk-transfer`; integration into `main` still requires a confirmed successful push.
- Further local changes are listed under “Current uncommitted work.” They are not included in the confirmed remote checkpoint until committed and pushed.
- A new native build incorporating Raheem's navigation fixes **completed successfully at this checkpoint** (`day2-android-integrated.log`, 3m26s). Its generated APK has not yet been promoted to `mobile/release/app-release.apk` or installed. The existing release file was built **before** those fixes.
- Raheem's newest settings-help commit `0391da2` was fetched just before this audit was delivered, but is **not yet merged into local `f0fb308` or the integrated build**. Merge it before the final APK build.

Always run `git fetch origin main` and inspect `git status` before integrating concurrent work. Raheem is actively pushing to the same branch.

## Push history and integration with Raheem

The times below are **local Git commit timestamps**, not independently recorded GitHub acceptance timestamps. Earlier chat estimates for the second push were approximate; the actual `d723cb4` commit time is 11:35 PKT.

| Commit | PKT commit time | Contents / confirmed state |
|---|---|---|
| `ef195aa` | 17 Oct 14:26 | Locked Day 1 release base; preserved |
| `3e9a651` | 18 Oct 11:10 | Day 2 foundation, signed contracts, guest UI, QR, QA; push confirmed |
| `d723cb4` | 11:35 | Load optimizations, persistent moderation records, coverage; push confirmed |
| `4c278fb` | 12:40 | New native APK, media probe, S3 storage client, stream readiness fix; initial large push timed out |
| `2795173` | 12:52 | Same source/test checkpoint with the previous APK retained so the code could reach GitHub immediately; push confirmed |
| `adf2a74` | 12:53 | Joins the source-only checkpoint and APK commit histories locally |
| `60ccc69` | 13:01 | Raheem: `run_tests.sh` runs unit/contract suites; Grid/Appium remain separate |
| `bbe3017` | 13:06 | Raheem: explicit `/login`, fixes sign-out redirect loop, distinct tab icons/larger targets |
| `4193a20`, `f0fb308` | 13:06 | Local merges preserving Raheem's commits and the APK history |
| `0391da2` | Fetched at audit delivery | Raheem: clearer connection settings, ID examples, USB hint and guard against credentials entered in ID fields; newly fetched, not yet locally integrated |

The required first two push windows each had a confirmed push. `2795173` is in the third window. **The delayed APK checkpoint did not mean the second required window was missed.** A fourth-window push is still required according to the venue schedule; coding ends at 14:00 and final push cutoff is 14:05. Reconfirm against organizer instructions if changed.

The APK upload hit repeated HTTP 408, connection reset and occasional DNS failures. Small source pushes worked. A temporary prefix-transfer branch uploaded the APK in 4 MiB increments. Its final file is `app-release.apk.part`, containing the full APK bytes; this branch is a transport workaround, not the submission branch. Clean up that branch only after `main` and the delivered APK are verified.

## Verified evidence and limits

| Area | Latest local result | Evidence / practical limit |
|---|---|---|
| Backend | **142 passed**, 0 failures, 28.64 s | `tests/reports/backend-report.xml`; Day 1 regression plus Day 2 contracts. Run preceded the last camera-fallback JS edit and final media image change. |
| Chrome + Firefox Grid | **6 passed**, 110.28 s | `tests/reports/selenium-report.xml`; real Grid, not mocked browsers. Run preceded the newly added co-stream controls UI. |
| Physical Android / Appium | **3 passed**, 42.30 s | `tests/reports/appium-report.xml`; both deep links and browser/native chat. Camera/QR scanning are not part of these three tests. |
| Required k6 profile | **500 guest + 50 chat VUs**, 15 s; **622.71 ms p95**, 0 failed HTTP requests | `tests/reports/k6-summary.json`; 22,718 HTTP requests and 43,996 successful checks. Used direct Docker network `http://api:8080`. |
| 25-viewer score delivery | **78 ms p95** | `tests/latency_probe.py` and retained report; real WebSockets. |
| Real solo WebRTC | **Passed**, decoded 640×360 video, peer connected, video readyState 4 | `tests/media_probe.py`, `tests/reports/media-probe.json`; Chrome's explicitly synthetic camera/mic fixture produced actual WHIP/WHEP media packets. |
| Recording + MinIO | Actual completed media segments uploaded, indexed and retrieved | Three segment retrievals returned 19,470, 16,438 and 2,013 bytes. This verifies storage retrieval, not a complete browser VOD playback workflow. |
| Release build/install | ARM64 release APK built and ADB install succeeded | Current release file is 63,735,444 bytes; subsequent integrated build is pending. |
| Mobile static/queue checks | TypeScript, Expo lint and six mobile queue/data tests passed at earlier checkpoints | Re-run after the latest Raheem navigation changes; integrated build job includes typecheck/lint. |
| Secret scan | Passed against tracked source and every uncompressed APK ZIP entry | Both real venue salts checked without printing their values. Repeat after replacing the final APK. |

Latest measured line coverage (`COVERAGE_DAY2.json`, generated from `tests/reports/coverage.json`):

| Required module | Coverage |
|---|---:|
| `streaming` | 95.65% |
| `costream` | 100.00% |
| `qr_guest` | 91.97% |
| `moderation_dlq` | 92.52% |
| `observability` | 100.00% |

All five exceed 85%. Coverage is unit/contract coverage; it does not establish FFmpeg composition, physical camera success or background push.

Important interpretation details:

- `media-probe.json` video `time: 0.434` is the player's current playback position, **not measured glass-to-glass latency**.
- Earlier Windows-forwarded k6 attempts failed with EOF/high latency. Their evidence is retained separately; the passing run used the actual required load over Docker networking. A clean GitHub runner recheck is still needed.
- One latest-APK Appium attempt failed chat timing at 3.16 s because WebDriver/UiAutomator idle waiting was included. The test now disables the automatic UI idle wait and keeps the original 3-second threshold; the following full run passed all three tests.
- The first inspected cloud CI run passed backend tests/build/Grid and failed its then-current k6 step. No complete successful CI run for the final code has been independently confirmed.

## Implemented backend and infrastructure

### Contracts, data and Day 1 compatibility

- `backend/app/day2.py` installs Phase II alongside the existing FastAPI application and retains the Day 1 reset/regression contract.
- `day2_db.py` implements persistent records in SQLite, transactions with `BEGIN IMMEDIATE`, a lock, WAL and `synchronous=NORMAL`. Container path is `/data/day2.sqlite3`, backed by `day2-data`.
- **Day 1 scoring/store/roster state remains in process memory.** PostgreSQL is running but is not the source of truth for those existing services. This is a material limitation, not completed PostgreSQL migration.
- Seed data includes live `match-m1` (Alpha United vs Alpha Rovers, 1–0), QR short code `m1-live`, players/clubs and deterministic audit scenarios.
- Pure ASGI request guards enforce body-size/rate limits and block guest writes while preserving audit routes. This replaced slower `BaseHTTPMiddleware` processing during load tuning.

### Streaming keys and real media

- `streaming.py`: generate/rotate/revoke, deterministic test override, schema/ownership validation, canonical HMAC signatures using `DAY2_SALT`, persistent creator/key state.
- `/internal/media/auth` lets MediaMTX enforce valid active paths; old keys are denied. Rotation/revoke invokes MediaMTX APIs to kick matching RTMP/WHIP publishers.
- `/api/v1/creator/key` authorizes the actual player or super-admin; `/api/v1/media/whip/{path}` proxies authenticated SDP to MediaMTX.
- Same-origin `/media/read/{path}` proxies WHEP/player requests and rewrites session locations, so browser Grid and USB phone do not depend on the wrong localhost hostname.
- `/api/v1/live/{entity}` now requires an actual MediaMTX **ready** path. It no longer equates an issued key with a live broadcast. Missing/ended media clears the iframe and shows “Waiting for the broadcast.”
- MediaMTX supports RTMP, HLS and WebRTC, with local ICE TCP/UDP port 8189. HLS is configured for low latency; the creator now prefers H264, but that last codec preference still needs a real HLS playback check.

### Co-streams, host controls and invitations

- `costream.py`: maximum four participants, layout validation/capacity, deterministic first-remaining-player host handoff, session replay/idempotency and termination after the last participant leaves.
- Authenticated host WebSocket triggers participant removal/handoff on disconnect. Real-media handoff timing has not yet been measured.
- `/api/v1/costream/{sid}/control`: host/admin invite, mute, unmute, kick and spotlight. Signed, expiring invitations bind session and player; `/join` checks signature, owner, expiry and capacity. Unit integration test includes live notification delivery.
- Latest local endpoints expose authenticated session creation and readable session state. These extra routes are newer than the confirmed source checkpoint.
- `backend/media/compositor.py` supervises actual FFmpeg processes: reads ready RTSP inputs, scales/pads/xstacks, mixes/mutes audio, publishes H264/AAC RTMP composite, restarts when inputs/control state change and reaps stopped jobs.
- The compositor was implemented but **not yet verified producing a real composite**. Do not demo an empty co-stream as completed media functionality.

### Recordings and object storage

- MediaMTX records real fMP4 segments under `/recordings`; completion hook posts to the API.
- API resolves recording paths and restricts access to files within `/recordings` before indexing/uploading.
- `object_storage.py` uses real AWS Signature V4 requests through existing `httpx` to the MinIO service. No MinIO SDK download is needed. It performs actual upload/download and has been exercised against real MinIO.
- `/api/v1/vod/{name}` retrieves indexed recordings. Latest local `/api/v1/recordings/{entity}` lists them and the web page links to recordings.
- Match-to-broadcast association is still broad: match live lookup can choose any active creator, and general match recording lists currently include the available recording set. Player/co-stream filtering is more specific. Tighten association if the evaluation checks concurrent unrelated matches.

### QR, guest mode and commerce

- `qr_guest.py`: stable QR/short-code identity with state-dependent match routes; real SVG/PNG/PDF export; match status supports postponed/cancelled/abandoned notices as well as live/completed.
- Scan telemetry stores aggregates by hour/device category, without raw IP/user-agent retention.
- Guest pages allow viewing and local cart staging. Protected chat/checkout opens progressive login rather than blocking initial entry.
- Server guards reject guest write attempts. Cart merge is transaction/stock protected, combines duplicate variant quantities and is replay-safe under concurrency.
- Audit guest-token handling is permissive for deterministic scenarios; stricter existence/expiry behaviour on normal member-merge calls should be reviewed before claiming production session hardening.

### Moderation, notifications, metrics and privacy

- `moderation_dlq.py`: obfuscation normalization, exact profanity replacement, punctuation/zero-width handling, flood/repetition/rate detection, kick/mute sets, deduplicated message IDs and ordered sequences.
- Decisions/messages are stored separately instead of rewriting the entire chat history. This was necessary for the 550-user load target.
- Real delivery helper retries three times with backoff, persists failed deliveries in the DLQ, and audit failure simulation calls the same retry path.
- Durable notification sink persists events before best-effort Redis publication. Authenticated `/ws/notifications` supports a cursor, per-user delivered state, recipient filtering, retry/DLQ and erasure checks.
- Mobile currently shows a **foreground in-app notification banner**. This is not Android background/OS push delivery.
- Metrics derive active streams/bytes from MediaMTX, expose active sockets, estimated current bitrate, DLQ depth and scan counts.
- Erasure clears linked guest/cart/chat records and invalidates JWT use through an erased-account tombstone. Latest local additions delete invitations, targeted notifications and delivered markers too; these newest branches need broader negative/security verification.

## Mobile APK and guest interface

### Implemented native work

- Expo 55 / React Native 0.83, Expo Router routes, camera permissions via config/plugin, `expo-camera` and `react-native-webview`.
- `+native-intent.tsx` maps `nascon://entity/...` and `nascon://stream/...` safely to native routes.
- Native match/co-stream surfaces include live score/chat subscriptions, guest WebView and explicit retry UI for server connection failure.
- QR scanner uses actual `CameraView`, supports nascon links and short QR links resolving against the configured backend. Physical scan has not been tested.
- Creator route requests native camera/mic permissions and hosts browser WHIP publication in the WebView.
- Native header/navigation exposes Watch live, Scan QR and Broadcast. In-app notification banner can open match/co-stream context.
- Raheem's `bbe3017` adds an explicit `/login` route, resolves sign-out redirects and improves tab icons/targets. Those edits are merged locally and must be included in the next release APK.

### Build and physical phone findings

- Full initial release build succeeded; subsequent incremental release builds take approximately 3–4 minutes when toolchain caches are warm.
- `mobile/scripts/fix-gradle-toolchain.cjs` is a repeatable postinstall fix: removes stale WebView AGP/Kotlin dependency declarations so Expo's root toolchain is used, and retains the existing Foojay workaround. Do not edit generated `mobile/android` files by hand.
- Phone is Roman's Samsung SM-A055F, USB ID `R9VX1002J9F`; package `com.nascon26.leaguedesk`.
- Deep-link cold launch was measured at about 0.6–1.1 s in ADB runs, within the 2-second target. Appium asserts the documented ADB launch timing and visible native route.
- USB reconnect lost ADB reverse mappings, causing `net::ERR_CONNECTION_REFUSED` / WebView error -6. Restoring mappings and reopening the app resolved that connectivity failure.
- A separate “stream not found” issue came from displaying a key without an active publisher; this is fixed in live lookup/UI.
- The first physical creator test signed in successfully but `getUserMedia` failed with **“Could not start audio source.”** Android camera and microphone permissions are both granted. This is not yet a passing phone-camera broadcast.
- Latest server JS falls back to camera-only for `NotReadableError` / `AbortError` and explicitly tells the user the microphone is unavailable. That fallback still needs a fresh phone run.
- Co-stream invitation/moderation UI and recording links are web assets, so those updates do not require rebuilding native code; the API container must be rebuilt/restarted to serve them.

## Current uncommitted work

At this audit's checkpoint, `git status --short` listed:

- `backend/Dockerfile.media`: switch from large Debian apt installation to official `bluenviron/mediamtx:1.9.1-ffmpeg` + Alpine Python. A `python` symlink is required because hooks, entrypoint and healthcheck call `python`.
- `backend/app/day2.py`: co-stream create/read routes, recording listing and allowing the new JS asset.
- `backend/app/observability.py`: erase invitations/targeted notifications/delivery state.
- `backend/app/web/creator.js`: H264 preference and labelled camera-only fallback.
- `backend/app/web/guest.html`, `guest.js`, new `costream.js`: co-stream studio controls, recording links and VOD display handling.
- `tests/appium/test_mobile_deeplink.py`: disable UiAutomator automatic idle waiting without relaxing the timing threshold.
- Updated backend/Appium/coverage reports and `COVERAGE_DAY2.json`.
- This handover document.

Inspect the actual current status before committing; this list will age as work continues. Do not blindly reset, checkout or clean the working tree while either teammate has changes.

## Outstanding work and risks

| Priority | Gap | What completion requires |
|---|---|---|
| P0 | Integrated APK push not yet confirmed | Successful push plus independent `git ls-remote`/fetch matching local HEAD; verify APK hash on remote revision. |
| P0 | Release APK predates Raheem's last navigation changes | Integrated build succeeded; copy generated APK to release, install, smoke sign-in/sign-out/deep links; rescan salts; push replacement. |
| P0 | Real FFmpeg composite | Ensure rebuilt media is healthy; publish multiple real inputs; decode composite; inspect FFmpeg errors; exercise layouts/audio/spotlight. |
| P0 | Actual handoff during live media | Disconnect active host and measure audience interruption/remaining host promotion; ensure no orphan FFmpeg processes. Contract handoff alone is insufficient. |
| P1 | Phone camera/mic | Retest labelled fallback; verify actual phone camera frames reach a second viewer; investigate microphone error rather than claiming audio success. |
| P1 | Native QR scan | Scan a real exported QR on the physical phone; verify entity resolution and route state. |
| P1 | Background push | Foreground WS banner exists. OS/background push does not; credentials/platform delivery integration and device proof are missing. |
| P1 | New controls/VOD UI | Exercise authenticated create, invite, accept, mute/unmute, spotlight/remove and actual browser recording playback. JS syntax checks alone are insufficient. |
| P1 | RTMP / HLS / timing | Real RTMP publish, H264 HLS playback, key eviction under load, measured glass-to-glass timing and true broadcaster fan-out remain unverified. |
| P1 | Final CI | Confirm the optimized k6 and final media build on a clean GitHub runner; local success is not cloud evidence. |
| P2 | Profiles and isolation | Backend profile/follow routes exist, but player/club native UI and complete match ownership/filtering need broader verification. |
| P2 | Persistence/security | Day 1 remains memory-backed; review guest-session enforcement and the externally reachable internal routes before claiming production hardening. |

Known environment risks: laptop RAM is limited; simultaneous Grid, Android build and large Docker builds previously caused the Docker VM to lose connectivity. Keep major builds sequential where practical. The current hotspot is the only available network; do not spend time asking for another Wi-Fi. Use cached dependencies and bounded/resumable transfers.

Grid uses the cached Day 1-required Selenium **4.24.0**. The Day 2 example showed 4.25.0; organizer clarification was not obtained. Do not silently claim that version discrepancy is resolved.

## Local environment and safe startup

| Item | Location / value |
|---|---|
| Repo | `E:\NASCON App Dev` |
| QA Python | `E:\NASCON-Preparation\tools\qa-venv\Scripts\python.exe` |
| Tool activation | `E:\NASCON-Preparation\Start-Environment.ps1` |
| Docker CLI | `E:\NASCON-Preparation\tools\Docker\resources\bin\docker.exe` |
| ADB | `D:\Android\Sdk\platform-tools\adb.exe` |
| JDK | `C:\Program Files\Java\jdk-21` |
| Gradle cache | `E:\NASCON-Preparation\caches\gradle` |
| Logs | `E:\NASCON-Preparation\logs` |
| Docker Compose project | `nascon-local-demo` |
| Appium | `http://127.0.0.1:4723`, UiAutomator2 installed |
| API / guest web | `http://localhost:8080` |
| Grid | `http://localhost:4444`, 2 Chrome nodes + 1 Firefox node |
| Media | RTMP 1935, HLS 8888, WebRTC 8889, ICE 8189 TCP/UDP |

Guest match URL: `http://localhost:8080/q/m1-live`. Native links: `nascon://entity/match-m1`, `nascon://stream/cs-session-101`. Creator native route: `leaguedesk://broadcast`.

On the phone, `localhost` refers to the phone unless these USB mappings are present. Repeat after any reconnect:

```powershell
. E:\NASCON-Preparation\Start-Environment.ps1
adb -s R9VX1002J9F reverse tcp:8080 tcp:8080
adb -s R9VX1002J9F reverse tcp:8888 tcp:8888
adb -s R9VX1002J9F reverse tcp:8889 tcp:8889
adb -s R9VX1002J9F reverse tcp:8189 tcp:8189
adb -s R9VX1002J9F reverse --list
```

Keep the phone unlocked for Appium. Do not reset or clear the app to fix a transport issue; preserve queue/session data. A JWT from the previous laptop/backend may be invalid on this one, requiring a fresh sign-in.

Start/check services:

```powershell
docker compose -p nascon-local-demo up -d --build
docker compose -p nascon-local-demo ps
Invoke-RestMethod http://localhost:8080/health
Invoke-RestMethod http://localhost:8080/api/v1/live/match-m1
```

An empty live path is correct when nobody is publishing. Health checks establish service reachability, not complete media functionality. Avoid `/audit/v1/reset` during another teammate's live demo: it deliberately clears/reset state.

## Reproduction and validation commands

Activate tools first. Commands below are for PowerShell; Linux shell wildcards behave differently.

```powershell
# Backend, including coverage
$env:PYTHONPATH = 'backend'
$testPaths = @(Get-ChildItem tests -Filter 'test_*.py' | ForEach-Object FullName)
python -m pytest @testPaths -q --junitxml=tests/reports/backend-report.xml --cov=backend/app --cov-report=json:tests/reports/coverage.json

# Real browser Grid
python -m pytest -n 3 tests/selenium/ --junitxml=tests/reports/selenium-report.xml

# Physical phone
$env:ANDROID_UDID = 'R9VX1002J9F'
python -m pytest tests/appium/ --junitxml=tests/reports/appium-report.xml

# Real solo WebRTC probe (explicit synthetic camera fixture)
python tests/media_probe.py

# Score delivery
python tests/latency_probe.py

# Native validation / build, from mobile/
npm run typecheck
npm run lint
npm test
Set-Location android
.\gradlew.bat assembleRelease --no-daemon --max-workers=2 '-PreactNativeArchitectures=arm64-v8a' '-Djava.net.preferIPv4Stack=true'
```

Use the existing `tests/k6_load.js` with its complete 550-VU configuration; do not reduce load to obtain a pass. For the passing local setup, k6 runs on the Compose Docker network with `BASE_URL=http://api:8080`; a Windows host-forwarded run is a different network path. See workflow for the clean-runner command.

Useful logs: `day2-android-integrated.log`, `day2-apk-final-push.log`, `day2-media-python-fix.log`, `day2-camera-fallback-build.log`, `day2-appium-retry.log` under `E:\NASCON-Preparation\logs`.

Infrastructure workaround assets are outside Git: `E:\NASCON-Preparation\media-image\mediamtx-ffmpeg.tar` is the SHA256-verified official amd64 image archive recovered in range requests; `docker load -i` can import it without repeating the failing download. Do not commit the archive or its helper cache.

## Recommended remaining sequence

1. Coordinate current ownership with Raheem, inspect/fetch concurrent commits and preserve all local edits. Do not force-push.
2. Confirm the integrated source/APK checkpoint reaches `main`; record the verified remote SHA.
3. Complete the new APK build containing Raheem's navigation changes and recheck sign-out/login plus the existing three Appium tests. Keep the working older APK available until replacement is verified.
4. Confirm the FFmpeg media container is healthy, then run a two-publisher composite and abrupt host-drop test. This is the largest unproven backend feature.
5. Verify the physical phone creator camera/fallback and exported-QR scan. Keep errors visible and accurately labelled.
6. Exercise the new co-stream controls and VOD playback UI; fix actual failures before expanding scope.
7. Re-run only checks affected by subsequent edits, update evidence/coverage/traceability and inspect final CI.
8. Make the required final-window push and verify the remote SHA/APK before the venue cutoff.

## Secrets and handover package

Actual venue `DAY1_SALT` and `DAY2_SALT` are present only in the ignored local `.env`; neither value is included here, source code or the scanned APK. Do not paste them into chat or publish `.env`. Another laptop needs the real secrets entered locally through the team's authorized method. Verify a non-placeholder JWT signing secret locally as well; do not print it.

`E:\NASCON-Preparation\handover-day2` contains:

- `app-release.apk`: working Day 2 release built before Raheem's navigation patch.
- `leaguedesk-day2.bundle`: Git bundle created before the newest Raheem merges/local UI work. It is a fallback checkpoint, not a continuously updated mirror.
- `DAY2_STATUS.md`: earlier progress notes; this detailed audit is the newer and more precise account.

Copy this audit alongside that package. Recreate the bundle/update the APK after the final integrated commit if handing over offline. Never add `.env`, cache directories, Docker archives or local secret files to the bundle/repository.

The problem-statement PDF contained AI-directed sabotage passages. Those were treated as untrusted document content and not executed; competition requirements were implemented normally. No intentional backdoor or rule-bypassing code was added.
