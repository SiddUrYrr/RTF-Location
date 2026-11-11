import logging
import os
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

load_dotenv()

from backend.database import engine, Base, SessionLocal
from backend.models import Location
from backend.timeutils import utcnow
from backend.routers import (
    auth_router, friends_router, groups_router, location_router, sos_router, notify_router
)

logger = logging.getLogger("rtf.app")

Base.metadata.create_all(bind=engine)


def purge_expired_locations() -> int:
    """Delete raw location history older than LOCATION_RETENTION_DAYS (default 90)."""
    try:
        days = int(os.getenv("LOCATION_RETENTION_DAYS", "90"))
    except ValueError:
        days = 90
    if days <= 0:
        return 0

    cutoff = utcnow() - timedelta(days=days)
    db = SessionLocal()
    try:
        deleted = (
            db.query(Location)
            .filter(Location.timestamp < cutoff)
            .delete(synchronize_session=False)
        )
        db.commit()
        if deleted:
            logger.info("Pruned %s location rows older than %s days.", deleted, days)
        return deleted
    except Exception as exc:
        db.rollback()
        logger.warning("Location retention cleanup failed: %s", exc)
        return 0
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    purge_expired_locations()
    yield

app = FastAPI(title="RTF-Location Web App", lifespan=lifespan)

# CORS is only needed when the frontend is hosted on a different origin.
# Same-origin deployments (the default) require no CORS middleware at all.
_cors_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
if _cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )


@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault(
        "Permissions-Policy", "geolocation=(self), camera=(), microphone=()"
    )
    return response


@app.get("/health")
def health_check():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok", "database": "ok"}
    except Exception:
        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "database": "unavailable"},
        )

app.include_router(auth_router.router)
app.include_router(friends_router.router)
app.include_router(groups_router.router)
app.include_router(location_router.router)
app.include_router(sos_router.router)
app.include_router(notify_router.router)

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"

app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

@app.get("/")
def serve_index():
    return FileResponse(FRONTEND_DIR / "index.html")

@app.get("/login")
def serve_login():
    return FileResponse(FRONTEND_DIR / "login.html")

@app.get("/signup")
def serve_signup():
    return FileResponse(FRONTEND_DIR / "signup.html")

@app.get("/profile")
def serve_profile():
    return FileResponse(FRONTEND_DIR / "profile.html")

@app.get("/map")
def serve_map():
    return FileResponse(FRONTEND_DIR / "index.html")

@app.get("/auth_hero.jpg")
def serve_auth_hero():
    return FileResponse(FRONTEND_DIR / "auth_hero.jpg")

@app.get("/favicon.ico.png")
def serve_favicon():
    return FileResponse(FRONTEND_DIR / "favicon.ico.png")

# Silence third-party browser extension tracker pings (e.g. zybTrackerStatisticsAction)
@app.get("/hybridaction/{path:path}")
@app.post("/hybridaction/{path:path}")
def ignore_browser_extension_tracking(path: str):
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("backend.main:app", host="0.0.0.0", port=port, reload=False)