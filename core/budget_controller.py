"""
The Architect — Budget Controller
Every dollar tracked. Every API call pre-authorized.
Local savings calculated and reported.
"""
import json
from datetime import datetime
from typing import Optional
import redis.asyncio as redis

from architect.config.settings import settings
from architect.models.budget import Authorization, CostEntry, CostReport


class BudgetController:
    """
    Unified cost controller across ALL spend vectors.
    Pre-authorizes every API call. Tracks savings from local routing.
    """

    PROVIDERS = ["claude", "grok", "openrouter", "vast", "twilio"]

    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        self.limits = settings.budget

    def _daily_key(self, provider: str) -> str:
        today = datetime.utcnow().strftime("%Y-%m-%d")
        return f"architect:budget:daily:{today}:{provider}"

    def _monthly_key(self, provider: str) -> str:
        month = datetime.utcnow().strftime("%Y-%m")
        return f"architect:budget:monthly:{month}:{provider}"

    def _savings_key(self) -> str:
        today = datetime.utcnow().strftime("%Y-%m-%d")
        return f"architect:budget:savings:{today}"

    async def pre_authorize(
        self,
        provider: str,
        estimated_cost: float,
        task_id: str
    ) -> Authorization:
        """
        Pre-authorize spending before ANY API call.
        Must be called before every cloud bridge request.
        """
        # Provider daily limit
        provider_daily = await self._get_daily_spend(provider)
        provider_limit = getattr(self.limits, f"{provider}_daily", 0)

        if provider_limit > 0 and provider_daily + estimated_cost > provider_limit:
            suggestion = self._suggest_alternative(provider)
            return Authorization(
                approved=False,
                provider=provider,
                reason=f"{provider} daily limit (${provider_limit:.2f}) "
                       f"would be exceeded. Spent: ${provider_daily:.2f}",
                suggestion=suggestion
            )

        # Total daily limit
        total_daily = await self._get_total_daily_spend()
        if total_daily + estimated_cost > self.limits.total_daily:
            return Authorization(
                approved=False,
                provider=provider,
                reason=f"Total daily limit (${self.limits.total_daily:.2f}) "
                       f"would be exceeded. Total spent: ${total_daily:.2f}",
                suggestion="Queue for tomorrow or route to local model"
            )

        # Total monthly limit
        total_monthly = await self._get_total_monthly_spend()
        if total_monthly + estimated_cost > self.limits.total_monthly:
            return Authorization(
                approved=False,
                provider=provider,
                reason=f"Monthly limit (${self.limits.total_monthly:.2f}) "
                       f"would be exceeded",
                suggestion="Requires manual override from Jeremy"
            )

        # Approved — reserve the budget
        return Authorization(
            approved=True,
            provider=provider,
            reserved=estimated_cost,
            daily_remaining=provider_limit - provider_daily - estimated_cost,
            monthly_remaining=self.limits.total_monthly - total_monthly - estimated_cost
        )

    async def log_spend(
        self,
        provider: str,
        task_id: str,
        tokens_in: int,
        tokens_out: int,
        cost_usd: float,
        model: str = ""
    ):
        """Log actual spending after an API call completes."""
        entry = CostEntry(
            provider=provider,
            task_id=task_id,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost_usd,
            timestamp=datetime.utcnow(),
            model=model
        )

        # Increment daily counter
        daily_key = self._daily_key(provider)
        await self.redis.incrbyfloat(daily_key, cost_usd)
        await self.redis.expire(daily_key, 86400 * 2)  # TTL 2 days

        # Increment monthly counter
        monthly_key = self._monthly_key(provider)
        await self.redis.incrbyfloat(monthly_key, cost_usd)
        await self.redis.expire(monthly_key, 86400 * 35)  # TTL 35 days

        # Log detailed entry
        log_key = f"architect:budget:log:{datetime.utcnow().strftime('%Y-%m-%d')}"
        await self.redis.rpush(log_key, entry.model_dump_json())
        await self.redis.expire(log_key, 86400 * 90)  # Keep 90 days

    async def log_local_savings(
        self,
        task_id: str,
        estimated_cloud_cost: float,
        provider_avoided: str = "claude"
    ):
        """Track money saved by routing locally instead of to cloud."""
        savings_key = self._savings_key()
        await self.redis.incrbyfloat(savings_key, estimated_cloud_cost)
        await self.redis.expire(savings_key, 86400 * 2)

        # Also increment local task counter
        counter_key = f"architect:budget:local_tasks:{datetime.utcnow().strftime('%Y-%m-%d')}"
        await self.redis.incr(counter_key)
        await self.redis.expire(counter_key, 86400 * 2)

    async def is_local_only_mode(self) -> bool:
        """Check if budget is tight enough to force local-only routing."""
        total_daily = await self._get_total_daily_spend()
        ratio = total_daily / self.limits.total_daily if self.limits.total_daily > 0 else 0
        return ratio >= self.limits.pause_at

    async def should_warn(self) -> Optional[str]:
        """Check if we should warn Jeremy about budget status."""
        total_daily = await self._get_total_daily_spend()
        ratio = total_daily / self.limits.total_daily if self.limits.total_daily > 0 else 0

        if ratio >= self.limits.emergency_only_at:
            return (
                f"BUDGET CRITICAL: ${total_daily:.2f} / "
                f"${self.limits.total_daily:.2f} ({ratio*100:.0f}%). "
                f"Emergency tasks only."
            )
        elif ratio >= self.limits.pause_at:
            return (
                f"BUDGET HIGH: ${total_daily:.2f} / "
                f"${self.limits.total_daily:.2f} ({ratio*100:.0f}%). "
                f"Non-critical tasks paused."
            )
        elif ratio >= self.limits.warn_at:
            return (
                f"Budget alert: ${total_daily:.2f} / "
                f"${self.limits.total_daily:.2f} ({ratio*100:.0f}%)."
            )
        return None

    async def get_daily_report(self) -> CostReport:
        """Generate today's cost report."""
        today = datetime.utcnow().strftime("%Y-%m-%d")
        report = CostReport(period="daily", date=today)

        for provider in self.PROVIDERS:
            spent = await self._get_daily_spend(provider)
            limit = getattr(self.limits, f"{provider}_daily", 0)
            pct = (spent / limit * 100) if limit > 0 else 0

            report.providers[provider] = {
                "spent": round(spent, 2),
                "limit": limit,
                "percentage": round(pct, 1)
            }
            report.total_spent += spent

        report.total_limit = self.limits.total_daily

        # Local savings
        savings_key = self._savings_key()
        savings = await self.redis.get(savings_key)
        report.local_savings = float(savings) if savings else 0.0

        counter_key = f"architect:budget:local_tasks:{today}"
        local_count = await self.redis.get(counter_key)
        report.local_tasks = int(local_count) if local_count else 0

        # Effective cost per task
        total_tasks = report.local_tasks + report.cloud_tasks
        if total_tasks > 0:
            report.effective_cost_per_task = round(
                report.total_spent / total_tasks, 2
            )

        return report

    async def _get_daily_spend(self, provider: str) -> float:
        val = await self.redis.get(self._daily_key(provider))
        return float(val) if val else 0.0

    async def _get_total_daily_spend(self) -> float:
        total = 0.0
        for provider in self.PROVIDERS:
            total += await self._get_daily_spend(provider)
        return total

    async def _get_total_monthly_spend(self) -> float:
        total = 0.0
        for provider in self.PROVIDERS:
            val = await self.redis.get(self._monthly_key(provider))
            total += float(val) if val else 0.0
        return total

    def _suggest_alternative(self, provider: str) -> str:
        alternatives = {
            "claude": "Route to Qwen locally or queue for tomorrow",
            "grok": "Use NemoClaw web crawling instead of Grok search",
            "openrouter": "Route to Qwen locally",
            "vast": "Queue for local processing overnight",
            "twilio": "Batch notifications into fewer SMS messages",
        }
        return alternatives.get(provider, "Queue for manual review")
