import logging
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from src.config import settings
from src.services.execution_engine import run_batch

logger = logging.getLogger(__name__)

_scheduler: Optional[BackgroundScheduler] = None


def start_scheduler() -> None:
    global _scheduler
    _scheduler = BackgroundScheduler()
    _scheduler.add_job(
        func=run_batch,
        trigger=IntervalTrigger(seconds=settings.execution_poll_interval_seconds),
        id="poll_due_captures",
        name="Poll and execute due captures",
        max_instances=1,
        replace_existing=True,
    )
    _scheduler.start()
    logger.info(
        f"Scheduler started — polling every {settings.execution_poll_interval_seconds}s"
    )


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")
