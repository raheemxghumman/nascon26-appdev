"""Phase II integration; keeps the Phase I contract and history intact."""
import asyncio
import json
import secrets
from pathlib import Path
import httpx
from fastapi import Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse, Response, StreamingResponse
from . import auth, config
from .day2_db import Database
from .streaming import Streaming
from .costream import Costream
from .qr_guest import QRGuest
from .moderation_dlq import Moderation
from .observability import Observability
from .errors import APIError, validation_error


class PhaseII:
    def __init__(self, core):
        self.core = core
        self.db = Database()
        self.streaming = Streaming(self.db, auth.PLAYERS)
        self.costream = Costream(self.db, auth.PLAYERS)
        self.qr = QRGuest(self.db, core.ENGINE, core.STORE)
        self.moderation = Moderation(self.db)
        self.observability = Observability(self.db)
        self.seed()

    def seed(self):
        c = self.core
        auth.PLAYERS["player-beta-2"] = "club-beta-1"
        if "match-m1" not in c.ENGINE.matches:
            c.ENGINE.create_stream("match-m1", "football", "club-alpha-1", "club-alpha-2", "league-alpha-1")
            c.LEAGUES["league-alpha-1"]["fixtures"].append({"match_id": "match-m1", "home": "club-alpha-1", "away": "club-alpha-2"})
            c.ENGINE.append({"event_id": "day2-start", "match_id": "match-m1", "type": "match_start", "payload": {}})
            c.ENGINE.append({"event_id": "day2-goal", "match_id": "match-m1", "type": "score",
                             "payload": {"team_id": "club-alpha-1", "event_type": "goal"}})
        self.qr.seed()

    def reset(self):
        self.db.clear()
        self.seed()


def install(core):
    d = PhaseII(core)
    app = core.app

    @app.post("/audit/v1/stream/key")
    async def stream_key(request: Request):
        status, result = d.streaming.key(await core.read_json(request))
        return core.respond(status, result)

    @app.post("/audit/v1/costream/session")
    async def session(request: Request):
        status, result = d.costream.session(await core.read_json(request))
        return core.respond(status, result)

    @app.get("/audit/v1/qr/{entity_id}/export.{fmt}")
    def qr_export(entity_id: str, fmt: str):
        data, mime = d.qr.export(entity_id, fmt)
        return Response(data, media_type=mime, headers={"Content-Disposition": f'inline; filename="qr.{fmt}"'})

    @app.get("/audit/v1/qr/{entity_id}")
    def qr(entity_id: str, request: Request, inspect: bool = False):
        return d.qr.metadata(entity_id, inspect, request.headers.get("user-agent", ""))

    @app.get("/q/{code}")
    def short_link(code: str, request: Request):
        entity = d.db.get("short", code)
        if entity is None:
            raise APIError(404, "QR_NOT_FOUND", "Unknown short code.")
        result = d.qr.metadata(entity, False, request.headers.get("user-agent", ""))
        return RedirectResponse(result["target_route"], status_code=302)

    @app.post("/audit/v1/guest/cart-merge")
    async def cart_merge(request: Request):
        return d.qr.merge(await core.read_json(request))

    @app.post("/audit/v1/moderation/test")
    async def moderation(request: Request):
        return d.moderation.process(await core.read_json(request))

    @app.get("/metrics")
    def metrics():
        return Response(d.observability.metrics(), headers={"Content-Type": "text/plain; version=0.0.4"})

    @app.delete("/audit/v1/privacy/user/{uid}")
    def erase(uid: str):
        return d.observability.erase(uid, auth.USERS, auth.PLAYERS)

    @app.post("/internal/media/auth")
    async def media_auth(request: Request):
        body = await core.read_json(request)
        if not isinstance(body, dict):
            raise validation_error(["body"])
        return d.streaming.media_auth(body)

    @app.get("/internal/costreams")
    def compositor_state():
        sessions = []
        for sid, state in d.db.all("session").items():
            inputs = []
            for pid in state["active_participants"]:
                key = d.db.get("creator", pid)
                if key and key["status"] == "active":
                    inputs.append({"path": "live/" + key["stream_key"], "player_id": pid})
            sessions.append({**state, "inputs": inputs})
        return sessions

    @app.post("/internal/media/recording")
    async def recording(request: Request):
        import os
        from minio import Minio
        body = await core.read_json(request)
        if not isinstance(body, dict) or not isinstance(body.get("path"), str) or not isinstance(body.get("stream"), str):
            raise validation_error(["path", "stream"])
        path = Path(body["path"]).resolve()
        if not path.is_relative_to(Path("/recordings")) or not path.is_file():
            raise validation_error(["path"])
        storage = Minio(os.environ.get("MINIO_ENDPOINT", "minio:9000"),
                        access_key=os.environ.get("MINIO_ACCESS_KEY", "minioadmin"),
                        secret_key=os.environ.get("MINIO_SECRET_KEY", "minioadmin"), secure=False)
        if not storage.bucket_exists("recordings"):
            storage.make_bucket("recordings")
        object_name = str(path.relative_to("/recordings"))
        await asyncio.to_thread(storage.fput_object, "recordings", object_name, str(path), content_type="video/mp4")
        record = {"object": object_name, "stream": body["stream"], "playback_url": "/api/v1/vod/" + object_name}
        d.db.put("vod", object_name, record)
        key = d.db.get("key", body["stream"].removeprefix("live/"))
        if key:
            d.db.put("vod:" + key["player_id"], object_name, record)
        return {"status": "indexed", **record}

    @app.get("/api/v1/vod/{name:path}")
    def vod(name: str):
        import os
        from minio import Minio
        if d.db.get("vod", name) is None:
            raise APIError(404, "STREAM_NOT_FOUND", "Recording not found.")
        storage = Minio(os.environ.get("MINIO_ENDPOINT", "minio:9000"),
                        access_key=os.environ.get("MINIO_ACCESS_KEY", "minioadmin"),
                        secret_key=os.environ.get("MINIO_SECRET_KEY", "minioadmin"), secure=False)
        response = storage.get_object("recordings", name)
        def chunks():
            try:
                yield from response.stream(64 * 1024)
            finally:
                response.close()
                response.release_conn()
        return StreamingResponse(chunks(), media_type="video/mp4")

    @app.post("/api/v1/guest/session")
    def guest_session():
        import time
        token = "guest_anon_tok_" + secrets.token_hex(16)
        d.db.put("guest", token, {"valid": True, "merged": False, "expires": time.time() + 1800})
        return {"guest_token": token, "expires_in": 1800, "role": "guest"}

    @app.post("/api/v1/creator/key")
    async def creator_key(request: Request):
        claims = auth.verify_token(request.headers.get("authorization"))
        body = await core.read_json(request)
        if not isinstance(body, dict):
            raise validation_error(["body"])
        if claims.get("player_id") != body.get("player_id") and claims["role"] != "super_admin":
            raise APIError(403, "FORBIDDEN", "You can only broadcast as your own player.")
        status, result = d.streaming.key(body)
        return core.respond(status, result)

    @app.get("/api/v1/live/{entity}")
    def live_media(entity: str):
        if entity.startswith("cs-session-"):
            session = d.db.get("session", entity)
            if session and session["status"] == "active":
                return {"path": f"costream/{entity}"}
        for record in d.db.all("creator").values():
            if record["status"] == "active" and (not entity.startswith("player-") or entity == record["player_id"]):
                return {"path": "live/" + record["stream_key"]}
        return {"path": None}

    @app.post("/api/v1/media/whip/{path:path}")
    async def whip_proxy(path: str, request: Request):
        claims = auth.verify_token(request.headers.get("authorization"))
        record = d.db.get("key", path.removeprefix("live/"))
        if not record or record["status"] != "active":
            raise APIError(409, "KEY_REVOKED", "Unknown or revoked stream key.")
        if claims.get("player_id") != record["player_id"] and claims["role"] != "super_admin":
            raise APIError(403, "FORBIDDEN", "This is another player's stream.")
        raw = await request.body()
        if len(raw) > config.MAX_BODY_BYTES:
            raise APIError(413, "PAYLOAD_TOO_LARGE", "SDP offer exceeds 1 MB.")
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                response = await client.post(f"http://media:8889/{path}/whip", content=raw,
                                             headers={"Content-Type": "application/sdp"})
            return Response(response.content, status_code=response.status_code, media_type="application/sdp")
        except httpx.HTTPError:
            raise APIError(503, "UNAVAILABLE", "Media server is unavailable.")

    @app.post("/api/v1/guest/cart-merge")
    async def member_merge(request: Request):
        claims = auth.verify_token(request.headers.get("authorization"))
        body = await core.read_json(request)
        if not isinstance(body, dict):
            raise validation_error(["body"])
        uid = claims.get("player_id", claims["user_id"])
        if body.get("registered_user_id") != uid:
            raise APIError(403, "FORBIDDEN", "You may only merge into your own cart.")
        return d.qr.merge(body)

    @app.post("/api/v1/chat")
    async def chat_post(request: Request):
        authorization = request.headers.get("authorization")
        if not authorization:
            raise APIError(403, "GUEST_WRITE_FORBIDDEN", "Sign in to post chat.")
        claims = auth.verify_token(authorization)
        if d.db.get("erased", claims.get("player_id", claims["user_id"])):
            raise APIError(403, "FORBIDDEN", "Account has been anonymized.")
        body = await core.read_json(request)
        if not isinstance(body, dict):
            raise validation_error(["body"])
        sender = claims.get("player_id", claims["user_id"])
        room = body.get("chat_room_id")
        state = d.db.get("chat", room, {}) if isinstance(room, str) else {}
        if sender in state.get("muted", []) or sender in state.get("kicked", []):
            raise APIError(403, "FORBIDDEN", "You are muted or removed from this room.")
        result = d.moderation.process({"chat_room_id": room, "incoming_messages": [{
            "message_id": body.get("message_id", "msg-" + secrets.token_hex(12)),
            "sender": sender, "text": body.get("text")}]})
        return result

    @app.get("/api/v1/chat/{room}")
    def chat_read(room: str):
        return {"messages": d.db.get("chat", room, {"messages": []})["messages"]}

    @app.get("/api/v1/players/{pid}")
    def player_profile(pid: str):
        if pid not in auth.PLAYERS:
            raise APIError(404, "PLAYER_NOT_FOUND", "Unknown player.")
        return {"player_id": pid, "club_id": auth.PLAYERS[pid], "followers": sum(bool(v) for v in d.db.all("social:" + pid).values()),
                "matches": [core.ENGINE.score(mid) for mid in core.ENGINE.matches],
                "vod": list(d.db.all("vod:" + pid).values())}

    @app.post("/api/v1/players/{pid}/follow")
    async def follow(pid: str, request: Request):
        claims = auth.verify_token(request.headers.get("authorization"))
        body = await core.read_json(request)
        if not isinstance(body, dict) or not isinstance(body.get("following"), bool):
            raise validation_error(["following"])
        if pid not in auth.PLAYERS:
            raise APIError(404, "PLAYER_NOT_FOUND", "Unknown player.")
        with d.db.transaction():
            d.db.put("social:" + pid, claims["user_id"], body["following"])
            total = sum(bool(v) for v in d.db.all("social:" + pid).values())
        return {"following": body["following"], "follower_count": total}

    @app.get("/api/v1/costream/{sid}")
    def session_read(sid: str):
        result = d.db.get("session", sid)
        if result is None:
            raise APIError(404, "STREAM_NOT_FOUND", "Unknown co-stream.")
        return result

    @app.websocket("/ws/matches/{mid}")
    async def match_socket(ws: WebSocket, mid: str):
        await ws.accept()
        if mid not in core.ENGINE.matches:
            await ws.close(code=1008)
            return
        d.observability.connections += 1
        try:
            version = -1
            while True:
                with core.LOCK:
                    current = core.ENGINE.score(mid)
                if current["version"] != version:
                    await ws.send_json(current)
                    version = current["version"]
                # Receive with a timeout detects closed viewers without waiting for a score change.
                try:
                    await asyncio.wait_for(ws.receive_text(), timeout=0.025)
                except asyncio.TimeoutError:
                    pass
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            d.observability.connections -= 1

    @app.websocket("/ws/chat/{room}")
    async def chat_socket(ws: WebSocket, room: str):
        await ws.accept()
        d.observability.connections += 1
        try:
            sequence = 0
            while True:
                state = d.db.get("chat", room, {"messages": []})
                for message in state["messages"]:
                    if message["sequence"] > sequence:
                        await ws.send_json(message)
                        sequence = message["sequence"]
                try:
                    await asyncio.wait_for(ws.receive_text(), timeout=0.05)
                except asyncio.TimeoutError:
                    pass
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            d.observability.connections -= 1

    @app.websocket("/ws/costream/{sid}/{pid}")
    async def host_socket(ws: WebSocket, sid: str, pid: str):
        try:
            claims = auth.verify_token("Bearer " + ws.query_params.get("token", ""))
        except APIError:
            await ws.close(code=1008)
            return
        state = d.db.get("session", sid)
        if not state or pid not in state["active_participants"] or (claims.get("player_id") != pid and claims["role"] != "super_admin"):
            await ws.close(code=1008)
            return
        await ws.accept()
        try:
            while True:
                await ws.send_json(d.db.get("session", sid))
                await ws.receive_text()
        except WebSocketDisconnect:
            d.costream.drop(sid, pid)

    @app.get("/web/{route:path}", response_class=HTMLResponse)
    def guest_web(route: str):
        return HTMLResponse((Path(__file__).parent / "web" / "guest.html").read_text(encoding="utf-8"))

    @app.get("/assets/{name}")
    def web_asset(name: str):
        if name not in ("guest.js", "guest.css", "creator.js"):
            raise APIError(404, "NOT_FOUND", "Unknown asset.")
        path = Path(__file__).parent / "web" / name
        return Response(path.read_bytes(), media_type="text/css" if name.endswith("css") else "application/javascript")

    return d
