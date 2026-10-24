"""
api/main.py — FastAPI backend for the Renal Risk Prediction System.
Serves clinical tabular CKD risk prediction and kidney CT image inference
to the Next.js frontend in web/.
"""

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

# Ensure repository root is on sys.path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.routes import health, kidney, renal_twin
from api.services import get_tabular_module, get_image_module

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("renal-api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager: warm up model loaders on API startup."""
    logger.info("Initializing Renal Risk Prediction System API...")
    try:
        get_tabular_module()
        logger.info("Tabular CKD model loaded and ready.")
    except Exception as e:
        logger.warning(f"Could not preload tabular model on startup: {e}")

    try:
        get_image_module()
        logger.info("Image CT metadata and gate loaded.")
    except Exception as e:
        logger.warning(f"Could not preload image model metadata on startup: {e}")

    yield
    logger.info("Shutting down Renal Risk Prediction System API.")


app = FastAPI(
    title="Renal Risk Prediction System API",
    description="FastAPI service for tabular CKD risk prediction and kidney CT scan analysis.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ---- CORS Configuration -----------------------------------------------------
# Configured for Next.js development and local clients
origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3001",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---- Exception Handlers -----------------------------------------------------
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Clean validation error response without exposing stack traces."""
    errors = []
    for err in exc.errors():
        field_loc = " -> ".join(str(loc) for loc in err.get("loc", []))
        msg = err.get("msg", "Invalid value")
        errors.append(f"{field_loc}: {msg}" if field_loc else msg)
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": "; ".join(errors) if errors else "Validation error occurred."},
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch unhandled errors and return a safe HTTP 500 error without exposing stack traces."""
    logger.error(f"Unhandled error processing {request.method} {request.url}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An internal server error occurred while processing the request."},
    )


# ---- Mount Routers ----------------------------------------------------------
# All endpoints mounted under /api
app.include_router(health.router, prefix="/api")
app.include_router(kidney.router, prefix="/api")
app.include_router(renal_twin.router, prefix="/api")

# Also provide direct /health for standard health checks
app.include_router(health.router)
