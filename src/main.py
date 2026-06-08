import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException, RequestValidationError
from fastapi.responses import JSONResponse

from src.config import settings
from src.database import engine, Base

logging.basicConfig(
    level=logging.INFO,
    format='{"time": "%(asctime)s", "level": "%(levelname)s", "message": "%(message)s"}',
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up Payment Capture Service...")
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created/verified")

    if not settings.testing:
        from src.database import SessionLocal
        from src.models.scheduled_capture import ScheduledCapture
        db = SessionLocal()
        try:
            count = db.query(ScheduledCapture).count()
        finally:
            db.close()

        if count == 0:
            logger.info("Database is empty — running auto-seed...")
            from scripts.seed_data import seed as do_seed
            db = SessionLocal()
            try:
                seeded = do_seed(db)
                logger.info(f"Auto-seeded {seeded} captures")
            finally:
                db.close()
        else:
            logger.info(f"Database has {count} existing captures — skipping seed")

        from src.scheduler import start_scheduler
        start_scheduler()

    yield

    if not settings.testing:
        from src.scheduler import stop_scheduler
        stop_scheduler()

    logger.info("Shutdown complete")


app = FastAPI(
    title="Payment Capture Scheduling Service",
    description=(
        "Automated payment capture scheduling service for Serenity Cruises. "
        "Eliminates revenue leakage from missed manual captures."
    ),
    version="1.0.0",
    lifespan=lifespan,
)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if isinstance(exc.detail, dict) and "detail" in exc.detail:
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": str(exc.detail), "code": "HTTP_ERROR"},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors(), "code": "VALIDATION_ERROR"},
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.exception(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "code": "INTERNAL_ERROR"},
    )


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok", "version": "1.0.0"}


# Routers registered after app is fully configured
from src.api import alerts, captures, execution, stats  # noqa: E402

app.include_router(alerts.router)    # /captures/alerts — must be before /{capture_id}
app.include_router(captures.router)  # /captures, /captures/{id}, ...
app.include_router(execution.router) # /execution/trigger
app.include_router(stats.router)     # /stats
