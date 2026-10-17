"""Roster scenarios, transfers, loans, releases and the immutable audit trail (spec 5.11)."""
import copy
import json
import re
import threading
from datetime import date, datetime, timedelta, timezone

from .errors import APIError, validation_error

ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")
ROLES = {"captain", "vice_captain", "starter", "substitute"}
TYPES = {"transfer", "loan", "release"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_date(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _is_id(value) -> bool:
    return isinstance(value, str) and bool(ID_RE.match(value))


def _canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class RosterService:
    def __init__(self):
        self.lock = threading.RLock()
        self.reset()

    def reset(self) -> None:
        with self.lock:
            self.leagues = {}    # league_id -> league config with squads and matches
            self.players = {}    # player_id -> player record with registration
            self.audit = {}      # player_id -> [audit entries], oldest first
            self.requests = {}   # request_id -> (canonical body, stored response)
            self.audit_counter = 0

    # ---------- setup ----------

    def setup(self, body: dict, sports: dict) -> dict:
        if not isinstance(body, dict):
            raise validation_error(["body"])
        league = body.get("league")
        squads = body.get("squads", [])
        players = body.get("players", [])
        matches = body.get("matches_in_progress", [])
        bad = []
        if not isinstance(league, dict):
            raise validation_error(["league"])
        for f in ("league_id", "tenant_id", "sport_id"):
            if not _is_id(league.get(f)):
                bad.append(f"league.{f}")
        window = league.get("transfer_window")
        if not isinstance(window, dict) or _parse_date(window.get("open")) is None \
                or _parse_date(window.get("close")) is None:
            bad.append("league.transfer_window")
        if "max_squad_size" in league and league["max_squad_size"] is not None and (
                not isinstance(league["max_squad_size"], int) or isinstance(league["max_squad_size"], bool)
                or league["max_squad_size"] < 1):
            bad.append("league.max_squad_size")
        if "required_positions" in league and league["required_positions"] is not None and \
                not isinstance(league["required_positions"], dict):
            bad.append("league.required_positions")
        if not isinstance(squads, list) or not all(isinstance(s, dict) and _is_id(s.get("squad_id")) for s in squads):
            bad.append("squads")
        if not isinstance(players, list) or not all(
                isinstance(p, dict) and _is_id(p.get("player_id")) and _is_id(p.get("squad_id"))
                and isinstance(p.get("position"), str) for p in players):
            bad.append("players")
        if not isinstance(matches, list) or not all(
                isinstance(m, dict) and _is_id(m.get("match_id")) for m in matches):
            bad.append("matches_in_progress")
        if bad:
            raise validation_error(bad)
        for p in players:
            if p.get("role", "starter") not in ROLES:
                raise validation_error(["players.role"])

        sport = sports.get(league["sport_id"]) if sports else None
        if sport is None and ("max_squad_size" not in league or "required_positions" not in league):
            raise APIError(404, "SPORT_NOT_FOUND", f"Sport {league['sport_id']} does not exist.",
                           {"sport_id": league["sport_id"]})
        sport_roster = (sport or {}).get("roster", {})
        max_size = league.get("max_squad_size")
        if max_size is None:
            max_size = sport_roster.get("max_squad_size", 10**9)
        required = league.get("required_positions")
        if required is None:
            required = sport_roster.get("required_positions", {})

        squad_map = {}
        for s in squads:
            squad_map[s["squad_id"]] = {
                "squad_id": s["squad_id"],
                "club_id": s.get("club_id"),
                "tenant_id": s.get("tenant_id", league["tenant_id"]),
                "name": s.get("name", s["squad_id"]),
            }
        for p in players:
            if p["squad_id"] not in squad_map:
                raise APIError(404, "SQUAD_NOT_FOUND", f"Squad {p['squad_id']} does not exist.",
                               {"squad_id": p["squad_id"]})

        league_id = league["league_id"]
        with self.lock:
            # Re-sending the same league replaces its roster state.
            for pid in [pid for pid, rec in self.players.items() if rec["league_id"] == league_id]:
                del self.players[pid]
                self.audit.pop(pid, None)
            self.leagues[league_id] = {
                "league_id": league_id,
                "tenant_id": league["tenant_id"],
                "sport_id": league["sport_id"],
                "window_open": _parse_date(window["open"]),
                "window_close": _parse_date(window["close"]),
                "max_squad_size": max_size,
                "required_positions": dict(required),
                "squads": squad_map,
                "matches_in_progress": [
                    {"match_id": m["match_id"], "home_squad_id": m.get("home_squad_id"),
                     "away_squad_id": m.get("away_squad_id")} for m in matches],
            }
            counts = {sid: 0 for sid in squad_map}
            for p in players:
                self.players[p["player_id"]] = {
                    "player_id": p["player_id"],
                    "name": p.get("name", p["player_id"]),
                    "position": p["position"],
                    "league_id": league_id,
                    "reg": {"squad_id": p["squad_id"], "parent_squad_id": None,
                            "registration_type": "initial", "start_date": None,
                            "loan_end_date": None, "role": p.get("role", "starter")},
                }
                self.audit.setdefault(p["player_id"], [])
                counts[p["squad_id"]] += 1
        return {"league_id": league_id, "status": "configured", "squad_counts": counts}

    # ---------- state helpers ----------

    def _effective(self, player: dict, on: date) -> dict | None:
        """Registration as of a date, applying an expired loan's automatic return."""
        reg = player["reg"]
        if reg is None:
            return None
        if reg["registration_type"] == "loan" and reg["loan_end_date"] is not None \
                and on > _parse_date(reg["loan_end_date"]):
            return {"squad_id": reg["parent_squad_id"], "parent_squad_id": None,
                    "registration_type": "loan_return", "start_date": None,
                    "loan_end_date": None, "role": "substitute"}
        return reg

    def _squad_count(self, league_id: str, squad_id: str, on: date, position: str | None = None,
                     exclude: str | None = None) -> int:
        n = 0
        for pid, rec in self.players.items():
            if rec["league_id"] != league_id or pid == exclude:
                continue
            reg = self._effective(rec, on)
            if reg is not None and reg["squad_id"] == squad_id and (position is None or rec["position"] == position):
                n += 1
        return n

    def _append_audit(self, entry: dict) -> dict:
        self.audit_counter += 1
        entry = {"audit_id": f"au-{self.audit_counter:04d}", **entry}
        self.audit.setdefault(entry["player_id"], []).append(entry)
        return entry

    def _materialize_return(self, player: dict, on: date, now_iso: str) -> None:
        """Write the loan_return entry once, when a loan has ended by `on`."""
        reg = player["reg"]
        if reg is None or reg["registration_type"] != "loan" or on <= _parse_date(reg["loan_end_date"]):
            return
        return_date = _parse_date(reg["loan_end_date"]) + timedelta(days=1)
        self._append_audit({
            "action": "loan_return", "player_id": player["player_id"], "league_id": player["league_id"],
            "from_squad_id": reg["squad_id"], "to_squad_id": reg["parent_squad_id"],
            "effective_date": return_date.isoformat(), "state": "active",
            "who": "system", "when": now_iso, "why": "Loan ended",
        })
        player["reg"] = {"squad_id": reg["parent_squad_id"], "parent_squad_id": None,
                         "registration_type": "loan_return", "start_date": return_date.isoformat(),
                         "loan_end_date": None, "role": "substitute"}

    # ---------- transfer ----------

    def is_duplicate(self, body: dict) -> bool:
        with self.lock:
            rid = body.get("request_id") if isinstance(body, dict) else None
            stored = self.requests.get(rid)
            return stored is not None and stored[0] == _canonical(body)

    def _validate(self, body):
        if not isinstance(body, dict):
            raise validation_error(["body"])
        bad = []
        for f in ("request_id", "league_id", "player_id", "from_squad_id"):
            if not _is_id(body.get(f)):
                bad.append(f)
        kind = body.get("type")
        if kind not in TYPES:
            bad.append("type")
        eff = _parse_date(body.get("effective_date"))
        if eff is None:
            bad.append("effective_date")
        if kind in ("transfer", "loan") and not _is_id(body.get("to_squad_id")):
            bad.append("to_squad_id")
        if kind == "loan":
            end = _parse_date(body.get("loan_end_date"))
            if end is None or (eff is not None and end <= eff):
                bad.append("loan_end_date")
        for f in ("reason", "requested_by"):
            if f in body and body[f] is not None and not isinstance(body[f], str):
                bad.append(f)
        if bad:
            raise validation_error(bad)
        return kind, eff

    def transfer(self, body: dict, now_iso: str | None = None) -> tuple[int, dict]:
        with self.lock:
            if isinstance(body, dict) and isinstance(body.get("request_id"), str) \
                    and body["request_id"] in self.requests:
                stored_body, stored_resp = self.requests[body["request_id"]]
                if stored_body == _canonical(body):
                    return 200, copy.deepcopy(stored_resp)
                raise validation_error(["request_id"], "request_id was already used with a different body.")

            kind, eff = self._validate(body)
            now_iso = now_iso or _now_iso()

            # 2. existence
            league = self.leagues.get(body["league_id"])
            if league is None:
                raise APIError(404, "LEAGUE_NOT_FOUND", f"League {body['league_id']} does not exist.",
                               {"league_id": body["league_id"]})
            player = self.players.get(body["player_id"])
            if player is None:
                raise APIError(404, "PLAYER_NOT_FOUND", f"Player {body['player_id']} does not exist.",
                               {"player_id": body["player_id"]})
            from_id = body["from_squad_id"]
            to_id = body.get("to_squad_id") if kind != "release" else None
            for sid in (from_id, to_id):
                if sid is not None and sid not in league["squads"]:
                    raise APIError(404, "SQUAD_NOT_FOUND", f"Squad {sid} does not exist.", {"squad_id": sid})

            # 3. tenant isolation
            for sid in (from_id, to_id):
                if sid is not None and league["squads"][sid]["tenant_id"] != league["tenant_id"]:
                    raise APIError(409, "CROSS_TENANT_TRANSFER",
                                   f"Squad {sid} belongs to another tenant.", {"squad_id": sid})

            # 4. current squad
            reg = self._effective(player, eff) if player["league_id"] == league["league_id"] else None
            current = reg["squad_id"] if reg else None
            if current != from_id:
                raise APIError(409, "NOT_IN_SQUAD",
                               f"Player {player['player_id']} is not in squad {from_id}.",
                               {"player_id": player["player_id"], "squad_id": from_id,
                                "current_squad_id": current})

            # 5. transfer window (release allowed any day)
            if kind != "release" and not (league["window_open"] <= eff <= league["window_close"]):
                raise APIError(409, "TRANSFER_WINDOW_CLOSED",
                               f"{eff.isoformat()} is outside the transfer window.",
                               {"effective_date": eff.isoformat(),
                                "window_open": league["window_open"].isoformat(),
                                "window_close": league["window_close"].isoformat()})

            # 6. loaned players cannot move
            if reg["registration_type"] == "loan":
                raise APIError(409, "PLAYER_ON_LOAN", f"Player {player['player_id']} is on loan.",
                               {"player_id": player["player_id"], "parent_squad_id": reg["parent_squad_id"]})

            # 7. destination capacity
            if kind != "release":
                if self._squad_count(league["league_id"], to_id, eff) + 1 > league["max_squad_size"]:
                    raise APIError(409, "SQUAD_FULL", f"Squad {to_id} is full.",
                                   {"squad_id": to_id, "max_squad_size": league["max_squad_size"]})

            # 8. minimum positions kept in the source squad
            position = player["position"]
            need = league["required_positions"].get(position, 0)
            remaining = self._squad_count(league["league_id"], from_id, eff, position, exclude=player["player_id"])
            if remaining < need:
                raise APIError(409, "MIN_POSITION_VIOLATION",
                               f"Squad {from_id} would drop below {need} {position}.",
                               {"squad_id": from_id, "position": position, "required": need,
                                "remaining": remaining})

            # Accepted: record any implicit loan return first, then the new change.
            self._materialize_return(player, eff, now_iso)
            blocking = None
            for m in league["matches_in_progress"]:
                if from_id in (m["home_squad_id"], m["away_squad_id"]):
                    blocking = m["match_id"]
                    break
            state = "deferred_until_match_end" if blocking else "active"

            if kind == "release":
                player["reg"] = None
                registration = None
            else:
                player["reg"] = {
                    "squad_id": to_id,
                    "parent_squad_id": from_id if kind == "loan" else None,
                    "registration_type": kind,
                    "start_date": eff.isoformat(),
                    "loan_end_date": body.get("loan_end_date") if kind == "loan" else None,
                    "role": "substitute",
                }
                registration = {"player_id": player["player_id"], "league_id": league["league_id"],
                                **player["reg"]}
            entry = self._append_audit({
                "action": kind, "player_id": player["player_id"], "league_id": league["league_id"],
                "from_squad_id": from_id, "to_squad_id": to_id, "effective_date": eff.isoformat(),
                "state": state, "who": body.get("requested_by") or "unknown", "when": now_iso,
                "why": body.get("reason") or "",
            })
            resp = {"request_id": body["request_id"], "status": "accepted", "state": state,
                    "blocking_match_id": blocking, "registration": registration,
                    "audit_entry": dict(entry)}
            self.requests[body["request_id"]] = (_canonical(body), copy.deepcopy(resp))
            return 201, resp

    # ---------- history ----------

    def history(self, player_id: str, as_of: str | None) -> dict:
        with self.lock:
            player = self.players.get(player_id)
            if player is None:
                raise APIError(404, "PLAYER_NOT_FOUND", f"Player {player_id} does not exist.",
                               {"player_id": player_id})
            if as_of is None:
                on = datetime.now(timezone.utc).date()
            else:
                on = _parse_date(as_of)
                if on is None:
                    raise validation_error(["as_of"])
            self._materialize_return(player, on, _now_iso())
            reg = self._effective(player, on)
            return {
                "player_id": player_id,
                "as_of": on.isoformat(),
                "league_id": player["league_id"],
                "current_squad_id": reg["squad_id"] if reg else None,
                "parent_squad_id": reg["parent_squad_id"] if reg else None,
                "history": copy.deepcopy(self.audit.get(player_id, [])),
            }

    def player_version(self, player_id: str) -> int:
        with self.lock:
            if player_id not in self.players:
                raise APIError(404, "PLAYER_NOT_FOUND", f"Player {player_id} does not exist.",
                               {"player_id": player_id})
            return len(self.audit.get(player_id, []))
