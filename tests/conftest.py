import importlib
import os
import sys
import types

import pytest
from fastapi.testclient import TestClient


def _load_app_with_stubs(monkeypatch):
    os.environ.setdefault("GLM_API_KEY", "test-key")

    fake_chain = types.ModuleType("src.chain")
    fake_chain.ask = lambda **_kwargs: {
        "answer": "stub answer",
        "source_documents": [],
        "session_id": "stub-session",
    }
    fake_chain.get_session_messages = lambda _sid: []
    fake_chain.clear_session_history = lambda _sid: None

    fake_data_loader = types.ModuleType("src.data_loader")
    fake_data_loader.SUPPORTED_EXTENSIONS = {".pdf", ".md", ".txt"}
    fake_data_loader.parse_book_metadata = lambda _path: {}

    fake_indexer = types.ModuleType("src.indexer")
    fake_indexer.delete_file = lambda _path: True
    fake_indexer.delete_note = lambda _note_id: True
    fake_indexer.index_file = lambda *_args, **_kwargs: 1
    fake_indexer.index_note_text = lambda **_kwargs: ("note-1", 1, "data/notes/note-1.md")
    fake_indexer.load_manifest = lambda: {"data/raw/book.md": {"book_id": "book-1"}}
    fake_indexer.load_note_manifest = lambda: {}

    monkeypatch.setitem(sys.modules, "src.chain", fake_chain)
    monkeypatch.setitem(sys.modules, "src.data_loader", fake_data_loader)
    monkeypatch.setitem(sys.modules, "src.indexer", fake_indexer)

    if "src.app" in sys.modules:
        del sys.modules["src.app"]
    app_module = importlib.import_module("src.app")
    client = TestClient(app_module.app)
    return client, app_module


def _chat_payload(**overrides):
    payload = {
        "question": "什么是RAG？",
        "session_id": "session-123",
        "use_reranker": True,
        "recall_top_k": 10,
        "rerank_top_k": 3,
        "filters": {},
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def app_client(monkeypatch):
    return _load_app_with_stubs(monkeypatch)


@pytest.fixture
def chat_payload():
    return _chat_payload
