"""Prometheus counters from actual runtime state and transactional privacy erasure."""
import httpx
import time
from . import config
from .errors import APIError


class Observability:
    def __init__(self, db):
        self.db = db
        self.connections = 0
        self.last_bytes = 0
        self.last_sample = time.monotonic()

    def metrics(self):
        active, bitrate = 0, 0
        try:
            data = httpx.get(config.MEDIA_API + "/v3/paths/list", timeout=0.5).json()
            active = sum(bool(p.get("ready")) for p in data.get("items", []))
            current_bytes = sum(p.get("bytesReceived", 0) for p in data.get("items", []))
            now = time.monotonic()
            bitrate = max(0, current_bytes - self.last_bytes) * 8 / 1000 / max(.001, now - self.last_sample)
            self.last_bytes, self.last_sample = current_bytes, now
        except (httpx.HTTPError, ValueError):
            pass
        values = {"nascon_active_ws_connections": self.connections,
                  "nascon_active_streams_total": active, "nascon_stream_bitrate_kbps": bitrate,
                  "nascon_dlq_depth": len(self.db.all("dlq")),
                  "nascon_qr_scans_total": sum(q["scan_count"] for q in self.db.all("qr").values())}
        return "".join(f"# TYPE {name} gauge\n{name} {value}\n" for name, value in values.items())

    def erase(self, uid, users, players):
        if uid not in players and uid not in [u["user_id"] for u in users.values()]:
            raise APIError(404, "PLAYER_NOT_FOUND", "Unknown user.")
        with self.db.transaction():
            for token, record in self.db.all("guest").items():
                if record.get("user_id") == uid:
                    self.db.put("guest", token, {"valid": False, "anonymized": True})
                    self.db.put("merge", token, None)
            self.db.put("cart", uid, {})
            self.db.put("erased", uid, True)
            for room, state in self.db.all("chat").items():
                for msg in state["messages"]:
                    if msg["sender"] == uid:
                        msg["sender"], msg["text"] = "anonymous", "[removed]"
                state["decisions"] = {}
                state["rates"].pop(uid, None)
                state["kicked"] = ["anonymous" if x == uid else x for x in state["kicked"]]
                state["muted"] = ["anonymous" if x == uid else x for x in state["muted"]]
                self.db.put("chat", room, state)
        return {"user_id": uid, "status": "anonymized", "pii_retained": False, "tokens_wiped": True}
