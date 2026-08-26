import os
import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.api.routes import router
from app.api.telemetry_routes import router as telemetry_router
from app.api.telemetry_routes import get_session_store, get_audit_logger, get_policy_engine
from app.core.risk_engine import RiskEngine
from app.core.airlock import router as airlock_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: initialize resources
    app.state.policy_engine = get_policy_engine()
    config_dir = os.path.join(os.path.dirname(__file__), "..", "config", "profiles")
    if os.path.isdir(config_dir):
        app.state.policy_engine.load_profiles(config_dir)
        
    app.state.session_store = get_session_store()
    app.state.audit_logger = get_audit_logger()
    app.state.risk_engine = RiskEngine()
    
    # Start eviction loop in background
    eviction_task = asyncio.create_task(app.state.session_store.start_eviction_loop())
    
    yield
    # Shutdown: cleanup
    eviction_task.cancel()

app = FastAPI(
    title="ControlPlane.ai",
    description="Enterprise AI Guardrail Middleware",
    version="0.1.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure per environment
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(telemetry_router)
app.include_router(airlock_router)

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "controlplane"}
