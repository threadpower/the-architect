"""
The Architect — Iteration Engine
The core loop: dispatch → collect → review → test → converge.
This is the automated version of Jeremy copy-pasting between models.
"""
import json
from datetime import datetime
from typing import Optional
import redis.asyncio as redis

from architect.models.task import Task, ModelResponse, TaskResult
from architect.core.model_router import ModelRouter, RoutingDecision
from architect.core.budget_controller import BudgetController
from architect.guardrails.kernel import GuardrailKernel
from architect.bridges.local_bridge import OllamaBridge
from architect.bridges.cloud_bridge import (
    ClaudeBridge, GrokBridge, BudgetExceeded, CloudBridgeError
)
from architect.utils.complexity import estimate_cloud_cost


class IterationEngine:
    """
    Orchestrates multi-model development cycles.
    
    The loop:
    1. Route task to primary model
    2. Collect response
    3. Send to reviewer (if configured and budget allows)
    4. Evaluate convergence
    5. Loop or surface to human
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        router: ModelRouter,
        budget: BudgetController,
        guardrails: GuardrailKernel,
        ollama: OllamaBridge,
        claude: Optional[ClaudeBridge] = None,
        grok: Optional[GrokBridge] = None,
    ):
        self.redis = redis_client
        self.router = router
        self.budget = budget
        self.guardrails = guardrails
        self.ollama = ollama
        self.claude = claude
        self.grok = grok

    async def run_task(self, task: Task) -> TaskResult:
        """Main orchestration loop for a task."""

        # Step 0: Guardrail check
        guard_check = await self.guardrails.check_task(task)
        if not guard_check.approved:
            return TaskResult(
                task_id=task.id,
                status="blocked",
                iterations=0,
                total_cost_usd=0.0,
                final_output=f"Blocked by guardrails: {guard_check.reason}",
            )

        # Step 1: Route the task
        routing = await self.router.route(task)
        await self._log_event(task, "routed", routing.to_dict())

        # Step 2: Iteration loop
        artifacts: list[ModelResponse] = []
        iteration = 0
        total_cost = 0.0

        while iteration < task.iteration.max_rounds:
            iteration += 1
            task.iteration_count = iteration
            await self._log_event(task, "iteration_start", {"round": iteration})

            # Dispatch to primary model
            try:
                primary_prompt = self._build_primary_prompt(
                    task, artifacts, iteration
                )
                primary_result = await self._dispatch(
                    routing.primary, primary_prompt, task
                )
                artifacts.append(primary_result)
                total_cost += primary_result.cost_usd

                # Track local savings if routed locally
                if primary_result.provider == "local":
                    cloud_cost = estimate_cloud_cost(task, "claude")
                    await self.budget.log_local_savings(
                        task.id, cloud_cost
                    )

            except BudgetExceeded as e:
                await self._log_event(task, "budget_exceeded", {"error": str(e)})
                return TaskResult(
                    task_id=task.id,
                    status="paused",
                    iterations=iteration,
                    total_cost_usd=total_cost,
                    artifacts=artifacts,
                    final_output=f"Paused: {e}",
                )
            except Exception as e:
                await self._log_event(task, "error", {"error": str(e)})
                # If cloud fails, try local fallback
                if routing.primary != "qwen-local":
                    try:
                        primary_result = await self._dispatch(
                            "qwen-local", primary_prompt, task
                        )
                        artifacts.append(primary_result)
                    except Exception as fallback_error:
                        return TaskResult(
                            task_id=task.id,
                            status="failed",
                            iterations=iteration,
                            total_cost_usd=total_cost,
                            artifacts=artifacts,
                            final_output=f"Failed: {e}. Fallback also failed: {fallback_error}",
                        )
                else:
                    return TaskResult(
                        task_id=task.id,
                        status="failed",
                        iterations=iteration,
                        total_cost_usd=total_cost,
                        artifacts=artifacts,
                        final_output=f"Failed: {e}",
                    )

            # Send to reviewer (if configured and budget allows)
            if routing.reviewer and iteration < task.iteration.max_rounds:
                # Check if we can afford the review
                can_continue = not await self.budget.is_local_only_mode()
                reviewer_is_local = routing.reviewer == "qwen-local"

                if can_continue or reviewer_is_local:
                    try:
                        review_prompt = self._build_review_prompt(
                            task, primary_result, iteration
                        )
                        review_result = await self._dispatch(
                            routing.reviewer, review_prompt, task
                        )
                        artifacts.append(review_result)
                        total_cost += review_result.cost_usd

                        # Check convergence
                        if self._evaluate_convergence(task, review_result):
                            await self._log_event(
                                task, "converged",
                                {"round": iteration, "reason": "reviewer_approved"}
                            )
                            break

                    except BudgetExceeded:
                        # Skip review if budget is tight — use primary result
                        await self._log_event(
                            task, "review_skipped", {"reason": "budget"}
                        )
                        break

            # Budget check between iterations
            warning = await self.budget.should_warn()
            if warning:
                await self._log_event(task, "budget_warning", {"message": warning})

        # Step 3: Record self-improvement cycle if applicable
        if task.source.type == "self_improve":
            await self.guardrails.record_self_improve_cycle()

        # Step 4: Build result
        final_output = artifacts[-1].content if artifacts else None
        task.actual_cost_usd = total_cost
        task.status = "complete"
        task.updated_at = datetime.utcnow()

        result = TaskResult(
            task_id=task.id,
            status="complete",
            iterations=iteration,
            total_cost_usd=round(total_cost, 4),
            cloud_cost_avoided=0.0,  # Populated by budget tracking
            artifacts=artifacts,
            final_output=final_output,
        )

        await self._log_event(task, "complete", {
            "iterations": iteration,
            "cost": total_cost,
        })

        return result

    async def _dispatch(
        self, model: str, prompt: str, task: Task
    ) -> ModelResponse:
        """Dispatch a prompt to the appropriate model bridge."""

        if model == "qwen-local":
            return await self.ollama.generate(
                prompt=prompt,
                context_files=task.context.files,
            )

        elif model == "claude":
            if not self.claude:
                raise CloudBridgeError("Claude bridge not configured")
            return await self.claude.generate(
                prompt=prompt,
                task_id=task.id,
            )

        elif model == "grok":
            if not self.grok:
                raise CloudBridgeError("Grok bridge not configured")
            return await self.grok.generate(
                prompt=prompt,
                task_id=task.id,
                enable_search=task.context.web_search,
            )

        else:
            # Fallback: try local
            return await self.ollama.generate(prompt=prompt)

    def _build_primary_prompt(
        self, task: Task, artifacts: list[ModelResponse], iteration: int
    ) -> str:
        """Build the prompt for the primary model."""

        parts = [f"# Task: {task.name}\n\n{task.description}"]

        if iteration > 1 and artifacts:
            parts.append("\n\n## Previous Iteration Results\n")
            for i, artifact in enumerate(artifacts[-4:], 1):  # Last 4 artifacts
                role = "Primary" if i % 2 == 1 else "Reviewer"
                parts.append(
                    f"### {role} (Round {(i+1)//2}):\n{artifact.content[:2000]}\n"
                )

        if task.output.format:
            parts.append(
                f"\n\n## Output Format\n"
                f"Respond in {task.output.format} format."
            )

        return "\n".join(parts)

    def _build_review_prompt(
        self, task: Task, primary_result: ModelResponse, iteration: int
    ) -> str:
        """Build the prompt for the reviewer model."""

        return (
            f"# Review Request\n\n"
            f"You are reviewing work for the following task:\n\n"
            f"**Task:** {task.name}\n"
            f"**Description:** {task.description}\n\n"
            f"## Work to Review (Iteration {iteration}):\n\n"
            f"{primary_result.content}\n\n"
            f"## Instructions\n"
            f"1. Assess the quality and completeness of this work\n"
            f"2. Identify any issues, gaps, or improvements needed\n"
            f"3. If the work is ready, say 'APPROVED' clearly\n"
            f"4. If not ready, provide specific feedback for improvement\n"
            f"5. Rate the work 1-10 for overall quality\n"
        )

    def _evaluate_convergence(
        self, task: Task, review_result: ModelResponse
    ) -> bool:
        """Determine if the review cycle can stop."""

        text = review_result.content.lower()

        if task.iteration.convergence.value == "reviewer_approved":
            approval_signals = [
                "approved", "looks good", "no major issues",
                "ready to ship", "well-structured", "solid work",
                "no significant issues", "ready for deployment",
            ]
            return any(signal in text for signal in approval_signals)

        elif task.iteration.convergence.value == "score_threshold":
            # Look for a numeric score
            import re
            scores = re.findall(r'\b(\d+)\s*/\s*10\b', review_result.content)
            if scores:
                score = int(scores[-1])
                return score >= task.iteration.score_threshold

        elif task.iteration.convergence.value == "human_approved":
            return False  # Always requires human

        elif task.iteration.convergence.value == "tests_pass":
            # Will be implemented when test runner is ready
            return "all tests pass" in text or "tests passing" in text

        return False

    async def _log_event(self, task: Task, event: str, data: dict):
        """Log task events to Redis for audit trail."""
        entry = json.dumps({
            "timestamp": datetime.utcnow().isoformat(),
            "task_id": task.id,
            "event": event,
            "data": data,
            "guardrail_version": task.guardrail_version,
        })
        key = f"architect:task_log:{task.id}"
        await self.redis.rpush(key, entry)
        await self.redis.expire(key, 86400 * 90)  # 90 day retention
