import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import routes_pipeline, routes_review, routes_candidates
from app.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.APP_NAME,
    description=settings.APP_TAGLINE,
    version="1.0.0"
)

# CORS (allow all for local dev)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.api import routes_pipeline, routes_review, routes_candidates, routes_audit, auth

# Include routers
app.include_router(auth.router)
app.include_router(routes_pipeline.router)
app.include_router(routes_review.router)
app.include_router(routes_candidates.router)
app.include_router(routes_audit.router)

@app.get("/config/branding", tags=["config"])
async def get_branding():
    """Returns the white-label branding config for the frontend to consume."""
    return {
        "app_name": settings.APP_NAME,
        "tagline": settings.APP_TAGLINE,
    }

# Mount frontend — must come LAST so API routes take priority
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
