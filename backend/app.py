import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from backend.database import init_db
from backend.routes import api_keys, conversations, chat, custom_models, auth, panel_presets

# Path to the built React frontend
FRONTEND_DIST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend", "dist")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database on startup."""
    await init_db()
    yield


app = FastAPI(
    title="Unified UI",
    description="Multi-model LLM comparison chatbot",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS for development (Vite dev server on port 5173)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routes
app.include_router(auth.router)
app.include_router(api_keys.router)
app.include_router(conversations.router)
app.include_router(chat.router)
app.include_router(custom_models.router)
app.include_router(panel_presets.router)

# Serve React static files if the build exists
if os.path.isdir(FRONTEND_DIST):
    # Mount the assets directory
    assets_dir = os.path.join(FRONTEND_DIST, "assets")
    if os.path.isdir(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/")
    async def serve_root():
        return FileResponse(os.path.join(FRONTEND_DIST, "index.html"))

    # Catch-all for client-side routing (must be after API routes)
    @app.get("/{rest_of_path:path}")
    async def serve_spa(rest_of_path: str):
        # Try to serve static file first
        file_path = os.path.join(FRONTEND_DIST, rest_of_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        # Fall back to index.html for SPA routing
        return FileResponse(os.path.join(FRONTEND_DIST, "index.html"))
