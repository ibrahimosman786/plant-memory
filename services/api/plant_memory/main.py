from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from . import API_VERSION, PIPELINE_VERSION, RULES_VERSION, TEMPLATES_VERSION, TOOLS_VERSION
from .config import get_settings
from .db.session import get_engine
from .routers import analysis, auth, chat, documents, internal_tools, projects, records, reviews, runs
from .runs.service import resume_orphaned_runs

log = logging.getLogger("plant_memory")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=get_settings().log_level)
    try:
        n = resume_orphaned_runs()
        if n:
            log.info("resumed %d orphaned runs", n)
    except Exception:  # DB may not be migrated yet; health will say so
        log.exception("could not resume runs on startup")
    yield


app = FastAPI(title="Plant Memory API", version=API_VERSION, lifespan=lifespan, docs_url="/docs" if get_settings().environment != "production" else None)
app.add_middleware(CORSMiddleware, allow_origins=get_settings().cors_origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"], expose_headers=["Content-Disposition"])

for r in (auth.router, projects.router, documents.router, records.router, runs.router, reviews.router, analysis.router, chat.router, internal_tools.router):
    app.include_router(r)


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    log.exception("unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "internal error", "type": type(exc).__name__})


@app.get("/healthz")
def healthz() -> dict:
    db_ok = True
    try:
        with get_engine().connect() as c:
            c.execute(text("select 1"))
    except Exception:
        db_ok = False
    return {"ok": db_ok, "db": db_ok, "versions": {"api": API_VERSION, "pipeline": PIPELINE_VERSION, "rules": RULES_VERSION, "templates": TEMPLATES_VERSION, "tools": TOOLS_VERSION}}
