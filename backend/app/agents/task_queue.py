"""In-process FIFO task queue for a workflow run.

Kept deliberately simple (a deque) — the interface is what matters: the
workflow engine only push/pops, so this can be swapped for Celery/Redis
in production without touching the coordinator.
"""
from collections import deque

from app.agents.base_agent import AgentTask


class TaskQueue:
    def __init__(self):
        self._queue: deque[AgentTask] = deque()

    def push(self, task: AgentTask) -> None:
        self._queue.append(task)

    def pop(self) -> AgentTask | None:
        return self._queue.popleft() if self._queue else None

    def __len__(self) -> int:
        return len(self._queue)
