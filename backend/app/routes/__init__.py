"""Routes package"""
from fastapi import APIRouter
from .components import router as components_router
from .versions import router as versions_router
from .deployments import router as deployments_router
from .feedbacks import router as feedbacks_router
from .requirements import router as requirements_router
from .doubt import router as doubt_router
from .health import router as health_router
from .search import router as search_router

api_router = APIRouter()
api_router.include_router(components_router, prefix="/api/v1/components", tags=["components"])
api_router.include_router(versions_router, prefix="/api/v1/versions", tags=["versions"])
api_router.include_router(deployments_router, prefix="/api/v1/deployments", tags=["deployments"])
api_router.include_router(feedbacks_router, prefix="/api/v1/feedbacks", tags=["feedbacks"])
api_router.include_router(requirements_router, prefix="/api/v1/requirements", tags=["requirements"])
api_router.include_router(doubt_router, prefix="/api/v1/doubt", tags=["doubt"])
api_router.include_router(health_router, tags=["health"])
api_router.include_router(search_router, prefix="/api/v1", tags=["search"])