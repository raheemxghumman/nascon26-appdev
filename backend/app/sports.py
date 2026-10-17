"""Sport configuration as data (FR-1.1, spec 5.6). No sport-specific branching anywhere."""
import copy
import re

from .common import is_int
from .errors import APIError, validation_error

SPORT_ID_RE = re.compile(r"^[a-z0-9_-]{2,40}$")
EVENT_KEY_RE = re.compile(r"^[a-z0-9_]{1,40}$")
TIE_BREAKS = ["h2h_points", "h2h_diff", "overall_diff", "scored", "fair_play", "draw_lots"]
OVERTIME_POLICIES = {"none", "extra_time", "shootout", "golden_score", "super_over"}

BASELINE_SPORTS = [
    {"sport_id": "football", "name": "Football", "scoring_model": "event",
     "periods": {"count": 2, "duration_minutes": 45},
     "scoring_events": {"goal": {"points": 1}},
     "draw_allowed": True, "overtime": {"policy": "none"},
     "tie_break_order": list(TIE_BREAKS),
     "roster": {"min_squad_size": 11, "max_squad_size": 25, "required_positions": {"gk": 1}}},
    {"sport_id": "basketball", "name": "Basketball", "scoring_model": "event",
     "periods": {"count": 4, "duration_minutes": 12},
     "scoring_events": {"free_throw": {"points": 1}, "two_pointer": {"points": 2}, "three_pointer": {"points": 3}},
     "draw_allowed": False, "overtime": {"policy": "extra_time", "duration_minutes": 5},
     "tie_break_order": list(TIE_BREAKS),
     "roster": {"min_squad_size": 5, "max_squad_size": 15, "required_positions": {}}},
    {"sport_id": "cricket", "name": "Cricket", "scoring_model": "innings",
     "periods": {"innings_per_team": 1, "overs_per_innings": 20, "balls_per_over": 6, "wickets_per_innings": 10},
     "scoring_events": {
         "dot_ball": {"runs": 0, "legal_ball": True, "wicket": False},
         "single": {"runs": 1, "legal_ball": True, "wicket": False},
         "two": {"runs": 2, "legal_ball": True, "wicket": False},
         "four": {"runs": 4, "legal_ball": True, "wicket": False},
         "six": {"runs": 6, "legal_ball": True, "wicket": False},
         "wide": {"runs": 1, "legal_ball": False, "wicket": False},
         "no_ball": {"runs": 1, "legal_ball": False, "wicket": False},
         "wicket": {"runs": 0, "legal_ball": True, "wicket": True}},
     "draw_allowed": True, "overtime": {"policy": "super_over"},
     "tie_break_order": list(TIE_BREAKS),
     "roster": {"min_squad_size": 11, "max_squad_size": 18, "required_positions": {"wicketkeeper": 1}}},
    {"sport_id": "esports", "name": "Esports", "scoring_model": "round",
     "periods": {"best_of": 3},
     "scoring_events": {"round_win": {"rounds": 1}},
     "draw_allowed": False, "overtime": {"policy": "none"},
     "tie_break_order": list(TIE_BREAKS),
     "roster": {"min_squad_size": 5, "max_squad_size": 8, "required_positions": {}}},
]


def _pos_int(v, minimum=1) -> bool:
    return is_int(v) and v >= minimum


def validate_sport(body) -> dict:
    """Return the normalised config or raise 400 VALIDATION_ERROR listing bad fields."""
    if not isinstance(body, dict):
        raise validation_error(["body"])
    bad = []
    sid = body.get("sport_id")
    if not isinstance(sid, str) or not SPORT_ID_RE.match(sid):
        bad.append("sport_id")
    name = body.get("name")
    if not isinstance(name, str) or not 1 <= len(name) <= 80:
        bad.append("name")
    model = body.get("scoring_model")
    if model not in ("event", "innings", "round"):
        bad.append("scoring_model")

    periods = body.get("periods")
    if not isinstance(periods, dict):
        bad.append("periods")
    elif model == "event":
        if not (_pos_int(periods.get("count")) and _pos_int(periods.get("duration_minutes"))):
            bad.append("periods")
    elif model == "innings":
        keys = ("innings_per_team", "overs_per_innings", "balls_per_over", "wickets_per_innings")
        if not all(_pos_int(periods.get(k)) for k in keys):
            bad.append("periods")
    elif model == "round":
        b = periods.get("best_of")
        if not (_pos_int(b) and b % 2 == 1):
            bad.append("periods")

    events = body.get("scoring_events")
    if not isinstance(events, dict) or not events:
        bad.append("scoring_events")
    else:
        for key, val in events.items():
            ok = isinstance(key, str) and EVENT_KEY_RE.match(key) and isinstance(val, dict)
            if ok and model == "event":
                ok = _pos_int(val.get("points"))
            elif ok and model == "innings":
                ok = (_pos_int(val.get("runs"), 0) and isinstance(val.get("legal_ball"), bool)
                      and isinstance(val.get("wicket"), bool))
            elif ok and model == "round":
                ok = _pos_int(val.get("rounds"))
            if not ok:
                bad.append("scoring_events")
                break

    if not isinstance(body.get("draw_allowed"), bool):
        bad.append("draw_allowed")
    ot = body.get("overtime")
    if not (isinstance(ot, dict) and ot.get("policy") in OVERTIME_POLICIES
            and (ot.get("duration_minutes") is None or _pos_int(ot.get("duration_minutes"), 0))):
        bad.append("overtime")

    tbo = body.get("tie_break_order")
    if tbo is not None and not (isinstance(tbo, list) and all(t in TIE_BREAKS for t in tbo)
                                and len(set(tbo)) == len(tbo)):
        bad.append("tie_break_order")

    roster = body.get("roster")
    if not (isinstance(roster, dict) and _pos_int(roster.get("min_squad_size"))
            and _pos_int(roster.get("max_squad_size"))
            and roster["min_squad_size"] <= roster["max_squad_size"]
            and isinstance(roster.get("required_positions"), dict)
            and all(isinstance(k, str) and _pos_int(v, 0) for k, v in roster["required_positions"].items())):
        bad.append("roster")
    if bad:
        raise validation_error(bad)

    config = copy.deepcopy(body)
    config["tie_break_order"] = resolve_tie_breaks(tbo)
    return config


def resolve_tie_breaks(order) -> list:
    order = list(order) if order else list(TIE_BREAKS)
    if "draw_lots" in order:
        order.remove("draw_lots")
    return order + ["draw_lots"]


def create_sport(sports: dict, body) -> dict:
    config = validate_sport(body)
    if config["sport_id"] in sports:
        raise APIError(409, "SPORT_EXISTS", f"Sport {config['sport_id']} already exists.",
                       {"sport_id": config["sport_id"]})
    sports[config["sport_id"]] = config
    return {"sport_id": config["sport_id"], "status": "created", "config": config}
