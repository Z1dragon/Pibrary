from types import SimpleNamespace


def test_chat_endpoint_returns_answer_and_sources(app_client, chat_payload):
    client, app_module = app_client

    source_doc = SimpleNamespace(
        metadata={
            "file_name": "book.md",
            "book_id": "book-1",
            "title": "测试书籍",
            "author": "作者A",
            "domain": "computer_science",
            "source_type": "book_content",
            "chunk_index": 0,
            "page_num": 12,
            "chapter_title": "第一章",
        },
        page_content="这是检索到的原文片段。",
    )

    app_module.load_manifest = lambda: {"data/raw/book.md": {"book_id": "book-1"}}
    app_module.ask = lambda **_kwargs: {
        "answer": "这是回答",
        "source_documents": [source_doc],
        "session_id": "session-123",
    }

    resp = client.post("/api/chat", json=chat_payload())

    assert resp.status_code == 200
    data = resp.json()
    assert data["answer"] == "这是回答"
    assert data["session_id"] == "session-123"
    assert len(data["sources"]) == 1
    assert data["sources"][0]["file_name"] == "book.md"


def test_chat_generates_session_id_when_missing(app_client, chat_payload):
    client, app_module = app_client

    captured = {}
    app_module.load_manifest = lambda: {"data/raw/book.md": {"book_id": "book-1"}}

    def fake_ask(**kwargs):
        captured["session_id"] = kwargs.get("session_id")
        return {
            "answer": "ok",
            "source_documents": [],
            "session_id": kwargs.get("session_id"),
        }

    app_module.ask = fake_ask

    resp = client.post("/api/chat", json=chat_payload(question="继续", session_id=None))

    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"]
    assert captured["session_id"] == data["session_id"]


def test_chat_rejects_empty_question(app_client, chat_payload):
    client, _app_module = app_client

    resp = client.post("/api/chat", json=chat_payload(question="   "))

    assert resp.status_code == 400
    assert "问题不能为空" in resp.json()["detail"]


def test_chat_rejects_invalid_page_range(app_client, chat_payload):
    client, _app_module = app_client

    resp = client.post(
        "/api/chat",
        json=chat_payload(page_num_range={"min_page": 20, "max_page": 10}),
    )

    assert resp.status_code == 400
    assert "起始页不能大于结束页" in resp.json()["detail"]


def test_chat_returns_warning_when_kb_is_empty(app_client, chat_payload):
    client, app_module = app_client

    called = {"ask": False}
    app_module.load_manifest = lambda: {}

    def fake_ask(**_kwargs):
        called["ask"] = True
        return {"answer": "should not run", "source_documents": [], "session_id": "x"}

    app_module.ask = fake_ask

    resp = client.post("/api/chat", json=chat_payload())

    assert resp.status_code == 200
    assert "知识库为空" in resp.json()["answer"]
    assert called["ask"] is False
