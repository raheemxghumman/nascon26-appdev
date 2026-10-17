"""JWT auth, five-tier RBAC policy matrix and rate limiting (FR-5.1, NFR-5, spec 5.13)."""
import base64
import hashlib
import hmac
import json
import math
import threading
import time
from collections import defaultdict, deque

from . import config
from .errors import APIError

ROLES = ("super_admin", "league_organizer", "club_manager", "player", "viewer")

# Seeded scenario (spec 5.5). Ownership is data, used by the policy functions below.
TENANTS = {"tenant-alpha": {"name": "Alpha Sports", "primary_color": "#0D3B66", "logo": "alpha"},
           "tenant-beta": {"name": "Beta Athletics", "primary_color": "#7A1F2B", "logo": "beta"}}
LEAGUES = {"league-alpha-1": "tenant-alpha", "league-alpha-2": "tenant-alpha", "league-beta-1": "tenant-beta"}
CLUBS = {"club-alpha-1": "tenant-alpha", "club-alpha-2": "tenant-alpha", "club-beta-1": "tenant-beta"}
PLAYERS = {"player-alpha-1": "club-alpha-1", "player-alpha-2": "club-alpha-2", "player-beta-1": "club-beta-1"}

USERS = {
    "admin@nascon.test": {"user_id": "user-admin", "role": "super_admin", "tenant_id": None},
    "organizer@nascon.test": {"user_id": "user-organizer", "role": "league_organizer",
                              "tenant_id": "tenant-alpha", "league_id": "league-alpha-1"},
    "manager@nascon.test": {"user_id": "user-manager", "role": "club_manager",
                            "tenant_id": "tenant-alpha", "club_id": "club-alpha-1"},
    "player@nascon.test": {"user_id": "user-player", "role": "player",
                           "tenant_id": "tenant-alpha", "player_id": "player-alpha-1", "club_id": "club-alpha-1"},
    "viewer@nascon.test": {"user_id": "user-viewer", "role": "viewer", "tenant_id": "tenant-alpha"},
}
PASSWORD_SALT = b"nascon-demo"
PASSWORD_HASH = hashlib.pbkdf2_hmac("sha256", b"Nascon@26", PASSWORD_SALT, 100_000).hex()


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def issue_token(user: dict, ttl_seconds: int = 4 * 3600) -> str:
    now = int(time.time())
    claims = {k: v for k, v in user.items() if v is not None}
    claims.update({"sub": user["user_id"], "iat": now, "exp": now + ttl_seconds})
    header = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    body = _b64(json.dumps(claims, separators=(",", ":")).encode())
    sig = hmac.new(config.JWT_SECRET.encode(), f"{header}.{body}".encode(), hashlib.sha256).digest()
    return f"{header}.{body}.{_b64(sig)}"


def unauthenticated(msg="Missing or invalid token."):
    return APIError(401, "UNAUTHENTICATED", msg)


def verify_token(authorization) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise unauthenticated()
    parts = authorization[7:].strip().split(".")
    if len(parts) != 3:
        raise unauthenticated()
    try:
        header = json.loads(_unb64(parts[0]))
        claims = json.loads(_unb64(parts[1]))
        sig = _unb64(parts[2])
    except Exception:
        raise unauthenticated()
    if not isinstance(header, dict) or header.get("alg") != "HS256" or not isinstance(claims, dict):
        raise unauthenticated()
    expected = hmac.new(config.JWT_SECRET.encode(), f"{parts[0]}.{parts[1]}".encode(), hashlib.sha256).digest()
    if not hmac.compare_digest(sig, expected):
        raise unauthenticated()
    exp = claims.get("exp")
    if not isinstance(exp, (int, float)) or exp <= time.time() or claims.get("role") not in ROLES:
        raise unauthenticated("Token expired or invalid.")
    return claims


def login(email, password) -> dict:
    user = USERS.get(email.lower()) if isinstance(email, str) else None
    ok = isinstance(password, str) and hmac.compare_digest(
        hashlib.pbkdf2_hmac("sha256", password.encode(), PASSWORD_SALT, 100_000).hex(), PASSWORD_HASH)
    if user is None or not ok:
        raise APIError(401, "UNAUTHENTICATED", "Email or password is incorrect.")
    return {"token": issue_token(user), "role": user["role"], "user_id": user["user_id"],
            "tenant_id": user["tenant_id"], "email": email.lower(),
            **{k: user[k] for k in ("league_id", "club_id", "player_id") if k in user}}


def rbac_matrix() -> dict:
    return {
        "tokens": {u["role"]: issue_token(u) for u in USERS.values()},
        "context": {"tenant_id": "tenant-alpha", "foreign_tenant_id": "tenant-beta",
                    "own_league_id": "league-alpha-1", "other_league_id": "league-alpha-2",
                    "foreign_league_id": "league-beta-1",
                    "own_club_id": "club-alpha-1", "other_club_id": "club-alpha-2", "foreign_club_id": "club-beta-1",
                    "own_player_id": "player-alpha-1", "other_player_id": "player-alpha-2",
                    "foreign_player_id": "player-beta-1"},
    }


# ---- policy-as-code: (action, claims, resource) -> allowed? -----------------
def _same_tenant(claims, tenant):
    return tenant is not None and claims.get("tenant_id") == tenant


def can(action: str, claims: dict, resource_id=None) -> bool:
    role = claims["role"]
    if role == "super_admin":
        return True
    if action in ("tenants.create", "platform.config"):
        return False
    if action == "league.fixtures.write":
        return role == "league_organizer" and claims.get("league_id") == resource_id
    if action in ("club.roster.write", "club.products.write"):
        return role == "club_manager" and claims.get("club_id") == resource_id
    if action == "player.write":
        if role == "club_manager":
            return PLAYERS.get(resource_id) == claims.get("club_id")
        return role == "player" and claims.get("player_id") == resource_id
    if action == "club.read":
        return _same_tenant(claims, CLUBS.get(resource_id))
    if action == "score.write":
        return role == "league_organizer"
    return False


def authorize(authorization, action, resource_id=None, exists=True) -> dict:
    claims = verify_token(authorization)
    if not can(action, claims, resource_id):
        raise APIError(403, "FORBIDDEN", "You are not allowed to perform this action.")
    if not exists:
        raise APIError(404, "NOT_FOUND", "Resource does not exist.", {"id": resource_id})
    return claims


# ---- rate limiter: 100 requests per rolling 10 s per client IP --------------
class RateLimiter:
    def __init__(self, limit=100, window=10.0):
        self.limit, self.window = limit, window
        self.hits = defaultdict(deque)
        self.lock = threading.Lock()

    def check(self, key: str):
        now = time.monotonic()
        with self.lock:
            q = self.hits[key]
            while q and q[0] <= now - self.window:
                q.popleft()
            if len(q) >= self.limit:
                return max(1, math.ceil(q[0] + self.window - now))
            q.append(now)
            return None
