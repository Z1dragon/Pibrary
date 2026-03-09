import json


def test_build_kb_endpoint_handles_mixed_results(app_client, tmp_path):
    client, app_module = app_client

    app_module.RAW_DATA_DIR = tmp_path

    calls = []

    def fake_index_file(save_path, force=False, manual_metadata=None):
        calls.append(
            {
                "name": save_path.name,
                "force": force,
                "meta": manual_metadata,
                "exists": save_path.exists(),
            }
        )
        if save_path.name == "bad.md":
            raise RuntimeError("mock index failed")
        return 2

    app_module.index_file = fake_index_file

    files = [
        ("files", ("good.md", b"good content", "text/markdown")),
        ("files", ("bad.md", b"bad content", "text/markdown")),
    ]
    payload = {
        "metadata_json": json.dumps(
            {
                "good.md": {"book_id": "book-good"},
                "bad.md": {"book_id": "book-bad"},
            }
        ),
        "force_rebuild": "true",
    }

    resp = client.post("/api/kb/build", data=payload, files=files)

    assert resp.status_code == 200
    data = resp.json()
    assert data["total_files"] == 2
    assert data["total_chunks"] == 2
    assert len(data["results"]) == 2
    assert data["results"][0]["success"] is True
    assert data["results"][1]["success"] is False
    assert "mock index failed" in data["results"][1]["error"]
    assert calls[0]["exists"] is True
    assert calls[0]["force"] is True
    assert calls[0]["meta"]["book_id"] == "book-good"


def test_build_kb_rejects_invalid_metadata_json(app_client):
    client, _app_module = app_client

    files = [("files", ("only.md", b"content", "text/markdown"))]
    resp = client.post(
        "/api/kb/build",
        data={"metadata_json": "{invalid-json}", "force_rebuild": "false"},
        files=files,
    )

    assert resp.status_code == 400
    assert "metadata_json 非法" in resp.json()["detail"]
