"""Shared working memory for one workflow run.

Agents communicate indirectly: each step's output is written here under
the task type, and later steps read it via AgentTask.context. This is the
'blackboard' pattern — agents stay decoupled from each other.
"""
from typing import Any


class WorkflowMemory:
    def __init__(self):
        self._store: dict[str, Any] = {}
        self.trace: list[str] = []       # human-readable execution log

    def write(self, key: str, value: Any) -> None:
        self._store[key] = value

    def read(self, key: str, default: Any = None) -> Any:
        return self._store.get(key, default)

    def snapshot(self) -> dict:
        return dict(self._store)

    def log(self, message: str) -> None:
        self.trace.append(message)
