"""Multi-agent RAG system (Module 6).

One clean architecture — eight specialized agents + one orchestrator:

    Planner → (Retriever ∥ Metadata) → Reranker → Compressor
            → Answer Generator → Verifier → Citation Validator

See :mod:`app.agents.orchestrator` for the execution pipeline and
:mod:`app.agents.base` for the shared execution-state/trace contract.
"""
from app.agents.answer_generator import AnswerGeneratorAgent
from app.agents.base import BaseAgent, PipelineContext, UserInfo
from app.agents.citation_validator import CitationValidationAgent
from app.agents.compressor import ContextCompressionAgent
from app.agents.metadata import MetadataAgent
from app.agents.orchestrator import AgentOrchestrator, get_orchestrator
from app.agents.planner import PlannerAgent
from app.agents.reranker import RerankerAgent
from app.agents.retriever import RetrieverAgent
from app.agents.schemas import FinalResponse, Plan
from app.agents.verifier import VerificationAgent

AGENT_REGISTRY = [
    {"name": PlannerAgent.name, "order": 1, "description": PlannerAgent.description},
    {"name": RetrieverAgent.name, "order": 2, "description": RetrieverAgent.description},
    {"name": MetadataAgent.name, "order": 3, "description": MetadataAgent.description},
    {"name": RerankerAgent.name, "order": 4, "description": RerankerAgent.description},
    {"name": ContextCompressionAgent.name, "order": 5, "description": ContextCompressionAgent.description},
    {"name": AnswerGeneratorAgent.name, "order": 6, "description": AnswerGeneratorAgent.description},
    {"name": VerificationAgent.name, "order": 7, "description": VerificationAgent.description},
    {"name": CitationValidationAgent.name, "order": 8, "description": CitationValidationAgent.description},
]

__all__ = [
    "BaseAgent", "PipelineContext", "UserInfo",
    "PlannerAgent", "RetrieverAgent", "MetadataAgent", "RerankerAgent",
    "ContextCompressionAgent", "AnswerGeneratorAgent", "VerificationAgent",
    "CitationValidationAgent", "AgentOrchestrator", "get_orchestrator",
    "FinalResponse", "Plan", "AGENT_REGISTRY",
]
