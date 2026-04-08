"""
Nester Agent Platform — FastAPI application entry point.

Startup sequence:
  1. Load settings and validate required secrets
  2. Initialize Mem0 agent memory (Qdrant embedded + SQLite)
  3. Initialize SQLite operations (cache, cost, webhooks, metrics)
  4. Load MCP tool registry
  5. Discover and compile all flows from flows/*.yaml
  6. Initialize Langfuse tracing
  7. Start Playwright browser pool
  8. Start MCP health monitor
  9. Start APScheduler for cron-triggered flows
  10. Mark startup complete

Shutdown sequence:
  Graceful drain of active flows → flush traces → close connections
"""

import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
load_dotenv()  # load .env into os.environ before anything else

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config.settings import get_settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — startup and shutdown hooks."""
    settings = get_settings()

    # ── Export API keys to os.environ for LLM SDKs ─────────────────────────
    if settings.openai_api_key and not os.environ.get("OPENAI_API_KEY"):
        os.environ["OPENAI_API_KEY"] = settings.openai_api_key

    # ── Configure logging ─────────────────────────────────────────────────
    logging.basicConfig(
        level=getattr(logging, settings.log_level),
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )

    # Silence noisy third-party loggers
    for noisy_logger in (
        "httpx", "httpcore", "openai", "openai._base_client",
        "anthropic", "anthropic._base_client",
        "langchain_core", "langchain_openai", "langchain_anthropic",
        "langgraph", "langgraph.graph", "langgraph.pregel",
        "urllib3", "urllib3.connectionpool",
        "playwright", "asyncio",
        "primp",  # HTTP library used by browser search fallback
    ):
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)

    logger.info("=" * 60)
    logger.info("NESTER AGENT PLATFORM — starting")
    logger.info("=" * 60)

    # ── 1. Initialize Mem0 agent memory ────────────────────────────────────
    try:
        from memory.mem0_store import init_mem0
        from pathlib import Path
        mem0_dir = str(Path(settings.nester_data_dir).expanduser() / "mem0")
        init_mem0(
            data_dir=mem0_dir,
            llm_model=settings.mem0_llm_model,
            embedding_model=settings.mem0_embedding_model,
        )
        logger.info("[Startup] Mem0 agent memory ready")
    except Exception as e:
        logger.warning("[Startup] Mem0 failed (agent memory disabled): %s", e)

    # ── 1b. Initialize SQLite operations ────────────────────────────────────
    try:
        from memory.sqlite_ops import init_sqlite_ops
        ops_db = str(Path(settings.nester_data_dir).expanduser() / "ops.db")
        init_sqlite_ops(db_path=ops_db)
        logger.info("[Startup] SQLite ops ready")
    except Exception as e:
        logger.error("[Startup] SQLite init failed: %s", e)

    # ── 2. Load MCP tool registry ─────────────────────────────────────────
    from tools.registry import load_registry
    load_registry()

    # ── 3. Register all agent nodes ─────────────────────────────────────
    import nodes  # noqa: F401 — triggers @register_node decorators
    from core.registry import list_registered_nodes
    logger.info("[Startup] Registered nodes: %s", list_registered_nodes())

    # ── 4. Discover flows ─────────────────────────────────────────────────
    from core.engine import discover_flows
    flows = discover_flows()
    logger.info("[Startup] Discovered flows: %s", flows)

    # ── 4. Initialize Langfuse ────────────────────────────────────────────
    from observability.tracing import init_tracing
    init_tracing()

    # ── 5. Start Playwright browser pool ────────────────────────────────────
    try:
        from tools.browser import startup_browser_pool
        await startup_browser_pool(
            headless=settings.playwright_headless,
            pool_size=settings.browser_pool_size,
            page_timeout_ms=settings.browser_page_timeout_ms,
        )
        logger.info("[Startup] Browser pool ready")
    except Exception as e:
        logger.warning("[Startup] Browser pool failed (scraping will use httpx fallback): %s", e)

    # ── 6. Start MCP health monitor ───────────────────────────────────────
    from tools.health import start_health_monitor
    start_health_monitor()

    # ── 8. Start scheduler ────────────────────────────────────────────────
    from api.routes.scheduler import start_scheduler
    start_scheduler()

    # ── 9. Mark startup complete ──────────────────────────────────────────
    from api.routes.health import mark_startup_complete
    mark_startup_complete()

    logger.info("[Startup] Platform ready — %d flows loaded", len(flows))

    yield  # ── Application running ────────────────────────────────────────

    # ── Shutdown ──────────────────────────────────────────────────────────
    from api.shutdown import graceful_shutdown
    await graceful_shutdown()


# ── Create app ────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Nester Agent Platform",
    description="Build Once. Configure Many. Deploy Any Flow.",
    version="1.0.0",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Mount routes ──────────────────────────────────────────────────────────────
from api.routes.health import router as health_router
from api.routes.flows import router as flows_router
from api.routes.webhooks import router as webhooks_router
from api.routes.scheduler import router as scheduler_router
from api.routes.integrations import router as integrations_router
from api.routes.oauth import router as oauth_router
from api.streaming import router as streaming_router
from api.routes.verify import router as verify_router
from api.routes.runs import router as runs_router
from api.routes.chat import router as chat_router
from api.routes.knowledge import router as knowledge_router
from api.routes.settings import router as settings_router
from api.routes.sow import router as sow_router

app.include_router(health_router)
app.include_router(flows_router)
app.include_router(webhooks_router)
app.include_router(scheduler_router)
app.include_router(integrations_router)
app.include_router(oauth_router)
app.include_router(streaming_router)
app.include_router(verify_router)
app.include_router(runs_router)
app.include_router(chat_router)
app.include_router(knowledge_router)
app.include_router(settings_router)
app.include_router(sow_router)


@app.get("/")
async def root():
    return {
        "platform": "Nester Agent Platform",
        "version": "1.0.0",
        "docs": "/docs",
    }
