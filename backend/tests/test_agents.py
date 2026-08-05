from app.agents.base_agent import AgentTask
from app.agents.coordinator import CoordinatorAgent
from app.agents.specialized import EvaluationAgent


def test_registry_lists_all_agents(db):
    agents = CoordinatorAgent(db).registry.all_agents()
    names = {a["name"] for a in agents}
    assert names == {"document_agent", "metadata_agent", "search_agent",
                     "analytics_agent", "report_agent", "evaluation_agent",
                     "notification_agent"}


def test_coordinator_analytics_workflow(db):
    result = CoordinatorAgent(db).handle("analytics", {})
    assert result["success"]
    assert result["output"]["total_documents"] == 0
    assert result["trace"]


def test_evaluation_agent_scores_refusal():
    task = AgentTask("evaluate_answer",
                     {"answer": "The knowledge base does not contain enough information.",
                      "citations": []})
    result = EvaluationAgent().run(task)
    assert result.success
    assert result.output["refused"] is True
    assert result.output["score"] == 0.0
