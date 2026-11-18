import os, logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from app.core.config import settings
from app.core.db import engine
from app.core import ratelimit
from app.core.deps import client_ip
from app.api.v1 import api

log = logging.getLogger("careers")
HEADERS = {"X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY", "Referrer-Policy": "no-referrer", "Permissions-Policy": "camera=(), microphone=(), geolocation=()"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs(os.path.join(settings.data_dir, "logos"), exist_ok=True)
    if settings.env == "prod" and settings.jwt_secret.startswith("change-me"): raise RuntimeError("CAREERS_JWT_SECRET must be set in production")
    yield


app = FastAPI(title="CareerNL API", version="1.0", lifespan=lifespan, docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None)
if settings.cors_list: app.add_middleware(CORSMiddleware, allow_origins=settings.cors_list, allow_credentials=True, allow_methods=["*"], allow_headers=["*"], expose_headers=["X-Total-Count"])


@app.middleware("http")
async def guard(request: Request, call_next):
    if request.url.path.startswith("/api") and not ratelimit.allow("ip:" + client_ip(request), settings.rate_limit_per_min):
        return JSONResponse({"detail": "rate limit exceeded"}, status_code=429, headers={"Retry-After": "30"})
    resp = await call_next(request)
    for k, v in HEADERS.items(): resp.headers.setdefault(k, v)
    return resp


@app.get("/healthz")
def healthz(): return {"ok": True}


@app.get("/readyz")
def readyz():
    with engine.connect() as c: c.execute(text("SELECT 1"))
    return {"ok": True}


app.include_router(api)
logos = os.path.join(settings.data_dir, "logos")
os.makedirs(logos, exist_ok=True)
app.mount("/logos", StaticFiles(directory=logos), name="logos")
# Built React app (frontend/dist) is served by the API in the single-container deployment; SPA fallback to index.html
DIST = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist"))
if os.path.isdir(DIST):
    app.mount("/assets", StaticFiles(directory=os.path.join(DIST, "assets")), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        f = os.path.join(DIST, path)
        return FileResponse(f if path and os.path.isfile(f) else os.path.join(DIST, "index.html"))
