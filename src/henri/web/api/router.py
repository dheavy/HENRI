"""Main API router — aggregates all endpoint modules."""

from fastapi import APIRouter

from .dashboard import router as dashboard_router
from .countries import router as countries_router
from .surges import router as surges_router
from .delegations import router as delegations_router
from .alerts import router as alerts_router

api_router = APIRouter()

api_router.include_router(dashboard_router, tags=["dashboard"])
api_router.include_router(countries_router, prefix="/countries", tags=["countries"])
api_router.include_router(surges_router, prefix="/surges", tags=["surges"])
api_router.include_router(delegations_router, prefix="/delegations", tags=["delegations"])
api_router.include_router(alerts_router, prefix="/alerts", tags=["alerts"])
