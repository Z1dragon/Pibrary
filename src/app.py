"""
FastAPI Web 应用入口
前端采用 Vite 构建版 React + CSS，后端提供知识库构建与问答 API。
"""

import json
import logging
import sys
import time
from uuid import uuid4
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# 确保项目根目录在 sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config import LOG_LEVEL, RAW_DATA_DIR, VALID_DOMAINS
from src.chain import ask
from src.chain import clear_session_history, get_session_messages
from src.data_loader import SUPPORTED_EXTENSIONS, parse_book_metadata
from src.indexer import (
    delete_file,
    delete_note,
    index_file,
    index_note_text,
    load_manifest,
    load_note_manifest,
)


if not logging.getLogger().handlers:
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
logger = logging.getLogger(__name__)


class PageRangeModel(BaseModel):
    min_page: int = Field(ge=1)
    max_page: int = Field(ge=1)


class AskRequest(BaseModel):
    question: str
    session_id: Optional[str] = None
    use_reranker: bool = True
    recall_top_k: int = 10
    rerank_top_k: int = 3
    filters: Dict[str, Any] = Field(default_factory=dict)
    page_num_range: Optional[PageRangeModel] = None


app = FastAPI(title="中文 RAG 知识库", version="0.0.2")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # 开发环境可以写 "*"，生产环境建议写死前端域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 静态文件配置
STATIC_DIR = PROJECT_ROOT / "src" / "static" / "dist"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    logger.info(f"已挂载静态文件目录: {STATIC_DIR}")
else:
    logger.warning(f"静态文件目录不存在: {STATIC_DIR}，请先运行 'cd frontend && npm run build'")

@app.get("/api/config")
def get_config() -> Dict[str, Any]:
    return {
        "valid_domains": VALID_DOMAINS,
        "supported_extensions": sorted(ext.lstrip(".") for ext in SUPPORTED_EXTENSIONS),
        "default_recall_top_k": 10,
        "default_rerank_top_k": 3,
        "default_use_reranker": True,
    }


@app.get("/api/kb/manifest")
def get_manifest() -> Dict[str, Any]:
    manifest = load_manifest()
    items = []
    for file_path, info in manifest.items():
        items.append({
            "file_path": file_path,
            "file_name": Path(file_path).name,
            "chunk_count": info.get("chunk_count", 0),
            "processed_at": info.get("processed_at", ""),
            "book_id": info.get("book_id", ""),
            "title": info.get("title", Path(file_path).name),
            "author": info.get("author", "未知作者"),
            "domain": info.get("domain", ""),
        })
    return {
        "total": len(items),
        "items": sorted(items, key=lambda x: x.get("processed_at", ""), reverse=True),
    }


@app.get("/api/notes/manifest")
def get_note_manifest() -> Dict[str, Any]:
    note_manifest = load_note_manifest()
    items = []
    for note_id, info in note_manifest.items():
        items.append({
            "note_id": note_id,
            "book_id": info.get("book_id", ""),
            "note_title": info.get("note_title", ""),
            "chunk_count": info.get("chunk_count", 0),
            "processed_at": info.get("processed_at", ""),
            "title": info.get("title", ""),
            "author": info.get("author", "未知作者"),
            "domain": info.get("domain", ""),
        })
    return {
        "total": len(items),
        "items": sorted(items, key=lambda x: x.get("processed_at", ""), reverse=True),
    }


@app.post("/api/meta/parse")
async def parse_metadata(file: UploadFile = File(...)) -> Dict[str, Any]:
    suffix = Path(file.filename).suffix
    temp_path = RAW_DATA_DIR / f".__tmp_meta__{int(time.time() * 1000)}_{file.filename}"
    content = await file.read()
    temp_path.write_bytes(content)
    try:
        metadata = parse_book_metadata(temp_path)
        return {"file_name": file.filename, "metadata": metadata}
    finally:
        try:
            temp_path.unlink(missing_ok=True)
        except Exception:
            pass


@app.post("/api/kb/build")
async def build_knowledge_base(
    files: list[UploadFile] = File(...),
    metadata_json: str = Form("{}"),
    force_rebuild: bool = Form(False),
) -> Dict[str, Any]:
    try:
        metadata_map = json.loads(metadata_json or "{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"metadata_json 非法: {exc}")

    results = []
    total_chunks = 0

    for uploaded_file in files:
        file_name = uploaded_file.filename
        save_path = RAW_DATA_DIR / file_name
        save_path.write_bytes(await uploaded_file.read())

        manual_meta = metadata_map.get(file_name, {})

        try:
            count = index_file(save_path, force=force_rebuild, manual_metadata=manual_meta)
            total_chunks += count
            results.append({
                "file_name": file_name,
                "success": True,
                "chunk_count": count,
            })
        except Exception as exc:
            logger.error("文件入库失败: %s, error=%s", file_name, exc)
            results.append({
                "file_name": file_name,
                "success": False,
                "error": str(exc),
            })

    return {
        "total_files": len(files),
        "total_chunks": total_chunks,
        "results": results,
    }


@app.post("/api/notes/upload")
def upload_note_text(
    book_id: str = Form(...),
    note_text: str = Form(...),
    note_title: str = Form(""),
) -> Dict[str, Any]:
    target_book_id = (book_id or "").strip()
    if not target_book_id:
        raise HTTPException(status_code=400, detail="book_id 不能为空")
    if not (note_text or "").strip():
        raise HTTPException(status_code=400, detail="笔记内容不能为空")

    source_book_meta: Dict[str, Any] = {}
    for _file_path, info in load_manifest().items():
        if str(info.get("book_id", "")).strip() == target_book_id:
            source_book_meta = info
            break

    try:
        note_id, chunk_count, note_file_path = index_note_text(
            note_text=note_text,
            book_id=target_book_id,
            note_title=note_title,
            source_book_meta=source_book_meta,
        )
    except Exception as exc:
        logger.error("笔记入库失败: book_id=%s, error=%s", target_book_id, exc)
        raise HTTPException(status_code=500, detail=f"笔记入库失败: {exc}")

    return {
        "success": True,
        "note_id": note_id,
        "book_id": target_book_id,
        "note_title": (note_title or "").strip(),
        "chunk_count": chunk_count,
        "file_path": note_file_path,
    }


@app.delete("/api/kb/file")
def remove_file(file_path: str) -> Dict[str, Any]:
    ok = delete_file(file_path)
    if not ok:
        raise HTTPException(status_code=400, detail="删除失败，请检查日志")
    return {"success": True, "file_path": file_path}


@app.delete("/api/notes")
def remove_note(note_id: str) -> Dict[str, Any]:
    ok = delete_note(note_id)
    if not ok:
        raise HTTPException(status_code=400, detail="笔记删除失败，请检查 note_id 或日志")
    return {"success": True, "note_id": note_id}


@app.post("/api/chat")
def chat(req: AskRequest) -> Dict[str, Any]:
    question = req.question.strip()
    session_id = (req.session_id or "").strip() or str(uuid4())
    if not question:
        raise HTTPException(status_code=400, detail="问题不能为空")

    if not load_manifest():
        return {
            "answer": "⚠️ 知识库为空，请先上传文档并构建知识库。",
            "sources": [],
            "session_id": session_id,
        }

    filters = {k: v for k, v in req.filters.items() if str(v).strip()}
    page_range: Optional[Tuple[int, int]] = None
    if req.page_num_range:
        min_page = req.page_num_range.min_page
        max_page = req.page_num_range.max_page
        if min_page > max_page:
            raise HTTPException(status_code=400, detail="页码范围非法：起始页不能大于结束页")
        page_range = (min_page, max_page)

    try:
        result = ask(
            question=question,
            session_id=session_id,
            use_reranker=req.use_reranker,
            recall_top_k=req.recall_top_k,
            rerank_top_k=req.rerank_top_k,
            filters=filters,
            page_num_range=page_range,
        )
    except Exception as exc:
        logger.error("问答失败: %s", exc)
        raise HTTPException(status_code=500, detail=f"问答过程出错: {exc}")

    source_docs = result.get("source_documents", [])
    sources = []
    for doc in source_docs:
        meta = doc.metadata
        sources.append({
            "file_name": meta.get("file_name", "未知文件"),
            "book_id": meta.get("book_id", ""),
            "title": meta.get("title", meta.get("file_name", "未知书籍")),
            "author": meta.get("author", "未知作者"),
            "domain": meta.get("domain", ""),
            "source_type": meta.get("source_type", "book_content"),
            "note_id": meta.get("note_id", ""),
            "note_title": meta.get("note_title", ""),
            "preview": doc.page_content[:200] + "..." if len(doc.page_content) > 200 else doc.page_content,
            "chunk_index": meta.get("chunk_index", 0),
            "page_num": meta.get("page_num"),
            "chapter_title": meta.get("chapter_title"),
        })

    return {
        "answer": result.get("answer", ""),
        "sources": sources,
        "session_id": result.get("session_id", session_id),
    }


@app.get("/api/chat/history")
def get_chat_history(session_id: str) -> Dict[str, Any]:
    normalized_session_id = (session_id or "").strip()
    if not normalized_session_id:
        return {"session_id": "", "messages": []}
    return {
        "session_id": normalized_session_id,
        "messages": get_session_messages(normalized_session_id),
    }


@app.delete("/api/chat/history")
def delete_chat_history(session_id: str) -> Dict[str, Any]:
    normalized_session_id = (session_id or "").strip()
    if not normalized_session_id:
        raise HTTPException(status_code=400, detail="session_id 不能为空")
    clear_session_history(normalized_session_id)
    return {"success": True, "session_id": normalized_session_id}


# 根路由：返回前端页面
@app.get("/")
def read_root():
    """返回前端 index.html"""
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    else:
        raise HTTPException(
            status_code=404,
            detail="前端文件不存在，请先运行 'cd frontend && npm run build'"
        )
