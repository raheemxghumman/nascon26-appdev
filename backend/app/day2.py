"""Phase II integration; keeps the Phase I contract and history intact."""
import asyncio
import base64
import hmac
import json
import secrets
import time
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
        core.events_bus.durable_sink = self.enqueue

    def enqueue(self, event):
        import hashlib
        raw = json.dumps(event, sort_keys=True, separators=(",", ":"))
        eid = "notification-" + hashlib.sha256(raw.encode()).hexdigest()[:24]
        with self.db.transaction():
            if self.db.get("notification", eid) is None:
                self.db.put("notification", eid, {"event_id": eid, "created": time.time(), **event})

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
        self.qr.inspect_cache.clear()
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

    @app.post("/api/v1/costream/{sid}/control")
    async def session_control(sid: str, request: Request):
        claims = auth.verify_token(request.headers.get("authorization"))
        body = await core.read_json(request)
        if not isinstance(body, dict) or body.get("action") not in ("invite", "mute", "unmute", "kick", "spotlight") or not isinstance(body.get("player_id"), str):
            raise validation_error(["action", "player_id"])
        state = d.db.get("session", sid)
        if not state:
            raise APIError(404, "STREAM_NOT_FOUND", "Unknown co-stream.")
        if claims.get("player_id") != state["active_host"] and claims["role"] != "super_admin":
            raise APIError(403, "FORBIDDEN", "Only the active host may moderate this broadcast.")
        pid, action = body["player_id"], body["action"]
        if pid not in auth.PLAYERS:
            raise APIError(404, "PLAYER_NOT_FOUND", "Unknown player.")
        if action == "invite":
            from .streaming import signature
            payload = {"session_id": sid, "player_id": pid, "expires": int(time.time()) + 3600, "nonce": secrets.token_hex(8)}
            data = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode()
            token = data + "." + signature(sid, payload)
            d.db.put("invite", token, payload)
            core.events_bus.publish({"type": "costream.invite", "recipient": pid, "session_id": sid, "invite_token": token})
            return {"invite_token": token, "expires_in": 3600}
        if pid not in state["active_participants"]:
            raise validation_error(["player_id"])
        if action == "kick":
            return d.costream.drop(sid, pid)
        with d.db.transaction():
            controls = d.db.get("session_controls", sid, {"muted": [], "spotlight": None})
            if action == "mute" and pid not in controls["muted"]:
                controls["muted"].append(pid)
            elif action == "unmute":
                controls["muted"] = [p for p in controls["muted"] if p != pid]
            elif action == "spotlight":
                controls["spotlight"] = pid
            d.db.put("session_controls", sid, controls)
        return {"session_id": sid, **controls}

    @app.post("/api/v1/costream/{sid}/join")
    async def broadcaster_join(sid: str, request: Request):
        from .streaming import signature
        claims = auth.verify_token(request.headers.get("authorization"))
        body = await core.read_json(request)
        if not isinstance(body, dict) or not isinstance(body.get("invite_token"), str):
            raise validation_error(["invite_token"])
        token = body["invite_token"]
        invitation = d.db.get("invite", token)
        if (not invitation or invitation["expires"] < time.time() or invitation["session_id"] != sid
                or invitation["player_id"] != claims.get("player_id")
                or not hmac.compare_digest(token.rsplit(".", 1)[-1], signature(sid, invitation))):
            raise APIError(403, "FORBIDDEN", "Invalid, expired or foreign invitation.")
        with d.db.transaction():
            state = d.db.get("session", sid)
            if not state or state["status"] != "active":
                raise APIError(404, "STREAM_NOT_FOUND", "Broadcast is not active.")
            active = state["active_participants"]
            pid = claims["player_id"]
            if pid in active:
                return state
            if len(active) >= 4:
                raise APIError(409, "COSTREAM_SESSION_FULL", "Maximum four broadcasters.")
            if state["layout"] == "solo" or (state["layout"] == "grid_2" and len(active) >= 2):
                raise APIError(400, "UNSUPPORTED_LAYOUT", "Layout cannot fit another broadcaster.")
            active.append(pid)
            result = d.costream._response(sid, active, state["layout"], False, state["active_host"])
            d.db.put("session", sid, result)
            return result

    @app.get("/audit/v1/qr/{entity_id}/export.{fmt}")
    def qr_export(entity_id: str, fmt: str):
        data, mime = d.qr.export(entity_id, fmt)
        return Response(data, media_type=mime, headers={"Content-Disposition": f'inline; filename="qr.{fmt}"'})

    @app.get("/audit/v1/qr/{entity_id}")
    async def qr(entity_id: str, request: Request, inspect: bool = False):
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
            controls = d.db.get("session_controls", sid, {"muted": [], "spotlight": None})
            inputs = []
            for pid in state["active_participants"]:
                key = d.db.get("creator", pid)
                if key and key["status"] == "active":
                    inputs.append({"path": "live/" + key["stream_key"], "player_id": pid, "muted": pid in controls["muted"]})
            if controls["spotlight"]:
                inputs.sort(key=lambda item: item["player_id"] != controls["spotlight"])
            sessions.append({**state, "layout": "spotlight" if controls["spotlight"] else state["layout"], "inputs": inputs})
        return sessions

    @app.post("/internal/media/recording")
    async def recording(request: Request):
        from . import object_storage
        body = await core.read_json(request)
        if not isinstance(body, dict) or not isinstance(body.get("path"), str) or not isinstance(body.get("stream"), str):
            raise validation_error(["path", "stream"])
        path = Path(body["path"]).resolve()
        if not path.is_relative_to(Path("/recordings")) or not path.is_file():
            raise validation_error(["path"])
        object_name = str(path.relative_to("/recordings"))
        await asyncio.to_thread(object_storage.upload, object_name, path.read_bytes())
        record = {"object": object_name, "stream": body["stream"], "playback_url": "/api/v1/vod/" + object_name}
        d.db.put("vod", object_name, record)
        key = d.db.get("key", body["stream"].removeprefix("live/"))
        if key:
            d.db.put("vod:" + key["player_id"], object_name, record)
        return {"status": "indexed", **record}

    @app.get("/api/v1/vod/{name:path}")
    def vod(name: str):
        from . import object_storage
        if d.db.get("vod", name) is None:
            raise APIError(404, "STREAM_NOT_FOUND", "Recording not found.")
        return Response(object_storage.download(name), media_type="video/mp4")

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
        # A valid key authorizes ingest; only a ready media path proves a broadcast exists.
        try:
            response = httpx.get(f"{config.MEDIA_API}/v3/paths/list", timeout=1)
            response.raise_for_status()
            ready = {item["name"] for item in response.json().get("items", []) if item.get("ready")}
        except (httpx.HTTPError, ValueError, KeyError):
            return {"path": None}
        if entity.startswith("cs-session-"):
            session = d.db.get("session", entity)
            if session and session["status"] == "active" and f"costream/{entity}" in ready:
                return {"path": f"costream/{entity}"}
            return {"path": None}
        for record in d.db.all("creator").values():
            if record["status"] == "active" and "live/" + record["stream_key"] in ready and (not entity.startswith("player-") or entity == record["player_id"]):
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

    @app.api_route("/media/read/{path:path}", methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"])
    async def media_reader_proxy(path: str, request: Request):
        """Same-origin WHEP player works from Grid nodes, the phone and a LAN browser."""
        raw = await request.body()
        if len(raw) > config.MAX_BODY_BYTES:
            raise APIError(413, "PAYLOAD_TOO_LARGE", "Request body exceeds 1 MB.")
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                response = await client.request(request.method, f"http://media:8889/{path}",
                    params=request.query_params, content=raw,
                    headers={key: request.headers[key] for key in ("content-type", "if-match") if key in request.headers})
            headers = {key: response.headers[key] for key in ("content-type", "accept-patch", "etag", "link") if key in response.headers}
            if "location" in response.headers:
                from urllib.parse import urlparse
                headers["location"] = "/media/read" + urlparse(response.headers["location"]).path
            return Response(response.content, status_code=response.status_code, headers=headers)
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
        return {"messages": d.moderation.messages(room)}

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
                for message in d.moderation.messages(room):
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

    @app.websocket("/ws/notifications")
    async def notifications(ws: WebSocket):
        await ws.accept()
        connected_at = time.time()
        try:
            hello = await asyncio.wait_for(ws.receive_json(), timeout=3)
            claims = auth.verify_token("Bearer " + hello.get("token", ""))
        except (APIError, ValueError, TypeError, AttributeError, asyncio.TimeoutError, WebSocketDisconnect):
            await ws.close(code=1008)
            return
        uid = claims.get("player_id", claims["user_id"])
        last = d.db.get("notification", hello.get("last_event_id", ""))
        cutoff = last["created"] if last else connected_at
        d.observability.connections += 1
        try:
            while True:
                if d.db.get("erased", uid):
                    await ws.close(code=1008)
                    return
                for event in sorted(d.db.all("notification").values(), key=lambda x:x["created"]):
                    if event["created"] < cutoff or event.get("recipient") not in (None, uid, claims["user_id"]):
                        continue
                    eid = event["event_id"]
                    if d.db.get("delivered:" + uid, eid):
                        continue
                    for attempt in range(3):
                        try:
                            await ws.send_json(event)
                            d.db.put("delivered:" + uid, eid, True)
                            d.db.delete("dlq", "notify:" + eid + ":" + uid)
                            break
                        except (WebSocketDisconnect, RuntimeError, OSError):
                            if attempt < 2:
                                await asyncio.sleep(.02 * 2 ** attempt)
                    else:
                        d.db.put("dlq", "notify:" + eid + ":" + uid,
                                 {**event, "recipient": uid, "attempts": 3, "status": "undelivered"})
                        return
                try:
                    await asyncio.wait_for(ws.receive_text(), timeout=.1)
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
