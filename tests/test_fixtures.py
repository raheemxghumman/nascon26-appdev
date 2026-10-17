"""Fixture generation (spec 5.7): structural properties and exact sections."""
import itertools
from collections import Counter

import pytest

from app.errors import APIError
from app.fixtures import generate


def teams(n):
    return [f"t{i}" for i in range(1, n + 1)]


def all_matches(resp):
    return [m for r in resp["rounds"] for m in r["matches"]]


# --------------------------------------------------------------------------- validation


@pytest.mark.parametrize("body", [
    {"format": "nope", "teams": ["a", "b"]},
    {"format": "round_robin", "teams": ["a"]},
    {"format": "round_robin", "teams": ["a", "a"]},
    {"format": "round_robin", "teams": ["a", "b|c"]},
    {"format": "round_robin", "teams": "ab"},
    {"format": "double_elim", "teams": ["a", "b"]},
    {"format": "round_robin", "teams": teams(41)},
    {"format": "round_robin", "teams": ["a", "b"], "params": {"legs": 3}},
    {"format": "round_robin", "teams": ["a", "b"], "params": "x"},
])
def test_invalid_requests_are_400(body):
    with pytest.raises(APIError) as e:
        generate(body)
    assert e.value.status == 400 and e.value.code == "VALIDATION_ERROR"


# --------------------------------------------------------------------------- round robin


@pytest.mark.parametrize("n", [2, 3, 4, 5, 6, 7, 10, 11])
@pytest.mark.parametrize("legs", [1, 2])
def test_round_robin_properties(n, legs):
    resp = generate({"format": "round_robin", "teams": teams(n), "params": {"legs": legs}})
    per_leg = n - 1 if n % 2 == 0 else n
    assert resp["round_count"] == per_leg * legs
    assert resp["team_count"] == n and resp["legs"] == legs
    assert [r["round"] for r in resp["rounds"]] == list(range(1, per_leg * legs + 1))
    pair_count = Counter()
    ordered = Counter()
    for r in resp["rounds"]:
        assert len(r["matches"]) == n // 2
        assert len(r["byes"]) == (0 if n % 2 == 0 else 1)
        seen = [t for m in r["matches"] for t in (m["home"], m["away"])] + r["byes"]
        assert sorted(seen) == sorted(teams(n))
        for i, m in enumerate(r["matches"], 1):
            leg = 1 if r["round"] <= per_leg else 2
            assert m["match_id"] == f"RR-L{leg}-R{r['round']}-M{i}"
            assert m["leg"] == leg and m["status"] == "scheduled" and m["awarded_to"] is None
            pair_count[frozenset((m["home"], m["away"]))] += 1
            ordered[(m["home"], m["away"])] += 1
    assert set(pair_count.values()) == {legs}
    assert len(pair_count) == n * (n - 1) // 2
    if legs == 2:
        assert set(ordered.values()) == {1}
    for leg in range(1, legs + 1):
        home, away, byes = Counter(), Counter(), Counter()
        for r in resp["rounds"][(leg - 1) * per_leg: leg * per_leg]:
            for m in r["matches"]:
                home[m["home"]] += 1
                away[m["away"]] += 1
            byes.update(r["byes"])
        for t in teams(n):
            assert abs(home[t] - away[t]) <= 1
            if n % 2:
                assert byes[t] == 1
    assert resp["summary"] == {"total": len(pair_count) * legs, "scheduled": len(pair_count) * legs,
                               "forfeit": 0, "voided": 0}


def test_round_robin_forfeit_remaining():
    resp = generate({"format": "round_robin", "teams": teams(5),
                     "params": {"legs": 1, "withdrawals": [{"team_id": "t3", "after_round": 2}],
                                "withdrawal_policy": "forfeit_remaining"}})
    for r in resp["rounds"]:
        for m in r["matches"]:
            if "t3" in (m["home"], m["away"]):
                other = m["away"] if m["home"] == "t3" else m["home"]
                if r["round"] > 2:
                    assert m["status"] == "forfeit" and m["awarded_to"] == other
                else:
                    assert m["status"] == "scheduled" and m["awarded_to"] is None
            else:
                assert m["status"] == "scheduled"
    s = resp["summary"]
    assert s["total"] == 10 and s["scheduled"] + s["forfeit"] == 10 and s["voided"] == 0
    assert s["forfeit"] == sum(1 for m in all_matches(resp) if m["status"] == "forfeit")


def test_round_robin_void_all_and_both_withdrawn():
    resp = generate({"format": "round_robin", "teams": teams(4),
                     "params": {"withdrawals": [{"team_id": "t1", "after_round": 1}],
                                "withdrawal_policy": "void_all"}})
    for m in all_matches(resp):
        if "t1" in (m["home"], m["away"]):
            assert m["status"] == "voided" and m["awarded_to"] is None
    assert resp["summary"]["voided"] == 3 and resp["summary"]["total"] == 6

    resp = generate({"format": "round_robin", "teams": teams(4),
                     "params": {"withdrawals": [{"team_id": "t1", "after_round": 0},
                                                {"team_id": "t2", "after_round": 0}]}})
    both = [m for m in all_matches(resp) if {m["home"], m["away"]} == {"t1", "t2"}]
    assert both[0]["status"] == "voided" and both[0]["awarded_to"] is None
    assert resp["summary"]["forfeit"] == 4 and resp["summary"]["voided"] == 1


def test_round_robin_bad_withdrawal_is_400():
    for w in ({"team_id": "zz", "after_round": 1}, {"team_id": "t1", "after_round": 99}):
        with pytest.raises(APIError) as e:
            generate({"format": "round_robin", "teams": teams(4), "params": {"withdrawals": [w]}})
        assert e.value.status == 400


# --------------------------------------------------------------------------- swiss


def test_swiss_round_one_exact():
    resp = generate({"format": "swiss", "teams": teams(5), "params": {"total_rounds": 3}})
    assert resp["round"] == 1 and resp["total_rounds"] == 3
    assert resp["pairings"] == [
        {"match_id": "SW-R1-M1", "home": "t1", "away": "t3"},
        {"match_id": "SW-R1-M2", "home": "t2", "away": "t4"},
    ]
    assert resp["bye"] == "t5"
    assert [s["team_id"] for s in resp["standings"]] == teams(5)


def test_swiss_default_total_rounds():
    assert generate({"format": "swiss", "teams": teams(8)})["total_rounds"] == 3


def test_swiss_round_two_spec_example():
    resp = generate({"format": "swiss", "teams": teams(5), "params": {
        "total_rounds": 3, "round": 2,
        "history": [{"round": 1, "bye": "t5", "matches": [
            {"home": "t1", "away": "t3", "result": "home"},
            {"home": "t2", "away": "t4", "result": "draw"}]}]}})
    st = {s["team_id"]: s for s in resp["standings"]}
    assert [s["team_id"] for s in resp["standings"][:2]] == ["t1", "t5"]
    assert st["t1"]["score"] == 1.0 and st["t5"]["score"] == 1.0 and st["t2"]["score"] == 0.5
    assert st["t2"]["buchholz"] == 0.5 and st["t1"]["buchholz"] == 0.0
    assert resp["bye"] == "t3"  # lowest score without a bye
    assert resp["pairings"] == [{"match_id": "SW-R2-M1", "home": "t1", "away": "t2"},
                                {"match_id": "SW-R2-M2", "home": "t5", "away": "t4"}]
    score = {k: v["score"] for k, v in st.items()}
    cost = sum(abs(score[p["home"]] - score[p["away"]]) for p in resp["pairings"])
    assert cost == 1.0
    assert cost == brute_force_cost(score, resp["bye"], {frozenset(("t1", "t3")), frozenset(("t2", "t4"))})


def brute_force_cost(score, bye, played):
    names = [t for t in score if t != bye]
    best = None

    def rec(rem, cost):
        nonlocal best
        if not rem:
            best = cost if best is None else min(best, cost)
            return
        a = rem[0]
        for b in rem[1:]:
            if frozenset((a, b)) in played:
                continue
            rec([x for x in rem if x not in (a, b)], cost + abs(score[a] - score[b]))

    rec(names, 0)
    return best


def simulate_swiss(n, rounds, result_fn):
    history = []
    for rnd in range(1, rounds + 1):
        resp = generate({"format": "swiss", "teams": teams(n),
                         "params": {"total_rounds": rounds, "round": rnd, "history": history}})
        seen = [t for p in resp["pairings"] for t in (p["home"], p["away"])]
        if resp["bye"]:
            seen.append(resp["bye"])
        assert sorted(seen) == sorted(teams(n))
        played = {frozenset((m["home"], m["away"])) for h in history for m in h["matches"]}
        for p in resp["pairings"]:
            assert frozenset((p["home"], p["away"])) not in played
        if rnd >= 2:
            score = {s["team_id"]: s["score"] for s in resp["standings"]}
            cost = sum(abs(score[p["home"]] - score[p["away"]]) for p in resp["pairings"])
            assert cost == brute_force_cost(score, resp["bye"], played)
        history.append({"round": rnd, "bye": resp["bye"], "matches": [
            {"home": p["home"], "away": p["away"], "result": result_fn(p)} for p in resp["pairings"]]})
    return history


@pytest.mark.parametrize("n", [4, 5, 6, 7, 8])
def test_swiss_full_tournament_properties(n):
    simulate_swiss(n, n - 1 if n <= 6 else 4, lambda p: "home" if p["home"] < p["away"] else "away")
    byes = [h["bye"] for h in simulate_swiss(n, 3, lambda p: "draw") if h["bye"]]
    assert len(byes) == len(set(byes))


def test_swiss_impossible_pairing_409():
    # t1..t4 have all met each other, so all four would need t5/t6 as opponents.
    history = [
        {"round": 1, "bye": None, "matches": [{"home": "t1", "away": "t2", "result": "home"},
                                               {"home": "t3", "away": "t4", "result": "home"}]},
        {"round": 2, "bye": None, "matches": [{"home": "t1", "away": "t3", "result": "home"},
                                               {"home": "t2", "away": "t4", "result": "home"}]},
        {"round": 3, "bye": None, "matches": [{"home": "t1", "away": "t4", "result": "home"},
                                               {"home": "t2", "away": "t3", "result": "home"}]},
    ]
    with pytest.raises(APIError) as e:
        generate({"format": "swiss", "teams": teams(6),
                  "params": {"total_rounds": 5, "round": 4, "history": history}})
    assert e.value.status == 409 and e.value.code == "NO_VALID_PAIRING"
    assert e.value.details == {"round": 4}


def test_swiss_history_must_be_complete():
    with pytest.raises(APIError) as e:
        generate({"format": "swiss", "teams": teams(4), "params": {"total_rounds": 3, "round": 3,
                                                                    "history": []}})
    assert e.value.status == 400


# --------------------------------------------------------------------------- single elim


def test_single_elim_spec_example_n6():
    resp = generate({"format": "single_elim", "teams": teams(6)})
    assert resp["bracket_size"] == 8 and len(resp["rounds"]) == 3
    r1 = resp["rounds"][0]["matches"]
    assert [(m["home"], m["away"], m["bye"]) for m in r1] == [
        ("t1", None, True), ("t4", "t5", False), ("t2", None, True), ("t3", "t6", False)]
    assert r1[0]["winner"] == "t1" and r1[2]["winner"] == "t2"
    m = r1[1]
    assert m == {"match_id": "R1M2", "bracket": "main", "round": 1, "index": 2, "home": "t4",
                 "away": "t5", "home_seed": 4, "away_seed": 5, "bye": False, "winner": None,
                 "loser": None, "winner_to": {"match_id": "R2M1", "slot": "away"}, "loser_to": None}
    r2 = resp["rounds"][1]["matches"]
    assert r2[0]["home"] == "t1" and r2[0]["away"] is None
    assert r2[1]["home"] == "t2"
    assert resp["rounds"][2]["matches"][0]["winner_to"] is None


def test_single_elim_seed_order_8():
    resp = generate({"format": "single_elim", "teams": teams(8)})
    r1 = resp["rounds"][0]["matches"]
    assert [(m["home_seed"], m["away_seed"]) for m in r1] == [(1, 8), (4, 5), (2, 7), (3, 6)]


def test_single_elim_results_propagate_and_third_place():
    resp = generate({"format": "single_elim", "teams": teams(6), "params": {
        "third_place_match": True,
        "results": [{"match_id": "R1M2", "winner": "t4"}, {"match_id": "R1M4", "winner": "t6"},
                    {"match_id": "R2M1", "winner": "t4"}, {"match_id": "R2M2", "winner": "t2"}]}})
    r2 = resp["rounds"][1]["matches"]
    assert r2[0]["away"] == "t4" and r2[0]["away_seed"] == 4 and r2[0]["loser"] == "t1"
    assert r2[0]["loser_to"] == {"match_id": "TP", "slot": "home"}
    final, tp = resp["rounds"][2]["matches"]
    assert final["home"] == "t4" and final["away"] == "t2"
    assert tp["match_id"] == "TP" and tp["bracket"] == "third_place"
    assert tp["home"] == "t1" and tp["away"] == "t6"


def test_single_elim_bad_result_is_400():
    for res in ({"match_id": "R9M9", "winner": "t1"}, {"match_id": "R1M2", "winner": "t1"},
                {"match_id": "R2M1", "winner": "t1"}):
        with pytest.raises(APIError) as e:
            generate({"format": "single_elim", "teams": teams(6), "params": {"results": [res]}})
        assert e.value.status == 400


@pytest.mark.parametrize("n", [2, 3, 5, 9, 16, 33])
def test_single_elim_structure(n):
    resp = generate({"format": "single_elim", "teams": teams(n)})
    size = resp["bracket_size"]
    assert size >= n and size & (size - 1) == 0 and size // 2 < n
    for r, rd in enumerate(resp["rounds"], 1):
        assert len(rd["matches"]) == size >> r
        for i, m in enumerate(rd["matches"], 1):
            assert m["match_id"] == f"R{r}M{i}"


# --------------------------------------------------------------------------- double elim


def de_matches(resp):
    return ([m for r in resp["winners"] for m in r["matches"]]
            + [m for r in resp["losers"] for m in r["matches"]] + resp["grand_final"])


@pytest.mark.parametrize("n", [3, 4, 5, 8, 12, 16])
@pytest.mark.parametrize("reset", [True, False])
def test_double_elim_counts_and_routing(n, reset):
    resp = generate({"format": "double_elim", "teams": teams(n), "params": {"bracket_reset": reset}})
    size = resp["bracket_size"]
    k = size.bit_length() - 1
    assert len(resp["winners"]) == k
    for r, rd in enumerate(resp["winners"], 1):
        assert len(rd["matches"]) == size >> r
        assert all(m["match_id"] == f"WR{r}M{i}" and m["bracket"] == "winners"
                   for i, m in enumerate(rd["matches"], 1))
        assert all(m["loser_to"] is not None for m in rd["matches"])
    assert len(resp["losers"]) == 2 * (k - 1)
    for lr, rd in enumerate(resp["losers"], 1):
        j = (lr + 1) // 2
        assert len(rd["matches"]) == size >> (j + 1)
        assert all(m["match_id"] == f"LR{lr}M{i}" and m["loser_to"] is None
                   for i, m in enumerate(rd["matches"], 1))
    assert sum(len(rd["matches"]) for rd in resp["losers"]) == size - 2
    assert [m["match_id"] for m in resp["grand_final"]] == (["GF1", "GF2"] if reset else ["GF1"])

    feeds = Counter()
    for m in de_matches(resp):
        for key in ("winner_to", "loser_to"):
            if m[key]:
                feeds[(m[key]["match_id"], m[key]["slot"])] += 1
    by_id = {m["match_id"]: m for m in de_matches(resp)}
    for mid, m in by_id.items():
        if mid.startswith("WR1M"):
            continue
        for slot in ("home", "away"):
            if mid == "GF2":
                continue
            assert feeds[(mid, slot)] == 1, (mid, slot)
    final_wr = resp["winners"][-1]["matches"][0]
    assert final_wr["winner_to"] == {"match_id": "GF1", "slot": "home"}
    lb_final = resp["losers"][-1]["matches"][0]
    assert final_wr["loser_to"] == {"match_id": lb_final["match_id"], "slot": "away"}
    assert lb_final["winner_to"] == {"match_id": "GF1", "slot": "away"}
    for m in de_matches(resp):
        if m["match_id"] not in ("GF1", "GF2"):
            assert m["winner_to"] is not None


def play_out_double(n, reset, gf_winner_side):
    results = []
    resp = generate({"format": "double_elim", "teams": teams(n), "params": {"bracket_reset": reset}})
    for _ in range(200):
        pending = [m for m in de_matches(resp)
                   if m["winner"] is None and m["home"] and m["away"] and m["match_id"] != "GF2"
                   and not (m["match_id"] == "GF1" and any(r["match_id"] == "GF1" for r in results))]
        pending = [m for m in pending if m["match_id"] != "GF1" or
                   all(x["winner"] or x["bye"] for x in de_matches(resp) if x["match_id"] not in ("GF1", "GF2"))]
        if not pending:
            break
        m = pending[0]
        if m["match_id"] == "GF1":
            winner = m[gf_winner_side]
        else:
            winner = m["home"] if m["home_seed"] < m["away_seed"] else m["away"]
        results.append({"match_id": m["match_id"], "winner": winner})
        resp = generate({"format": "double_elim", "teams": teams(n),
                         "params": {"bracket_reset": reset, "results": results}})
    return resp, results


def test_double_elim_bracket_reset_required():
    resp = generate({"format": "double_elim", "teams": teams(4), "params": {"bracket_reset": True}})
    gf2 = resp["grand_final"][1]
    assert gf2["conditional"] is True and gf2["required"] is None

    resp, _ = play_out_double(4, True, "away")
    gf1, gf2 = resp["grand_final"]
    assert gf1["winner"] == gf1["away"]
    assert gf2["required"] is True
    assert {gf2["home"], gf2["away"]} == {gf1["home"], gf1["away"]}

    resp, _ = play_out_double(8, True, "home")
    gf1, gf2 = resp["grand_final"]
    assert gf1["winner"] == gf1["home"] and gf2["required"] is False


def test_double_elim_gf2_result_rejected_when_not_required():
    resp, results = play_out_double(4, True, "home")
    with pytest.raises(APIError) as e:
        generate({"format": "double_elim", "teams": teams(4), "params": {
            "bracket_reset": True, "results": results + [{"match_id": "GF2",
                                                          "winner": resp["grand_final"][0]["home"]}]}})
    assert e.value.status == 400


def test_double_elim_wr1_byes_like_single_elim():
    resp = generate({"format": "double_elim", "teams": teams(6)})
    r1 = resp["winners"][0]["matches"]
    assert [(m["home"], m["away"], m["bye"]) for m in r1] == [
        ("t1", None, True), ("t4", "t5", False), ("t2", None, True), ("t3", "t6", False)]
    assert resp["winners"][1]["matches"][0]["home"] == "t1"


def test_double_elim_full_playout_reaches_grand_final():
    resp, _ = play_out_double(8, False, "home")
    gf1 = resp["grand_final"][0]
    assert gf1["home"] == "t1" and gf1["away"] is not None and gf1["winner"] == "t1"
    losers_in_lb = [m["loser"] for r in resp["losers"] for m in r["matches"]]
    assert len([x for x in losers_in_lb if x]) == 6
    assert sorted(itertools.chain(losers_in_lb, [gf1["loser"]])) == sorted(teams(8)[1:])
