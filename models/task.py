"""
The Architect — Task Models
Strongly-typed task schema matching the YAML spec from v1-v5.
Every field validated at parse time. No loose dicts.
"""
from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum
from datetime import datetime
import uuid


class TaskType(str, Enum):
    CODE = "code"
    DOCUMENT = "document"
    CONFIG = "config"
    RESEARCH = "research"
    REVIEW = "review"
    UPSTREAM_MERGE = "upstream_merge"
    BUG_TRIAGE = "bug_triage"


class Priority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Convergence(str, Enum):
    REVIEWER_APPROVED = "reviewer_approved"
    SCORE_THRESHOLD = "score_threshold"
    HUMAN_APPROVED = "human_approved"
    TESTS_PASS = "tests_pass"


class TaskSource(str, Enum):
    MANUAL = "manual"
    FEEDBACK = "feedback"
    AGENT = "agent"
    UPSTREAM_SYNC = "upstream_sync"
    SENTINEL = "sentinel"
    SELF_IMPROVE = "self_improve"


class ModelAssignment(BaseModel):
    """Which models handle which roles for this task."""
    primary: str = "qwen-local"
    reviewer: Optional[str] = None
    implementer: Optional[str] = None


class IterationConfig(BaseModel):
    """How the task iterates between models."""
    max_rounds: int = Field(default=3, ge=1, le=10)
    convergence: Convergence = Convergence.REVIEWER_APPROVED
    human_checkpoint: bool = True
    score_threshold: float = Field(default=8.0, ge=1.0, le=10.0)


class BudgetConfig(BaseModel):
    """Per-task budget constraints."""
    max_tokens_input: int = Field(default=50000, ge=0)
    max_tokens_output: int = Field(default=20000, ge=0)
    max_cost_usd: float = Field(default=2.00, ge=0.0)
    prefer_local: bool = True


class TaskContext(BaseModel):
    """Context files and memory to include with the task."""
    files: list[str] = Field(default_factory=list)
    memory_keys: list[str] = Field(default_factory=list)
    web_search: bool = False


class TaskOutput(BaseModel):
    """Where and how to deliver results."""
    format: str = "markdown"  # markdown | python | yaml | json | git_patch
    save_to: Optional[str] = None
    run_tests: bool = False
    auto_deploy: bool = False
    notify: str = "sms"  # sms | webhook | dashboard | none


class TaskSourceInfo(BaseModel):
    """Where this task came from."""
    type: TaskSource = TaskSource.MANUAL
    ticket_id: Optional[str] = None
    incident_id: Optional[str] = None
    reporter: Optional[str] = None


class ProjectInfo(BaseModel):
    """Open-source project context for code tasks."""
    name: Optional[str] = None
    repo: Optional[str] = None
    branch: str = "main"
    affected_files: list[str] = Field(default_factory=list)
    test_command: Optional[str] = None


class Task(BaseModel):
    """
    The core unit of work in The Architect.
    Fully validated against the v1-v5 YAML schema.
    """
    id: str = Field(default_factory=lambda: f"architect-{uuid.uuid4().hex[:8]}")
    name: str
    description: str
    type: TaskType
    priority: Priority = Priority.MEDIUM

    models: ModelAssignment = Field(default_factory=ModelAssignment)
    iteration: IterationConfig = Field(default_factory=IterationConfig)
    budget: BudgetConfig = Field(default_factory=BudgetConfig)
    context: TaskContext = Field(default_factory=TaskContext)
    output: TaskOutput = Field(default_factory=TaskOutput)
    source: TaskSourceInfo = Field(default_factory=TaskSourceInfo)
    project: Optional[ProjectInfo] = None

    # Metadata (set by the system, not the user)
    status: str = "pending"  # pending | dispatched | iterating | review | complete | failed | paused
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    actual_cost_usd: float = 0.0
    iteration_count: int = 0
    guardrail_version: str = "1.0.0"


class ModelResponse(BaseModel):
    """Response from any model bridge."""
    content: str
    model: str
    provider: str  # local | claude | grok | openrouter
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    confidence: Optional[float] = None  # Grok's logprob recommendation
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class TaskResult(BaseModel):
    """Final result of a completed task."""
    task_id: str
    status: str  # complete | failed | paused
    iterations: int
    total_cost_usd: float
    cloud_cost_avoided: float = 0.0
    artifacts: list[ModelResponse] = Field(default_factory=list)
    final_output: Optional[str] = None
    completed_at: datetime = Field(default_factory=datetime.utcnow)
