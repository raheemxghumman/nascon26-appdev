"""Uniform error body (spec 5.2): {"error": {"code", "message", "details"}}."""
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class APIError(Exception):
    def __init__(self, status: int, code: str, message: str, details: dict | None = None):
        self.status = status
        self.code = code
        self.message = message
        self.details = details or {}


def error_response(status: int, code: str, message: str, details: dict | None = None, headers=None):
    body = {"error": {"code": code, "message": message, "details": details or {}}}
    return JSONResponse(status_code=status, content=body, headers=headers)


def validation_error(fields: list[str], message: str = "Request validation failed.") -> APIError:
    return APIError(400, "VALIDATION_ERROR", message, {"fields": fields})


async def api_error_handler(_: Request, exc: APIError):
    return error_response(exc.status, exc.code, exc.message, exc.details)


async def request_validation_handler(_: Request, exc: RequestValidationError):
    fields = []
    for err in exc.errors():
        loc = [str(p) for p in err.get("loc", []) if p != "body"]
        name = ".".join(loc) if loc else "body"
        if name not in fields:
            fields.append(name)
    return error_response(400, "VALIDATION_ERROR", "Request validation failed.", {"fields": fields})
