"""Dynamic QR routing, privacy-minimal scan counters and transactional guest cart migration."""
import io
from collections import Counter
from datetime import datetime, timezone
import qrcode
import qrcode.image.svg
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from . import auth, config
from .errors import APIError, validation_error
from .store import VARIANTS
from .streaming import signature


class QRGuest:
    def __init__(self, db, engine, store):
        self.db, self.engine, self.store = db, engine, store

    def seed(self):
        for entity, code in (("match-m1", "m1-live"), ("player-alpha-1", "p-alpha-1"), ("club-alpha-1", "c-alpha-1")):
            if self.db.get("qr", entity) is None:
                self.db.put("qr", entity, {"code": code, "scan_count": 0, "buckets": {}})
                self.db.put("short", code, entity)
        if self.db.get("guest", "guest_anon_tok_7721") is None:
            self.db.put("guest", "guest_anon_tok_7721", {"valid": True, "merged": False})

    def exists(self, entity):
        return (entity in self.engine.matches or entity in auth.PLAYERS or entity in auth.CLUBS
                or self.db.get("session", entity) is not None)

    def metadata(self, entity, inspect=False, user_agent=""):
        if not self.exists(entity):
            raise APIError(404, "QR_NOT_FOUND", "Unknown QR entity.")
        kind = "match" if entity in self.engine.matches else ("player" if entity in auth.PLAYERS else
                ("club" if entity in auth.CLUBS else "costream"))
        status = "active"
        if kind == "match":
            status = self.engine.score(entity)["status"]
            tail = {"upcoming": "preview", "in_progress": "live", "completed": "vod"}.get(status, f"notice?state={status}")
            route = f"/web/matches/{entity}/{tail}"
        else:
            route = f"/web/{'players' if kind == 'player' else 'clubs' if kind == 'club' else 'costream'}/{entity}"
        with self.db.transaction():
            record = self.db.get("qr", entity)
            if record is None:
                import hashlib
                code = hashlib.sha256(entity.encode()).hexdigest()[:12]
                record = {"code": code, "scan_count": 0, "buckets": {}}
                self.db.put("short", code, entity)
            if not inspect:
                record["scan_count"] += 1
                family = "mobile" if any(s in user_agent.lower() for s in ("mobile", "android", "iphone")) else "desktop"
                bucket = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:00:00Z") + ":" + family
                record["buckets"][bucket] = record["buckets"].get(bucket, 0) + 1
            if not inspect or self.db.get("qr", entity) is None:
                self.db.put("qr", entity, record)
        short = f"{config.PUBLIC_BASE}/q/{record['code']}"
        payload = {"entity_id": entity, "short_url": short, "target_route": route}
        return {**payload, "entity_type": kind, "entity_status": status,
                "deep_link_uri": f"nascon://entity/{entity}", "scan_count": record["scan_count"],
                "export_formats": {fmt: f"{config.PUBLIC_BASE}/audit/v1/qr/{entity}/export.{fmt}" for fmt in ("svg", "png", "pdf")},
                "signature": signature(entity, payload)}

    def export(self, entity, fmt):
        metadata = self.metadata(entity, inspect=True)
        url = metadata["short_url"]
        out = io.BytesIO()
        if fmt == "svg":
            qrcode.make(url, image_factory=qrcode.image.svg.SvgPathImage).save(out)
            return out.getvalue(), "image/svg+xml"
        if fmt == "png":
            qrcode.make(url).save(out, format="PNG")
            return out.getvalue(), "image/png"
        if fmt == "pdf":
            image = io.BytesIO()
            qrcode.make(url).save(image, format="PNG")
            pdf = canvas.Canvas(out)
            pdf.setTitle(f"LeagueDesk QR — {entity}")
            pdf.setFont("Helvetica-Bold", 22)
            pdf.drawString(70, 760, "LEAGUEDESK / SCAN TO WATCH")
            pdf.drawImage(ImageReader(image), 100, 320, 395, 395)
            pdf.setFont("Helvetica", 13)
            pdf.drawString(70, 270, entity)
            pdf.drawString(70, 245, url)
            pdf.save()
            return out.getvalue(), "application/pdf"
        raise validation_error(["fmt"])

    def merge(self, body):
        if not isinstance(body, dict):
            raise validation_error(["body"])
        token, uid, cart = body.get("guest_token"), body.get("registered_user_id"), body.get("guest_cart")
        bad = []
        if not isinstance(token, str) or not token.startswith("guest_"):
            bad.append("guest_token")
        if not isinstance(uid, str) or not uid:
            bad.append("registered_user_id")
        if (not isinstance(cart, list) or not 1 <= len(cart) <= 10 or any(
                not isinstance(i, dict) or not isinstance(i.get("variant_id"), str)
                or type(i.get("quantity")) is not int or i["quantity"] < 1 for i in cart)):
            bad.append("guest_cart")
        if not isinstance(body.get("test_write_block", True), bool):
            bad.append("test_write_block")
        if bad:
            raise validation_error(bad)
        if uid not in auth.PLAYERS and uid not in [u["user_id"] for u in auth.USERS.values()]:
            raise APIError(404, "PLAYER_NOT_FOUND", "Unknown registered user.")
        if any(i["variant_id"] not in VARIANTS for i in cart):
            raise APIError(404, "VARIANT_NOT_FOUND", "Unknown variant.")
        fingerprint = {"registered_user_id": uid, "guest_cart": cart}
        with self.store.lock, self.db.transaction():
            prior = self.db.get("merge", token)
            if prior:
                if prior["request"] != fingerprint:
                    raise APIError(409, "GUEST_TOKEN_ALREADY_MERGED", "This guest token has already been merged.")
                return prior["response"]
            guest = self.db.get("guest", token)
            if guest and not guest.get("valid", False):
                raise APIError(403, "GUEST_WRITE_FORBIDDEN", "Guest token is invalid.")
            quantities = Counter(self.db.get("cart", uid, {}))
            for item in cart:
                quantities[item["variant_id"]] += item["quantity"]
            for vid, qty in quantities.items():
                if qty > self.store.stock.get(vid, 0):
                    raise APIError(409, "OUT_OF_STOCK", "Merged quantity exceeds available stock.", {"variant_id": vid})
            blocked = body.get("test_write_block", True)
            if blocked:
                try:
                    forbid_guest("Bearer " + token)
                except APIError as exc:
                    blocked = exc.status == 403 and exc.code == "GUEST_WRITE_FORBIDDEN"
            total = sum(quantities.values())
            payload = {"cart_merged": True, "guest_token": token, "registered_user_id": uid,
                       "total_items": total, "write_rejection_code": 403 if blocked else 0}
            items = [{"variant_id": vid, "quantity": qty, "unit_price_minor": VARIANTS[vid]["price_minor"]}
                     for vid, qty in quantities.items()]
            response = {"guest_token": token, "write_block_verified": blocked,
                        "write_rejection_code": payload["write_rejection_code"], "cart_merged": True,
                        "active_cart": {"user_id": uid, "currency": "PKR", "total_items": total,
                            "subtotal_minor": sum(i["quantity"] * i["unit_price_minor"] for i in items), "items": items},
                        "signature": signature(token, payload)}
            self.db.put("cart", uid, dict(quantities))
            self.db.put("merge", token, {"request": fingerprint, "response": response})
            self.db.put("guest", token, {"valid": False, "merged": True, "user_id": uid})
            return response


def forbid_guest(authorization):
    if isinstance(authorization, str) and authorization.removeprefix("Bearer ").strip().startswith("guest_"):
        raise APIError(403, "GUEST_WRITE_FORBIDDEN", "Anonymous guest tokens cannot perform write mutations.")
