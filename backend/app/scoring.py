"""Event-sourced match scoring (FR-1.1, spec 5.9). The log is append-only; scores are
always rebuilt from it. Every rule comes from the sport config, never from sport names."""
import copy

from . import config
from .common import check_ids, is_id, is_int
from .errors import APIError, validation_error
from .signing import sign

STATUS_EVENTS = {"match_postpone": "postponed", "match_postponed": "postponed", "match_cancel": "cancelled",
                 "match_cancelled": "cancelled", "match_abandon": "abandoned", "match_abandoned": "abandoned"}
EVENT_TYPES = {"match_init", "match_start", "score", "discipline", "tiebreak_winner", "match_end", "compensation"} | set(STATUS_EVENTS)
COMPENSABLE = {"score", "discipline", "tiebreak_winner"}


class ScoringEngine:
    def __init__(self, sports: dict):
        self.sports = sports
        self.matches: dict[str, dict] = {}   # match_id -> stream
        self.events: dict[str, dict] = {}    # event_id -> {"body", "response", "match_id", "type"}

    # ---- streams -------------------------------------------------------
    def create_stream(self, match_id, sport_id, home, away, league_id=None):
        self.matches[match_id] = {"match_id": match_id, "sport_id": sport_id, "home": home,
                                  "away": away, "league_id": league_id, "log": []}

    def version(self, match_id) -> int:
        return len(self.matches[match_id]["log"])

    # ---- append ---------------------------------------------------------
    def validate_shape(self, body):
        if not isinstance(body, dict):
            raise validation_error(["body"])
        bad = [f for f in ("event_id", "match_id") if not is_id(body.get(f))]
        if body.get("type") not in EVENT_TYPES:
            bad.append("type")
        default = {} if body.get("type") in ({"match_start", "match_end"} | set(STATUS_EVENTS)) else None
        payload = body.get("payload", default)
        if not isinstance(payload, dict):
            bad.append("payload")
        if bad:
            raise validation_error(bad)
        t = body["type"]
        if t == "match_init":
            check_ids(payload, "sport_id", "home_team_id", "away_team_id", optional=("league_id",))
            if payload["home_team_id"] == payload["away_team_id"]:
                raise validation_error(["payload.away_team_id"])
        elif t in ("score", "discipline", "tiebreak_winner"):
            if not is_id(payload.get("team_id")):
                raise validation_error(["payload.team_id"])
            if t == "score" and not isinstance(payload.get("event_type"), str):
                raise validation_error(["payload.event_type"])
            if t == "discipline" and not is_int(payload.get("points")):
                raise validation_error(["payload.points"])
        elif t == "compensation":
            if not is_id(payload.get("compensates")):
                raise validation_error(["payload.compensates"])
            if not isinstance(payload.get("reason", ""), str):
                raise validation_error(["payload.reason"])
        return payload

    def is_duplicate(self, body) -> bool:
        stored = self.events.get(body.get("event_id")) if isinstance(body, dict) else None
        return stored is not None and stored["body"] == body

    def append(self, body) -> tuple:
        payload = self.validate_shape(body)
        stored = self.events.get(body["event_id"])
        if stored is not None:
            if stored["body"] == body:
                return 200, copy.deepcopy(stored["response"])
            raise APIError(409, "DUPLICATE_EVENT_ID", "event_id was already used with a different body.",
                           {"event_id": body["event_id"]})
        t, match_id = body["type"], body["match_id"]

        if t == "match_init":
            if payload["sport_id"] not in self.sports:
                raise APIError(404, "SPORT_NOT_FOUND", "Unknown sport.", {"sport_id": payload["sport_id"]})
            if match_id in self.matches:
                raise APIError(409, "MATCH_EXISTS", "Match stream already exists.", {"match_id": match_id})
            self.create_stream(match_id, payload["sport_id"], payload["home_team_id"],
                               payload["away_team_id"], payload.get("league_id"))
            return self._record(body, payload)

        stream = self.matches.get(match_id)
        if stream is None:
            raise APIError(404, "MATCH_NOT_FOUND", "Unknown match.", {"match_id": match_id})
        sport = self.sports[stream["sport_id"]]
        state = self.project(match_id)
        status = state["status"]

        if t in ("score", "discipline", "tiebreak_winner"):
            if payload["team_id"] not in (stream["home"], stream["away"]):
                raise validation_error(["payload.team_id"], "team_id is not a participant of this match.")
            if t == "score" and payload["event_type"] not in sport["scoring_events"]:
                raise APIError(400, "UNKNOWN_EVENT_TYPE", "event_type is not defined for this sport.",
                               {"event_type": payload["event_type"]})
            if status != "in_progress":
                raise APIError(409, "MATCH_NOT_IN_PROGRESS", "Match is not in progress.", {"match_id": match_id})
            if t == "score":
                self._check_limits(sport, stream, state, payload["team_id"])
        elif t == "match_start":
            if status != "upcoming":
                raise APIError(409, "ILLEGAL_TRANSITION", "Only an upcoming match can start.",
                               {"match_id": match_id, "from": status, "to": "in_progress"})
        elif t == "match_end":
            if status != "in_progress":
                raise APIError(409, "ILLEGAL_TRANSITION", "Only an in-progress match can end.",
                               {"match_id": match_id, "from": status, "to": "completed"})
            level = state["home"]["score"] == state["away"]["score"]
            if level and not sport["draw_allowed"] and state["tiebreak_winner_team_id"] is None:
                raise APIError(409, "TIE_NOT_ALLOWED", "Scores are level and draws are not allowed.",
                               {"match_id": match_id})
        elif t in STATUS_EVENTS:
            if status not in ("upcoming", "in_progress"):
                raise APIError(409, "ILLEGAL_TRANSITION", "Only an upcoming or live match may be suspended.")
        elif t == "compensation":
            target = self.events.get(payload["compensates"])
            if target is None:
                raise APIError(404, "EVENT_NOT_FOUND", "Compensated event not found.",
                               {"event_id": payload["compensates"]})
            already = any(e["type"] == "compensation" and e["payload"]["compensates"] == payload["compensates"]
                          for e in stream["log"])
            if target["match_id"] != match_id or target["type"] not in COMPENSABLE or already:
                raise APIError(409, "INVALID_COMPENSATION", "Event cannot be compensated.",
                               {"event_id": payload["compensates"]})
        return self._record(body, payload)

    def _check_limits(self, sport, stream, state, team_id):
        model, periods = sport["scoring_model"], sport["periods"]
        side = state["home"] if team_id == stream["home"] else state["away"]
        if model == "innings":
            max_balls = periods["innings_per_team"] * periods["overs_per_innings"] * periods["balls_per_over"]
            max_wkts = periods["innings_per_team"] * periods["wickets_per_innings"]
            if side["balls"] >= max_balls or side["wickets"] >= max_wkts:
                raise APIError(409, "INNINGS_COMPLETE", "The innings of this team is complete.",
                               {"team_id": team_id})
        elif model == "round":
            need = (periods["best_of"] + 1) // 2
            if state["home"]["score"] >= need or state["away"]["score"] >= need:
                raise APIError(409, "SERIES_ALREADY_DECIDED", "The series is already decided.",
                               {"match_id": stream["match_id"]})

    def _record(self, body, payload) -> tuple:
        stream = self.matches[body["match_id"]]
        signature = sign(config.DAY1_SALT, body["event_id"], payload)
        entry = {"event_id": body["event_id"], "type": body["type"], "payload": copy.deepcopy(payload),
                 "signature": signature}
        stream["log"].append(entry)
        seq = len(stream["log"])
        response = {"event_id": body["event_id"], "match_id": body["match_id"], "type": body["type"],
                    "sequence": seq, "match_version": seq, "signature": signature}
        self.events[body["event_id"]] = {"body": copy.deepcopy(body), "response": response,
                                         "match_id": body["match_id"], "type": body["type"]}
        return 201, copy.deepcopy(response)

    # ---- projection -------------------------------------------------------
    def project(self, match_id) -> dict:
        stream = self.matches[match_id]
        sport = self.sports[stream["sport_id"]]
        model, events_cfg = sport["scoring_model"], sport["scoring_events"]
        log = stream["log"]
        compensated_by = {e["payload"]["compensates"]: e["event_id"] for e in log if e["type"] == "compensation"}
        status = "upcoming"
        sides = {stream["home"]: _blank(model), stream["away"]: _blank(model)}
        tiebreak = None
        for e in log:
            t = e["type"]
            if t == "match_start":
                status = "in_progress"
            elif t == "match_end":
                status = "completed"
            elif t in STATUS_EVENTS:
                status = STATUS_EVENTS[t]
            if e["event_id"] in compensated_by or t == "compensation":
                continue
            if t == "score":
                rule = events_cfg[e["payload"]["event_type"]]
                s = sides[e["payload"]["team_id"]]
                if model == "event":
                    s["score"] += rule["points"]
                elif model == "innings":
                    s["score"] += rule["runs"]
                    s["balls"] += 1 if rule["legal_ball"] else 0
                    s["wickets"] += 1 if rule["wicket"] else 0
                else:
                    s["score"] += rule["rounds"]
            elif t == "discipline":
                sides[e["payload"]["team_id"]]["fair_play"] += e["payload"]["points"]
            elif t == "tiebreak_winner":
                tiebreak = e["payload"]["team_id"]
        home, away = sides[stream["home"]], sides[stream["away"]]
        if model == "innings":
            bpo = sport["periods"]["balls_per_over"]
            for s in (home, away):
                s["overs"] = "%d.%d" % (s["balls"] // bpo, s["balls"] % bpo)
        if home["score"] > away["score"]:
            winner = stream["home"]
        elif away["score"] > home["score"]:
            winner = stream["away"]
        else:
            winner = tiebreak
        if status != "completed":
            outcome = "pending"
        elif winner == stream["home"]:
            outcome = "home_win"
        elif winner == stream["away"]:
            outcome = "away_win"
        else:
            outcome = "draw" if sport["draw_allowed"] else "undecided"
        return {
            "match_id": match_id, "sport_id": stream["sport_id"], "league_id": stream["league_id"],
            "status": status, "outcome": outcome, "winner_team_id": winner,
            "tiebreak_winner_team_id": tiebreak,
            "home": {"team_id": stream["home"], **home},
            "away": {"team_id": stream["away"], **away},
            "version": len(log),
            "events": [{"sequence": i + 1, "event_id": e["event_id"], "type": e["type"],
                        "payload": copy.deepcopy(e["payload"]), "signature": e["signature"],
                        "compensated": e["event_id"] in compensated_by,
                        "compensated_by": compensated_by.get(e["event_id"])} for i, e in enumerate(log)],
        }

    def score(self, match_id) -> dict:
        if match_id not in self.matches:
            raise APIError(404, "MATCH_NOT_FOUND", "Unknown match.", {"match_id": match_id})
        return self.project(match_id)


def _blank(model):
    if model == "innings":
        return {"score": 0, "wickets": 0, "balls": 0, "overs": "0.0", "fair_play": 0}
    return {"score": 0, "wickets": None, "balls": None, "overs": None, "fair_play": 0}
