"""Merchandise store: concurrency-safe checkout, mock payment gateway, signed PDF receipts
(FR-2.3, NFR-3, spec 5.12). Stock changes happen only while holding the store lock, so
reserve-then-commit can never oversell."""
import base64
import copy
import threading

from . import config
from .common import is_id, is_int, now_iso
from .errors import APIError, validation_error
from .signing import sign

DISCOUNTS = {"WELCOME10": 10}
VARIANTS = {
    "var-jersey-001-M": {"product_id": "prod-jersey-001", "label": "Size M", "price_minor": 450000},
    "var-jersey-001-L": {"product_id": "prod-jersey-001", "label": "Size L", "price_minor": 450000},
}
PRODUCTS = {
    "prod-jersey-001": {"product_id": "prod-jersey-001", "tenant_id": "tenant-alpha", "club_id": "club-alpha-1",
                        "name": "Alpha Home Jersey 2026", "category": "apparel",
                        "description": "Official home jersey.", "currency": "PKR"},
}


class Store:
    def __init__(self, publish=None):
        self.lock = threading.RLock()
        self.publish = publish or (lambda event: None)
        self.reset({})

    def reset(self, stock: dict):
        with self.lock:
            self.stock = {"var-jersey-001-M": 1, "var-jersey-001-L": 5}
            self.stock.update(stock or {})
            self.reserved = {v: 0 for v in self.stock}
            self.orders: dict[str, dict] = {}
            self.counter = 0

    def inventory(self, variant_id: str) -> dict:
        with self.lock:
            if variant_id not in self.stock:
                raise APIError(404, "VARIANT_NOT_FOUND", "Unknown variant.", {"variant_id": variant_id})
            return {"variant_id": variant_id, "stock": self.stock[variant_id], "reserved": self.reserved[variant_id]}

    def products(self) -> list:
        with self.lock:
            out = []
            for pid, p in PRODUCTS.items():
                variants = [{"variant_id": vid, "label": v["label"], "price_minor": v["price_minor"],
                             "currency": "PKR", "stock": self.stock.get(vid, 0)}
                            for vid, v in VARIANTS.items() if v["product_id"] == pid]
                out.append({**p, "variants": variants})
            return out

    # ---- checkout -------------------------------------------------------
    def _validate(self, body):
        if not isinstance(body, dict):
            raise validation_error(["body"])
        bad = []
        if not is_id(body.get("order_id")):
            bad.append("order_id")
        cust = body.get("customer_id")
        if not isinstance(cust, str) or not 1 <= len(cust) <= 256:
            bad.append("customer_id")
        items = body.get("items")
        if not isinstance(items, list) or not 1 <= len(items) <= 10:
            bad.append("items")
        else:
            seen = set()
            for it in items:
                if (not isinstance(it, dict) or not is_id(it.get("variant_id")) or not is_int(it.get("quantity"))
                        or not 1 <= it["quantity"] <= 10 or it["variant_id"] in seen):
                    bad.append("items")
                    break
                seen.add(it["variant_id"])
        code = body.get("discount_code")
        if code is not None and not isinstance(code, str):
            bad.append("discount_code")
        pay = body.get("payment")
        if not isinstance(pay, dict) or not isinstance(pay.get("token"), str):
            bad.append("payment")
        if bad:
            raise validation_error(bad)

    def checkout(self, body) -> tuple:
        self._validate(body)
        order_id = body["order_id"]
        with self.lock:
            stored = self.orders.get(order_id)
            if stored is not None:
                if stored["request"] == body:
                    return 200, copy.deepcopy(stored["response"])
                raise APIError(409, "DUPLICATE_ORDER_ID", "order_id was already used with a different body.",
                               {"order_id": order_id})
            for it in body["items"]:
                if it["variant_id"] not in self.stock:
                    raise APIError(404, "VARIANT_NOT_FOUND", "Unknown variant.", {"variant_id": it["variant_id"]})
            code = body.get("discount_code")
            if code is not None and code not in DISCOUNTS:
                raise APIError(400, "INVALID_DISCOUNT_CODE", "Unknown discount code.", {"discount_code": code})
            # Reserve everything or nothing.
            for it in body["items"]:
                if self.stock[it["variant_id"]] < it["quantity"]:
                    raise APIError(409, "OUT_OF_STOCK", f"Variant {it['variant_id']} has no stock left.",
                                   {"variant_id": it["variant_id"]})
            for it in body["items"]:
                self.stock[it["variant_id"]] -= it["quantity"]
                self.reserved[it["variant_id"]] += it["quantity"]
            self.counter += 1
            n = self.counter
        try:
            token = body["payment"]["token"]
            if token != "tok_success" and token != "tok_capture_fail":
                raise APIError(402, "PAYMENT_DECLINED", "The payment was declined.", {"order_id": order_id})
            if token == "tok_capture_fail":
                raise APIError(402, "PAYMENT_CAPTURE_FAILED", "The payment could not be captured.",
                               {"order_id": order_id})
        except APIError:
            with self.lock:
                for it in body["items"]:
                    self.stock[it["variant_id"]] += it["quantity"]
                    self.reserved[it["variant_id"]] -= it["quantity"]
            self.publish({"type": "order.payment_failed", "order_id": order_id})
            raise
        with self.lock:
            for it in body["items"]:
                self.reserved[it["variant_id"]] -= it["quantity"]
            response = self._receipt(body, n)
            self.orders[order_id] = {"request": copy.deepcopy(body), "response": response, "status": "paid"}
        self.publish({"type": "order.status_changed", "order_id": order_id, "from": "pending", "to": "paid"})
        return 201, copy.deepcopy(response)

    def _receipt(self, body, n) -> dict:
        items = [{"variant_id": it["variant_id"], "quantity": it["quantity"],
                  "unit_price_minor": VARIANTS[it["variant_id"]]["price_minor"]
                  if it["variant_id"] in VARIANTS else 0} for it in body["items"]]
        subtotal = sum(i["quantity"] * i["unit_price_minor"] for i in items)
        pct = DISCOUNTS.get(body.get("discount_code"), 0)
        discount = subtotal * pct // 100
        total = subtotal - discount
        payload = {"order_id": body["order_id"], "customer_id": body["customer_id"], "items": items,
                   "subtotal_minor": subtotal, "discount_minor": discount, "total_minor": total,
                   "currency": "PKR", "paid_at": now_iso()}
        pdf = render_receipt_pdf(payload)
        return {"order_id": body["order_id"], "status": "paid", "currency": "PKR", "items": items,
                "subtotal_minor": subtotal, "discount_minor": discount, "total_minor": total,
                "payment": {"authorization_id": f"auth_{n}", "capture_id": f"cap_{n}", "state": "captured"},
                "receipt": {"payload": payload, "signature": sign(config.DAY1_SALT, body["order_id"], payload),
                            "pdf_base64": base64.b64encode(pdf).decode("ascii")}}


def money(minor: int) -> str:
    return "PKR %d.%02d" % (minor // 100, minor % 100)


def _pdf_text(s: str) -> str:
    s = s.encode("ascii", "replace").decode("ascii")
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def render_receipt_pdf(p: dict) -> bytes:
    """Minimal single-page PDF (Helvetica text) generated server-side."""
    lines = ["NaSCon League Store - Receipt", f"Order: {p['order_id']}", f"Customer: {p['customer_id']}",
             f"Paid at: {p['paid_at']}", ""]
    for it in p["items"]:
        lines.append(f"{it['variant_id']} x{it['quantity']}  {money(it['unit_price_minor'] * it['quantity'])}")
    lines += ["", f"Subtotal: {money(p['subtotal_minor'])}", f"Discount: {money(p['discount_minor'])}",
              f"Total: {money(p['total_minor'])}"]
    ops = ["BT", "/F1 12 Tf", "50 790 Td", "16 TL"]
    for line in lines:
        ops.append(f"({_pdf_text(line)}) Tj T*")
    ops.append("ET")
    stream = "\n".join(ops).encode("ascii")
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> "
            b"/Contents 5 0 R >>",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
            b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)
