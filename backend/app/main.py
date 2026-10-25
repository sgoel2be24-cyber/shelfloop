"""ShelfLoop FastAPI application. One process serves the API and the built SPA."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import db, seed
from .config import FRONTEND_DIST
from .routes.api import router

app = FastAPI(title="ShelfLoop", version="0.1.0",
              description="Idle stock into useful stock: multi-shop exchange planning "
                          "under cash, stock, shelf-life and transport constraints.")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                   allow_headers=["*"], expose_headers=["*"])
app.include_router(router)


@app.on_event("startup")
def startup():
    db.init_db()
    if seed.seed():
        print("[shelfloop] database seeded with synthetic demo data")


if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        target = FRONTEND_DIST / full_path
        if full_path and target.is_file():
            return FileResponse(target)
        return FileResponse(FRONTEND_DIST / "index.html")
