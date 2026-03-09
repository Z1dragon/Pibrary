def test_upload_note_endpoint_success(app_client):
    client, app_module = app_client

    app_module.load_manifest = lambda: {
        "data/raw/book.md": {
            "book_id": "book-1",
            "title": "测试书籍",
            "author": "作者A",
            "domain": "computer_science",
        }
    }

    captured = {}

    def fake_index_note_text(**kwargs):
        captured.update(kwargs)
        return "note-123", 4, "data/notes/note-123.md"

    app_module.index_note_text = fake_index_note_text

    resp = client.post(
        "/api/notes/upload",
        data={
            "book_id": "book-1",
            "note_text": "这是我的读书笔记",
            "note_title": "第一章随记",
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["note_id"] == "note-123"
    assert data["chunk_count"] == 4
    assert captured["book_id"] == "book-1"
    assert captured["source_book_meta"]["title"] == "测试书籍"


def test_upload_note_validates_required_fields(app_client):
    client, _app_module = app_client

    resp = client.post(
        "/api/notes/upload",
        data={"book_id": "", "note_text": "x", "note_title": "t"},
    )
    assert resp.status_code == 422

    resp1 = client.post(
        "/api/notes/upload",
        data={"book_id": "   ", "note_text": "x", "note_title": "t"},
    )
    assert resp1.status_code == 400
    assert "book_id 不能为空" in resp1.json()["detail"]

    resp2 = client.post(
        "/api/notes/upload",
        data={"book_id": "book-1", "note_text": "   ", "note_title": "t"},
    )
    assert resp2.status_code == 400
    assert "笔记内容不能为空" in resp2.json()["detail"]
