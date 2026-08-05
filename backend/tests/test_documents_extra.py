import io


def _upload(client, name="note.txt", content=b"hello enterprise world of documents"):
    return client.post("/api/documents/upload",
                       files={"file": (name, io.BytesIO(content), "text/plain")})


def test_download_original_file(client):
    doc = _upload(client).json()["document"]
    res = client.get(f"/api/documents/{doc['id']}/download")
    assert res.status_code == 200
    assert res.content == b"hello enterprise world of documents"
    assert "note.txt" in res.headers["content-disposition"]


def test_patch_rename_category_tags(client):
    doc = _upload(client).json()["document"]
    res = client.patch(f"/api/documents/{doc['id']}", json={
        "filename": "renamed.txt", "category": "finance",
        "description": "quarterly notes", "tags": ["q3", "internal"]})
    assert res.status_code == 200
    body = res.json()
    assert body["filename"] == "renamed.txt"
    assert body["category"] == "finance"
    assert body["tags"] == ["q3", "internal"]


def test_patch_empty_body_rejected(client):
    doc = _upload(client).json()["document"]
    assert client.patch(f"/api/documents/{doc['id']}", json={}).status_code == 400


def test_search_analytics_endpoint(client):
    client.post("/api/search", json={"query": "hello world", "top_k": 3})
    res = client.get("/api/analytics/searches?days=7")
    assert res.status_code == 200
    body = res.json()
    assert body["total"] >= 1
    assert len(body["daily"]) == 7
    assert body["top_queries"][0]["query"] == "hello world"


def test_metrics_endpoint(client):
    client.get("/api/documents")
    res = client.get("/api/metrics")
    assert res.status_code == 200
    assert "api_requests_total" in res.text
