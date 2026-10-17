import psycopg
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError

from . import config
from .errors import APIError, api_error_handler, error_response, request_validation_handler

app = FastAPI(title="NaSCon'26 League & Club Operations Platform")
app.add_exception_handler(APIError, api_error_handler)
app.add_exception_handler(RequestValidationError, request_validation_handler)


@app.middleware("http")
async def limit_body_size(request: Request, call_next):
    length = request.headers.get("content-length")
    if length is not None and length.isdigit() and int(length) > config.MAX_BODY_BYTES:
        return error_response(413, "PAYLOAD_TOO_LARGE", "Request body exceeds 1 MB.")
    return await call_next(request)


@app.get("/health")
def health():
    try:
        with psycopg.connect(config.DATABASE_URL, connect_timeout=2) as conn:
            conn.execute("SELECT 1")
    except Exception:
        return error_response(503, "UNAVAILABLE", "Database is not reachable.")
    return {"status": "ok"}
