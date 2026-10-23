"""
api/routes/health.py — Health check endpoint.
"""

from datetime import datetime, timezone
from fastapi import APIRouter
from api.schemas import HealthResponse

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """System health check endpoint."""
    return HealthResponse(
        status="healthy",
        service="Renal Risk Prediction System API",
        organ="kidney",
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
