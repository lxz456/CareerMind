# CareerMind AI - Main Application Entry Point
"""
CareerMind AI: Intelligent Career Development Platform
Powered by LangGraph + LangChain + FastAPI

Run:
    uvicorn app.main:app --reload
"""
from contextlib import asynccontextmanager
import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.core.logging import configure_logging, reset_request_id, set_request_id
from app.database import init_db
from app.memory.checkpoint import close_checkpointer, init_checkpointer
from app.api import auth, users, resume, interview, workflow, knowledge

settings = get_settings()
configure_logging()
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown events."""
    # Startup
    await init_db()
    await init_checkpointer()
    # Graphs are compiled only after the async SQLite connection is available.
    from app.agents.graph import init_career_planning_graph
    from app.agents.interview_graph import init_interview_graph
    init_career_planning_graph()
    init_interview_graph()
    from app.services.workflow_service import WorkflowService
    interrupted = await WorkflowService.mark_interrupted_workflows()
    logger.info("%s v%s started", settings.APP_NAME, settings.APP_VERSION)
    logger.info("Database initialized")
    logger.info("Marked interrupted career planning workflows count=%d", interrupted)
    logger.info(
        "LLM configured provider=%s model=%s",
        settings.LLM_PROVIDER,
        settings.DASHSCOPE_MODEL,
    )
    logger.info("API docs available url=http://localhost:8010/docs")
    yield
    # Shutdown
    await WorkflowService.stop_background_workflows()
    await close_checkpointer()
    logger.info("%s shutdown", settings.APP_NAME)

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="AI-powered career development platform with Multi-Agent architecture",
    lifespan=lifespan,
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    """Add a traceable request id and one completion/failure log per HTTP call."""
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    token = set_request_id(request_id)
    started = time.perf_counter()
    try:
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - started) * 1000)
        log_completed = (
            logger.debug
            if request.url.path.endswith("/status") or request.url.path == "/health"
            else logger.info
        )
        log_completed(
            "HTTP request completed method=%s path=%s status_code=%d duration_ms=%d",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        response.headers["X-Request-ID"] = request_id
        return response
    except Exception:
        duration_ms = round((time.perf_counter() - started) * 1000)
        logger.exception(
            "HTTP request failed method=%s path=%s duration_ms=%d",
            request.method,
            request.url.path,
            duration_ms,
        )
        raise
    finally:
        reset_request_id(token)

# Register API routers
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(resume.router)
app.include_router(interview.router)
app.include_router(workflow.router)
app.include_router(knowledge.router)

@app.get("/")
async def root():
    """Root endpoint - API health check."""
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
        "docs": "/docs",
    }

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}
