"""
The Architect — FastAPI Application
Sovereign Development & Autonomy Platform
Threadpower Labs / P.A.T.R.I.C.I.A. Stack

Endpoints:
  POST /tasks           — Submit a new task (JSON body)
  POST /tasks/yaml      — Submit a task from YAML content
  GET  /tasks           — List tasks
  GET  /tasks/{id}      — Get task details
  GET  /tasks/{id}/log  — Get task event log
  POST /tasks/{id}/run  — Execute a submitted task
  GET  /budget          — Today's budget report
  GET  /health          — Platform health check
  GET  /guardrails      — View active guardrails
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from typing import Optional
import redis.asyncio as redis

from architect.config.settings import settings
from architect.models.task import Task
from architect.core.task_manager import TaskManager
from architect.core.budget_controller import BudgetController
from architect.core.model_router import ModelRouter
from architect.core.iteration_engine import IterationEngine
from architect.guardrails.kernel import GuardrailKernel
from architect.bridges.local_bridge import OllamaBridge
from architect.bridges.cloud_bridge import ClaudeBridge, GrokBridge
from architect.utils.yaml_parser import parse_task_yaml

import sys
sys.path.insert(0, '/forge/lib')
from sovereign_obs import safe_endpoint, get_logger, trace



# ─── Application Lifespan ───────────────────────────────────
redis_client: redis.Redis = None
task_manager: TaskManager = None
budget: BudgetController = None
router: ModelRouter = None
engine: IterationEngine = None
guardrails: GuardrailKernel = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize all components on startup, cleanup on shutdown."""
    global redis_client, task_manager, budget, router, engine, guardrails

    # Connect Redis
    redis_client = redis.from_url(settings.redis_url, decode_responses=False)
    await redis_client.ping()

    # Initialize core components
    task_manager = TaskManager(redis_client)
    budget = BudgetController(redis_client)
    guardrails = GuardrailKernel(redis_client)
    await guardrails.initialize()

    router = ModelRouter(budget)
    ollama = OllamaBridge()

    # Cloud bridges (only if keys are configured)
    claude = ClaudeBridge(budget) if settings.anthropic_api_key else None
    grok = GrokBridge(budget) if settings.xai_api_key else None

    engine = IterationEngine(
        redis_client=redis_client,
        router=router,
        budget=budget,
        guardrails=guardrails,
        ollama=ollama,
        claude=claude,
        grok=grok,
    )

    print(f"\n{'='*60}")
    print(f"  THE ARCHITECT v{settings.platform_version}")
    print(f"  Sovereign Development & Autonomy Platform")
    print(f"  Threadpower Labs / P.A.T.R.I.C.I.A. Stack")
    print(f"{'='*60}")
    print(f"  Redis:      Connected")
    print(f"  Ollama:     {settings.ollama_host}")
    print(f"  Claude API: {'Configured' if claude else 'Not configured'}")
    print(f"  Grok API:   {'Configured' if grok else 'Not configured'}")
    print(f"  Guardrails: v{guardrails.guardrails['version']} "
          f"(hash: {guardrails.hash[:16]}...)")
    print(f"  Budget:     ${settings.budget.total_daily}/day, "
          f"${settings.budget.total_monthly}/month")
    print(f"{'='*60}\n")

    yield

    # Cleanup
    await redis_client.close()


# ─── FastAPI App ─────────────────────────────────────────────
app = FastAPI(
    title="The Architect",
    description="Sovereign Development & Autonomy Platform — Threadpower Labs",
    version=settings.platform_version,
    lifespan=lifespan,
)


# ─── Endpoints ───────────────────────────────────────────────

@app.get("/health")
@safe_endpoint
async def health_check():
    """Platform health check."""
    ollama = OllamaBridge()
    ollama_ok = await ollama.health_check()
    redis_ok = await redis_client.ping()
    guard_ok = await guardrails.verify_integrity()

    status = "healthy" if (ollama_ok and redis_ok and guard_ok) else "degraded"
    return {
        "status": status,
        "platform": settings.platform_name,
        "version": settings.platform_version,
        "guardrail_version": guardrails.guardrails["version"],
        "components": {
            "redis": "up" if redis_ok else "down",
            "ollama": "up" if ollama_ok else "down",
            "guardrails": "verified" if guard_ok else "INTEGRITY FAILURE",
            "claude": "configured" if settings.anthropic_api_key else "not configured",
            "grok": "configured" if settings.xai_api_key else "not configured",
        },
    }


@app.post("/tasks")
@safe_endpoint
async def submit_task(task: Task):
    """Submit a new task via JSON body."""
    saved = await task_manager.submit(task)
    routing = await router.route(saved)

    return {
        "task_id": saved.id,
        "status": saved.status,
        "routing": routing.to_dict(),
        "guardrail_version": guardrails.guardrails["version"],
    }


@app.post("/tasks/yaml")
@safe_endpoint
async def submit_task_yaml(yaml_content: str):
    """Submit a task from YAML content (POST body as string)."""
    try:
        task = parse_task_yaml(yaml_content)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid task YAML: {e}")

    saved = await task_manager.submit(task)
    routing = await router.route(saved)

    return {
        "task_id": saved.id,
        "status": saved.status,
        "routing": routing.to_dict(),
    }


@app.post("/tasks/{task_id}/run")
@safe_endpoint
async def run_task(task_id: str):
    """Execute a submitted task through the iteration engine."""
    task = await task_manager.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    if task.status not in ("pending", "paused"):
        raise HTTPException(
            status_code=400,
            detail=f"Task {task_id} is {task.status}, cannot run"
        )

    await task_manager.update_status(task_id, "dispatched")

    result = await engine.run_task(task)

    await task_manager.update_status(
        task_id, result.status, result.total_cost_usd
    )

    return {
        "task_id": result.task_id,
        "status": result.status,
        "iterations": result.iterations,
        "total_cost_usd": result.total_cost_usd,
        "output_preview": result.final_output[:500] if result.final_output else None,
    }


@app.get("/tasks")
@safe_endpoint
async def list_tasks(status: Optional[str] = None, limit: int = 20):
    """List tasks, optionally filtered by status."""
    tasks = await task_manager.list_tasks(status=status, limit=limit)
    return {
        "count": len(tasks),
        "tasks": [
            {
                "id": t.id,
                "name": t.name,
                "type": t.type.value,
                "status": t.status,
                "priority": t.priority.value,
                "cost": t.actual_cost_usd,
                "created": t.created_at.isoformat(),
            }
            for t in tasks
        ],
    }


@app.get("/tasks/{task_id}")
@safe_endpoint
async def get_task(task_id: str):
    """Get full task details."""
    task = await task_manager.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return task.model_dump()


@app.get("/tasks/{task_id}/log")
@safe_endpoint
async def get_task_log(task_id: str):
    """Get the event log for a task."""
    log = await task_manager.get_task_log(task_id)
    return {"task_id": task_id, "events": log}


@app.get("/budget")
@safe_endpoint
async def get_budget():
    """Today's budget report with savings tracking."""
    report = await budget.get_daily_report()
    warning = await budget.should_warn()

    return {
        "report": report.model_dump(),
        "warning": warning,
        "local_only_mode": await budget.is_local_only_mode(),
    }


@app.get("/guardrails")
@safe_endpoint
async def get_guardrails():
    """View active guardrails and integrity status."""
    integrity = await guardrails.verify_integrity()
    return {
        "guardrails": guardrails.guardrails,
        "hash": guardrails.hash,
        "integrity": "verified" if integrity else "COMPROMISED",
        "version": guardrails.guardrails["version"],
    }
