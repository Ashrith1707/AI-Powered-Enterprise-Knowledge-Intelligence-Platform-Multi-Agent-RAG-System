import io


def test_upload_txt_and_list(client):
    content = b"Quarterly revenue increased by 12 percent. Contact finance@corp.com."
    res = client.post("/api/documents/upload",
                      files={"file": ("report.txt", io.BytesIO(content), "text/plain")})
    assert res.status_code == 201
    doc = res.json()["document"]
    assert doc["file_type"] == "txt"

    res = client.get("/api/documents")
    assert res.status_code == 200
    assert len(res.json()) == 1


def test_upload_rejects_bad_extension(client):
    res = client.post("/api/documents/upload",
                      files={"file": ("virus.exe", io.BytesIO(b"xx"), "application/octet-stream")})
    assert res.status_code == 400


def test_upload_rejects_empty_file(client):
    res = client.post("/api/documents/upload",
                      files={"file": ("empty.txt", io.BytesIO(b""), "text/plain")})
    assert res.status_code == 400


def test_duplicate_upload_rejected(client):
    content = b"same file content for duplicate detection test"
    files = {"file": ("a.txt", io.BytesIO(content), "text/plain")}
    assert client.post("/api/documents/upload", files=files).status_code == 201
    files = {"file": ("a.txt", io.BytesIO(content), "text/plain")}
    assert client.post("/api/documents/upload", files=files).status_code == 400
