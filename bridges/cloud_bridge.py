"""
The Architect — Cloud Bridges (Claude + Grok)
Every call pre-authorized by BudgetController.
Every dollar logged. Every token tracked.
"""
import httpx
from typing import Optional

from architect.config.settings import settings
from architect.models.task import ModelResponse
from architect.core.budget_controller import BudgetController


class CloudBridgeError(Exception):
    """Raised when a cloud API call fails."""
    pass


class BudgetExceeded(CloudBridgeError):
    """Raised when budget is insufficient for the requested call."""
    pass


class ClaudeBridge:
    """Interface to Anthropic Claude API with budget controls."""

    def __init__(self, budget_controller: BudgetController):
        self.budget = budget_controller
        self.api_key = settings.anthropic_api_key
        self.base_url = "https://api.anthropic.com/v1/messages"
        self.default_model = "claude-sonnet-4-20250514"
        self.timeout = httpx.Timeout(120.0, connect=10.0)
        # Approximate pricing per 1K tokens (verify current rates)
        self.pricing = {"input": 0.003, "output": 0.015}

    async def generate(
        self,
        prompt: str,
        task_id: str,
        system: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: int = 4096,
    ) -> ModelResponse:
        """Generate via Claude API. Pre-authorized and cost-tracked."""

        if not self.api_key:
            raise CloudBridgeError(
                "ANTHROPIC_API_KEY not configured. "
                "Set ARCHITECT_ANTHROPIC_API_KEY in .env"
            )

        # Pre-flight: estimate cost and get authorization
        estimated_cost = self._estimate_cost(prompt, max_tokens)
        auth = await self.budget.pre_authorize("claude", estimated_cost, task_id)

        if not auth.approved:
            raise BudgetExceeded(
                f"Claude budget exceeded: {auth.reason}. "
                f"Suggestion: {auth.suggestion}"
            )

        # Make the API call
        use_model = model or self.default_model
        headers = {
            "x-api-key": self.api_key,
            "content-type": "application/json",
            "anthropic-version": "2023-06-01",
        }
        payload = {
            "model": use_model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            payload["system"] = system

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                self.base_url, headers=headers, json=payload
            )

            if response.status_code != 200:
                raise CloudBridgeError(
                    f"Claude API error {response.status_code}: "
                    f"{response.text[:500]}"
                )

            data = response.json()

        tokens_in = data["usage"]["input_tokens"]
        tokens_out = data["usage"]["output_tokens"]
        actual_cost = (
            tokens_in * self.pricing["input"] / 1000
            + tokens_out * self.pricing["output"] / 1000
        )

        # Log actual spend
        await self.budget.log_spend(
            provider="claude",
            task_id=task_id,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=actual_cost,
            model=use_model,
        )

        return ModelResponse(
            content=data["content"][0]["text"],
            model=data["model"],
            provider="claude",
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=actual_cost,
        )

    def _estimate_cost(self, prompt: str, max_tokens: int) -> float:
        est_input_tokens = len(prompt) / 4  # ~4 chars per token
        est_output_tokens = max_tokens * 0.5  # Assume 50% utilization
        return (
            est_input_tokens * self.pricing["input"] / 1000
            + est_output_tokens * self.pricing["output"] / 1000
        )


class GrokBridge:
    """Interface to xAI Grok API with budget controls and X search."""

    def __init__(self, budget_controller: BudgetController):
        self.budget = budget_controller
        self.api_key = settings.xai_api_key
        self.base_url = "https://api.x.ai/v1/chat/completions"
        self.default_model = "grok-3"
        self.timeout = httpx.Timeout(120.0, connect=10.0)
        self.pricing = {"input": 0.003, "output": 0.015}

    async def generate(
        self,
        prompt: str,
        task_id: str,
        system: Optional[str] = None,
        model: Optional[str] = None,
        enable_search: bool = False,
    ) -> ModelResponse:
        """Generate via Grok API. Supports X/Twitter search."""

        if not self.api_key:
            raise CloudBridgeError(
                "XAI_API_KEY not configured. "
                "Set ARCHITECT_XAI_API_KEY in .env"
            )

        estimated_cost = self._estimate_cost(prompt)
        auth = await self.budget.pre_authorize("grok", estimated_cost, task_id)

        if not auth.approved:
            raise BudgetExceeded(
                f"Grok budget exceeded: {auth.reason}. "
                f"Suggestion: {auth.suggestion}"
            )

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {"model": model or self.default_model, "messages": messages}
        if enable_search:
            payload["search"] = {"enabled": True}

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                self.base_url, headers=headers, json=payload
            )

            if response.status_code != 200:
                raise CloudBridgeError(
                    f"Grok API error {response.status_code}: "
                    f"{response.text[:500]}"
                )

            data = response.json()

        tokens_in = data["usage"]["prompt_tokens"]
        tokens_out = data["usage"]["completion_tokens"]
        actual_cost = (
            tokens_in * self.pricing["input"] / 1000
            + tokens_out * self.pricing["output"] / 1000
        )

        await self.budget.log_spend(
            provider="grok",
            task_id=task_id,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=actual_cost,
            model=model or self.default_model,
        )

        return ModelResponse(
            content=data["choices"][0]["message"]["content"],
            model=data["model"],
            provider="grok",
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=actual_cost,
        )

    def _estimate_cost(self, prompt: str) -> float:
        est_input_tokens = len(prompt) / 4
        est_output_tokens = est_input_tokens * 0.5
        return (
            est_input_tokens * self.pricing["input"] / 1000
            + est_output_tokens * self.pricing["output"] / 1000
        )
