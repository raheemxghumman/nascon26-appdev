"""Fixture and bracket generation (spec 5.7). Pure computation: nothing is stored.

Custom implementation (third-party fixture libraries are prohibited): round robin via
the circle method, Swiss pairing with exact minimum-cost rematch-free matching,
single elimination and double elimination brackets with result propagation.
"""
import math
import re

from .errors import APIError, validation_error

ID_RE = re.compile(r"[A-Za-z0-9_.:-]{1,64}")
LIMITS = {
    "round_robin": (2, 40),
    "swiss": (2, 64),
    "single_elim": (2, 128),
    "double_elim": (3, 128),
}
SWISS_STEP_LIMIT = 400_000


def _is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _is_id(v) -> bool:
    return isinstance(v, str) and ID_RE.fullmatch(v) is not None


def generate(body: dict) -> dict:
    if not isinstance(body, dict):
        raise validation_error(["body"])
    fmt = body.get("format")
    if not isinstance(fmt, str) or fmt not in LIMITS:
        raise validation_error(["format"])
    teams = body.get("teams")
    if (
        not isinstance(teams, list)
        or not all(_is_id(t) for t in teams)
        or len(set(teams)) != len(teams)
    ):
        raise validation_error(["teams"])
    lo, hi = LIMITS[fmt]
    if not lo <= len(teams) <= hi:
        raise validation_error(["teams"])
    params = body.get("params")
    if params is None:
        params = {}
    if not isinstance(params, dict):
        raise validation_error(["params"])
    handler = {
        "round_robin": _round_robin,
        "swiss": _swiss,
        "single_elim": _single_elim,
        "double_elim": _double_elim,
    }[fmt]
    return handler(list(teams), params)


# --------------------------------------------------------------------------- round robin


def _withdrawal_status(home, away, rnd, after, policy):
    h_wd, a_wd = home in after, away in after
    if not h_wd and not a_wd:
        return "scheduled", None
    if policy == "void_all":
        return "voided", None
    h_gone = h_wd and rnd > after[home]
    a_gone = a_wd and rnd > after[away]
    if h_gone and a_gone:
        return "voided", None
    if h_gone:
        return "forfeit", away
    if a_gone:
        return "forfeit", home
    return "scheduled", None


def _round_robin(teams, params):
    legs = params.get("legs", 1)
    if legs is None:
        legs = 1
    if not _is_int(legs) or legs not in (1, 2):
        raise validation_error(["params.legs"])
    policy = params.get("withdrawal_policy", "forfeit_remaining")
    if policy is None:
        policy = "forfeit_remaining"
    if policy not in ("void_all", "forfeit_remaining"):
        raise validation_error(["params.withdrawal_policy"])

    n = len(teams)
    # Odd field: a phantom "bye" occupies the fixed slot, so each real team gets
    # exactly one bye per leg and stays perfectly home/away balanced.
    slots = list(teams) if n % 2 == 0 else [None] + list(teams)
    size = len(slots)
    per_leg = size - 1
    round_count = per_leg * legs

    withdrawals = params.get("withdrawals", [])
    if withdrawals is None:
        withdrawals = []
    if not isinstance(withdrawals, list):
        raise validation_error(["params.withdrawals"])
    after = {}
    for w in withdrawals:
        if not isinstance(w, dict):
            raise validation_error(["params.withdrawals"])
        tid, ar = w.get("team_id"), w.get("after_round")
        if not isinstance(tid, str) or tid not in teams:
            raise validation_error(["params.withdrawals"])
        if not _is_int(ar) or not 0 <= ar <= round_count:
            raise validation_error(["params.withdrawals"])
        after[tid] = min(after.get(tid, ar), ar)

    base_rounds = []
    arr = slots[:]
    for r in range(per_leg):
        pairs = []
        for i in range(size // 2):
            a, b = arr[i], arr[size - 1 - i]
            if i == 0:
                pairs.append((a, b) if r % 2 == 0 else (b, a))
            else:
                pairs.append((a, b))
        base_rounds.append(pairs)
        arr = [arr[0], arr[-1]] + arr[1:-1]

    rounds = []
    summary = {"total": 0, "scheduled": 0, "forfeit": 0, "voided": 0}
    for leg in range(1, legs + 1):
        for r, pairs in enumerate(base_rounds):
            gr = (leg - 1) * per_leg + r + 1
            matches, byes = [], []
            idx = 0
            for home, away in pairs:
                if home is None or away is None:
                    byes.append(away if home is None else home)
                    continue
                if leg == 2:
                    home, away = away, home
                idx += 1
                status, awarded = _withdrawal_status(home, away, gr, after, policy)
                summary["total"] += 1
                summary[status] += 1
                matches.append({
                    "match_id": f"RR-L{leg}-R{gr}-M{idx}",
                    "leg": leg,
                    "home": home,
                    "away": away,
                    "status": status,
                    "awarded_to": awarded,
                })
            rounds.append({"round": gr, "matches": matches, "byes": byes})

    return {
        "format": "round_robin",
        "legs": legs,
        "team_count": n,
        "round_count": round_count,
        "rounds": rounds,
        "summary": summary,
    }


# --------------------------------------------------------------------------- swiss


def _min_cost_matching(nodes, score, banned):
    """Exact minimum sum of |score diff| perfect matching avoiding banned pairs.

    nodes: team indices in standings order. Branch and bound with the
    unconstrained optimum (adjacent pairs in sorted order) as lower bound and
    memoised failure budgets. Returns list of (a, b) pairs or None.
    """
    best = {"cost": None, "pairs": None}
    fail = {}
    steps = [0]

    def lower_bound(rem):
        vals = sorted((score[i] for i in rem), reverse=True)
        return sum(vals[k] - vals[k + 1] for k in range(0, len(vals), 2))

    def rec(rem, mask, cost, pairs):
        if not rem:
            if best["cost"] is None or cost < best["cost"]:
                best["cost"] = cost
                best["pairs"] = list(pairs)
            return
        steps[0] += 1
        if steps[0] > SWISS_STEP_LIMIT:
            return
        budget = float("inf") if best["cost"] is None else best["cost"] - cost
        if fail.get(mask, -1) >= budget:
            return
        if lower_bound(rem) >= budget:
            return
        first = rem[0]
        cands = [j for j in rem[1:] if frozenset((first, j)) not in banned]
        cands.sort(key=lambda j: abs(score[first] - score[j]))
        before = best["cost"]
        for j in cands:
            d = abs(score[first] - score[j])
            if best["cost"] is not None and cost + d >= best["cost"]:
                break
            nrem = tuple(x for x in rem if x != first and x != j)
            pairs.append((first, j))
            rec(nrem, mask & ~(1 << first) & ~(1 << j), cost + d, pairs)
            pairs.pop()
        if best["cost"] == before:
            fail[mask] = max(fail.get(mask, -1), budget)

    mask = 0
    for i in nodes:
        mask |= 1 << i
    rec(tuple(nodes), mask, 0, [])
    return best["pairs"]


def _swiss(teams, params):
    n = len(teams)
    index = {t: i for i, t in enumerate(teams)}
    total = params.get("total_rounds")
    if total is None:
        total = max(1, math.ceil(math.log2(n)))
    if not _is_int(total) or not 1 <= total <= n - 1:
        raise validation_error(["params.total_rounds"])
    rnd = params.get("round", 1)
    if rnd is None:
        rnd = 1
    if not _is_int(rnd) or not 1 <= rnd <= total:
        raise validation_error(["params.round"])
    history = params.get("history", [])
    if history is None:
        history = []
    if not isinstance(history, list):
        raise validation_error(["params.history"])

    score = [0] * n  # half points x2, kept integral
    opponents = [[] for _ in range(n)]
    played = set()
    had_bye = set()
    seen_rounds = []
    for entry in history:
        if not isinstance(entry, dict) or not _is_int(entry.get("round")):
            raise validation_error(["params.history"])
        seen_rounds.append(entry["round"])
        matches = entry.get("matches", [])
        if matches is None:
            matches = []
        if not isinstance(matches, list):
            raise validation_error(["params.history"])
        for m in matches:
            if not isinstance(m, dict):
                raise validation_error(["params.history"])
            h, a, res = m.get("home"), m.get("away"), m.get("result")
            if not isinstance(h, str) or not isinstance(a, str) or h not in index or a not in index or h == a:
                raise validation_error(["params.history"])
            if res not in ("home", "away", "draw"):
                raise validation_error(["params.history"])
            hi, ai = index[h], index[a]
            if res == "home":
                score[hi] += 2
            elif res == "away":
                score[ai] += 2
            else:
                score[hi] += 1
                score[ai] += 1
            opponents[hi].append(ai)
            opponents[ai].append(hi)
            played.add(frozenset((hi, ai)))
        bye = entry.get("bye")
        if bye is not None:
            if not isinstance(bye, str) or bye not in index:
                raise validation_error(["params.history"])
            score[index[bye]] += 2
            had_bye.add(index[bye])
    if sorted(seen_rounds) != list(range(1, rnd)):
        raise validation_error(["params.history"])

    buchholz = [sum(score[o] for o in opponents[i]) for i in range(n)]
    order = sorted(range(n), key=lambda i: (-score[i], -buchholz[i], i))
    standings = [
        {"rank": r + 1, "team_id": teams[i], "score": score[i] / 2, "buchholz": buchholz[i] / 2}
        for r, i in enumerate(order)
    ]

    pos = {i: p for p, i in enumerate(order)}
    pairs = None
    bye_idx = None
    if rnd == 1:
        m = n // 2
        pairs = [(i, i + m) for i in range(m)]
        bye_idx = n - 1 if n % 2 else None
    else:
        if n % 2:
            pool = [i for i in range(n) if i not in had_bye] or list(range(n))
            candidates = sorted(pool, key=lambda i: (score[i], -i))
        else:
            candidates = [None]
        for cand in candidates:
            nodes = [i for i in order if i != cand]
            found = _min_cost_matching(nodes, score, played)
            if found is not None:
                pairs = [(a, b) if pos[a] < pos[b] else (b, a) for a, b in found]
                pairs.sort(key=lambda p: pos[p[0]])
                bye_idx = cand
                break
        if pairs is None:
            raise APIError(409, "NO_VALID_PAIRING",
                           f"No rematch-free pairing exists for round {rnd}.", {"round": rnd})

    return {
        "format": "swiss",
        "round": rnd,
        "total_rounds": total,
        "pairings": [
            {"match_id": f"SW-R{rnd}-M{k + 1}", "home": teams[a], "away": teams[b]}
            for k, (a, b) in enumerate(pairs)
        ],
        "bye": teams[bye_idx] if bye_idx is not None else None,
        "standings": standings,
    }


# --------------------------------------------------------------------------- brackets

_PUBLIC = ("match_id", "bracket", "round", "index", "home", "away", "home_seed", "away_seed",
           "bye", "winner", "loser", "winner_to", "loser_to")


def _bracket_size(n):
    b = 1
    while b < n:
        b *= 2
    return b


def _seed_order(size):
    order = [1, 2]
    while len(order) < size:
        k2 = len(order) * 2
        order = [x for s in order for x in (s, k2 + 1 - s)]
    return order[:size] if size >= 2 else [1]


class _Bracket:
    """Match graph with slot feeding, bye auto-advance and result propagation."""

    def __init__(self, teams):
        self.teams = teams
        self.seed_of = {t: i + 1 for i, t in enumerate(teams)}
        self.matches = {}

    def add(self, match_id, bracket, rnd, index):
        m = {
            "match_id": match_id, "bracket": bracket, "round": rnd, "index": index,
            "home": None, "away": None, "home_seed": None, "away_seed": None,
            "bye": False, "winner": None, "loser": None, "winner_to": None, "loser_to": None,
            "_dead": set(), "_decided": False,
        }
        self.matches[match_id] = m
        return m

    def place(self, target, team):
        if target is None:
            return
        m = self.matches[target["match_id"]]
        slot = target["slot"]
        if team is None:
            m["_dead"].add(slot)
        else:
            m[slot] = team
            m[slot + "_seed"] = self.seed_of[team]

    def decide(self, m, winner, loser):
        m["winner"], m["loser"], m["_decided"] = winner, loser, True
        self.place(m["winner_to"], winner)
        self.place(m["loser_to"], loser)

    def _slot_state(self, m, slot):
        if m[slot] is not None:
            return "team"
        if slot in m["_dead"]:
            return "dead"
        return "open"

    def settle(self):
        changed = True
        while changed:
            changed = False
            for m in self.matches.values():
                if m["_decided"]:
                    continue
                hs, as_ = self._slot_state(m, "home"), self._slot_state(m, "away")
                if "open" in (hs, as_) or (hs == "team" and as_ == "team"):
                    continue
                if hs == "dead" and as_ == "dead":
                    m["_decided"] = True
                    self.place(m["winner_to"], None)
                    self.place(m["loser_to"], None)
                else:
                    present = m["home"] if hs == "team" else m["away"]
                    m["bye"] = True
                    self.decide(m, present, None)
                changed = True

    def apply_results(self, results, gate=None):
        if results is None:
            results = []
        if not isinstance(results, list):
            raise validation_error(["params.results"])
        for res in results:
            if not isinstance(res, dict):
                raise validation_error(["params.results"])
            mid, winner = res.get("match_id"), res.get("winner")
            if not isinstance(mid, str) or mid not in self.matches or not isinstance(winner, str):
                raise validation_error(["params.results"])
            m = self.matches[mid]
            if gate is not None and not gate(m):
                raise validation_error(["params.results"])
            if m["_decided"]:
                if m["winner"] == winner:
                    continue
                raise validation_error(["params.results"])
            if m["home"] is None or m["away"] is None or winner not in (m["home"], m["away"]):
                raise validation_error(["params.results"])
            loser = m["away"] if winner == m["home"] else m["home"]
            self.decide(m, winner, loser)
            self.settle()

    def seed_first_round(self, prefix, bracket_size):
        n = len(self.teams)
        order = _seed_order(bracket_size)
        for i in range(1, bracket_size // 2 + 1):
            a, b = order[2 * i - 2], order[2 * i - 1]
            lo, hi = min(a, b), max(a, b)
            m = self.matches[f"{prefix}{i}"]
            self.place({"match_id": m["match_id"], "slot": "home"}, self.teams[lo - 1])
            if hi <= n:
                self.place({"match_id": m["match_id"], "slot": "away"}, self.teams[hi - 1])
            else:
                self.place({"match_id": m["match_id"], "slot": "away"}, None)

    @staticmethod
    def public(m, extra=()):
        out = {k: m[k] for k in _PUBLIC}
        for k in extra:
            out[k] = m[k]
        return out


def _bool_param(params, key):
    v = params.get(key, False)
    if v is None:
        v = False
    if not isinstance(v, bool):
        raise validation_error([f"params.{key}"])
    return v


def _single_elim(teams, params):
    third_place = _bool_param(params, "third_place_match")
    n = len(teams)
    size = _bracket_size(n)
    total_rounds = int(math.log2(size))
    br = _Bracket(teams)
    rounds = []
    for r in range(1, total_rounds + 1):
        ids = []
        for i in range(1, (size >> r) + 1):
            m = br.add(f"R{r}M{i}", "main", r, i)
            if r < total_rounds:
                m["winner_to"] = {"match_id": f"R{r + 1}M{(i + 1) // 2}",
                                  "slot": "home" if i % 2 else "away"}
            ids.append(m["match_id"])
        rounds.append(ids)
    if third_place and total_rounds >= 2:
        br.add("TP", "third_place", total_rounds, 1)
        semis = rounds[total_rounds - 2]
        br.matches[semis[0]]["loser_to"] = {"match_id": "TP", "slot": "home"}
        br.matches[semis[1]]["loser_to"] = {"match_id": "TP", "slot": "away"}
        rounds[total_rounds - 1].append("TP")
    br.seed_first_round("R1M", size)
    br.settle()
    br.apply_results(params.get("results", []))
    return {
        "format": "single_elim",
        "bracket_size": size,
        "rounds": [
            {"round": r + 1, "matches": [br.public(br.matches[mid]) for mid in ids]}
            for r, ids in enumerate(rounds)
        ],
    }


def _double_elim(teams, params):
    reset = _bool_param(params, "bracket_reset")
    n = len(teams)
    size = _bracket_size(n)
    k = int(math.log2(size))
    br = _Bracket(teams)

    winners = []
    for r in range(1, k + 1):
        ids = []
        for i in range(1, (size >> r) + 1):
            m = br.add(f"WR{r}M{i}", "winners", r, i)
            if r < k:
                m["winner_to"] = {"match_id": f"WR{r + 1}M{(i + 1) // 2}",
                                  "slot": "home" if i % 2 else "away"}
            else:
                m["winner_to"] = {"match_id": "GF1", "slot": "home"}
            if r == 1:
                m["loser_to"] = {"match_id": f"LR1M{(i + 1) // 2}",
                                 "slot": "home" if i % 2 else "away"}
            else:
                m["loser_to"] = {"match_id": f"LR{2 * r - 2}M{i}", "slot": "away"}
            ids.append(m["match_id"])
        winners.append(ids)

    losers = []
    last_lr = 2 * (k - 1)
    for lr in range(1, last_lr + 1):
        j = (lr + 1) // 2
        ids = []
        for i in range(1, (size >> (j + 1)) + 1):
            m = br.add(f"LR{lr}M{i}", "losers", lr, i)
            if lr == last_lr:
                m["winner_to"] = {"match_id": "GF1", "slot": "away"}
            elif lr % 2 == 1:
                m["winner_to"] = {"match_id": f"LR{lr + 1}M{i}", "slot": "home"}
            else:
                m["winner_to"] = {"match_id": f"LR{lr + 1}M{(i + 1) // 2}",
                                  "slot": "home" if i % 2 else "away"}
            ids.append(m["match_id"])
        losers.append(ids)

    gf1 = br.add("GF1", "grand_final", 1, 1)
    gf_ids = ["GF1"]
    if reset:
        br.add("GF2", "grand_final", 2, 1)
        gf1["winner_to"] = {"match_id": "GF2", "slot": "home"}
        gf1["loser_to"] = {"match_id": "GF2", "slot": "away"}
        gf_ids.append("GF2")

    def gf2_required():
        if not reset or gf1["winner"] is None:
            return None
        return gf1["winner"] == gf1["away"]

    br.seed_first_round("WR1M", size)
    br.settle()
    br.apply_results(params.get("results", []),
                     gate=lambda m: m["match_id"] != "GF2" or gf2_required() is True)

    def render_gf(mid):
        m = br.matches[mid]
        out = br.public(m)
        if mid == "GF1":
            out["conditional"] = False
            out["required"] = True
        else:
            if out["home"] is None and out["away"] is None:
                out["home"], out["away"] = gf1["home"], gf1["away"]
                out["home_seed"], out["away_seed"] = gf1["home_seed"], gf1["away_seed"]
            out["conditional"] = True
            out["required"] = gf2_required()
        return out

    return {
        "format": "double_elim",
        "bracket_size": size,
        "bracket_reset": reset,
        "winners": [
            {"round": r + 1, "matches": [br.public(br.matches[mid]) for mid in ids]}
            for r, ids in enumerate(winners)
        ],
        "losers": [
            {"round": r + 1, "matches": [br.public(br.matches[mid]) for mid in ids]}
            for r, ids in enumerate(losers)
        ],
        "grand_final": [render_gf(mid) for mid in gf_ids],
    }
