"""Synchronous filtering with durable deduplicated decisions and retry/DLQ records."""
import re
import time
import uuid
import unicodedata
from .errors import validation_error
from .streaming import signature

WORDS = ("badword", "porn", "scam", "fuck", "shit", "bitch", "asshole", "idiotspam")
TRANSLATE = str.maketrans({"@": "a", "0": "o", "1": "i", "!": "i", "3": "e", "$": "s"})


def mask(text):
    # Preserve original character offsets so only offending spans are replaced.
    spans = []
    # The brief uses ! both as an i substitution and as an inserted separator.
    for bang_is_separator in (False, True):
        compact, positions = [], []
        for index, character in enumerate(text):
            if bang_is_separator and character == "!":
                continue
            normalized = unicodedata.normalize("NFKC", character).lower().translate(TRANSLATE)
            for ch in normalized:
                if ch.isalnum():
                    compact.append(ch)
                    positions.append(index)
        normalized = "".join(compact)
        for word in WORDS:
            for match in re.finditer(re.escape(word), normalized):
                spans.append((positions[match.start()], positions[match.end() - 1] + 1))
    # Merge overlapping matches and replace from the end to preserve offsets.
    merged = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    for start, end in reversed(merged):
        text = text[:start] + "***" + text[end:]
    return text, bool(merged)


class Moderation:
    def __init__(self, db):
        self.db = db

    def messages(self, room):
        return sorted(self.db.all("chat_message:" + room).values(), key=lambda m: m["sequence"])

    def deliver(self, event, sender):
        """Try actual delivery three times, then persist the undelivered event."""
        for attempt in range(1, 4):
            try:
                sender(event)
                return True
            except (ConnectionError, TimeoutError, OSError):
                if attempt < 3:
                    time.sleep(0.02 * 2 ** (attempt - 1))
        record = {**event, "attempts": 3, "retry_delays_ms": [20, 40], "status": "undelivered"}
        self.db.put("dlq", event["event_id"], record)
        return False

    def process(self, body):
        if not isinstance(body, dict):
            raise validation_error(["body"])
        room, incoming = body.get("chat_room_id"), body.get("incoming_messages")
        bad = []
        if not isinstance(room, str) or not room:
            bad.append("chat_room_id")
        if (not isinstance(incoming, list) or any(not isinstance(m, dict) or any(
                not isinstance(m.get(k), str) or not m[k] for k in ("message_id", "sender", "text")) for m in incoming)):
            bad.append("incoming_messages")
        if not isinstance(body.get("check_dlq", False), bool):
            bad.append("check_dlq")
        failures = body.get("simulate_failed_notifications", 0)
        if type(failures) is not int or not 0 <= failures <= 10000:
            bad.append("simulate_failed_notifications")
        if bad:
            raise validation_error(bad)
        # The explicit audit simulation uses the same retry path as real delivery.
        def disconnected_target(event):
            raise ConnectionError("Simulated disconnected notification target")
        for _ in range(failures):
            self.deliver({"event_id": "failed-" + uuid.uuid4().hex, "chat_room_id": room}, disconnected_target)
        filtered = []
        flagged_count = 0
        with self.db.transaction():
            state = self.db.get("chat", room, {"kicked": [], "muted": [], "messages": [], "decisions": {}, "rates": {}, "seq": 0})
            for msg in incoming:
                mid, sender, text = msg["message_id"], msg["sender"], msg["text"]
                prior = self.db.get("chat_decision:" + room, mid)
                if prior:
                    if prior["message"] is not None:
                        filtered.append(prior["message"])
                    flagged_count += int(prior["flagged"])
                    continue
                flood = bool(re.search(r"(.)\1{3,}|[!?]{3,}", text, re.I))
                now = time.time()
                recent = [t for t in state["rates"].get(sender, []) if t > now - 2]
                recent.append(now)
                state["rates"][sender] = recent
                limited = len(recent) > 3
                cleaned, profanity = mask(text)
                flagged = flood or limited or profanity
                flagged_count += int(flagged)
                result = None
                if flood or limited:
                    if sender not in state["muted"]:
                        state["muted"].append(sender)
                else:
                    result = {**msg, "text": cleaned, "flagged": profanity,
                              "reason": "profanity_leetspeak" if profanity else None}
                    filtered.append(result)
                    state["seq"] += 1
                    message = {**result, "sequence": state["seq"]}
                    self.db.put("chat_message:" + room, mid, message)
                    state["messages"] = (state["messages"] + [message])[-20:]
                if profanity and sender not in state["kicked"]:
                    state["kicked"].append(sender)
                self.db.put("chat_decision:" + room, mid, {"flagged": flagged, "message": result})
            state["decisions"] = {}
            self.db.put("chat", room, state)
            dlq = list(self.db.all("dlq").values())
            payload = {"chat_room_id": room, "flagged_count": flagged_count,
                       "kicked_users": state["kicked"], "queue_depth": len(dlq)}
            return {"chat_room_id": room, "filtered_messages": filtered,
                    "kicked_users": state["kicked"], "muted_users": state["muted"],
                    "dlq_status": {"queue_depth": len(dlq), "undelivered_events": dlq},
                    "signature": signature(room, payload)}
