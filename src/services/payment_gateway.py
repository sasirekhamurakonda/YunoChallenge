import random
import time
import uuid
from dataclasses import dataclass
from typing import Optional

from src.config import settings

_FAILURE_DIST = [
    ("card_declined", 0.40),
    ("insufficient_funds", 0.25),
    ("authorization_expired", 0.15),
    ("network_timeout", 0.12),
    ("issuer_unavailable", 0.08),
]


@dataclass
class GatewayResult:
    success: bool
    failure_reason: Optional[str]
    transaction_id: Optional[str]
    duration_ms: int
    raw_response: dict


def execute_capture(payment_reference: str, amount: float, currency: str) -> GatewayResult:
    start = time.time()
    time.sleep(random.uniform(0.05, 0.3))
    duration_ms = int((time.time() - start) * 1000)

    if random.random() < settings.gateway_success_rate:
        txn_id = f"txn_sim_{uuid.uuid4().hex[:16]}"
        return GatewayResult(
            success=True,
            failure_reason=None,
            transaction_id=txn_id,
            duration_ms=duration_ms,
            raw_response={
                "gateway": "yuno_simulated",
                "success": True,
                "transaction_id": txn_id,
            },
        )

    rand = random.random()
    cumulative = 0.0
    reason = "card_declined"
    for r, weight in _FAILURE_DIST:
        cumulative += weight
        if rand < cumulative:
            reason = r
            break

    return GatewayResult(
        success=False,
        failure_reason=reason,
        transaction_id=None,
        duration_ms=duration_ms,
        raw_response={
            "gateway": "yuno_simulated",
            "success": False,
            "reason": reason,
            "message": f"Payment declined: {reason.replace('_', ' ')}",
        },
    )
