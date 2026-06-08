from typing import Optional, List, Dict
from pydantic import BaseModel


class AlertItem(BaseModel):
    capture_id: str
    booking_id: str
    payment_reference: str
    amount: float
    currency: str
    status: str
    alert_type: str
    alert_message: str
    scheduled_capture_at: str
    auth_expires_at: Optional[str] = None
    hours_until_expiry: Optional[float] = None


class AlertsResponse(BaseModel):
    alerts: List[AlertItem]
    total: int


class StatsWindow(BaseModel):
    date_from: Optional[str] = None
    date_to: Optional[str] = None


class StatsTotals(BaseModel):
    scheduled: int
    captured: int
    failed: int
    retrying: int
    pending: int
    cancelled: int
    processing: int


class StatsResponse(BaseModel):
    window: StatsWindow
    totals: StatsTotals
    success_rate_pct: float
    avg_capture_latency_hours: Optional[float] = None
    failure_breakdown: Dict[str, int]
