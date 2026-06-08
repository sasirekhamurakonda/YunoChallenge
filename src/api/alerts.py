from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from src.database import get_db
from src.schemas.stats import AlertsResponse
from src.services import capture_service

router = APIRouter(tags=["alerts"])


@router.get("/captures/alerts", response_model=AlertsResponse)
def get_alerts(
    alert_type: Optional[str] = Query(None, description="scheduling_conflict or expiry_imminent"),
    threshold_hours: int = Query(48, ge=1, description="Hours before expiry to trigger alert"),
    db: Session = Depends(get_db),
):
    return capture_service.get_alerts(db, alert_type, threshold_hours)
