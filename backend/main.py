from __future__ import annotations

import logging

from fastapi import FastAPI
from contextlib import asynccontextmanager

from backend.config import settings
from backend.security.dlp import DLPMiddleware
from backend.routers import vault_api, ingestion_api, search_api, agent_api, legacy_adapter_api, graph_api
from backend.admin.routes import router as admin_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=settings.log_level)
    logging.getLogger(__name__).info("Vault root: %s", settings.vault_root.resolve())
    # Init audit DB once at startup instead of per-request
    from backend.agents.checkpointer import init_audit_db
    init_audit_db()
    yield


app = FastAPI(title="MaLife Lake - Secure Agentic RAG", version="0.1.0", lifespan=lifespan)

app.add_middleware(DLPMiddleware)

app.include_router(vault_api.router, prefix="/api/v1/vault", tags=["vault"])
app.include_router(ingestion_api.router, prefix="/api/v1/ingest", tags=["ingestion"])
app.include_router(search_api.router, prefix="/api/v1/search", tags=["search"])
app.include_router(agent_api.router, prefix="/api/v1/agent", tags=["agent"])
app.include_router(legacy_adapter_api.router, prefix="/api/v1/legacy", tags=["legacy"])
app.include_router(admin_router, prefix="/api/v1/admin", tags=["admin"])
app.include_router(graph_api.router, prefix="/api/v1/graph", tags=["graph"])


@app.get("/health")
async def health():
    return {"status": "ok"}
