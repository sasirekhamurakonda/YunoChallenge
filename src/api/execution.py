from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.database import get_db
from src.services.execution_engine import run_batch_with_db

router = APIRouter(tags=["execution"])


class TriggerResponse(BaseModel):
    processed: int
    succeeded: int
    failed: int
    retrying: int
    duration_ms: int


@router.post("/execution/trigger", response_model=TriggerResponse)
def trigger_execution(
    batch_size: int = Query(default=100, ge=1, le=500, description="Max captures to process"),
    db: Session = Depends(get_db),
):
    result = run_batch_with_db(db, batch_size=batch_size)
    return TriggerResponse(
        processed=result.processed,
        succeeded=result.succeeded,
        failed=result.failed,
        retrying=result.retrying,
        duration_ms=result.duration_ms,
    )
