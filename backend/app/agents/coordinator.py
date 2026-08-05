"""Coordinator Agent — the brain of Phase 2.

Responsibilities:
  1. Build the registry (all specialized agents for this request's DB session)
  2. PLAN: map a high-level intent to an ordered list of agent tasks
  3. EXECUTE: hand the plan to the workflow engine
  4. REPORT: return final output + full execution trace for monitoring
"""
from sqlalchemy.orm import Session

from app.agents.base_agent import AgentTask
from app.agents.registry import AgentRegistry
from app.agents.specialized import (AnalyticsAgent, DocumentAgent, EvaluationAgent,
                                    MetadataAgent, NotificationAgent, ReportAgent,
                                    SearchAgent)
from app.agents.workflow import WorkflowEngine
from app.core.exceptions import ValidationError


class CoordinatorAgent:
    def __init__(self, db: Session):
        self.db = db
        self.registry = AgentRegistry()
        for agent in (DocumentAgent(db), MetadataAgent(db), SearchAgent(db),
                      AnalyticsAgent(db), ReportAgent(db), EvaluationAgent(),
                      NotificationAgent(db)):
            self.registry.register(agent)
        self.engine = WorkflowEngine(self.registry)

    # ---------- task planner ----------
    def plan(self, intent: str, payload: dict) -> list[AgentTask]:
        if intent == "ask":
            return [
                AgentTask("rag_answer", {"question": payload["question"]}),
                AgentTask("evaluate_answer", {}),
                AgentTask("notify", {"message": f"Question answered: {payload['question'][:80]}",
                                     "entity_type": "search"}),
            ]
        if intent == "ingest":
            return [
                AgentTask("process_document", {"document_id": payload["document_id"]}),
                AgentTask("notify", {"message": f"Document {payload['document_id']} processed",
                                     "entity_type": "document",
                                     "entity_id": payload["document_id"]}),
            ]
        if intent == "report":
            return [AgentTask("generate_report", payload)]
        if intent == "analytics":
            return [AgentTask("dashboard_stats", {})]
        raise ValidationError(f"Coordinator has no plan for intent '{intent}'.")

    # ---------- entry point ----------
    def handle(self, intent: str, payload: dict) -> dict:
        tasks = self.plan(intent, payload)
        results, memory = self.engine.execute(tasks)
        last = results[-1] if results else None
        # The user-facing output is the first non-notification result payload.
        primary = next((r.output for r in results
                        if r.task_type not in ("notify",) and r.success), None)
        return {
            "intent": intent,
            "success": bool(last and last.success),
            "output": primary,
            "evaluation": memory.read("evaluate_answer"),
            "trace": memory.trace,
            "error": next((r.error for r in results if not r.success), None),
        }
