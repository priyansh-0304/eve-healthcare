import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from app.routers import auth, centres, bookings, payments
from app.routers.payments import limiter

# ---------- Structured-ish logging ----------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s level=%(levelname)s logger=%(name)s %(message)s",
)
logger = logging.getLogger("eve.api")

# Schema is owned by Alembic migrations (see alembic/), not created here.
# Run `alembic upgrade head` before starting the app — docker-compose and the
# Dockerfile's default CMD both do this automatically.

app = FastAPI(
    title="EVE Healthcare — Diagnostic Booking API",
    description="Backend service for diagnostic test bookings and simulated payments.",
    version="1.0.0",
)

app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded, please try again later."})


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Minimal structured request logging with a correlation id per request."""
    request_id = str(uuid.uuid4())[:8]
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000
    logger.info(
        "request_id=%s method=%s path=%s status=%s duration_ms=%.2f",
        request_id, request.method, request.url.path, response.status_code, duration_ms,
    )
    response.headers["X-Request-ID"] = request_id
    return response


app.include_router(auth.router)
app.include_router(centres.router)
app.include_router(bookings.router)
app.include_router(payments.router)


@app.get("/health", tags=["health"])
def health_check():
    return {"status": "ok"}
