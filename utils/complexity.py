"""
The Architect — Complexity Scoring
Heuristic scorer for routing decisions. Cheap to run (no LLM call).
Will be upgraded to LLM-based scoring in Phase 4.
"""
from architect.models.task import Task


def score_complexity(task: Task) -> int:
    """
    Score task complexity 0-10 for routing decisions.
    
    < 4  → Route to local model (Qwen)
    4-7  → Route to primary cloud model
    > 7  → Route to best available, no budget override
    
    From v1 section 4.3, extended in v2 for upstream merges.
    """
    score = 0.0

    # Description length as rough complexity proxy
    score += len(task.description) / 100

    # More context files = more complex
    score += len(task.context.files) * 2

    # Web search = needs cloud capability
    if task.context.web_search:
        score += 3

    # Document tasks tend to need strategic thinking
    if task.type.value == "document":
        score += 5

    # Strategy/investment keywords signal high complexity
    desc_lower = task.description.lower()
    if "strategy" in desc_lower:
        score += 5
    if "investment" in desc_lower:
        score += 5

    # Many affected files = complex code task
    if task.project and len(task.project.affected_files) > 3:
        score += 3

    # Upstream merges with conflicts are always complex
    if task.type.value == "upstream_merge":
        score += 4

    return min(int(score), 10)


def estimate_cloud_cost(task: Task, model: str) -> float:
    """
    Estimate what this task would cost on a cloud provider.
    Used for "$ saved by staying local" tracking.
    """
    # Rough token estimates based on description + context length
    estimated_input = len(task.description) + sum(
        500 for _ in task.context.files  # ~500 tokens per file avg
    )
    estimated_output = estimated_input * 0.4  # Rough output ratio

    # Per-1K-token pricing (approximate, mid-2026)
    pricing = {
        "claude": {"input": 0.003, "output": 0.015},
        "grok": {"input": 0.003, "output": 0.015},
        "openrouter": {"input": 0.002, "output": 0.010},
    }

    rates = pricing.get(model, pricing["openrouter"])
    cost = (
        estimated_input * rates["input"] / 1000
        + estimated_output * rates["output"] / 1000
    )

    return round(cost, 4)
