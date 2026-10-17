"""End-to-end tests of the /audit/v1 contract through the FastAPI app."""
import base64
import json
import os
import threading

os.environ.setdefault("DAY1_SALT", "demo-salt")

import pytest
from fastapi.testclient import TestClient

from app import config, main
from app.signing import sign

config.DAY1_SALT = "demo-salt"
client = TestClient(main.app)


@pytest.fixture(autouse=True)
def fresh():
    r = client.post("/audit/v1/reset", json={})
    assert r.status_code == 200
    yield


def ev(eid, mid, typ, payload=None):
    return client.post("/audit/v1/events", json={"event_id": eid, "match_id": mid, "type": typ,
                                                 "payload": payload or {}})


# ---- reset / sports ---------------------------------------------------------
def test_reset_contract_and_repeatable():
    r = client.post("/audit/v1/reset", json={"seed": 7, "stock": {"var-jersey-001-M": 3}})
    assert r.json() == {"status": "reset_complete", "seed": 7,
                        "sports": ["football", "basketball", "cricket", "esports"],
                        "tenants": ["tenant-alpha", "tenant-beta"],
                        "stock": {"var-jersey-001-M": 3, "var-jersey-001-L": 5}}
    assert client.get("/audit/v1/inventory/var-jersey-001-M").json() == {
        "variant_id": "var-jersey-001-M", "stock": 3, "reserved": 0}
    assert client.post("/audit/v1/reset").status_code == 200


KABADDI = {"sport_id": "kabaddi", "name": "Kabaddi", "scoring_model": "event",
           "periods": {"count": 2, "duration_minutes": 20},
           "scoring_events": {"raid_point": {"points": 1}, "tackle_point": {"points": 1}, "all_out": {"points": 2}},
           "draw_allowed": False, "overtime": {"policy": "golden_score", "duration_minutes": 5},
           "tie_break_order": ["h2h_points", "h2h_diff", "overall_diff", "scored", "fair_play", "draw_lots"],
           "roster": {"min_squad_size": 7, "max_squad_size": 12, "required_positions": {"raider": 2}}}


def test_mystery_sport_create_duplicate_and_validation():
    r = client.post("/audit/v1/sports", json=KABADDI)
    assert r.status_code == 201 and r.json()["sport_id"] == "kabaddi" and r.json()["status"] == "created"
    assert client.post("/audit/v1/sports", json=KABADDI).json()["error"]["code"] == "SPORT_EXISTS"
    bad = dict(KABADDI, sport_id="x'; DROP TABLE sports;--")
    r = client.post("/audit/v1/sports", json=bad)
    assert r.status_code == 400 and r.json()["error"]["code"] == "VALIDATION_ERROR"
    assert "sport_id" in r.json()["error"]["details"]["fields"]


def test_mystery_sport_usable_in_events():
    client.post("/audit/v1/sports", json=KABADDI)
    assert ev("k1", "km", "match_init", {"sport_id": "kabaddi", "home_team_id": "a", "away_team_id": "b"}).status_code == 201
    ev("k2", "km", "match_start")
    ev("k3", "km", "score", {"team_id": "a", "event_type": "all_out"})
    assert ev("k4", "km", "score", {"team_id": "a", "event_type": "goal"}).json()["error"]["code"] == "UNKNOWN_EVENT_TYPE"
    s = client.get("/audit/v1/score/km").json()
    assert s["home"]["score"] == 2 and s["status"] == "in_progress" and s["outcome"] == "pending"


# ---- events / score ---------------------------------------------------------
def test_event_flow_signature_compensation_and_idempotency():
    r = ev("e1", "m1", "match_init", {"sport_id": "football", "home_team_id": "t1", "away_team_id": "t2"})
    assert r.status_code == 201 and r.json()["sequence"] == 1
    assert ev("e2", "m1", "score", {"team_id": "t1", "event_type": "goal"}).json()["error"]["code"] == "MATCH_NOT_IN_PROGRESS"
    ev("e3", "m1", "match_start")
    r = ev("e4", "m1", "score", {"team_id": "t1", "event_type": "goal"})
    body = r.json()
    assert r.status_code == 201 and body["sequence"] == 3 and body["match_version"] == 3
    assert body["signature"] == sign("demo-salt", "e4", {"team_id": "t1", "event_type": "goal"})
    replay = ev("e4", "m1", "score", {"team_id": "t1", "event_type": "goal"})
    assert replay.status_code == 200 and replay.json() == body
    assert ev("e4", "m1", "score", {"team_id": "t2", "event_type": "goal"}).json()["error"]["code"] == "DUPLICATE_EVENT_ID"
    ev("e5", "m1", "discipline", {"team_id": "t2", "points": -1})
    ev("e6", "m1", "match_end")
    assert client.get("/audit/v1/score/m1").json()["outcome"] == "home_win"
    assert ev("e7", "m1", "compensation", {"compensates": "e4", "reason": "VAR"}).status_code == 201
    s = client.get("/audit/v1/score/m1").json()
    assert s["outcome"] == "draw" and s["home"]["score"] == 0 and s["away"]["fair_play"] == -1
    assert s["events"][2]["compensated"] is True and s["events"][2]["compensated_by"] == "e7"
    assert ev("e8", "m1", "compensation", {"compensates": "e4", "reason": "x"}).json()["error"]["code"] == "INVALID_COMPENSATION"
    assert ev("e9", "m1", "compensation", {"compensates": "nope", "reason": "x"}).status_code == 404
    assert ev("e10", "m1", "match_start").json()["error"]["code"] == "ILLEGAL_TRANSITION"
    assert ev("x1", "missing", "match_start").json()["error"]["code"] == "MATCH_NOT_FOUND"
    assert ev("x2", "m1", "match_init", {"sport_id": "football", "home_team_id": "a", "away_team_id": "b"}).json()["error"]["code"] == "MATCH_EXISTS"


def test_tie_not_allowed_and_tiebreak_winner():
    ev("b1", "bm", "match_init", {"sport_id": "basketball", "home_team_id": "h", "away_team_id": "a"})
    ev("b2", "bm", "match_start")
    assert ev("b3", "bm", "match_end").json()["error"]["code"] == "TIE_NOT_ALLOWED"
    ev("b4", "bm", "tiebreak_winner", {"team_id": "a"})
    assert ev("b5", "bm", "match_end").status_code == 201
    s = client.get("/audit/v1/score/bm").json()
    assert s["outcome"] == "away_win" and s["winner_team_id"] == "a" and s["tiebreak_winner_team_id"] == "a"
    ev("b6", "bm", "compensation", {"compensates": "b4", "reason": "review"})
    assert client.get("/audit/v1/score/bm").json()["outcome"] == "undecided"


def test_innings_and_round_limits():
    client.post("/audit/v1/sports", json={
        "sport_id": "mini_cricket", "name": "Mini", "scoring_model": "innings",
        "periods": {"innings_per_team": 1, "overs_per_innings": 1, "balls_per_over": 2, "wickets_per_innings": 1},
        "scoring_events": {"six": {"runs": 6, "legal_ball": True, "wicket": False},
                           "wide": {"runs": 1, "legal_ball": False, "wicket": False}},
        "draw_allowed": True, "overtime": {"policy": "none"},
        "roster": {"min_squad_size": 1, "max_squad_size": 5, "required_positions": {}}})
    ev("c1", "cm", "match_init", {"sport_id": "mini_cricket", "home_team_id": "h", "away_team_id": "a"})
    ev("c2", "cm", "match_start")
    ev("c3", "cm", "score", {"team_id": "h", "event_type": "wide"})
    ev("c4", "cm", "score", {"team_id": "h", "event_type": "six"})
    ev("c5", "cm", "score", {"team_id": "h", "event_type": "six"})
    assert ev("c6", "cm", "score", {"team_id": "h", "event_type": "six"}).json()["error"]["code"] == "INNINGS_COMPLETE"
    s = client.get("/audit/v1/score/cm").json()
    assert s["home"]["score"] == 13 and s["home"]["balls"] == 2 and s["home"]["overs"] == "1.0"

    ev("r1", "rm", "match_init", {"sport_id": "esports", "home_team_id": "h", "away_team_id": "a"})
    ev("r2", "rm", "match_start")
    ev("r3", "rm", "score", {"team_id": "h", "event_type": "round_win"})
    ev("r4", "rm", "score", {"team_id": "h", "event_type": "round_win"})
    assert ev("r5", "rm", "score", {"team_id": "a", "event_type": "round_win"}).json()["error"]["code"] == "SERIES_ALREADY_DECIDED"


# ---- leagues / standings ----------------------------------------------------
def test_league_registration_and_standings():
    league = {"league_id": "lg-1", "sport_id": "football", "teams": ["t1", "t2", "t3"],
              "fixtures": [{"match_id": "m1", "home": "t1", "away": "t2"},
                           {"match_id": "m2", "home": "t2", "away": "t3"}],
              "qualification": {"spots": 1}}
    r = client.post("/audit/v1/leagues", json=league)
    assert r.json() == {"league_id": "lg-1", "status": "created", "team_count": 3, "fixture_count": 2}
    assert client.post("/audit/v1/leagues", json=league).json()["error"]["code"] == "LEAGUE_EXISTS"
    assert client.post("/audit/v1/leagues", json=dict(league, league_id="lg-2")).json()["error"]["code"] == "MATCH_EXISTS"
    assert client.post("/audit/v1/leagues", json=dict(league, league_id="lg-3", sport_id="nope")).status_code == 404
    ev("s1", "m1", "match_start")
    ev("s2", "m1", "score", {"team_id": "t1", "event_type": "goal"})
    ev("s3", "m1", "match_end")
    t = client.get("/audit/v1/standings/lg-1").json()
    assert t["table"][0]["team_id"] == "t1" and t["table"][0]["points"] == 3
    assert t["h2h"]["t1"]["t2"] == {"played": 1, "points": 3, "scored": 1, "conceded": 0}
    assert client.get("/audit/v1/standings/none").status_code == 404


# ---- checkout ------------------------------------------------------------------
def order(oid, token="tok_success", code=None, variant="var-jersey-001-M"):
    return {"order_id": oid, "customer_id": "cust-<script>\"1", "items": [{"variant_id": variant, "quantity": 1}],
            "discount_code": code, "payment": {"token": token}}


def test_twenty_concurrent_buyers_last_unit():
    results = []
    barrier = threading.Barrier(20)

    def buy(i):
        barrier.wait()
        try:
            results.append(main.STORE.checkout(order(f"ord-{i}"))[0])
        except main.APIError as exc:
            results.append(exc.status)

    threads = [threading.Thread(target=buy, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(results) == [201] + [409] * 19
    assert client.get("/audit/v1/inventory/var-jersey-001-M").json() == {
        "variant_id": "var-jersey-001-M", "stock": 0, "reserved": 0}


def test_checkout_receipt_signature_pdf_discount_and_replay():
    r = client.post("/audit/v1/checkout", json=order("ord-1", code="WELCOME10", variant="var-jersey-001-L"))
    body = r.json()
    assert r.status_code == 201 and body["discount_minor"] == 45000 and body["total_minor"] == 405000
    payload = body["receipt"]["payload"]
    assert body["receipt"]["signature"] == sign("demo-salt", "ord-1", payload)
    pdf = base64.b64decode(body["receipt"]["pdf_base64"])
    assert pdf.startswith(b"%PDF") and b"ord-1" in pdf and b"PKR 4050.00" in pdf
    assert payload["customer_id"] == "cust-<script>\"1"
    again = client.post("/audit/v1/checkout", json=order("ord-1", code="WELCOME10", variant="var-jersey-001-L"))
    assert again.status_code == 200 and again.json() == body
    assert client.post("/audit/v1/checkout", json=order("ord-1")).json()["error"]["code"] == "DUPLICATE_ORDER_ID"


def test_payment_failures_release_stock_and_errors():
    assert client.post("/audit/v1/checkout", json=order("o1", "tok_declined")).json()["error"]["code"] == "PAYMENT_DECLINED"
    r = client.post("/audit/v1/checkout", json=order("o2", "tok_capture_fail"))
    assert r.status_code == 402 and r.json()["error"]["code"] == "PAYMENT_CAPTURE_FAILED"
    assert client.get("/audit/v1/inventory/var-jersey-001-M").json()["stock"] == 1
    assert client.post("/audit/v1/checkout", json=order("o3", code="BOGUS")).json()["error"]["code"] == "INVALID_DISCOUNT_CODE"
    assert client.post("/audit/v1/checkout", json=order("o4", variant="var-x")).status_code == 404
    assert client.post("/audit/v1/checkout", json={"order_id": "o5"}).status_code == 400
    assert client.post("/audit/v1/checkout", json=order("o6")).status_code == 201
    assert client.post("/audit/v1/checkout", json=order("o7")).json()["error"]["code"] == "OUT_OF_STOCK"


# ---- RBAC / security -------------------------------------------------------------
A, D = 200, 403
MATRIX = [  # (method, path, [super, organizer, manager, player, viewer])
    ("post", "/audit/v1/rbac/tenants", [A, D, D, D, D]),
    ("post", "/audit/v1/rbac/leagues/league-alpha-1/fixtures", [A, A, D, D, D]),
    ("post", "/audit/v1/rbac/leagues/league-alpha-2/fixtures", [A, D, D, D, D]),
    ("post", "/audit/v1/rbac/leagues/league-beta-1/fixtures", [A, D, D, D, D]),
    ("post", "/audit/v1/rbac/clubs/club-alpha-1/roster", [A, D, A, D, D]),
    ("post", "/audit/v1/rbac/clubs/club-alpha-2/products", [A, D, D, D, D]),
    ("post", "/audit/v1/rbac/clubs/club-beta-1/roster", [A, D, D, D, D]),
    ("patch", "/audit/v1/rbac/players/player-alpha-1", [A, D, A, A, D]),
    ("patch", "/audit/v1/rbac/players/player-alpha-2", [A, D, D, D, D]),
    ("patch", "/audit/v1/rbac/players/player-beta-1", [A, D, D, D, D]),
    ("get", "/audit/v1/rbac/clubs/club-alpha-2", [A, A, A, A, A]),
    ("get", "/audit/v1/rbac/clubs/club-beta-1", [A, D, D, D, D]),
    ("get", "/audit/v1/rbac/platform/config", [A, D, D, D, D]),
]


def test_rbac_matrix_every_cell():
    tokens = client.post("/audit/v1/rbac-matrix").json()["tokens"]
    roles = ["super_admin", "league_organizer", "club_manager", "player", "viewer"]
    for method, path, expected in MATRIX:
        for role, want in zip(roles, expected):
            kwargs = {"headers": {"Authorization": f"Bearer {tokens[role]}"}}
            if method != "get":
                kwargs["json"] = {}
            r = getattr(client, method)(path, **kwargs)
            assert r.status_code == want, (path, role, r.status_code)
            if want == D:
                assert r.json()["error"]["code"] == "FORBIDDEN"


def test_tampered_none_and_missing_tokens():
    tok = client.post("/audit/v1/rbac-matrix").json()["tokens"]["super_admin"]
    assert client.get("/audit/v1/rbac/platform/config").json()["error"]["code"] == "UNAUTHENTICATED"
    h, p, s = tok.split(".")
    tampered = f"{h}.{p}.{s[:-2]}{'AA' if s[-2:] != 'AA' else 'BB'}"
    none_header = base64.urlsafe_b64encode(json.dumps({"alg": "none", "typ": "JWT"}).encode()).rstrip(b"=").decode()
    for bad in (tampered, f"{none_header}.{p}."):
        r = client.get("/audit/v1/rbac/platform/config", headers={"Authorization": f"Bearer {bad}"})
        assert r.status_code == 401


def test_rate_limit_and_body_limit():
    main.LIMITER.hits.clear()
    codes = [client.get("/api/v1/ping").status_code for _ in range(150)]
    assert codes[0] == 200 and codes.count(429) >= 40
    r = client.get("/api/v1/ping")
    assert r.status_code == 429 and "retry-after" in r.headers
    assert client.post("/audit/v1/reset").status_code == 200   # audit routes are exempt
    big = client.post("/audit/v1/sports", content=b"{" + b" " * (1024 * 1024 + 10) + b"}",
                      headers={"Content-Type": "application/json"})
    assert big.status_code == 413 and big.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"
    main.LIMITER.hits.clear()


def test_login_route():
    main.LIMITER.hits.clear()
    r = client.post("/api/v1/auth/login", json={"email": "manager@nascon.test", "password": "Nascon@26"})
    assert r.status_code == 200 and r.json()["role"] == "club_manager"
    assert client.post("/api/v1/auth/login", json={"email": "manager@nascon.test", "password": "x"}).status_code == 401


# ---- offline sync -------------------------------------------------------------------
def test_offline_sync_conflicts_and_replay():
    ev("o1", "om", "match_init", {"sport_id": "football", "home_team_id": "t1", "away_team_id": "t2"})
    ev("o2", "om", "match_start")
    req = {"device_id": "dev-1", "actions": [
        {"action_id": "a2", "type": "score_event", "queued_at": "2026-10-17T11:01:00Z", "base_version": 1,
         "payload": {"event_id": "evt-b", "match_id": "om", "type": "score",
                     "payload": {"team_id": "t2", "event_type": "goal"}}},
        {"action_id": "a1", "type": "score_event", "queued_at": "2026-10-17T11:00:00Z", "base_version": 2,
         "payload": {"event_id": "evt-a", "match_id": "om", "type": "score",
                     "payload": {"team_id": "t1", "event_type": "goal"}}},
        {"action_id": "a3", "type": "score_event", "queued_at": "2026-10-17T11:02:00Z", "base_version": 99,
         "payload": {"event_id": "evt-c", "match_id": "om", "type": "score",
                     "payload": {"team_id": "t1", "event_type": "goal"}}},
        {"action_id": "a4", "type": "score_event", "queued_at": "2026-10-17T11:03:00Z", "base_version": 0,
         "payload": {"event_id": "evt-d", "match_id": "zz", "type": "score",
                     "payload": {"team_id": "t1", "event_type": "goal"}}}]}
    r = client.post("/audit/v1/offline-sync", json=req).json()
    res = {x["action_id"]: x for x in r["results"]}
    assert [x["action_id"] for x in r["results"]] == ["a2", "a1", "a3", "a4"]
    assert res["a1"]["resolution"] == "appended" and res["a1"]["processed_order"] == 1
    assert res["a2"]["resolution"] == "rebased_append" and res["a2"]["server_version"] == 4
    assert res["a1"]["signature"] == sign("demo-salt", "evt-a", {"team_id": "t1", "event_type": "goal"})
    assert res["a3"]["error_code"] == "INVALID_BASE_VERSION"
    assert res["a4"]["error_code"] == "MATCH_NOT_FOUND"
    assert r["summary"] == {"applied": 2, "rejected": 2, "duplicate": 0}
    again = client.post("/audit/v1/offline-sync", json=req).json()
    assert again["summary"] == {"applied": 0, "rejected": 0, "duplicate": 4}
    assert client.post("/audit/v1/offline-sync", json={"device_id": "d", "actions": []}).status_code == 400
