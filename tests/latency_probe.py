"""Measure real score fan-out latency to 25 simultaneous WebSocket clients."""
import asyncio
import json
import os
import statistics
import time
import uuid
from pathlib import Path
import httpx
import websockets


async def probe():
    base = os.environ.get("BASE_URL", "http://localhost:8080")
    client = httpx.AsyncClient()
    for attempt in range(30):
        try:
            response = await client.get(base + "/health")
            if response.status_code == 200:
                break
        except httpx.HTTPError:
            pass
        await asyncio.sleep(.2)
    else:
        raise RuntimeError("Backend did not become ready for latency probe")
    url = base.replace("http", "ws", 1) + "/ws/matches/match-m1"
    sockets = await asyncio.gather(*(websockets.connect(url) for _ in range(25)))
    try:
        initial = await asyncio.gather(*(socket.recv() for socket in sockets))
        version = max(json.loads(m)["version"] for m in initial)
        start = time.monotonic()
        async def receive(socket):
            while True:
                data = json.loads(await asyncio.wait_for(socket.recv(), 2))
                if data["version"] > version:
                    return (time.monotonic() - start) * 1000
        pending = [asyncio.create_task(receive(socket)) for socket in sockets]
        response = await client.post(base + "/audit/v1/events", json={"event_id": "latency-" + uuid.uuid4().hex,
            "match_id": "match-m1", "type": "score", "payload": {"team_id": "club-alpha-1", "event_type": "goal"}})
        response.raise_for_status()
        samples = await asyncio.gather(*pending)
        samples.sort()
        p95 = samples[23]
        result = {"clients": 25, "p95_ms": round(p95, 2), "max_ms": round(max(samples), 2), "passed": p95 < 500}
        Path("tests/reports/latency-report.json").write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result))
        assert result["passed"], "Score fan-out p95 exceeded 500ms"
    finally:
        await client.aclose()
        await asyncio.gather(*(socket.close() for socket in sockets))


if __name__ == "__main__":
    asyncio.run(probe())
