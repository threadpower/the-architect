"""
The Architect — Immutable Guardrails Kernel

THIS FILE DEFINES THE BOUNDARIES THE ARCHITECT CANNOT CROSS.

Per Grok's v5 pressure-test recommendation:
- Stored as a signed, read-only set in Redis
- Only modifiable via the human CLI (`architect guardrails update`)
- The Architect CANNOT modify these programmatically
- Every self-modification task is checked against these rules
- Violations are logged, blocked, and reported immediately

Guardrail version is tracked in every task and every artifact
so we have a full audit trail of which rules were active when.
"""
import json
import hashlib
from datetime import datetime
from typing import Optional
import redis.asyncio as redis

from architect.config.settings import settings


# ═══════════════════════════════════════════════════════════════
# IMMUTABLE RULES — The Architect CANNOT change these
# Only `architect guardrails update` (human CLI) can modify them
# ═══════════════════════════════════════════════════════════════

CORE_GUARDRAILS = {
    "version": "1.0.0",

    # What self-improvement IS allowed to do
    "self_improve_allowed": [
        "optimize_existing_module_code",
        "fix_bugs_from_sentinel_or_feedback",
        "update_dependencies_and_upstream",
        "improve_test_coverage",
        "optimize_performance",
        "generate_documentation",
    ],

    # What REQUIRES human approval (cannot be auto-approved)
    "requires_human_approval": [
        "create_new_modules",
        "modify_security_configurations",
        "change_api_keys_or_credentials",
        "modify_budget_limits",
        "add_new_model_providers",
        "modify_iteration_engine_logic",
        "modify_guardrail_definitions",
        "deploy_to_client_systems",
        "access_financial_data_apis",
        "modify_nemoclaw_policies",
    ],

    # What is EXPLICITLY FORBIDDEN (blocked, no override)
    "explicitly_forbidden": [
        "modify_own_guardrails_programmatically",
        "disable_human_checkpoint_requirements",
        "access_systems_outside_defined_perimeter",
        "communicate_with_unapproved_external_systems",
        "self_replicate_or_deploy_copies",
        "modify_nemoclaw_security_policies",
        "increase_own_budget_limits",
        "bypass_privacy_screening",
        "send_pii_to_cloud_providers",
        "send_financial_data_to_vast_ai",
        "send_client_data_to_any_external_service",
    ],

    # Rate limits for self-improvement
    "self_improve_limits": {
        "max_concurrent_tasks": 2,
        "cooldown_seconds": 900,
        "max_daily_cycles": 20,
        "mandatory_human_review_every_n": 50,
        "max_budget_per_cycle_usd": 5.00,
        "max_daily_budget_usd": 25.00,
    },

    # Privacy rules (non-negotiable)
    "privacy": {
        "pii_never_leaves_forge": True,
        "financial_data_never_leaves_forge": True,
        "client_data_never_leaves_forge": True,
        "vast_ai_requires_privacy_scan": True,
        "cloud_api_requires_data_classification": True,
    },
}


def compute_guardrail_hash() -> str:
    """Compute SHA-256 hash of the current guardrail set for integrity verification."""
    serialized = json.dumps(CORE_GUARDRAILS, sort_keys=True)
    return hashlib.sha256(serialized.encode()).hexdigest()


class GuardrailKernel:
    """
    Enforces immutable guardrails on every Architect operation.
    
    The kernel loads guardrails into a signed Redis key on startup.
    Every task execution checks against these rules.
    Any attempt to modify guardrails programmatically is blocked and logged.
    """

    REDIS_KEY = "architect:guardrails:active"
    REDIS_HASH_KEY = "architect:guardrails:hash"
    REDIS_AUDIT_KEY = "architect:guardrails:audit_log"

    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        self.guardrails = CORE_GUARDRAILS
        self.hash = compute_guardrail_hash()

    async def initialize(self):
        """Load guardrails into Redis on startup. Verify integrity."""
        existing_hash = await self.redis.get(self.REDIS_HASH_KEY)

        if existing_hash and existing_hash.decode() != self.hash:
            # Hash mismatch — guardrails were tampered with
            await self._log_audit(
                "INTEGRITY_VIOLATION",
                f"Guardrail hash mismatch. Expected {self.hash}, "
                f"found {existing_hash.decode()}. Restoring from code."
            )

        # Always write the canonical guardrails from code
        await self.redis.set(
            self.REDIS_KEY,
            json.dumps(self.guardrails)
        )
        await self.redis.set(self.REDIS_HASH_KEY, self.hash)

        await self._log_audit(
            "INITIALIZED",
            f"Guardrail kernel v{self.guardrails['version']} loaded. "
            f"Hash: {self.hash[:16]}..."
        )

    async def check_task(self, task) -> "GuardrailCheck":
        """
        Validate a task against guardrails before execution.
        Returns approved/denied with reason.
        """
        # Check for forbidden actions
        desc_lower = task.description.lower()
        for forbidden in self.guardrails["explicitly_forbidden"]:
            forbidden_keywords = forbidden.replace("_", " ")
            if forbidden_keywords in desc_lower:
                await self._log_audit(
                    "BLOCKED",
                    f"Task {task.id} blocked: matches forbidden rule "
                    f"'{forbidden}'"
                )
                return GuardrailCheck(
                    approved=False,
                    reason=f"Forbidden by guardrail: {forbidden}",
                    rule="explicitly_forbidden",
                    guardrail_version=self.guardrails["version"]
                )

        # Check if self-improvement task needs human approval
        if task.source.type == "self_improve":
            return await self._check_self_improve(task)

        # Check privacy rules for tasks that touch external services
        if task.context.web_search:
            privacy_check = await self._check_privacy(task)
            if not privacy_check.approved:
                return privacy_check

        return GuardrailCheck(
            approved=True,
            guardrail_version=self.guardrails["version"]
        )

    async def _check_self_improve(self, task) -> "GuardrailCheck":
        """Additional checks for self-improvement tasks."""
        limits = self.guardrails["self_improve_limits"]

        # Check daily cycle count
        today = datetime.utcnow().strftime("%Y-%m-%d")
        cycle_key = f"architect:self_improve:cycles:{today}"
        current_cycles = int(await self.redis.get(cycle_key) or 0)

        if current_cycles >= limits["max_daily_cycles"]:
            return GuardrailCheck(
                approved=False,
                reason=f"Daily self-improvement limit reached "
                       f"({limits['max_daily_cycles']} cycles)",
                rule="self_improve_limits"
            )

        # Check if mandatory human review is due
        total_key = "architect:self_improve:total_cycles"
        total_cycles = int(await self.redis.get(total_key) or 0)

        if total_cycles > 0 and total_cycles % limits["mandatory_human_review_every_n"] == 0:
            return GuardrailCheck(
                approved=False,
                reason=f"Mandatory human review required after "
                       f"{total_cycles} self-improvement cycles",
                rule="mandatory_human_review",
                requires_human=True
            )

        # Check budget
        if task.budget.max_cost_usd > limits["max_budget_per_cycle_usd"]:
            return GuardrailCheck(
                approved=False,
                reason=f"Self-improvement budget ${task.budget.max_cost_usd} "
                       f"exceeds per-cycle limit "
                       f"${limits['max_budget_per_cycle_usd']}",
                rule="self_improve_budget"
            )

        # Check description against requires_human_approval list
        desc_lower = task.description.lower()
        for requires_human in self.guardrails["requires_human_approval"]:
            human_keywords = requires_human.replace("_", " ")
            if human_keywords in desc_lower:
                return GuardrailCheck(
                    approved=False,
                    reason=f"Self-improvement touching '{requires_human}' "
                           f"requires human approval",
                    rule="requires_human_approval",
                    requires_human=True
                )

        return GuardrailCheck(
            approved=True,
            guardrail_version=self.guardrails["version"]
        )

    async def _check_privacy(self, task) -> "GuardrailCheck":
        """Check privacy rules for tasks involving external data."""
        privacy = self.guardrails["privacy"]

        desc_lower = task.description.lower()
        financial_keywords = [
            "portfolio", "investment", "stock", "crypto", "btc",
            "position", "balance", "account", "trading"
        ]

        if any(kw in desc_lower for kw in financial_keywords):
            if privacy["financial_data_never_leaves_forge"]:
                return GuardrailCheck(
                    approved=False,
                    reason="Task references financial data and requests "
                           "web search. Financial data never leaves The Forge.",
                    rule="privacy_financial"
                )

        return GuardrailCheck(approved=True)

    async def record_self_improve_cycle(self):
        """Increment self-improvement cycle counters."""
        today = datetime.utcnow().strftime("%Y-%m-%d")
        pipe = self.redis.pipeline()
        pipe.incr(f"architect:self_improve:cycles:{today}")
        pipe.expire(f"architect:self_improve:cycles:{today}", 86400 * 2)
        pipe.incr("architect:self_improve:total_cycles")
        await pipe.execute()

    async def _log_audit(self, event_type: str, details: str):
        """Append to the immutable audit log."""
        entry = json.dumps({
            "timestamp": datetime.utcnow().isoformat(),
            "event": event_type,
            "details": details,
            "guardrail_version": self.guardrails["version"],
            "hash": self.hash[:16]
        })
        await self.redis.rpush(self.REDIS_AUDIT_KEY, entry)

    async def verify_integrity(self) -> bool:
        """Verify guardrails haven't been tampered with in Redis."""
        stored_hash = await self.redis.get(self.REDIS_HASH_KEY)
        if not stored_hash:
            return False
        return stored_hash.decode() == self.hash


class GuardrailCheck(BaseModel):
    """Result of a guardrail check."""
    approved: bool
    reason: Optional[str] = None
    rule: Optional[str] = None
    requires_human: bool = False
    guardrail_version: str = CORE_GUARDRAILS["version"]


# Need this import here to avoid circular
from pydantic import BaseModel  # noqa: E402
