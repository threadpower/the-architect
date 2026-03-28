"""
The Architect — Budget Models
Cost tracking, authorization, and reporting structures.
"""
from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class Authorization(BaseModel):
    """Result of a pre-authorization check."""
    approved: bool
    reason: Optional[str] = None
    reserved: float = 0.0
    provider: str = ""
    daily_remaining: float = 0.0
    monthly_remaining: float = 0.0
    suggestion: Optional[str] = None


class CostEntry(BaseModel):
    """Single cost log entry."""
    provider: str
    task_id: str
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    timestamp: datetime
    model: str = ""


class CostReport(BaseModel):
    """Daily or monthly cost summary."""
    period: str  # "daily" or "monthly"
    date: str
    providers: dict[str, dict] = {}  # provider -> {spent, limit, percentage}
    total_spent: float = 0.0
    total_limit: float = 0.0
    local_tasks: int = 0
    cloud_tasks: int = 0
    local_savings: float = 0.0  # Estimated cloud cost avoided
    vast_savings: float = 0.0   # Vast.ai vs AWS equivalent
    effective_cost_per_task: float = 0.0
