from fastapi import APIRouter, Depends

from app.core.config import get_settings
from app.core.security import get_current_operator
from app.models import Operator
from app.schemas.operator import OperatorRead

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me", response_model=OperatorRead)
def read_current_operator(operator: Operator = Depends(get_current_operator)) -> Operator:
    return operator


@router.get("/config")
def read_public_config() -> dict:
    """Safe, unauthenticated: only ever the two booleans the frontend needs
    to decide whether to show the demo-mode banner and which environment
    label to display. Never secrets, never anything else from Settings."""
    settings = get_settings()
    return {"demo_mode": settings.demo_mode, "environment": settings.environment}
