"""
Production AI Agent — Kết hợp tất cả Day 12 concepts

Checklist:
  ✅ Config từ environment (12-factor)
  ✅ Structured JSON logging
  ✅ API Key authentication
  ✅ Rate limiting
  ✅ Cost guard
  ✅ Input validation (Pydantic)
  ✅ Health check + Readiness probe
  ✅ Graceful shutdown
  ✅ Security headers
  ✅ CORS
  ✅ Error handling
"""
import sys
import os

# Thêm thư mục cha của 'app' vào sys.path để hỗ trợ chạy trực tiếp main.py bằng python
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

import time
import signal
import logging
import json
from datetime import datetime, timezone
from collections import defaultdict, deque
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Security, Depends, Request, Response
from fastapi.security.api_key import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
import uvicorn

from app.config import settings
from app.agent_loop import run_react_agent

# ─────────────────────────────────────────────────────────
# Logging — JSON structured
# ─────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format='{"ts":"%(asctime)s","lvl":"%(levelname)s","msg":"%(message)s"}',
)
logger = logging.getLogger(__name__)

START_TIME = time.time()
_is_ready = False
_request_count = 0
_error_count = 0

# ─────────────────────────────────────────────────────────
# Redis Connection — Stateless Design
# ─────────────────────────────────────────────────────────
USE_REDIS = False
_redis = None
_memory_store = {}

if settings.redis_url:
    try:
        import redis
        _redis = redis.from_url(settings.redis_url, decode_responses=True)
        _redis.ping()
        USE_REDIS = True
        logger.info(json.dumps({"event": "redis_connected", "msg": "Successfully connected to Redis"}))
    except Exception as e:
        logger.warning(json.dumps({"event": "redis_failed", "msg": f"Failed to connect to Redis: {str(e)}"}))

# ─────────────────────────────────────────────────────────
# Stateless Session History Storage
# ─────────────────────────────────────────────────────────
def save_history(history_key: str, data: list, ttl_seconds: int = 3600):
    serialized = json.dumps(data)
    if USE_REDIS:
        _redis.setex(f"history:{history_key}", ttl_seconds, serialized)
    else:
        _memory_store[f"history:{history_key}"] = data

def load_history(history_key: str) -> list:
    if USE_REDIS:
        data = _redis.get(f"history:{history_key}")
        return json.loads(data) if data else []
    return _memory_store.get(f"history:{history_key}", [])

def append_to_history(history_key: str, role: str, content: str):
    history = load_history(history_key)
    history.append({
        "role": role,
        "content": content,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    # Giới hạn lịch sử lưu trữ để tránh quá tải context cho LLM
    if len(history) > 10:
        history = history[-10:]
    save_history(history_key, history)
    return history

# ─────────────────────────────────────────────────────────
# Redis-backed Rate Limiter (with In-memory Fallback)
# ─────────────────────────────────────────────────────────
_rate_windows: dict[str, deque] = defaultdict(deque)

def check_rate_limit(key: str):
    now = time.time()
    limit = settings.rate_limit_per_minute
    window = 60
    
    if USE_REDIS:
        redis_key = f"rate_limit:{key}"
        pipe = _redis.pipeline()
        pipe.zremrangebyscore(redis_key, 0, now - window)
        pipe.zcard(redis_key)
        pipe.zadd(redis_key, {str(now): now})
        pipe.expire(redis_key, window)
        _, current_count, _, _ = pipe.execute()
        
        if current_count >= limit:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded: {limit} req/min",
                headers={"Retry-After": "60"},
            )
    else:
        window_deque = _rate_windows[key]
        while window_deque and window_deque[0] < now - window:
            window_deque.popleft()
        if len(window_deque) >= limit:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded: {limit} req/min",
                headers={"Retry-After": "60"},
            )
        window_deque.append(now)

# ─────────────────────────────────────────────────────────
# Redis-backed Cost Guard (with In-memory Fallback)
# ─────────────────────────────────────────────────────────
_daily_cost = 0.0
_cost_reset_day = time.strftime("%Y-%m-%d")

def check_and_record_cost(key: str, input_tokens: int, output_tokens: int):
    global _daily_cost, _cost_reset_day
    today = time.strftime("%Y-%m-%d")
    cost = (input_tokens / 1000) * 0.0003 + (output_tokens / 1000) * 0.0006
    
    if USE_REDIS:
        cost_key = f"cost:{key}:{today}"
        current_cost_str = _redis.get(cost_key)
        current_cost = float(current_cost_str) if current_cost_str else 0.0
        
        if current_cost >= settings.daily_budget_usd:
            raise HTTPException(503, "Daily budget exhausted. Try tomorrow.")
            
        pipe = _redis.pipeline()
        pipe.incrbyfloat(cost_key, cost)
        pipe.expire(cost_key, 24 * 3600 * 2) # lưu trong 2 ngày
        pipe.execute()
    else:
        if today != _cost_reset_day:
            _daily_cost = 0.0
            _cost_reset_day = today
        if _daily_cost >= settings.daily_budget_usd:
            raise HTTPException(503, "Daily budget exhausted. Try tomorrow.")
        _daily_cost += cost

def get_daily_cost(key: str) -> float:
    if USE_REDIS:
        today = time.strftime("%Y-%m-%d")
        cost_key = f"cost:{key}:{today}"
        cost_val = _redis.get(cost_key)
        return float(cost_val) if cost_val else 0.0
    else:
        return _daily_cost

# ─────────────────────────────────────────────────────────
# Auth
# ─────────────────────────────────────────────────────────
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

def verify_api_key(api_key: str = Security(api_key_header)) -> str:
    if not api_key or api_key != settings.agent_api_key:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key. Include header: X-API-Key: <key>",
        )
    return api_key

# ─────────────────────────────────────────────────────────
# Lifespan
# ─────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _is_ready
    logger.info(json.dumps({
        "event": "startup",
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
    }))
    time.sleep(0.1)  # simulate init
    _is_ready = True
    logger.info(json.dumps({"event": "ready"}))

    yield

    _is_ready = False
    logger.info(json.dumps({"event": "shutdown"}))

# ─────────────────────────────────────────────────────────
# App
# ─────────────────────────────────────────────────────────
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)

@app.middleware("http")
async def request_middleware(request: Request, call_next):
    global _request_count, _error_count
    start = time.time()
    _request_count += 1
    try:
        response: Response = await call_next(request)
        # Security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        if "server" in response.headers:
            del response.headers["server"]
        duration = round((time.time() - start) * 1000, 1)
        logger.info(json.dumps({
            "event": "request",
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "ms": duration,
        }))
        return response
    except Exception as e:
        _error_count += 1
        raise

# ─────────────────────────────────────────────────────────
# Models
# ─────────────────────────────────────────────────────────
class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000,
                          description="Your question for the agent")

class AskResponse(BaseModel):
    question: str
    answer: str
    model: str
    timestamp: str

# ─────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────

@app.get("/", tags=["Info"])
def root():
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "endpoints": {
            "ask": "POST /ask (requires X-API-Key)",
            "health": "GET /health",
            "ready": "GET /ready",
        },
    }


@app.post("/ask", response_model=AskResponse, tags=["Agent"])
async def ask_agent(
    body: AskRequest,
    request: Request,
    _key: str = Depends(verify_api_key),
):
    """
    Send a question to the AI agent.

    **Authentication:** Include header `X-API-Key: <your-key>`
    """
    # Rate limit per API key
    check_rate_limit(_key[:8])

    # Budget check
    input_tokens = len(body.question.split()) * 2
    check_and_record_cost(_key[:8], input_tokens, 0)

    logger.info(json.dumps({
        "event": "agent_call",
        "q_len": len(body.question),
        "client": str(request.client.host) if request.client else "unknown",
    }))

    # Load conversation history
    history = load_history(_key[:8])

    # Chạy ReAct Loop của Agent bằng Threadpool để tránh chặn FastAPI Event Loop
    answer = await run_in_threadpool(run_react_agent, body.question, history=history)

    output_tokens = len(answer.split()) * 2
    check_and_record_cost(_key[:8], 0, output_tokens)

    # Lưu lịch sử hội thoại (Stateless - được lưu vào Redis/Memory store)
    append_to_history(_key[:8], "user", body.question)
    append_to_history(_key[:8], "assistant", answer)

    return AskResponse(
        question=body.question,
        answer=answer,
        model=settings.llm_model,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@app.get("/health", tags=["Operations"])
def health():
    """Liveness probe. Platform restarts container if this fails."""
    status = "ok"
    checks = {
        "llm": "mock" if not settings.dashscope_api_key else "qwen-turbo",
        "redis": "connected" if USE_REDIS else "disconnected"
    }
    return {
        "status": status,
        "version": settings.app_version,
        "environment": settings.environment,
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "total_requests": _request_count,
        "checks": checks,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/ready", tags=["Operations"])
def ready():
    """Readiness probe. Load balancer stops routing here if not ready."""
    if not _is_ready:
        raise HTTPException(503, "Not ready")
    if settings.redis_url and not USE_REDIS:
        raise HTTPException(503, "Redis connection failed")
    return {"ready": True}


@app.get("/metrics", tags=["Operations"])
def metrics(_key: str = Depends(verify_api_key)):
    """Basic metrics (protected)."""
    current_cost = get_daily_cost(_key[:8])
    return {
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "total_requests": _request_count,
        "error_count": _error_count,
        "daily_cost_usd": round(current_cost, 4),
        "daily_budget_usd": settings.daily_budget_usd,
        "budget_used_pct": round(current_cost / settings.daily_budget_usd * 100, 1) if settings.daily_budget_usd > 0 else 0,
    }


# ─────────────────────────────────────────────────────────
# Graceful Shutdown
# ─────────────────────────────────────────────────────────
def _handle_signal(signum, _frame):
    logger.info(json.dumps({"event": "signal", "signum": signum}))

signal.signal(signal.SIGTERM, _handle_signal)


if __name__ == "__main__":
    logger.info(f"Starting {settings.app_name} on {settings.host}:{settings.port}")
    logger.info(f"API Key: {settings.agent_api_key[:4]}****")
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        timeout_graceful_shutdown=30,
    )
