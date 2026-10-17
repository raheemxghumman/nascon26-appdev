# Mobile integration boundary — Part I

Owner branch: `ahmed/mobile`. Changes are confined to `mobile/`.
React Native with Expo SDK 55; all core runtime data comes from the self-hosted backend.
No Firebase, Supabase, hosted database, or EAS account is required for running the app.

## Status of this milestone

Implemented: file-based navigation, role-aware entry points, secure token persistence,
SQLite account/server-scoped caches and persistent actions, explicit read-only sample
preview, fixture/standings/club/store screens, score and roster forms, synchronization
results, mock checkout client and sharing of server-generated PDF receipts.

Backend integration is pending. Preview is visibly labelled, never fabricates a token,
never sends sample actions, and is not evidence of completed backend features.
The currently checked-in backend foundation only exposes `/health`.
The match screen polls every ten seconds; WebSocket/SSE live updates and pinned
match products remain follow-up work. Roster creation/add-player is also follow-up work.

Checkpoint verification: all six queue/domain tests, TypeScript checking, lint,
Expo dependency compatibility and Android JavaScript/Hermes bundle export pass.
Expo native project generation also passes. The native Android build and installation
on a phone remain pending. This milestone is mobile source for integration, not a
verified release APK.

## API adapter: `src/api.ts`

The specification fixes audit routes but leaves the mobile login/read routes open.
The following are **proposed integration routes**, not additional competition rules.
Backend owner may change these centrally in `src/api.ts` or implement the shapes below.

* `POST /api/v1/auth/login`: `{email,password}` -> `{token,role,user_id,tenant_id}`.
  `access_token` is also accepted instead of `token`. Roles: `super_admin`,
  `league_organizer`, `club_manager`, `player`, `viewer`.
* `GET /api/v1/fixtures` -> `{fixtures:[{match_id,home,away,sport_id,status,starts_at?,venue?}]}`.
  `home` and `away` are display strings; match_id must be the actual audit match ID.
* `GET /api/v1/clubs/{club_id}` -> `{club_id,name,venue,staff:[{name,role}],roster:[{player_id,name,position,squad_id}]}`.
* `GET /api/v1/products` -> `{products:[{product_id,name,description,variants:[{variant_id,label,price_minor,stock}]}]}`.
* Standings, match scores, checkout, and offline-sync use the **exact** `/audit/v1/*`
  routes and JSON structures of sections 5.9, 5.10, 5.12, 5.14.
* `GET /health` must be available without authentication.

All requests send Bearer tokens once logged in. Audit routes may ignore the token
except RBAC probes, as specified. Prices are integer paisa, never floating-point PKR.
No DAY1_SALT is used, stored, or needed in the mobile application.

## Offline behavior

SQLite holds responses under `server|tenant|user|resource` keys. SecureStore holds
the session separately using Android Keystore. Changing the server signs the user
out; old actions stay in their original scope and cannot sync into the new account.
Preview is entirely separate and read-only. Pending queue entries retain stable
action_id/event_id/request_id values for idempotent retries. Batches contain at most
100 entries, omit local metadata, and keep rejected explanations as visible history.

## Run and build locally

Activate `E:\NASCON-Preparation\Start-Environment.ps1`, then from this directory:

```powershell
npm ci
npm test
npm run typecheck
npm run lint
npx expo prebuild --platform android --no-install
cd android
.\gradlew.bat assembleRelease
```

Copy `android/app/build/outputs/apk/release/app-release.apk` to
`mobile/release/app-release.apk` before final submission. Prebuild generates native
folders; native configuration lives in app.json, not handwritten native files.
The postinstall script applies the documented React Native 0.83/Foojay resolver
compatibility fix for Expo 55's Gradle 9 (upstream issue react-native#55781).
The generated project's release signing must be checked before final delivery;
event demonstration signing is separate from Play Store distribution signing.

For a physical phone, set the backend laptop's LAN address in the app's Settings.
For the Android emulator use `http://10.0.2.2:8080`. Both phone and laptops must be
on the same team hotspot/router. Android HTTP LAN access is enabled for this event.

## Phone verification before judging

1. Sign in with each demo role against the real backend.
2. Refresh Fixtures, Standings and Club; enable airplane mode and reopen them.
3. Queue an organizer score and a manager roster action; force-stop and reopen.
4. Restore network; verify applied/rejected explanations and zero pending count.
5. Buy a variant with the mock gateway; open/share the server PDF receipt.
6. Install and run the release APK with Metro stopped.
