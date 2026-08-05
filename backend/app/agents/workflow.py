"""Workflow engine: executes a planned sequence of agent tasks.

For each queued task it (1) finds the capable agent via the registry,
(2) injects shared memory as context, (3) times and runs the agent,
(4) writes the result back to memory, (5) records a trace line.
A failed step aborts the run and reports which agent failed.
"""
import time

from app.agents.base_agent import AgentResult, AgentTask
from app.agents.memory import WorkflowMemory
from app.agents.registry import AgentRegistry
from app.agents.task_queue import TaskQueue
from app.core.logging_config import get_logger

logger = get_logger("workflow")


class WorkflowEngine:
    def __init__(self, registry: AgentRegistry):
        self.registry = registry

    def execute(self, tasks: list[AgentTask]) -> tuple[list[AgentResult], WorkflowMemory]:
        queue = TaskQueue()
        memory = WorkflowMemory()
        for t in tasks:
            queue.push(t)

        results: list[AgentResult] = []
        while (task := queue.pop()) is not None:
            agent = self.registry.find_for(task.task_type)
            task.context = memory.snapshot()

            start = time.perf_counter()
            try:
                result = agent.run(task)
            except Exception as exc:                     # agent crashed
                logger.exception("Agent %s crashed on %s", agent.name, task.task_type)
                result = AgentResult(agent.name, task.task_type, False, error=str(exc))
            result.duration_ms = round((time.perf_counter() - start) * 1000, 1)

            results.append(result)
            memory.log(f"{agent.name} -> {task.task_type} "
                       f"[{'ok' if result.success else 'FAILED'}] {result.duration_ms}ms")
            logger.info(memory.trace[-1])

            if not result.success:
                break
            memory.write(task.task_type, result.output)
        return results, memory
