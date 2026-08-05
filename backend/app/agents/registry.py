"""Capability-based agent lookup. The coordinator never hardcodes agent
classes — it asks the registry which agent can handle a task type."""
from app.agents.base_agent import BaseAgent
from app.core.exceptions import ProcessingError


class AgentRegistry:
    def __init__(self):
        self._agents: dict[str, BaseAgent] = {}

    def register(self, agent: BaseAgent) -> None:
        self._agents[agent.name] = agent

    def find_for(self, task_type: str) -> BaseAgent:
        for agent in self._agents.values():
            if task_type in agent.capabilities:
                return agent
        raise ProcessingError(f"No agent registered for task type '{task_type}'.")

    def all_agents(self) -> list[dict]:
        return [{"name": a.name, "description": a.description,
                 "capabilities": a.capabilities} for a in self._agents.values()]
