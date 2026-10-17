"""Background worker: consumes the internal "domain-events" Redis stream (order status
changes, match events) through a consumer group and acknowledges each message."""
import json
import time

import redis

from . import config

STREAM, GROUP, CONSUMER = "domain-events", "workers", "worker-1"


def main():
    client = redis.Redis.from_url(config.REDIS_URL)
    while True:
        try:
            try:
                client.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
            except redis.ResponseError:
                pass  # group already exists
            while True:
                batch = client.xreadgroup(GROUP, CONSUMER, {STREAM: ">"}, count=50, block=5000)
                for _, messages in batch or []:
                    for msg_id, fields in messages:
                        event = json.loads(fields[b"event"])
                        print(f"[worker] {event.get('type')} {json.dumps(event)}", flush=True)
                        client.xack(STREAM, GROUP, msg_id)
        except redis.ConnectionError:
            time.sleep(1)


if __name__ == "__main__":
    main()
