"""API v1 Router - Versioned API endpoints"""
from fastapi import APIRouter

v1_router = APIRouter()


@v1_router.get("/health")
async def health_check():
    """Health check endpoint for v1 API"""
    return {"status": "healthy", "version": "v1"}


@v1_router.get("/info")
async def api_info():
    """API information"""
    return {
        "version": "1.0.0",
        "api": "v1",
        "endpoints": [
            "/v1/health",
            "/v1/info",
        ],
    }
