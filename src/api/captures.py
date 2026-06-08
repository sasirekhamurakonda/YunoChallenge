import math
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from src.database import get_db
from src.schemas.capture import (
    CreateCaptureRequest,
    CaptureResponse,
    PaginatedCapturesResponse,
    CaptureAttemptResponse,
)
from src.services import capture_service

router = APIRouter(prefix="/captures", tags=["captures"])


@router.post("", response_model=CaptureResponse, status_code=201)
def create_capture(request: CreateCaptureRequest, db: Session = Depends(get_db)):
    capture = capture_service.create_capture(db, request)
    return CaptureResponse.model_validate(capture)


@router.get("", response_model=PaginatedCapturesResponse)
def list_captures(
    status: Optional[str] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    booking_id: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    items, total = capture_service.list_captures(
        db, status, date_from, date_to, booking_id, page, page_size
    )
    pages = math.ceil(total / page_size) if page_size else 1
    return PaginatedCapturesResponse(
        items=[CaptureResponse.model_validate(i) for i in items],
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


@router.get("/{capture_id}", response_model=CaptureResponse)
def get_capture(capture_id: str, db: Session = Depends(get_db)):
    return CaptureResponse.model_validate(capture_service.get_capture(db, capture_id))


@router.post("/{capture_id}/cancel", response_model=CaptureResponse)
def cancel_capture(capture_id: str, db: Session = Depends(get_db)):
    return CaptureResponse.model_validate(capture_service.cancel_capture(db, capture_id))


@router.get("/{capture_id}/attempts", response_model=List[CaptureAttemptResponse])
def list_attempts(capture_id: str, db: Session = Depends(get_db)):
    attempts = capture_service.list_attempts(db, capture_id)
    return [CaptureAttemptResponse.model_validate(a) for a in attempts]
