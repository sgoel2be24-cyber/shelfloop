"""ShelfLoop FastAPI application. One process serves the API and the built SPA."""
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import db, seed
from .config import FRONTEND_DIST
from .routes.api import router

@asynccontextmanager
async def lifespan(app):
    db.init_db()
    if seed.seed():
        print("[shelfloop] database seeded with synthetic demo data")
    conn = db.connect()
    try:
        with db.tx(conn):
            conn.execute("UPDATE planning_runs SET status='error', error='Server restarted; start a new planning run', finished_at=? WHERE status IN ('queued','running')", (db.now_iso(),))
    finally:
        conn.close()
    yield


app = FastAPI(title="ShelfLoop", version="0.2.0", lifespan=lifespan,
              description="Idle stock into useful stock: multi-shop exchange planning "
                          "under cash, stock, shelf-life and transport constraints.")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                   allow_headers=["*"], expose_headers=["*"])
app.include_router(router)


@app.middleware("http")
async def cache_policy(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/api") or request.url.path in ("/sw.js", "/precache-manifest.json"):
        response.headers["Cache-Control"] = "no-store"
    return response


if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets", check_dir=False), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        if full_path == "api" or full_path.startswith("api/"):
            raise HTTPException(404, "API endpoint not found")
        if not (FRONTEND_DIST / "index.html").is_file():
            raise HTTPException(503, "Frontend build is not ready; the API remains available")
        target = (FRONTEND_DIST / full_path).resolve()
        if not target.is_relative_to(FRONTEND_DIST.resolve()):
            raise HTTPException(404, "file not found")
        if full_path and target.is_file():
            return FileResponse(target)
        return FileResponse(FRONTEND_DIST / "index.html")
