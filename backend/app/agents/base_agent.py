"""Contract every specialized agent implements.

An agent = a named unit of work with declared capabilities. The coordinator
plans a workflow, then dispatches AgentTask objects; each agent returns an
AgentResult. Uniform envelopes keep agents composable and monitorable.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class AgentTask:
    task_type: str
    payload: dict = field(default_factory=dict)
    context: dict = field(default_factory=dict)   # results of earlier steps


@dataclass
class AgentResult:
    agent_name: str
    task_type: str
    success: bool
    output: Any = None
    error: str | None = None
    started_at: datetime = field(default_factory=datetime.utcnow)
    duration_ms: float = 0.0


class BaseAgent(ABC):
    name: str = "base"
    description: str = ""
    capabilities: list[str] = []          # task_types this agent handles

    @abstractmethod
    def run(self, task: AgentTask) -> AgentResult:
        ...

    def _success(self, task: AgentTask, output: Any) -> AgentResult:
        return AgentResult(self.name, task.task_type, True, output=output)

    def _failure(self, task: AgentTask, error: str) -> AgentResult:
        return AgentResult(self.name, task.task_type, False, error=error)
