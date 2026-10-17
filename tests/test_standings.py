from app.signing import lots_key
from app.standings import compute_standings

FOOTBALL = {"sport_id": "football", "scoring_model": "event", "periods": {"count": 2, "duration_minutes": 45}}
CRICKET = {"sport_id": "cricket", "scoring_model": "innings",
           "periods": {"innings_per_team": 1, "overs_per_innings": 20, "balls_per_over": 6, "wickets_per_innings": 10}}
ESPORTS = {"sport_id": "esports", "scoring_model": "round", "periods": {"best_of": 3}}


def league(teams, spots=2, order=None, seed=42, league_id="lg-1", sport_id="football"):
    return {"league_id": league_id, "sport_id": sport_id, "teams": teams, "fixtures": [],
            "points": {"win": 3, "draw": 1, "loss": 0},
            "tie_break_order": order or ["h2h_points", "h2h_diff", "overall_diff", "scored", "fair_play", "draw_lots"],
            "qualification": {"spots": spots}, "lots_seed": seed}


def m(mid, home, away, hs=None, as_=None, status="completed", outcome=None, hfp=0, afp=0, **extra):
    if status == "completed" and outcome is None:
        outcome = "home_win" if hs > as_ else "away_win" if as_ > hs else "draw"
    return {"match_id": mid, "home": home, "away": away, "status": status, "outcome": outcome or "pending",
            "home_score": hs or 0, "away_score": as_ or 0, "home_balls": extra.get("hb"), "away_balls": extra.get("ab"),
            "home_wickets": extra.get("hw"), "away_wickets": extra.get("aw"),
            "home_fair_play": hfp, "away_fair_play": afp}


def by_team(result):
    return {r["team_id"]: r for r in result["table"]}


def test_basic_table_and_counts():
    res = compute_standings(league(["t1", "t2", "t3"]), FOOTBALL, [
        m("m1", "t1", "t2", 2, 1, afp=-1), m("m2", "t2", "t3", 1, 1), m("m3", "t3", "t1", 0, 0, status="upcoming"),
    ])
    t = by_team(res)
    assert [r["team_id"] for r in res["table"]] == ["t1", "t3", "t2"]  # t3 0 diff beats t2 -1
    assert t["t3"]["resolved_by"] == "overall_diff" and t["t2"]["resolved_by"] is None
    assert t["t1"] == {**t["t1"], "played": 1, "won": 1, "drawn": 0, "lost": 0, "scored": 2, "conceded": 1,
                       "diff": 1, "points": 3, "fair_play": 0, "rank": 1, "resolved_by": None}
    assert t["t2"]["points"] == 1 and t["t2"]["fair_play"] == -1 and t["t2"]["lost"] == 1
    assert res["qualification_spots"] == 2 and res["sport_id"] == "football"


def test_h2h_present_for_every_ordered_pair_with_zeros():
    res = compute_standings(league(["t1", "t2", "t3"]), FOOTBALL, [m("m1", "t1", "t2", 2, 1)])
    h = res["h2h"]
    assert h["t1"]["t2"] == {"played": 1, "points": 3, "scored": 2, "conceded": 1}
    assert h["t2"]["t1"] == {"played": 1, "points": 0, "scored": 1, "conceded": 2}
    assert h["t1"]["t3"] == {"played": 0, "points": 0, "scored": 0, "conceded": 0}
    assert "t1" not in h["t1"] and set(h) == {"t1", "t2", "t3"}


def test_three_way_tie_h2h_mini_league_with_restart_on_split():
    # t1, t2, t3 each beat one another in a cycle and all beat t4 -> 9 points each.
    # Mini-league h2h_points all 3; h2h_diff splits t1 (+2) from t2, t3 (0, -2)...
    matches = [
        m("a", "t1", "t2", 3, 0), m("b", "t2", "t3", 1, 0), m("c", "t3", "t1", 1, 0),
        m("d", "t1", "t4", 1, 0), m("e", "t2", "t4", 5, 0), m("f", "t3", "t4", 1, 0),
    ]
    res = compute_standings(league(["t1", "t2", "t3", "t4"]), FOOTBALL, matches)
    order = [r["team_id"] for r in res["table"]]
    # h2h diffs among {t1,t2,t3}: t1 = 3-1 = +2, t2 = 1-3 = -2, t3 = 1-1 = 0
    assert order == ["t1", "t3", "t2", "t4"]
    t = by_team(res)
    assert t["t1"]["resolved_by"] == "h2h_diff"
    assert t["t3"]["resolved_by"] == "h2h_diff"
    assert t["t2"]["resolved_by"] is None


def test_restart_from_first_criterion_after_split():
    # 3 teams tied on 6 pts; h2h_points splits t3 (6 h2h) off; t1 vs t2 resolved again from
    # h2h_points among only {t1,t2}: t2 beat t1.
    matches = [
        m("a", "t3", "t1", 1, 0), m("b", "t3", "t2", 1, 0),
        m("c", "t2", "t1", 1, 0),
        m("d", "t1", "t4", 9, 0), m("e", "t1", "t5", 9, 0),
        m("f", "t2", "t4", 1, 0),
        m("g", "t4", "t3", 5, 0), m("h", "t5", "t3", 5, 0),
    ]
    res = compute_standings(league(["t1", "t2", "t3", "t4", "t5"]), FOOTBALL, matches)
    t = by_team(res)
    assert t["t1"]["points"] == t["t2"]["points"] == t["t3"]["points"] == 6
    order = [r["team_id"] for r in res["table"]][:3]
    # among {t1,t2,t3}: t3 6 pts, t2 3 pts, t1 0 pts -> h2h_points fully splits
    assert order == ["t3", "t2", "t1"]
    assert t["t3"]["resolved_by"] == "h2h_points"


def test_draw_lots_vector_order():
    res = compute_standings(league(["t1", "t2", "t3"], spots=1), FOOTBALL, [])
    assert [r["team_id"] for r in res["table"]] == ["t1", "t3", "t2"]
    assert by_team(res)["t1"]["resolved_by"] == "draw_lots"
    assert by_team(res)["t2"]["resolved_by"] is None
    keys = sorted(["t1", "t2", "t3"], key=lambda x: lots_key(42, "lg-1", x))
    assert keys == ["t1", "t3", "t2"]


def test_custom_tie_break_order_appends_draw_lots():
    # equal points, scored decides because it's first in the custom order
    matches = [m("a", "t1", "t3", 1, 0), m("b", "t2", "t3", 4, 3)]
    res = compute_standings(league(["t1", "t2", "t3"], order=["scored"]), FOOTBALL, matches)
    assert [r["team_id"] for r in res["table"]][:2] == ["t2", "t1"]
    assert by_team(res)["t2"]["resolved_by"] == "scored"


def test_fair_play_tie_break():
    matches = [m("a", "t1", "t3", 1, 0, hfp=-2), m("b", "t2", "t4", 1, 0, hfp=-1)]
    res = compute_standings(league(["t1", "t2", "t3", "t4"], order=["fair_play"]), FOOTBALL, matches)
    assert [r["team_id"] for r in res["table"]][:2] == ["t2", "t1"]
    assert by_team(res)["t1"]["fair_play"] == -2


def test_undecided_and_unfinished_not_counted():
    matches = [
        m("a", "t1", "t2", 1, 1, outcome="undecided"),
        m("b", "t1", "t2", 2, 0, status="in_progress", outcome="pending"),
    ]
    res = compute_standings(league(["t1", "t2"], spots=1), FOOTBALL, matches)
    t = by_team(res)
    assert t["t1"]["played"] == 0 and t["t1"]["points"] == 0 and t["t1"]["scored"] == 0
    assert res["h2h"]["t1"]["t2"]["played"] == 0


def test_tiebreak_win_counts_as_win_from_outcome():
    res = compute_standings(league(["t1", "t2"], spots=1), FOOTBALL, [m("a", "t1", "t2", 1, 1, outcome="away_win")])
    t = by_team(res)
    assert t["t2"]["won"] == 1 and t["t2"]["points"] == 3 and t["t1"]["lost"] == 1


def test_innings_net_run_rate_with_all_out_rule():
    # t1: 150 runs in 120 balls (20 overs); t2: 100 all out (10 wickets) in 60 balls -> counts as 20 overs.
    matches = [m("a", "t1", "t2", 150, 100, hb=120, ab=60, hw=3, aw=10)]
    res = compute_standings(league(["t1", "t2"], spots=1, sport_id="cricket"), CRICKET, matches)
    t = by_team(res)
    assert t["t1"]["diff"] == round(150 / 20 - 100 / 20, 3) == 2.5
    assert t["t2"]["diff"] == -2.5


def test_innings_nrr_partial_overs_rounding():
    # t1 chased 121 in 15.4 overs (94 balls), t2 made 120/5 in 20 overs.
    matches = [m("a", "t2", "t1", 120, 121, hb=120, ab=94, hw=5, aw=4)]
    res = compute_standings(league(["t1", "t2"], spots=1, sport_id="cricket"), CRICKET, matches)
    t = by_team(res)
    expected = round(121 / (94 / 6) - 120 / 20, 3)
    assert t["t1"]["diff"] == expected
    assert t["t2"]["diff"] == round(120 / 20 - 121 / (94 / 6), 3)


def test_innings_zero_overs_guarded():
    res = compute_standings(league(["t1", "t2"], spots=1, sport_id="cricket"), CRICKET, [])
    assert by_team(res)["t1"]["diff"] == 0


def test_round_model_map_differential():
    matches = [m("a", "t1", "t2", 2, 1), m("b", "t2", "t3", 2, 0)]
    res = compute_standings(league(["t1", "t2", "t3"], sport_id="esports"), ESPORTS, matches)
    t = by_team(res)
    assert t["t1"]["diff"] == 1 and t["t2"]["diff"] == 1 and t["t3"]["diff"] == -2


def test_qualification_statuses():
    # 4 teams, 2 spots. t1 has 9 pts and no games left; t4 has 0 and one game left.
    matches = [
        m("a", "t1", "t2", 1, 0), m("b", "t1", "t3", 1, 0), m("c", "t1", "t4", 1, 0),
        m("d", "t2", "t3", 1, 0),
        m("e", "t2", "t4", 0, 0, status="upcoming"),
        m("f", "t3", "t4", 0, 0, status="upcoming"),
    ]
    res = compute_standings(league(["t1", "t2", "t3", "t4"], spots=2), FOOTBALL, matches)
    t = by_team(res)
    # max: t1 9, t2 3+3=6, t3 0+3=3, t4 0+6=6
    assert t["t1"]["status"] == "clinched"        # others with max >= 9: none
    assert t["t2"]["status"] == "still_possible"  # t1(9), t4(6) have max >= 3 -> 2, not < 2
    assert t["t3"]["status"] == "still_possible"  # only t1 (9) has points > max(t3)=3
    assert t["t4"]["status"] == "still_possible"


def test_qualification_eliminated_requires_k_teams_strictly_above_max():
    matches = [m("a", "t1", "t3", 1, 0), m("b", "t2", "t3", 1, 0)]
    res = compute_standings(league(["t1", "t2", "t3"], spots=2), FOOTBALL, matches)
    t = by_team(res)
    assert t["t3"]["status"] == "eliminated"
    assert t["t1"]["status"] == "clinched" and t["t2"]["status"] == "clinched"


def test_subgroup_restarts_at_first_criterion():
    # Cycle among t1,t2,t3 (h2h points and diff all equal); overall_diff splits t3 off;
    # {t1,t2} must restart at h2h_points (t1 beat t2), not continue to scored.
    matches = [
        m("a", "t1", "t2", 1, 0), m("b", "t2", "t3", 1, 0), m("c", "t3", "t1", 1, 0),
        m("d", "t1", "t4", 1, 0), m("e", "t2", "t4", 1, 0), m("f", "t3", "t4", 5, 0),
    ]
    res = compute_standings(league(["t1", "t2", "t3", "t4"]), FOOTBALL, matches)
    assert [r["team_id"] for r in res["table"]] == ["t3", "t1", "t2", "t4"]
    t = by_team(res)
    assert t["t3"]["resolved_by"] == "overall_diff"
    assert t["t1"]["resolved_by"] == "h2h_points"
    assert t["t2"]["resolved_by"] is None
