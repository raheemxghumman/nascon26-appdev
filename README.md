# NaSCon'26 League & Club Operations Platform

Multi-tenant sports league, fixture scheduling, roster and merchandise platform (Phase I).

## Run the backend

```sh
DAY1_SALT=<team-salt> docker compose up -d --build
curl http://localhost:8080/health      # {"status":"ok"}
```

The API listens on host port **8080**. `DAY1_SALT` is read from the environment only; see `.env.example`.

## Tests

```sh
./run_tests.sh
```

## Demo accounts

Created on every startup and every `POST /audit/v1/reset`.

| Role | Email | Password |
|---|---|---|
| Platform Super-Admin | admin@nascon.test | Nascon@26 |
| League Organizer (owns league-alpha-1) | organizer@nascon.test | Nascon@26 |
| Club Manager (owns club-alpha-1) | manager@nascon.test | Nascon@26 |
| Player (player-alpha-1) | player@nascon.test | Nascon@26 |
| General Viewer | viewer@nascon.test | Nascon@26 |

## Architecture

| Service | Purpose |
|---|---|
| `api` | FastAPI app on :8080: audit contract (`/audit/v1/*`), mobile routes (`/api/v1/*`), SSE live scores |
| `worker` | Consumes the internal `domain-events` Redis Stream (order status changes, match events) |
| `postgres` | Database (readiness probe) |
| `redis` | Cache and internal event queue (Redis Streams) |

Design decisions are in `ADR.md`; requirement-to-code-to-test mapping is in `TRACEABILITY.md`.

## Mobile app

React Native (Expo SDK 55), Android. Source in `mobile/`; release build at `mobile/release/app-release.apk`.

1. Install: `adb install -r mobile/release/app-release.apk` (Android 10+).
2. Point the app at the backend in **Settings**:
   - emulator: `http://10.0.2.2:8080` (default)
   - phone over USB: run `adb reverse tcp:8080 tcp:8080`, then use `http://localhost:8080`
   - phone on the team hotspot: `http://<laptop LAN IP>:8080`
3. Log in with one of the demo accounts above.

Build from source: `cd mobile && npm install && npx expo prebuild --platform android && cd android && ./gradlew assembleRelease`.
