"""Roster rules, loans, auto-return and audit trail (spec 5.11, edge case 6)."""
import pytest

from app.errors import APIError
from app.roster import RosterService

SPORTS = {"football": {"roster": {"min_squad_size": 11, "max_squad_size": 25, "required_positions": {"gk": 1}}}}
NOW = "2026-09-30T08:12:44Z"


def scenario(**league_overrides):
    league = {"league_id": "lg-r1", "tenant_id": "tenant-alpha", "sport_id": "football",
              "transfer_window": {"open": "2026-09-01", "close": "2026-09-30"},
              "max_squad_size": 3, "required_positions": {"gk": 1}}
    league.update(league_overrides)
    return {
        "league": league,
        "squads": [{"squad_id": "sq-a", "club_id": "club-a", "tenant_id": "tenant-alpha", "name": "A"},
                   {"squad_id": "sq-b", "club_id": "club-b", "tenant_id": "tenant-alpha", "name": "B"},
                   {"squad_id": "sq-x", "club_id": "club-x", "tenant_id": "tenant-beta", "name": "X"}],
        "players": [{"player_id": "p1", "name": "Ali", "position": "gk", "squad_id": "sq-a", "role": "captain"},
                    {"player_id": "p2", "name": "Bilal", "position": "df", "squad_id": "sq-a", "role": "starter"}],
        "matches_in_progress": [],
    }


def req(**over):
    body = {"request_id": "tr-001", "league_id": "lg-r1", "player_id": "p2", "type": "transfer",
            "from_squad_id": "sq-a", "to_squad_id": "sq-b", "effective_date": "2026-09-15",
            "loan_end_date": None, "reason": "Tactical move", "requested_by": "user-77"}
    body.update(over)
    return body


@pytest.fixture
def svc():
    s = RosterService()
    assert s.setup(scenario(), SPORTS) == {"league_id": "lg-r1", "status": "configured",
                                            "squad_counts": {"sq-a": 2, "sq-b": 0, "sq-x": 0}}
    return s


def code_of(svc, body):
    with pytest.raises(APIError) as e:
        svc.transfer(body, NOW)
    return e.value.status, e.value.code


def test_transfer_accepted_shape(svc):
    status, resp = svc.transfer(req(), NOW)
    assert status == 201
    assert resp["status"] == "accepted" and resp["state"] == "active" and resp["blocking_match_id"] is None
    assert resp["registration"] == {"player_id": "p2", "league_id": "lg-r1", "squad_id": "sq-b",
                                    "parent_squad_id": None, "registration_type": "transfer",
                                    "start_date": "2026-09-15", "loan_end_date": None, "role": "substitute"}
    assert resp["audit_entry"] == {"audit_id": "au-0001", "action": "transfer", "player_id": "p2",
                                   "league_id": "lg-r1", "from_squad_id": "sq-a", "to_squad_id": "sq-b",
                                   "effective_date": "2026-09-15", "state": "active", "who": "user-77",
                                   "when": NOW, "why": "Tactical move"}


def test_idempotent_replay_and_conflicting_reuse(svc):
    first = svc.transfer(req(), NOW)[1]
    assert svc.is_duplicate(req())
    assert svc.transfer(req(), "2026-10-01T00:00:00Z") == (200, first)
    assert svc.player_version("p2") == 1
    assert code_of(svc, req(reason="other")) == (400, "VALIDATION_ERROR")


@pytest.mark.parametrize("over,field", [
    ({"type": "swap"}, "type"),
    ({"effective_date": "2026-13-01"}, "effective_date"),
    ({"to_squad_id": None}, "to_squad_id"),
    ({"type": "loan", "loan_end_date": None}, "loan_end_date"),
    ({"type": "loan", "loan_end_date": "2026-09-15"}, "loan_end_date"),
])
def test_validation_errors(svc, over, field):
    with pytest.raises(APIError) as e:
        svc.transfer(req(**over), NOW)
    assert e.value.status == 400 and field in e.value.details["fields"]


def test_existence_order(svc):
    assert code_of(svc, req(league_id="nope", player_id="nope")) == (404, "LEAGUE_NOT_FOUND")
    assert code_of(svc, req(player_id="nope", to_squad_id="nope")) == (404, "PLAYER_NOT_FOUND")
    assert code_of(svc, req(to_squad_id="nope")) == (404, "SQUAD_NOT_FOUND")


def test_cross_tenant_before_not_in_squad(svc):
    assert code_of(svc, req(from_squad_id="sq-b", to_squad_id="sq-x")) == (409, "CROSS_TENANT_TRANSFER")


def test_not_in_squad_before_window(svc):
    assert code_of(svc, req(from_squad_id="sq-b", to_squad_id="sq-a",
                            effective_date="2026-12-01")) == (409, "NOT_IN_SQUAD")


def test_window_inclusive_and_release_any_day(svc):
    assert code_of(svc, req(effective_date="2026-08-31")) == (409, "TRANSFER_WINDOW_CLOSED")
    assert svc.transfer(req(request_id="tr-last", effective_date="2026-09-30"), NOW)[0] == 201
    status, resp = svc.transfer(req(request_id="tr-rel", type="release", from_squad_id="sq-b",
                                    to_squad_id=None, effective_date="2027-03-01"), NOW)
    assert status == 201 and resp["registration"] is None and resp["audit_entry"]["action"] == "release"
    assert svc.history("p2", "2027-03-02")["current_squad_id"] is None


def test_player_on_loan_refused(svc):
    svc.transfer(req(type="loan", loan_end_date="2026-12-31"), NOW)
    assert code_of(svc, req(request_id="tr-2", from_squad_id="sq-b", to_squad_id="sq-a",
                            effective_date="2026-09-20")) == (409, "PLAYER_ON_LOAN")
    assert code_of(svc, req(request_id="tr-3", type="release", from_squad_id="sq-b",
                            to_squad_id=None, effective_date="2026-10-01")) == (409, "PLAYER_ON_LOAN")


def test_squad_full():
    s = RosterService()
    body = scenario(max_squad_size=1)
    body["players"].append({"player_id": "p3", "name": "C", "position": "df", "squad_id": "sq-b"})
    s.setup(body, SPORTS)
    assert code_of(s, req()) == (409, "SQUAD_FULL")


def test_min_position_violation(svc):
    assert code_of(svc, req(player_id="p1")) == (409, "MIN_POSITION_VIOLATION")
    # release also keeps the minimum
    assert code_of(svc, req(player_id="p1", type="release", to_squad_id=None)) == (409, "MIN_POSITION_VIOLATION")


def test_rejected_request_writes_nothing(svc):
    code_of(svc, req(player_id="p1"))
    assert svc.player_version("p1") == 0
    assert svc.history("p1", "2026-09-15")["history"] == []


def test_loan_counts_toward_borrower_and_auto_returns_once(svc):
    status, resp = svc.transfer(req(type="loan", loan_end_date="2026-12-31"), NOW)
    assert status == 201
    assert resp["registration"]["parent_squad_id"] == "sq-a"
    assert resp["registration"]["registration_type"] == "loan"
    during = svc.history("p2", "2026-12-31")
    assert during["current_squad_id"] == "sq-b" and during["parent_squad_id"] == "sq-a"
    assert len(during["history"]) == 1
    after = svc.history("p2", "2027-01-05")
    assert after["current_squad_id"] == "sq-a" and after["parent_squad_id"] is None
    actions = [e["action"] for e in after["history"]]
    assert actions == ["loan", "loan_return"]
    ret = after["history"][1]
    assert ret["who"] == "system" and ret["from_squad_id"] == "sq-b" and ret["to_squad_id"] == "sq-a"
    assert ret["effective_date"] == "2027-01-01"
    again = svc.history("p2", "2027-01-05")
    assert [e["action"] for e in again["history"]] == ["loan", "loan_return"]


def test_returned_player_can_move_again_next_window(svc):
    svc.transfer(req(type="loan", effective_date="2026-09-01", loan_end_date="2026-09-10"), NOW)
    status, resp = svc.transfer(req(request_id="tr-2", effective_date="2026-09-20"), NOW)
    assert status == 201
    actions = [e["action"] for e in svc.history("p2", "2026-09-21")["history"]]
    assert actions == ["loan", "loan_return", "transfer"]


def test_last_window_day_with_in_progress_match_is_deferred():
    s = RosterService()
    body = scenario()
    body["matches_in_progress"] = [{"match_id": "m-live", "home_squad_id": "sq-a", "away_squad_id": "sq-b"}]
    s.setup(body, SPORTS)
    status, resp = s.transfer(req(effective_date="2026-09-30"), NOW)
    assert status == 201
    assert resp["state"] == "deferred_until_match_end" and resp["blocking_match_id"] == "m-live"
    assert resp["audit_entry"]["state"] == "deferred_until_match_end"


def test_setup_replaces_league_and_defaults_from_sport():
    s = RosterService()
    body = scenario()
    del body["league"]["max_squad_size"]
    del body["league"]["required_positions"]
    s.setup(body, SPORTS)
    assert s.leagues["lg-r1"]["max_squad_size"] == 25
    assert s.leagues["lg-r1"]["required_positions"] == {"gk": 1}
    s.transfer(req(), NOW)
    s.setup(scenario(), SPORTS)
    assert s.player_version("p2") == 0
    assert s.history("p2", "2026-09-20")["current_squad_id"] == "sq-a"


def test_history_unknown_player(svc):
    with pytest.raises(APIError) as e:
        svc.history("ghost", None)
    assert e.value.code == "PLAYER_NOT_FOUND"
