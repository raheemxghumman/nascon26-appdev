"""HMAC signatures and drawing-of-lots keys (spec 5.3, 5.10, Appendix A)."""
import hashlib
import hmac
import json


def canonical(obj) -> str:
    """Sorted keys, no whitespace, UTF-8 without escaping non-ASCII."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sign(salt: str, id_: str, payload_obj) -> str:
    msg = (id_ + "|" + canonical(payload_obj)).encode("utf-8")
    return hmac.new(salt.encode("utf-8"), msg, hashlib.sha256).hexdigest()


def lots_key(seed: int, league_id: str, team_id: str) -> str:
    return hashlib.sha256(f"{seed}|{league_id}|{team_id}".encode("utf-8")).hexdigest()
