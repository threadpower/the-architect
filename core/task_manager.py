"""
The Architect — Task Manager
Handles task submission, persistence, status tracking, and retrieval.
All state stored in Redis for sovereignty.
"""
import json
from datetime import datetime
from typing import Optional
import redis.asyncio as redis

from architect.models.task import Task


class TaskManager:
    """Manages task lifecycle in Redis."""

    TASK_KEY_PREFIX = "architect:tasks"
    QUEUE_KEY = "architect:task_queue"

    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client

    async def submit(self, task: Task) -> Task:
        """Submit a new task. Stores in Redis and adds to queue."""
        task.status = "pending"
        task.created_at = datetime.utcnow()
        task.updated_at = datetime.utcnow()

        # Store task
        key = f"{self.TASK_KEY_PREFIX}:{task.id}"
        await self.redis.set(key, task.model_dump_json())
        await self.redis.expire(key, 86400 * 90)  # 90 day retention

        # Add to processing queue
        await self.redis.rpush(self.QUEUE_KEY, task.id)

        return task

    async def get(self, task_id: str) -> Optional[Task]:
        """Retrieve a task by ID."""
        key = f"{self.TASK_KEY_PREFIX}:{task_id}"
        data = await self.redis.get(key)
        if not data:
            return None
        return Task.model_validate_json(data)

    async def update_status(
        self, task_id: str, status: str, cost: float = 0.0
    ):
        """Update task status and cost."""
        task = await self.get(task_id)
        if task:
            task.status = status
            task.actual_cost_usd = cost
            task.updated_at = datetime.utcnow()
            key = f"{self.TASK_KEY_PREFIX}:{task_id}"
            await self.redis.set(key, task.model_dump_json())

    async def list_tasks(
        self,
        status: Optional[str] = None,
        limit: int = 20,
    ) -> list[Task]:
        """List tasks, optionally filtered by status."""
        # Get all task keys
        pattern = f"{self.TASK_KEY_PREFIX}:architect-*"
        keys = []
        async for key in self.redis.scan_iter(match=pattern, count=100):
            keys.append(key)

        tasks = []
        for key in sorted(keys, reverse=True)[:limit * 2]:
            data = await self.redis.get(key)
            if data:
                task = Task.model_validate_json(data)
                if status is None or task.status == status:
                    tasks.append(task)
                    if len(tasks) >= limit:
                        break

        return tasks

    async def next_pending(self) -> Optional[Task]:
        """Pop the next pending task from the queue."""
        task_id = await self.redis.lpop(self.QUEUE_KEY)
        if not task_id:
            return None
        return await self.get(task_id.decode() if isinstance(task_id, bytes) else task_id)

    async def get_task_log(self, task_id: str) -> list[dict]:
        """Get the event log for a task."""
        key = f"architect:task_log:{task_id}"
        entries = await self.redis.lrange(key, 0, -1)
        return [
            json.loads(e.decode() if isinstance(e, bytes) else e)
            for e in entries
        ]
