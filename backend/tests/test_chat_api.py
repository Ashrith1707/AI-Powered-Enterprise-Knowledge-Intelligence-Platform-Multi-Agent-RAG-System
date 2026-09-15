"""Chat API tests: /api/chat/ask, SSE streaming, conversations, agent traces."""
from __future__ import annotations

import json

from tests.conftest import (
    SAFETY_DOC,
    auth_headers,
    login,
    register_user,
    upload_document,
    wait_for_processing,
)


def _ingest(client, headers) -> int:
    doc = upload_document(client, headers, "safety.txt", SAFETY_DOC.encode())
    wait_for_processing(client, headers, doc["id"])
    return doc["id"]


def test_ask_endpoint_returns_full_agent_payload(client, user_client):
    client, headers, _ = user_client
    _ingest(client, headers)

    r = client.post("/api/chat/ask", headers=headers,
                    json={"question": "What PPE is required on the production floor?"})
    assert r.status_code == 200
    body = r.json()
    assert body["answer"]
    assert body["plan"]["intent"] == "knowledge_retrieval"
    assert len(body["trace"]["steps"]) == 8
    assert body["citations"]
    assert body["verification"]["verified"] is True
    assert body["conversation_id"] is not None
    assert body["ai_mode"] == "mock"


def test_ask_requires_auth(client):
    r = client.post("/api/chat/ask", json={"question": "hello"})
    assert r.status_code == 401


def test_ask_validates_question(client, user_client):
    client, headers, _ = user_client
    r = client.post("/api/chat/ask", headers=headers, json={"question": ""})
    assert r.status_code == 422


def test_stream_endpoint_emits_sse_events(client, user_client):
    client, headers, _ = user_client
    _ingest(client, headers)

    with client.stream(
        "POST", "/api/chat/ask/stream", headers=headers,
        json={"question": "What are the safety requirements for machine maintenance?"},
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        events = []
        final_payload = None
        current_event = None
        for line in response.iter_lines():
            if line.startswith("event:"):
                current_event = line.split(":", 1)[1].strip()
                events.append(current_event)
            elif line.startswith("data:") and current_event == "final":
                final_payload = json.loads(line.split(":", 1)[1].strip())

    assert "plan" in events
    assert "token" in events
    assert "final" in events
    assert events[-1] == "done"
    assert "trace" in events
    # The final payload wraps the complete FinalResponse under "response"
    assert final_payload is not None
    final = final_payload["response"]
    assert final["answer"]
    assert len(final["trace"]["steps"]) == 8
    assert final["citations"]
    assert final["verification"]["verified"] is True


def test_conversation_persistence_and_history(client, user_client):
    client, headers, _ = user_client
    _ingest(client, headers)

    r = client.post("/api/chat/ask", headers=headers, json={"question": "What is the LOTO procedure?"})
    conv_id = r.json()["conversation_id"]
    r = client.post("/api/chat/ask", headers=headers,
                    json={"question": "What about PPE?", "conversation_id": conv_id})
    assert r.json()["conversation_id"] == conv_id

    convs = client.get("/api/conversations", headers=headers).json()
    assert len(convs) == 1
    assert convs[0]["message_count"] == 4

    detail = client.get(f"/api/conversations/{conv_id}", headers=headers).json()
    assistant_msgs = [m for m in detail["messages"] if m["role"] == "assistant"]
    assert assistant_msgs
    # persisted trace + citations + metrics
    assert assistant_msgs[0]["agent_trace"]["steps"]
    assert assistant_msgs[0]["metrics"]["total_latency_ms"] > 0

    r = client.delete(f"/api/conversations/{conv_id}", headers=headers)
    assert r.status_code == 204
    assert client.get(f"/api/conversations/{conv_id}", headers=headers).status_code == 404


def test_conversation_of_other_user_inaccessible(client):
    register_user(client, "alice@test.dev")
    alice = auth_headers(login(client, "alice@test.dev"))
    register_user(client, "bob@test.dev")
    bob = auth_headers(login(client, "bob@test.dev"))

    r = client.post("/api/chat/ask", headers=alice, json={"question": "hi"})
    conv_id = r.json()["conversation_id"]
    assert client.get(f"/api/conversations/{conv_id}", headers=bob).status_code == 404
    assert client.delete(f"/api/conversations/{conv_id}", headers=bob).status_code == 404


def test_agent_registry_endpoint(client, user_client):
    client, headers, _ = user_client
    r = client.get("/api/agents", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["architecture"] == "multi-agent-rag"
    assert len(body["agents"]) == 8
    assert body["pipeline"][0] == "planner"
    assert body["pipeline"][-1] == "citation_validator"


def test_agent_trace_endpoint(client, user_client):
    client, headers, _ = user_client
    _ingest(client, headers)
    r = client.post("/api/chat/ask", headers=headers, json={"question": "What is the LOTO procedure?"})
    message_id = r.json()["message_id"]

    trace = client.get(f"/api/agents/traces/{message_id}", headers=headers).json()
    assert trace["message_id"] == message_id
    assert len(trace["agent_trace"]["steps"]) == 8
    # traces expose summaries, never prompts or hidden chain-of-thought
    dumped = json.dumps(trace)
    assert "system_instruction" not in dumped
    assert "You are KnowledgeIQ" not in dumped

    latest = client.get("/api/agents/traces", headers=headers).json()
    assert latest and latest[0]["message_id"] == message_id


def test_chat_mode_reports_providers(client, user_client):
    client, headers, _ = user_client
    r = client.get("/api/chat/mode", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["llm"]["provider"] == "mock"
    assert body["embeddings"]["provider"] == "local-hash"
    assert "text-embedding-004" not in json.dumps(body)
