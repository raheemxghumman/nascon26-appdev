"""Phase II contract, signatures, negative cases, persistence and concurrency."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import hmac
import json
import pytest
from fastapi.testclient import TestClient
from app import config, main

client = TestClient(main.app)
config.DAY2_SALT = "test-only-day2"


@pytest.fixture(autouse=True)
def fresh():
    client.post("/audit/v1/reset", json={})


def signed(entity, payload):
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hmac.new(config.DAY2_SALT.encode(), (entity + "|" + canonical).encode(), hashlib.sha256).hexdigest()


def test_keys_rotate_revoke_signature_and_denied_old_ingest(monkeypatch):
    monkeypatch.setattr(main.DAY2.streaming, "disconnect", lambda key: None)
    path = "/audit/v1/stream/key"
    body = {"action": "generate", "player_id": "player-alpha-1", "stream_key_override": "sk_live_9f83a1b2c3d4e5f6"}
    r = client.post(path, json=body)
    assert r.status_code == 201
    out = r.json()
    assert out["signature"] == signed(out["stream_key"], {"action": "generate", "player_id": body["player_id"],
        "status": "active", "stream_key": out["stream_key"]})
    r = client.post(path, json={**body, "action": "rotate", "stream_key_override": "sk_live_aaaaaaaaaaaaaaaa"})
    assert r.status_code == 200
    old = client.post("/internal/media/auth", json={"path": "live/" + out["stream_key"], "action": "publish"})
    assert old.status_code == 409
    assert client.post(path, json={"action": "revoke", "player_id": body["player_id"]}).json()["playback_url"] is None
    assert client.post(path, json={"action": "revoke", "player_id": "player-beta-1"}).status_code == 404


@pytest.mark.parametrize("body,status", [({},400), ({"action":"bad","player_id":"player-alpha-1"},400),
    ({"action":"generate","player_id":"missing"},404), ({"action":"generate","player_id":"player-alpha-1","label":""},400)])
def test_key_validation(body, status):
    assert client.post("/audit/v1/stream/key",json=body).status_code == status


def session_body(**extra):
    return {"session_id":"cs-session-101","host_player_id":"player-alpha-1",
            "participants":["player-alpha-1","player-alpha-2","player-beta-1","player-beta-2"], **extra}


def test_handoff_replay_and_last_host():
    body=session_body(simulate_host_drop=True)
    result=client.post("/audit/v1/costream/session",json=body)
    assert result.status_code==201
    out=result.json()
    assert out["active_host"]=="player-alpha-2" and out["participant_count"]==3
    payload={k:out[k] for k in ("active_host","handoff_occurred","layout","participant_count","session_id","status")}
    assert out["signature"]==signed("cs-session-101",payload)
    assert client.post("/audit/v1/costream/session",json=body).json()==out
    body=session_body(session_id="cs-solo",participants=["player-alpha-1"],simulate_host_drop=True)
    out=client.post("/audit/v1/costream/session",json=body).json()
    assert out["active_host"] is None and out["status"]=="terminated" and out["handoff_occurred"] is False


def test_session_validation():
    for body,status in [(session_body(participants=[]),400),(session_body(participants=["missing"]),404),
        (session_body(host_player_id="player-beta-2",participants=["player-alpha-1"]),400),
        (session_body(layout="solo"),400),(session_body(layout="bad"),400),
        (session_body(participants=["player-alpha-1"]*2),400)]:
        assert client.post("/audit/v1/costream/session",json=body).status_code==status


def test_qr_dynamic_route_counter_inspect_and_real_exports():
    url="/audit/v1/qr/match-m1"
    first=client.get(url+"?inspect=true").json()
    assert first["scan_count"]==0 and first["target_route"].endswith("/live")
    assert client.get(url).json()["scan_count"]==1
    assert client.get(url+"?inspect=true").json()["scan_count"]==1
    assert client.get("/q/m1-live",follow_redirects=False).status_code==302
    assert client.post("/audit/v1/events",json={"event_id":"end-m1","match_id":"match-m1","type":"match_end"}).status_code==201
    after=client.get(url).json()
    assert after["short_url"]==first["short_url"] and after["target_route"].endswith("/vod") and after["signature"]!=first["signature"]
    for fmt,magic in [("svg",b"<?xml"),("png",b"\x89PNG\r\n\x1a\n"),("pdf",b"%PDF-")]:
        out=client.get(url+"/export."+fmt)
        assert out.status_code==200 and (out.content.startswith(magic) or (fmt=="svg" and out.content.startswith(b"<svg")))
    assert client.get("/audit/v1/qr/missing").status_code==404
    assert client.get("/q/missing",follow_redirects=False).status_code==404


def merge_body(**extra):
    return {"guest_token":"guest_anon_tok_7721","registered_user_id":"player-alpha-1",
            "guest_cart":[{"variant_id":"var-jersey-001-L","quantity":1}],"test_write_block":True,**extra}


def test_guest_direct_write_guard_and_atomic_concurrent_retry():
    headers={"Authorization":"Bearer guest_anon_tok_7721"}
    for path in ("/api/v1/chat","/audit/v1/events","/audit/v1/checkout","/audit/v1/roster/transfer"):
        r=client.post(path,json={},headers=headers)
        assert r.status_code==403 and r.json()["error"]["code"]=="GUEST_WRITE_FORBIDDEN"
    with ThreadPoolExecutor(max_workers=10) as pool:
        results=list(pool.map(lambda _: client.post("/audit/v1/guest/cart-merge",json=merge_body()),range(10)))
    assert all(r.status_code==200 and r.json()["active_cart"]["total_items"]==1 for r in results)
    assert client.post("/audit/v1/guest/cart-merge",json=merge_body(registered_user_id="player-alpha-2")).status_code==409


def test_merge_validation_and_stock():
    for body,status in [(merge_body(guest_cart=[]),400),(merge_body(registered_user_id="missing"),404),
       (merge_body(guest_cart=[{"variant_id":"missing","quantity":1}]),404),
       (merge_body(guest_cart=[{"variant_id":"var-jersey-001-L","quantity":6}]),409),
       (merge_body(guest_cart=[{"variant_id":"var-jersey-001-L","quantity":True}]),400)]:
        assert client.post("/audit/v1/guest/cart-merge",json=body).status_code==status


def test_moderation_examples_concurrency_dlq_and_metrics():
    body={"chat_room_id":"chat-cs-session-101","incoming_messages":[
        {"message_id":"msg-1","sender":"clean","text":"Clean sports commentary"},
        {"message_id":"msg-2","sender":"user-spammer","text":"Watch this illegal stream b@d_w0rd now!"},
        {"message_id":"msg-3","sender":"user-flooder","text":"GOAL! AAAA!!!"}],"check_dlq":True}
    with ThreadPoolExecutor(max_workers=10) as pool:
        responses=list(pool.map(lambda _: client.post("/audit/v1/moderation/test",json=body),range(10)))
    assert all(r.status_code==200 for r in responses)
    out=responses[0].json()
    assert out["kicked_users"]==["user-spammer"] and out["muted_users"]==["user-flooder"]
    assert len(out["filtered_messages"])==2 and out["filtered_messages"][1]["text"]=="Watch this illegal stream *** now!"
    assert out["signature"]==signed(body["chat_room_id"],{"chat_room_id":body["chat_room_id"],"flagged_count":2,"kicked_users":["user-spammer"],"queue_depth":0})
    out=client.post("/audit/v1/moderation/test",json={**body,"incoming_messages":[],"simulate_failed_notifications":2}).json()
    assert out["dlq_status"]["queue_depth"]==2
    r=client.get("/metrics")
    assert r.status_code==200 and "nascon_dlq_depth 2" in r.text
    assert client.delete("/audit/v1/privacy/user/player-alpha-1").json()["tokens_wiped"] is True


@pytest.mark.parametrize("text",["p.0.r.n", "s!c@m", "f*u*c*k", "a$$h0le", "bad_word", "idiot_spam"])
def test_obfuscated_words(text):
    r=client.post("/audit/v1/moderation/test",json={"chat_room_id":"room","incoming_messages":[{"message_id":"m","sender":"s","text":text}]})
    assert r.status_code==200 and r.json()["filtered_messages"][0]["text"]=="***"


def test_live_web_and_socket():
    assert client.get("/web/matches/match-m1/live").status_code==200
    with client.websocket_connect("/ws/matches/match-m1") as ws:
        assert ws.receive_json()["home"]["score"]==1
        client.post("/audit/v1/events",json={"event_id":"new-goal","match_id":"match-m1","type":"score","payload":{"team_id":"club-alpha-2","event_type":"goal"}})
        assert ws.receive_json()["away"]["score"]==1
