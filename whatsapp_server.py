"""
WhatsApp Quiz Server - Minimal version
Servidor focado apenas em WhatsApp Group Quiz, sem dependências do RAG SDK completo
"""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("whatsapp-server")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle handler"""
    logger.info("Starting WhatsApp Quiz Server...")
    yield
    logger.info("Shutting down WhatsApp Quiz Server...")


# Create FastAPI app
app = FastAPI(
    title="WhatsApp Quiz API",
    description="Backend para Quiz em Grupos WhatsApp",
    version="1.0.0",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# ROUTERS
# =============================================================================

try:
    from whatsapp.group_router import router as whatsapp_group_router
    app.include_router(whatsapp_group_router)
    logger.info("WhatsApp Group router loaded successfully")
except Exception as e:
    logger.error(f"Failed to load WhatsApp Group router: {e}")


# =============================================================================
# HEALTH ENDPOINT
# =============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "ok",
        "service": "whatsapp-quiz",
        "version": "1.0.0"
    }


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "WhatsApp Quiz API",
        "docs": "/docs",
        "health": "/health"
    }


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8001"))
    host = os.getenv("HOST", "0.0.0.0")

    logger.info(f"Starting server on {host}:{port}")
    uvicorn.run(
        "whatsapp_server:app",
        host=host,
        port=port,
        reload=False,
        log_level="info"
    )
