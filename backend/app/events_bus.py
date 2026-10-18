"""Internal job/event queue: domain events are appended to a Redis Stream (best effort,
never blocks or fails a request). Workers consume the "domain-events" stream."""
import json
import threading

import redis

from . import config

_client = None
_lock = threading.Lock()
durable_sink = None


def _redis():
    global _client
    with _lock:
        if _client is None:
            _client = redis.Redis.from_url(config.REDIS_URL, socket_connect_timeout=0.2, socket_timeout=0.2)
        return _client


def publish(event: dict) -> None:
    if durable_sink is not None:
        durable_sink(event)
    try:
        _redis().xadd("domain-events", {"event": json.dumps(event)}, maxlen=10000, approximate=True)
    except Exception:
        pass
