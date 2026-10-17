"""Standings engine (spec 5.10): table, tie-breakers, head-to-head, qualification.

Pure computation from per-fixture score projections; recomputed from scratch on every call.
"""
from .signing import lots_key

CRITERIA = ["h2h_points", "h2h_diff", "overall_diff", "scored", "fair_play", "draw_lots"]


def _tie_break_order(order) -> list[str]:
    result = []
    for token in order or CRITERIA:
        if token in CRITERIA and token not in result:
            result.append(token)
    if "draw_lots" in result:
        result.remove("draw_lots")
    result.append("draw_lots")
    return result


def _is_played(m: dict) -> bool:
    return m.get("status") == "completed" and m.get("outcome") not in ("undecided", "pending", None)


class _Engine:
    def __init__(self, league: dict, sport: dict, matches: list[dict]):
        self.league = league
        self.sport = sport
        self.model = sport.get("scoring_model", "event")
        periods = sport.get("periods") or {}
        ipt = int(periods.get("innings_per_team", 1) or 1)
        self.bpo = int(periods.get("balls_per_over", 6) or 6)
        self.full_overs = ipt * int(periods.get("overs_per_innings", 0) or 0)
        self.all_out = ipt * int(periods.get("wickets_per_innings", 0) or 0)
        pts = league.get("points") or {}
        self.win = int(pts.get("win", 3))
        self.draw = int(pts.get("draw", 1))
        self.loss = int(pts.get("loss", 0))
        self.teams = list(league["teams"])
        self.played = [m for m in matches if _is_played(m)]
        self.remaining = [m for m in matches if not _is_played(m)]

    # --- per-match helpers -------------------------------------------------
    def _side(self, m: dict, team: str):
        if m["home"] == team:
            return "home", "away"
        return "away", "home"

    def _result_points(self, m: dict, team: str) -> int:
        me, _ = self._side(m, team)
        outcome = m["outcome"]
        if outcome == "draw":
            return self.draw
        return self.win if outcome == f"{me}_win" else self.loss

    def _overs(self, m: dict, side: str) -> float:
        balls = m.get(f"{side}_balls") or 0
        wickets = m.get(f"{side}_wickets") or 0
        if self.all_out and wickets >= self.all_out and self.full_overs:
            return float(self.full_overs)
        return balls / self.bpo if self.bpo else 0.0

    def _diff(self, team: str, subset: list[dict]):
        scored = conceded = 0
        overs_faced = overs_bowled = 0.0
        for m in subset:
            me, opp = self._side(m, team)
            scored += m.get(f"{me}_score") or 0
            conceded += m.get(f"{opp}_score") or 0
            if self.model == "innings":
                overs_faced += self._overs(m, me)
                overs_bowled += self._overs(m, opp)
        if self.model != "innings":
            return scored - conceded
        rate_for = scored / overs_faced if overs_faced else 0.0
        rate_against = conceded / overs_bowled if overs_bowled else 0.0
        return round(rate_for - rate_against, 3)

    def _team_matches(self, team: str, among=None) -> list[dict]:
        out = []
        for m in self.played:
            if team not in (m["home"], m["away"]):
                continue
            if among is not None and not (m["home"] in among and m["away"] in among):
                continue
            out.append(m)
        return out

    # --- aggregates --------------------------------------------------------
    def row(self, team: str) -> dict:
        ms = self._team_matches(team)
        won = drawn = lost = scored = conceded = fair = 0
        for m in ms:
            me, opp = self._side(m, team)
            scored += m.get(f"{me}_score") or 0
            conceded += m.get(f"{opp}_score") or 0
            fair += m.get(f"{me}_fair_play") or 0
            if m["outcome"] == "draw":
                drawn += 1
            elif m["outcome"] == f"{me}_win":
                won += 1
            else:
                lost += 1
        return {
            "team_id": team, "played": len(ms), "won": won, "drawn": drawn, "lost": lost,
            "scored": scored, "conceded": conceded, "diff": self._diff(team, ms),
            "points": won * self.win + drawn * self.draw + lost * self.loss, "fair_play": fair,
        }

    def criterion(self, name: str, team: str, group: list[str], rows: dict):
        if name == "h2h_points":
            return sum(self._result_points(m, team) for m in self._team_matches(team, set(group)))
        if name == "h2h_diff":
            return self._diff(team, self._team_matches(team, set(group)))
        if name == "overall_diff":
            return rows[team]["diff"]
        if name == "scored":
            return rows[team]["scored"]
        if name == "fair_play":
            return rows[team]["fair_play"]
        raise ValueError(name)

    def resolve(self, group: list[str], rows: dict, order: list[str]):
        """Return (ordered teams, separators) where separators[i] names the criterion
        that split ordered[i] from ordered[i+1]."""
        if len(group) <= 1:
            return list(group), []
        for name in order:
            if name == "draw_lots":
                seed = self.league.get("lots_seed", 42)
                lid = self.league["league_id"]
                ordered = sorted(group, key=lambda t: lots_key(seed, lid, t))
                return ordered, ["draw_lots"] * (len(ordered) - 1)
            values = {t: self.criterion(name, t, group, rows) for t in group}
            distinct = sorted(set(values.values()), reverse=True)
            if len(distinct) == 1:
                continue
            ordered, seps = [], []
            for i, value in enumerate(distinct):
                sub = [t for t in group if values[t] == value]
                sub_order, sub_seps = self.resolve(sub, rows, order)
                if i > 0:
                    seps.append(name)
                ordered.extend(sub_order)
                seps.extend(sub_seps)
            return ordered, seps
        return list(group), [None] * (len(group) - 1)

    def head_to_head(self) -> dict:
        h2h = {}
        for a in self.teams:
            h2h[a] = {}
            for b in self.teams:
                if a == b:
                    continue
                cell = {"played": 0, "points": 0, "scored": 0, "conceded": 0}
                for m in self.played:
                    if {m["home"], m["away"]} != {a, b}:
                        continue
                    me, opp = self._side(m, a)
                    cell["played"] += 1
                    cell["points"] += self._result_points(m, a)
                    cell["scored"] += m.get(f"{me}_score") or 0
                    cell["conceded"] += m.get(f"{opp}_score") or 0
                h2h[a][b] = cell
        return h2h

    def qualification(self, rows: dict) -> dict:
        k = int((self.league.get("qualification") or {}).get("spots", 1))
        remaining = {t: 0 for t in self.teams}
        for m in self.remaining:
            for t in (m["home"], m["away"]):
                if t in remaining:
                    remaining[t] += 1
        max_pts = {t: rows[t]["points"] + self.win * remaining[t] for t in self.teams}
        status = {}
        for t in self.teams:
            others = [x for x in self.teams if x != t]
            if sum(1 for x in others if max_pts[x] >= rows[t]["points"]) < k:
                status[t] = "clinched"
            elif sum(1 for x in others if rows[x]["points"] > max_pts[t]) >= k:
                status[t] = "eliminated"
            else:
                status[t] = "still_possible"
        return status


def compute_standings(league: dict, sport: dict, matches: list[dict]) -> dict:
    eng = _Engine(league, sport, matches)
    rows = {t: eng.row(t) for t in eng.teams}
    order = _tie_break_order(league.get("tie_break_order"))

    final, resolved_by = [], {}
    for pts in sorted({r["points"] for r in rows.values()}, reverse=True):
        group = [t for t in eng.teams if rows[t]["points"] == pts]
        ordered, seps = eng.resolve(group, rows, order)
        for i, team in enumerate(ordered):
            resolved_by[team] = seps[i] if i < len(seps) else None
        final.extend(ordered)

    status = eng.qualification(rows)
    table = []
    for rank, team in enumerate(final, start=1):
        row = dict(rows[team])
        table.append({"rank": rank, **row, "status": status[team], "resolved_by": resolved_by[team]})
    return {
        "league_id": league["league_id"],
        "sport_id": league.get("sport_id", sport.get("sport_id")),
        "qualification_spots": int((league.get("qualification") or {}).get("spots", 1)),
        "table": table,
        "h2h": eng.head_to_head(),
    }
