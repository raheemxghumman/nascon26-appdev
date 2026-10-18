"""Durable co-stream state and deterministic ordered host handoff."""
import copy
from .errors import APIError, validation_error
from .streaming import signature


class Costream:
    def __init__(self, db, players):
        self.db, self.players = db, players

    def session(self, body):
        if not isinstance(body, dict):
            raise validation_error(["body"])
        bad = [k for k in ("session_id", "host_player_id") if not isinstance(body.get(k), str) or not body[k]]
        participants = body.get("participants")
        if (not isinstance(participants, list) or not participants
                or not all(isinstance(p, str) and p for p in participants)
                or len(set(participants)) != len(participants)):
            bad.append("participants")
        if not isinstance(body.get("simulate_host_drop", False), bool):
            bad.append("simulate_host_drop")
        if body.get("layout", "grid_4") not in ("solo", "grid_2", "grid_4", "spotlight"):
            bad.append("layout")
        if bad:
            raise validation_error(bad)
        host, sid = body["host_player_id"], body["session_id"]
        if any(p not in self.players for p in participants + [host]):
            raise APIError(404, "PLAYER_NOT_FOUND", "Unknown participant.")
        if host not in participants:
            raise validation_error(["host_player_id"])
        if len(participants) > 4:
            raise APIError(409, "COSTREAM_SESSION_FULL", "Maximum four broadcasters.")
        active = [p for p in participants if p != host] if body.get("simulate_host_drop", False) else list(participants)
        layout = body.get("layout", "grid_4")
        if len(active) > {"solo": 1, "grid_2": 2, "grid_4": 4, "spotlight": 4}[layout]:
            raise APIError(400, "UNSUPPORTED_LAYOUT", "Layout cannot fit active participants.")
        with self.db.transaction():
            prior = self.db.get("session_request", sid)
            if prior is not None:
                if prior != body:
                    raise APIError(409, "SESSION_EXISTS", "Session identifier already used.")
                return 200, self.db.get("session", sid)
            response = self._response(sid, active, layout,
                                      bool(body.get("simulate_host_drop", False) and active), host)
            self.db.put("session_request", sid, copy.deepcopy(body))
            self.db.put("session", sid, response)
            return 201, response

    def _response(self, sid, active, layout, handoff, original_host):
        host = active[0] if handoff and active else (original_host if active else None)
        payload = {"active_host": host, "handoff_occurred": handoff, "layout": layout,
                   "participant_count": len(active), "session_id": sid,
                   "status": "active" if active else "terminated"}
        return {**payload, "active_participants": active,
                "composite_playback_url": f"http://localhost:8888/costream/{sid}/index.m3u8",
                "chat_room_id": f"chat-{sid}", "signature": signature(sid, payload)}

    def drop(self, sid, player):
        with self.db.transaction():
            state = self.db.get("session", sid)
            if state is None:
                raise APIError(404, "STREAM_NOT_FOUND", "Unknown session.")
            active = [p for p in state["active_participants"] if p != player]
            host_dropped = player == state["active_host"]
            result = self._response(sid, active, state["layout"], bool(host_dropped and active), state["active_host"])
            self.db.put("session", sid, result)
            return result
