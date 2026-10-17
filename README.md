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

## Mobile

React Native (Android). Source in `mobile/`, release build at `mobile/release/app-release.apk`.
