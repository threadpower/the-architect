"""
The Architect — Model Router
Local-first routing with complexity scoring, budget awareness,
and confidence-based escalation (Grok's logprob recommendation).
"""
from architect.models.task import Task
from architect.utils.complexity import score_complexity
from architect.core.budget_controller import BudgetController


# Routing rules from v1 section 4.1, extended in v2
ROUTING_RULES: dict[str, dict[str, str | None]] = {
    "code": {
        "primary": "qwen-local",
        "reviewer": "claude",
        "fallback": "openrouter",
    },
    "document": {
        "primary": "claude",
        "reviewer": "grok",
        "fallback": "qwen-local",
    },
    "config": {
        "primary": "qwen-local",
        "reviewer": "claude",
        "fallback": None,
    },
    "research": {
        "primary": "grok",
        "reviewer": "claude",
        "fallback": "openrouter",
    },
    "review": {
        "primary": "grok",
        "reviewer": "qwen-local",
        "fallback": "claude",
    },
    "upstream_merge": {
        "primary": "qwen-local",
        "reviewer": "claude",
        "fallback": "grok",
    },
    "bug_triage": {
        "primary": "qwen-local",
        "reviewer": None,
        "fallback": None,
    },
}


class RoutingDecision:
    """Result of a routing decision with full rationale."""

    def __init__(
        self,
        primary: str,
        reviewer: str | None,
        complexity: int,
        reason: str,
        forced_local: bool = False,
    ):
        self.primary = primary
        self.reviewer = reviewer
        self.complexity = complexity
        self.reason = reason
        self.forced_local = forced_local

    def to_dict(self) -> dict:
        return {
            "primary": self.primary,
            "reviewer": self.reviewer,
            "complexity": self.complexity,
            "reason": self.reason,
            "forced_local": self.forced_local,
        }


class ModelRouter:
    """
    Routes tasks to the optimal model based on:
    1. Task type and complexity score
    2. Budget remaining (force local if tight)
    3. Task-defined model preferences
    4. Local-first principle (Qwen handles what it can)
    """

    def __init__(self, budget_controller: BudgetController):
        self.budget = budget_controller

    async def route(self, task: Task) -> RoutingDecision:
        """Determine which models should handle this task."""
        complexity = score_complexity(task)
        task_type = task.type.value

        # Rule 1: Budget check — if daily > 90%, force local
        if await self.budget.is_local_only_mode():
            return RoutingDecision(
                primary="qwen-local",
                reviewer="qwen-local",
                complexity=complexity,
                reason="Budget pause threshold reached — local only mode",
                forced_local=True,
            )

        # Rule 2: Task has explicit model assignments → respect them
        if task.models.primary != "qwen-local" or task.models.reviewer:
            # User/agent specified models — use them (but still budget-check)
            primary = task.models.primary
            reviewer = task.models.reviewer

            # If the specified model is a cloud model, verify budget
            if primary != "qwen-local":
                auth = await self.budget.pre_authorize(
                    provider=self._model_to_provider(primary),
                    estimated_cost=task.budget.max_cost_usd * 0.5,
                    task_id=task.id,
                )
                if not auth.approved:
                    # Can't afford specified model — fall back to local
                    return RoutingDecision(
                        primary="qwen-local",
                        reviewer=reviewer if reviewer == "qwen-local" else None,
                        complexity=complexity,
                        reason=f"Budget insufficient for {primary}: {auth.reason}",
                        forced_local=True,
                    )

            return RoutingDecision(
                primary=primary,
                reviewer=reviewer,
                complexity=complexity,
                reason=f"Task-defined models: {primary}/{reviewer}",
            )

        # Rule 3: Low complexity + local-capable type → stay local
        if complexity < 4 and task_type in ("code", "config", "bug_triage"):
            rules = ROUTING_RULES.get(task_type, {})
            return RoutingDecision(
                primary="qwen-local",
                reviewer=rules.get("reviewer"),
                complexity=complexity,
                reason=f"Low complexity ({complexity}) — routed local-first",
            )

        # Rule 4: Use routing rules table
        rules = ROUTING_RULES.get(task_type, ROUTING_RULES["code"])
        primary = rules["primary"]
        reviewer = rules.get("reviewer")

        # Rule 5: If primary is cloud, check budget before committing
        if primary != "qwen-local":
            auth = await self.budget.pre_authorize(
                provider=self._model_to_provider(primary),
                estimated_cost=task.budget.max_cost_usd * 0.5,
                task_id=task.id,
            )
            if not auth.approved:
                fallback = rules.get("fallback", "qwen-local")
                return RoutingDecision(
                    primary=fallback or "qwen-local",
                    reviewer=None,
                    complexity=complexity,
                    reason=f"Budget insufficient for {primary}, "
                           f"falling back to {fallback}: {auth.reason}",
                    forced_local=(fallback == "qwen-local"),
                )

        return RoutingDecision(
            primary=primary,
            reviewer=reviewer,
            complexity=complexity,
            reason=f"Routed by rules table: type={task_type}, "
                   f"complexity={complexity}",
        )

    @staticmethod
    def _model_to_provider(model: str) -> str:
        """Map model name to billing provider."""
        mapping = {
            "claude": "claude",
            "grok": "grok",
            "qwen-local": "local",
            "openrouter": "openrouter",
        }
        return mapping.get(model, "openrouter")
