def test_conversation_crud_flow(client):
    # create
    res = client.post("/api/conversations")
    assert res.status_code == 201
    convo = res.json()
    assert convo["title"] == "New conversation"

    # first user message names the conversation
    res = client.post(f"/api/conversations/{convo['id']}/messages", json={
        "role": "user", "content": "What is the Q3 revenue?"})
    assert res.status_code == 201

    res = client.post(f"/api/conversations/{convo['id']}/messages", json={
        "role": "assistant", "content": "Revenue was $2.4M [1].",
        "question": "What is the Q3 revenue?",
        "meta": {"confidence": 0.9, "citations": [{"marker": "[1]"}]}})
    assert res.status_code == 201

    res = client.get("/api/conversations")
    listing = res.json()
    assert len(listing) == 1
    assert listing[0]["title"] == "What is the Q3 revenue?"
    assert len(listing[0]["messages"]) == 2
    assert listing[0]["messages"][1]["meta"]["confidence"] == 0.9

    # rename + pin
    res = client.patch(f"/api/conversations/{convo['id']}",
                       json={"title": "Q3 financials", "pinned": True})
    assert res.json()["pinned"] is True
    assert res.json()["title"] == "Q3 financials"

    # delete
    assert client.delete(f"/api/conversations/{convo['id']}").status_code == 204
    assert client.get("/api/conversations").json() == []


def test_conversations_are_user_scoped(client):
    client.post("/api/conversations")
    # A different user must not see the first user's conversations.
    res = client.post("/api/auth/register", json={
        "email": "other@corp.com", "password": "OtherPass1!"})
    other_token = res.json()["access_token"]
    res = client.get("/api/conversations",
                     headers={"Authorization": f"Bearer {other_token}"})
    assert res.json() == []
