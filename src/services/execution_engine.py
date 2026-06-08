import json
import random
import threading
import time
import logging
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional

from src.database import SessionLocal
from src.models.scheduled_capture import ScheduledCapture, utcnow
from src.models.capture_attempt import CaptureAttempt, new_uuid
from src.services.payment_gateway import execute_capture
from src.config import settings

logger = logging.getLogger(__name__)

_lock = threading.Lock()

_STALE_MINUTES = 10


@dataclass
class ExecutionResult:
    processed: int
    succeeded: int
    failed: int
    retrying: int
    duration_ms: int


def _next_retry_at(retry_count: int) -> str:
    delay = settings.retry_base_delay_seconds * (2 ** retry_count) + random.uniform(0, 10)
    return (datetime.now(timezone.utc) + timedelta(seconds=delay)).isoformat()


def _process_single(db, capture: ScheduledCapture) -> str:
    capture.status = "processing"
    capture.updated_at = utcnow()
    db.commit()

    result = execute_capture(capture.payment_reference, capture.amount, capture.currency)

    attempt_number = (
        db.query(CaptureAttempt)
        .filter(CaptureAttempt.scheduled_capture_id == capture.id)
        .count()
        + 1
    )

    attempt = CaptureAttempt(
        id=new_uuid(),
        scheduled_capture_id=capture.id,
        attempt_number=attempt_number,
        status="success" if result.success else "failure",
        failure_reason=result.failure_reason,
        gateway_response=json.dumps(result.raw_response),
        duration_ms=result.duration_ms,
    )
    db.add(attempt)

    if result.success:
        capture.status = "captured"
        capture.captured_at = utcnow()
        capture.failure_reason = None
        logger.info(f"capture_succeeded capture_id={capture.id} amount={capture.amount}")
    else:
        capture.retry_count += 1
        capture.failure_reason = result.failure_reason
        if capture.retry_count < capture.max_retries:
            capture.status = "retrying"
            capture.next_retry_at = _next_retry_at(capture.retry_count)
            logger.warning(
                f"capture_retrying capture_id={capture.id} "
                f"retry={capture.retry_count} reason={result.failure_reason}"
            )
        else:
            capture.status = "failed"
            logger.error(
                f"capture_failed capture_id={capture.id} reason={result.failure_reason}"
            )

    capture.updated_at = utcnow()
    db.commit()
    return capture.status


def run_batch(batch_size: int = 100) -> ExecutionResult:
    start = time.time()
    with _lock:
        db = SessionLocal()
        try:
            now_iso = datetime.now(timezone.utc).isoformat()
            stale_threshold = (
                datetime.now(timezone.utc) - timedelta(minutes=_STALE_MINUTES)
            ).isoformat()

            stale = (
                db.query(ScheduledCapture)
                .filter(
                    ScheduledCapture.status == "processing",
                    ScheduledCapture.updated_at < stale_threshold,
                )
                .all()
            )
            for s in stale:
                s.status = "pending"
                s.updated_at = utcnow()
            if stale:
                db.commit()
                logger.info(f"Reset {len(stale)} stale processing records to pending")

            due_pending = (
                db.query(ScheduledCapture)
                .filter(
                    ScheduledCapture.status == "pending",
                    ScheduledCapture.scheduled_capture_at <= now_iso,
                )
                .limit(batch_size)
                .all()
            )

            remaining = batch_size - len(due_pending)
            due_retrying = []
            if remaining > 0:
                due_retrying = (
                    db.query(ScheduledCapture)
                    .filter(
                        ScheduledCapture.status == "retrying",
                        ScheduledCapture.next_retry_at.isnot(None),
                        ScheduledCapture.next_retry_at <= now_iso,
                    )
                    .limit(remaining)
                    .all()
                )

            due = due_pending + due_retrying
            succeeded = failed = retrying = 0

            for capture in due:
                try:
                    status = _process_single(db, capture)
                    if status == "captured":
                        succeeded += 1
                    elif status == "retrying":
                        retrying += 1
                    else:
                        failed += 1
                except Exception as exc:
                    logger.exception(f"Error processing capture {capture.id}: {exc}")
                    try:
                        capture.status = "pending"
                        capture.updated_at = utcnow()
                        db.commit()
                    except Exception:
                        db.rollback()

            return ExecutionResult(
                processed=len(due),
                succeeded=succeeded,
                failed=failed,
                retrying=retrying,
                duration_ms=int((time.time() - start) * 1000),
            )
        finally:
            db.close()
