from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.api.routes import router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: initialize resources
    yield
    # Shutdown: cleanup

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

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "controlplane"}
