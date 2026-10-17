import json
import threading

import psycopg
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from . import auth, config, events_bus
from .common import TS_RE, is_id, is_int
from .errors import APIError, api_error_handler, error_response, request_validation_handler, validation_error
from .fixtures import generate as generate_fixtures
from .roster import RosterService
from .scoring import ScoringEngine
from .sports import BASELINE_SPORTS, TIE_BREAKS, create_sport, resolve_tie_breaks
from .standings import compute_standings
from .store import Store

app = FastAPI(title="NaSCon'26 League & Club Operations Platform")
app.add_exception_handler(APIError, api_error_handler)
app.add_exception_handler(RequestValidationError, request_validation_handler)

LOCK = threading.RLock()          # serialises every domain mutation (single writer)
SPORTS: dict = {}
LEAGUES: dict = {}
ENGINE = ScoringEngine(SPORTS)
ROSTER = RosterService()
STORE = Store(publish=events_bus.publish)
LIMITER = auth.RateLimiter()
STATE = {"seed": 42, "seeded": False, "synced": set()}

DEMO_TEAMS = {"club-alpha-1": "Alpha United", "club-alpha-2": "Alpha Rovers",
              "club-alpha-3": "Alpha City", "club-alpha-4": "Alpha Athletic"}


def reset_state(body: dict) -> dict:
    seed = body.get("seed", 42)
    stock = body.get("stock", {})
    if not is_int(seed) or not isinstance(stock, dict) or not all(
            isinstance(k, str) and is_int(v) and v >= 0 for k, v in stock.items()):
        raise validation_error(["seed" if not is_int(seed) else "stock"])
    with LOCK:
        SPORTS.clear()
        for s in BASELINE_SPORTS:
            SPORTS[s["sport_id"]] = json.loads(json.dumps(s))
        LEAGUES.clear()
        ENGINE.matches.clear()
        ENGINE.events.clear()
        ROSTER.reset()
        STORE.reset(stock)
        STATE["seed"] = seed
        STATE["synced"] = set()
        _seed_demo_league()
        STATE["seeded"] = True
        current = {"var-jersey-001-M": STORE.stock["var-jersey-001-M"],
                   "var-jersey-001-L": STORE.stock["var-jersey-001-L"]}
        current.update({k: STORE.stock[k] for k in stock})
    return {"status": "reset_complete", "seed": seed, "sports": [s["sport_id"] for s in BASELINE_SPORTS],
            "tenants": list(auth.TENANTS), "stock": current}


def _seed_demo_league():
    """Demo fixtures for league-alpha-1 so the mobile app has data to show."""
    teams = list(DEMO_TEAMS)
    fixtures = [{"match_id": f"alpha-m{i + 1}", "home": h, "away": a}
                for i, (h, a) in enumerate([(teams[0], teams[1]), (teams[2], teams[3]),
                                            (teams[0], teams[2]), (teams[1], teams[3])])]
    register_league({"league_id": "league-alpha-1", "sport_id": "football", "teams": teams,
                     "fixtures": fixtures, "qualification": {"spots": 2}})
    for eid, (t, team) in enumerate([("match_start", None), ("score", teams[0]), ("score", teams[0]),
                                     ("score", teams[1]), ("match_end", None)], 1):
        payload = {} if team is None else {"team_id": team, "event_type": "goal"}
        ENGINE.append({"event_id": f"alpha-e{eid}", "match_id": "alpha-m1", "type": t, "payload": payload})
    ENGINE.append({"event_id": "alpha-e6", "match_id": "alpha-m2", "type": "match_start", "payload": {}})


def register_league(body) -> dict:
    if not isinstance(body, dict):
        raise validation_error(["body"])
    bad = [f for f in ("league_id", "sport_id") if not is_id(body.get(f))]
    teams = body.get("teams")
    if not (isinstance(teams, list) and 2 <= len(teams) <= 40 and all(is_id(t) for t in teams)
            and len(set(teams)) == len(teams)):
        bad.append("teams")
    fixtures = body.get("fixtures")
    if not isinstance(fixtures, list) or not all(
            isinstance(f, dict) and is_id(f.get("match_id")) and f.get("home") in (teams or [])
            and f.get("away") in (teams or []) and f.get("home") != f.get("away") for f in fixtures):
        bad.append("fixtures")
    elif len({f["match_id"] for f in fixtures}) != len(fixtures):
        bad.append("fixtures")
    points = body.get("points") or {}
    if not isinstance(points, dict) or not all(is_int(points.get(k, 0)) for k in ("win", "draw", "loss")):
        bad.append("points")
    tbo = body.get("tie_break_order")
    if tbo is not None and not (isinstance(tbo, list) and all(t in TIE_BREAKS for t in tbo)
                                and len(set(tbo)) == len(tbo)):
        bad.append("tie_break_order")
    qual = body.get("qualification")
    if not (isinstance(qual, dict) and is_int(qual.get("spots")) and isinstance(teams, list)
            and 1 <= qual["spots"] <= len(teams)):
        bad.append("qualification")
    if body.get("lots_seed") is not None and not is_int(body.get("lots_seed")):
        bad.append("lots_seed")
    if bad:
        raise validation_error(bad)
    with LOCK:
        sport = SPORTS.get(body["sport_id"])
        if sport is None:
            raise APIError(404, "SPORT_NOT_FOUND", "Unknown sport.", {"sport_id": body["sport_id"]})
        if body["league_id"] in LEAGUES:
            raise APIError(409, "LEAGUE_EXISTS", "League already exists.", {"league_id": body["league_id"]})
        for f in fixtures:
            if f["match_id"] in ENGINE.matches:
                raise APIError(409, "MATCH_EXISTS", "Match id already used.", {"match_id": f["match_id"]})
        league = {"league_id": body["league_id"], "sport_id": body["sport_id"], "teams": list(teams),
                  "fixtures": [{"match_id": f["match_id"], "home": f["home"], "away": f["away"]} for f in fixtures],
                  "points": {"win": points.get("win", 3), "draw": points.get("draw", 1),
                             "loss": points.get("loss", 0)},
                  "tie_break_order": resolve_tie_breaks(tbo if tbo is not None else sport.get("tie_break_order")),
                  "qualification": {"spots": qual["spots"]},
                  "lots_seed": body.get("lots_seed") if body.get("lots_seed") is not None else STATE["seed"]}
        LEAGUES[league["league_id"]] = league
        for f in league["fixtures"]:
            ENGINE.create_stream(f["match_id"], league["sport_id"], f["home"], f["away"], league["league_id"])
    return {"league_id": league["league_id"], "status": "created", "team_count": len(teams),
            "fixture_count": len(fixtures)}


def standings(league_id: str) -> dict:
    with LOCK:
        league = LEAGUES.get(league_id)
        if league is None:
            raise APIError(404, "LEAGUE_NOT_FOUND", "Unknown league.", {"league_id": league_id})
        projections = []
        for f in league["fixtures"]:
            p = ENGINE.project(f["match_id"])
            projections.append({
                "match_id": f["match_id"], "home": f["home"], "away": f["away"], "status": p["status"],
                "outcome": p["outcome"], "home_score": p["home"]["score"], "away_score": p["away"]["score"],
                "home_balls": p["home"]["balls"], "away_balls": p["away"]["balls"],
                "home_wickets": p["home"]["wickets"], "away_wickets": p["away"]["wickets"],
                "home_fair_play": p["home"]["fair_play"], "away_fair_play": p["away"]["fair_play"]})
        return compute_standings(league, SPORTS[league["sport_id"]], projections)


def offline_sync(body) -> dict:
    if not isinstance(body, dict) or not is_id(body.get("device_id")):
        raise validation_error(["device_id"])
    actions = body.get("actions")
    if not isinstance(actions, list) or not 1 <= len(actions) <= 100:
        raise validation_error(["actions"])
    for a in actions:
        if not (isinstance(a, dict) and is_id(a.get("action_id"))
                and a.get("type") in ("score_event", "roster_transfer")
                and isinstance(a.get("queued_at"), str) and TS_RE.match(a["queued_at"])
                and is_int(a.get("base_version")) and a["base_version"] >= 0
                and isinstance(a.get("payload"), dict)):
            raise validation_error(["actions"])
    device = body["device_id"]
    order = sorted(range(len(actions)), key=lambda i: (actions[i]["queued_at"], i))
    results = [None] * len(actions)
    with LOCK:
        for pos, i in enumerate(order, 1):
            results[i] = _sync_one(device, actions[i], pos)
    summary = {"applied": 0, "rejected": 0, "duplicate": 0}
    for r in results:
        summary[r["status"]] += 1
    return {"device_id": device, "results": results, "summary": summary}


def _sync_one(device, action, pos) -> dict:
    key = (device, action["action_id"])
    payload = action["payload"]
    score = action["type"] == "score_event"

    def current_version():
        try:
            if score:
                return ENGINE.version(payload.get("match_id")) if payload.get("match_id") in ENGINE.matches else 0
            return ROSTER.player_version(payload.get("player_id"))
        except APIError:
            return 0

    def result(status, resolution, code=None, signature=None):
        STATE["synced"].add(key)
        return {"action_id": action["action_id"], "status": status, "resolution": resolution,
                "error_code": code, "processed_order": pos, "server_version": current_version(),
                "signature": signature}

    if key in STATE["synced"] or (ENGINE.is_duplicate(payload) if score else ROSTER.is_duplicate(payload)):
        return result("duplicate", "skipped_duplicate")
    try:
        if score:
            ENGINE.validate_shape(payload)
            if payload["type"] != "match_init" and payload["match_id"] not in ENGINE.matches:
                raise APIError(404, "MATCH_NOT_FOUND", "Unknown match.")
            current = ENGINE.version(payload["match_id"]) if payload["match_id"] in ENGINE.matches else 0
        else:
            current = ROSTER.player_version(payload.get("player_id")) if is_id(payload.get("player_id")) else 0
        if action["base_version"] > current:
            return result("rejected", "server_wins", "INVALID_BASE_VERSION")
        if score:
            _, resp = ENGINE.append(payload)
            sig = resp["signature"]
        else:
            ROSTER.transfer(payload)
            sig = None
    except APIError as exc:
        return result("rejected", "server_wins", exc.code)
    return result("applied", "appended" if action["base_version"] == current else "rebased_append", signature=sig)


reset_state({})


# ---- middleware ----------------------------------------------------------
@app.middleware("http")
async def guards(request: Request, call_next):
    length = request.headers.get("content-length")
    if length is not None and length.isdigit() and int(length) > config.MAX_BODY_BYTES:
        return error_response(413, "PAYLOAD_TOO_LARGE", "Request body exceeds 1 MB.")
    if request.url.path.startswith("/api/v1/"):
        ip = request.client.host if request.client else "unknown"
        retry = LIMITER.check(ip)
        if retry is not None:
            return error_response(429, "RATE_LIMITED", "Too many requests, slow down.", {},
                                  headers={"Retry-After": str(retry)})
    return await call_next(request)


async def read_json(request: Request, optional=False):
    raw = await request.body()
    if len(raw) > config.MAX_BODY_BYTES:
        raise APIError(413, "PAYLOAD_TOO_LARGE", "Request body exceeds 1 MB.")
    if not raw.strip():
        if optional:
            return {}
        raise validation_error(["body"], "Request body is required.")
    try:
        return json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        raise validation_error(["body"], "Malformed JSON.")


def respond(status, body):
    return JSONResponse(status_code=status, content=body)


# ---- health / reset / sports / fixtures ----------------------------------
@app.get("/health")
def health():
    try:
        with psycopg.connect(config.DATABASE_URL, connect_timeout=2) as conn:
            conn.execute("SELECT 1")
    except Exception:
        return error_response(503, "UNAVAILABLE", "Database is not reachable.")
    if not STATE["seeded"]:
        return error_response(503, "UNAVAILABLE", "Baseline data is not seeded yet.")
    return {"status": "ok"}


@app.post("/audit/v1/reset")
async def reset(request: Request):
    body = await read_json(request, optional=True)
    if not isinstance(body, dict):
        raise validation_error(["body"])
    return respond(200, reset_state(body))


@app.post("/audit/v1/sports")
async def sports_create(request: Request):
    body = await read_json(request)
    with LOCK:
        return respond(201, create_sport(SPORTS, body))


@app.post("/audit/v1/fixtures")
async def fixtures(request: Request):
    body = await read_json(request)
    return respond(200, generate_fixtures(body))


@app.post("/audit/v1/leagues")
async def leagues(request: Request):
    return respond(201, register_league(await read_json(request)))


@app.post("/audit/v1/events")
async def events(request: Request):
    body = await read_json(request)
    with LOCK:
        status, resp = ENGINE.append(body)
    if status == 201:
        events_bus.publish({"type": "match.event", "match_id": resp["match_id"], "event_id": resp["event_id"]})
    return respond(status, resp)


@app.get("/audit/v1/score/{match_id}")
def score(match_id: str):
    with LOCK:
        return ENGINE.score(match_id)


@app.get("/audit/v1/standings/{league_id}")
def standings_route(league_id: str):
    return standings(league_id)


# ---- roster ----------------------------------------------------------------
@app.post("/audit/v1/roster/setup")
async def roster_setup(request: Request):
    body = await read_json(request)
    with LOCK:
        return respond(201, ROSTER.setup(body, SPORTS))


@app.post("/audit/v1/roster/transfer")
async def roster_transfer(request: Request):
    body = await read_json(request)
    with LOCK:
        status, resp = ROSTER.transfer(body)
    return respond(status, resp)


@app.get("/audit/v1/roster/history/{player_id}")
def roster_history(player_id: str, as_of: str | None = None):
    with LOCK:
        return ROSTER.history(player_id, as_of)


# ---- store -------------------------------------------------------------------
@app.post("/audit/v1/checkout")
async def checkout(request: Request):
    body = await read_json(request)
    status, resp = STORE.checkout(body)
    return respond(status, resp)


@app.get("/audit/v1/inventory/{variant_id}")
def inventory(variant_id: str):
    return STORE.inventory(variant_id)


# ---- RBAC ----------------------------------------------------------------------
@app.post("/audit/v1/rbac-matrix")
def rbac_matrix():
    return auth.rbac_matrix()


def _probe(request: Request, action, resource_id=None, table=None):
    exists = True if table is None else resource_id in table
    auth.authorize(request.headers.get("authorization"), action, resource_id, exists)
    return {"authorized": True}


@app.post("/audit/v1/rbac/tenants")
def probe_tenants(request: Request):
    return _probe(request, "tenants.create")


@app.post("/audit/v1/rbac/leagues/{league_id}/fixtures")
def probe_league_fixtures(league_id: str, request: Request):
    return _probe(request, "league.fixtures.write", league_id, auth.LEAGUES)


@app.post("/audit/v1/rbac/clubs/{club_id}/roster")
def probe_club_roster(club_id: str, request: Request):
    return _probe(request, "club.roster.write", club_id, auth.CLUBS)


@app.post("/audit/v1/rbac/clubs/{club_id}/products")
def probe_club_products(club_id: str, request: Request):
    return _probe(request, "club.products.write", club_id, auth.CLUBS)


@app.patch("/audit/v1/rbac/players/{player_id}")
def probe_player(player_id: str, request: Request):
    return _probe(request, "player.write", player_id, auth.PLAYERS)


@app.get("/audit/v1/rbac/clubs/{club_id}")
def probe_club_read(club_id: str, request: Request):
    return _probe(request, "club.read", club_id, auth.CLUBS)


@app.get("/audit/v1/rbac/platform/config")
def probe_platform(request: Request):
    return _probe(request, "platform.config")


@app.get("/api/v1/ping")
def ping():
    return {"pong": True}


@app.post("/audit/v1/offline-sync")
async def sync(request: Request):
    return respond(200, offline_sync(await read_json(request)))


# ---- production routes used by the mobile app ---------------------------------
@app.post("/api/v1/auth/login")
async def login(request: Request):
    body = await read_json(request)
    if not isinstance(body, dict):
        raise validation_error(["body"])
    return auth.login(body.get("email"), body.get("password"))


@app.get("/api/v1/fixtures")
def app_fixtures():
    with LOCK:
        out = []
        for league in LEAGUES.values():
            for f in league["fixtures"]:
                p = ENGINE.project(f["match_id"])
                out.append({"match_id": f["match_id"], "league_id": league["league_id"],
                            "sport_id": league["sport_id"],
                            "home": DEMO_TEAMS.get(f["home"], f["home"]),
                            "away": DEMO_TEAMS.get(f["away"], f["away"]),
                            "status": p["status"], "home_score": p["home"]["score"],
                            "away_score": p["away"]["score"], "venue": "Alpha Stadium"})
        return {"fixtures": out}


@app.get("/api/v1/clubs/{club_id}")
def app_club(club_id: str):
    if club_id not in auth.CLUBS and club_id not in DEMO_TEAMS:
        raise APIError(404, "NOT_FOUND", "Club not found.", {"club_id": club_id})
    tenant = auth.CLUBS.get(club_id, "tenant-alpha")
    roster = [{"player_id": pid, "name": pid.replace("-", " ").title(), "position": "mf", "squad_id": club_id}
              for pid, cid in auth.PLAYERS.items() if cid == club_id]
    return {"club_id": club_id, "name": DEMO_TEAMS.get(club_id, club_id), "tenant": auth.TENANTS[tenant],
            "venue": "Alpha Stadium, Islamabad", "venue_coordinates": {"lat": 33.6844, "lng": 73.0479},
            "social": {"instagram": "@" + club_id.replace("-", "")},
            "staff": [{"name": "Imran Khan", "role": "coach"}, {"name": "Sara Ali", "role": "manager"},
                      {"name": "Dr. Hamza", "role": "physio"}],
            "roster": roster}


@app.get("/api/v1/products")
def app_products():
    return {"products": STORE.products()}
