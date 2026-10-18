"""Signed creator keys, MediaMTX authentication and immediate publisher eviction."""
import secrets
from urllib.parse import quote
import httpx
from . import config
from .errors import APIError, validation_error
from .signing import sign


def signature(entity, payload):
    return sign(config.DAY2_SALT, entity, payload)


class Streaming:
    def __init__(self, db, players):
        self.db, self.players = db, players

    def key(self, body):
        if not isinstance(body, dict):
            raise validation_error(["body"])
        bad = []
        if body.get("action") not in ("generate", "rotate", "revoke"):
            bad.append("action")
        if not isinstance(body.get("player_id"), str) or not body["player_id"]:
            bad.append("player_id")
        if not isinstance(body.get("label", "default"), str) or not 1 <= len(body.get("label", "default")) <= 64:
            bad.append("label")
        if "stream_key_override" in body and (not isinstance(body["stream_key_override"], str)
                or not body["stream_key_override"] or len(body["stream_key_override"]) > 128
                or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in body["stream_key_override"])):
            bad.append("stream_key_override")
        if bad:
            raise validation_error(bad)
        pid, action = body["player_id"], body["action"]
        if pid not in self.players:
            raise APIError(404, "PLAYER_NOT_FOUND", "Unknown player.")
        old_key = None
        with self.db.transaction():
            old = self.db.get("creator", pid)
            if action == "revoke" and old is None:
                raise APIError(404, "STREAM_NOT_FOUND", "No stream key exists.")
            if old:
                old_key = old["stream_key"]
                self.db.put("key", old_key, {**old, "status": "revoked"})
            key = old_key if action == "revoke" else body.get("stream_key_override", "sk_live_" + secrets.token_hex(8))
            owner = self.db.get("key", key)
            if owner and owner["player_id"] != pid:
                raise APIError(409, "KEY_REVOKED", "Key already belongs to another creator.")
            status = "revoked" if action == "revoke" else "active"
            record = {"player_id": pid, "label": body.get("label", "default"), "stream_key": key, "status": status}
            self.db.put("key", key, record)
            self.db.put("creator", pid, record)
        if old_key:
            self.disconnect(old_key)
        payload = {"action": action, "player_id": pid, "status": status, "stream_key": key}
        return (201 if action == "generate" else 200), {
            **record,
            "ingest_endpoints": None if status == "revoked" else {
                "rtmp": f"rtmp://localhost:1935/live/{key}",
                "webrtc": f"http://localhost:8889/live/{key}/whip"},
            "playback_url": None if status == "revoked" else f"http://localhost:8888/live/{key}/index.m3u8",
            "signature": signature(key, payload)}

    def disconnect(self, key):
        """Kick every active RTMP/WHIP publisher using the invalidated path."""
        try:
            with httpx.Client(timeout=0.45) as client:
                for kind in ("rtmpconns", "webrtcsessions"):
                    res = client.get(f"{config.MEDIA_API}/v3/{kind}/list")
                    if res.status_code == 200:
                        for item in res.json().get("items", []):
                            if item.get("path") == f"live/{key}":
                                client.post(f"{config.MEDIA_API}/v3/{kind}/kick/{quote(item['id'], safe='')}")
        except httpx.HTTPError:
            # A stopped media server has no live publishers. New ingest is still denied by auth.
            pass

    def media_auth(self, body):
        path, action = body.get("path", ""), body.get("action")
        if path.startswith("costream/") and action in ("read", "publish"):
            session = self.db.get("session", path.split("/", 1)[1])
            if session and session["status"] == "active":
                return {"authorized": True}
        key = self.db.get("key", path.removeprefix("live/")) if path.startswith("live/") else None
        if key and key["status"] == "active":
            return {"authorized": True}
        raise APIError(409, "KEY_REVOKED", "Unknown or revoked media key.")
