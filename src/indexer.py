"""
向量化与索引模块（书籍结构化增强版）

核心职责：
1) 文档增量索引（哈希校验）
2) 书籍结构化元数据写入 Milvus Payload
3) 预留分区路由与个人笔记扩展位

简历亮点可描述：
- 设计增量更新+结构化元数据索引链路，支持可追溯检索和工程级扩展。
"""

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from langchain_core.documents import Document
from langchain_community.embeddings import HuggingFaceBgeEmbeddings
from langchain_milvus import Milvus

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import (
    AUTO_MIGRATE_MILVUS_SCHEMA,
    EMBEDDING_MODEL_NAME,
    EMBEDDING_DEVICE,
    ENABLE_PARTITION,
    LOG_LEVEL,
    MILVUS_COLLECTION_NAME,
    NOTE_UPLOAD_DIR,
    MILVUS_PASSWORD,
    MILVUS_URI,
    MILVUS_USER,
    NOTE_PAYLOAD_TYPE,
    PROCESSED_DATA_DIR,
    STRICT_BOOK_METADATA_WRITE,
)


if not logging.getLogger().handlers:
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
logger = logging.getLogger(__name__)


# ========================================================
# Embedding 模型单例
# ========================================================

_embedding_instance: Optional[HuggingFaceBgeEmbeddings] = None


def get_embedding_model() -> HuggingFaceBgeEmbeddings:
    """获取 Embedding 模型单例（首次调用时下载/加载模型）。"""
    global _embedding_instance
    if _embedding_instance is None:
        model_kwargs = {"device": EMBEDDING_DEVICE}
        encode_kwargs = {"normalize_embeddings": True}  # BGE 推荐归一化
        _embedding_instance = HuggingFaceBgeEmbeddings(
            model_name=EMBEDDING_MODEL_NAME,
            model_kwargs=model_kwargs,
            encode_kwargs=encode_kwargs,
            query_instruction="为这个句子生成表示以用于检索相关文章：",
        )
        logger.info("Embedding 模型已加载: %s (设备: %s)", EMBEDDING_MODEL_NAME, EMBEDDING_DEVICE)
    return _embedding_instance


# ========================================================
# Milvus 向量存储
# ========================================================

_vectorstore_instance: Optional[Milvus] = None


def _reset_vectorstore_instance() -> None:
    """重置向量存储单例（用于 schema 迁移后重建连接）。"""
    global _vectorstore_instance
    _vectorstore_instance = None


def _get_collection_schema_info(collection_name: str) -> tuple[bool, set[str], bool]:
    """获取集合是否存在、字段名集合、是否启用动态字段。"""
    from pymilvus import Collection, utility

    _ensure_milvus_connection()
    if not utility.has_collection(collection_name):
        return False, set(), False

    col = Collection(collection_name)
    schema = col.schema
    field_names = {field.name for field in schema.fields}
    dynamic_enabled = bool(getattr(schema, "enable_dynamic_field", False))
    return True, field_names, dynamic_enabled


def _migrate_collection_to_dynamic(collection_name: str) -> None:
    """将旧集合迁移为动态字段集合（直接重建）。"""
    logger.warning(
        "检测到集合 %s 未启用动态字段，将执行自动重建以支持结构化元数据写入。",
        collection_name,
    )
    logger.warning("重建集合会清空该集合已有向量，请确保可接受后再继续。")

    embedding = get_embedding_model()
    connection_args = {"uri": MILVUS_URI}
    if MILVUS_USER:
        connection_args["user"] = MILVUS_USER
    if MILVUS_PASSWORD:
        connection_args["password"] = MILVUS_PASSWORD

    Milvus(
        embedding_function=embedding,
        collection_name=collection_name,
        connection_args=connection_args,
        auto_id=True,
        drop_old=True,
        enable_dynamic_field=True,
    )
    logger.info("集合重建完成: %s（动态字段已启用）", collection_name)


def get_vectorstore(
    collection_name: str | None = None,
) -> Milvus:
    """
    获取 Milvus 向量存储实例。

    Args:
        collection_name: 集合名称，默认使用配置值

    Returns:
        Milvus 向量存储实例
    """
    global _vectorstore_instance
    target_collection = collection_name or MILVUS_COLLECTION_NAME

    exists, _field_names, dynamic_enabled = _get_collection_schema_info(target_collection)
    if exists and not dynamic_enabled and AUTO_MIGRATE_MILVUS_SCHEMA:
        _reset_vectorstore_instance()
        _migrate_collection_to_dynamic(target_collection)

    if _vectorstore_instance is None:
        embedding = get_embedding_model()
        connection_args = {"uri": MILVUS_URI}
        if MILVUS_USER:
            connection_args["user"] = MILVUS_USER
        if MILVUS_PASSWORD:
            connection_args["password"] = MILVUS_PASSWORD

        _vectorstore_instance = Milvus(
            embedding_function=embedding,
            collection_name=target_collection,
            connection_args=connection_args,
            auto_id=True,
            drop_old=False,
            enable_dynamic_field=True,
        )
        logger.info("Milvus 向量存储已连接: %s / %s", MILVUS_URI, target_collection)
    return _vectorstore_instance


def _ensure_milvus_connection() -> None:
    """确保已建立 pymilvus 连接（用于原生删除等操作）。"""
    from pymilvus import connections

    if connections.has_connection("default"):
        return

    connection_args = {"uri": MILVUS_URI}
    if MILVUS_USER:
        connection_args["user"] = MILVUS_USER
    if MILVUS_PASSWORD:
        connection_args["password"] = MILVUS_PASSWORD

    connections.connect(**connection_args)


def create_milvus_partitions() -> None:
    """
    预留接口：创建 Milvus 分区。

    后期优化方向：
    - 按 domain 创建分区，提升跨领域检索效率。

    当前不启用原因：
    - 当前数据量较小，Payload 过滤足够，分区收益不明显。
    """
    logger.info("create_milvus_partitions() 已预留，当前未启用。ENABLE_PARTITION=%s", ENABLE_PARTITION)


# ========================================================
# 增量更新机制
# ========================================================

def _compute_file_hash(file_path: str | Path) -> str:
    """计算文件内容的 MD5 哈希值，用于增量更新校验。"""
    hasher = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _get_processed_manifest_path() -> Path:
    """返回已处理文档清单文件路径。"""
    return PROCESSED_DATA_DIR / "manifest.json"


def _get_note_manifest_path() -> Path:
    """返回个人笔记清单文件路径。"""
    return PROCESSED_DATA_DIR / "notes_manifest.json"


def load_manifest() -> dict:
    """加载已处理文档清单。"""
    manifest_path = _get_processed_manifest_path()
    if manifest_path.exists():
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    return {}


def save_manifest(manifest: dict) -> None:
    """保存已处理文档清单。"""
    manifest_path = _get_processed_manifest_path()
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_note_manifest() -> dict:
    """加载个人笔记清单。"""
    manifest_path = _get_note_manifest_path()
    if manifest_path.exists():
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    return {}


def save_note_manifest(manifest: dict) -> None:
    """保存个人笔记清单。"""
    manifest_path = _get_note_manifest_path()
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def is_file_processed(file_path: str | Path) -> bool:
    """检查文件是否已被处理过（基于文件哈希比较）。"""
    file_path = str(Path(file_path).resolve())
    manifest = load_manifest()
    if file_path not in manifest:
        return False
    recorded_hash = manifest[file_path].get("hash", "")
    current_hash = _compute_file_hash(file_path)
    return recorded_hash == current_hash


def mark_file_processed(file_path: str | Path, chunk_count: int) -> None:
    """标记文件为已处理。"""
    file_path_str = str(Path(file_path).resolve())
    manifest = load_manifest()
    manifest[file_path_str] = {
        "hash": _compute_file_hash(file_path_str),
        "chunk_count": chunk_count,
        "processed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    save_manifest(manifest)


def mark_file_processed_with_meta(file_path: str | Path, chunk_count: int, book_meta: Dict[str, Any]) -> None:
    """标记文件为已处理（增强版：附带书籍关键元数据）。"""
    file_path_str = str(Path(file_path).resolve())
    manifest = load_manifest()
    manifest[file_path_str] = {
        "hash": _compute_file_hash(file_path_str),
        "chunk_count": chunk_count,
        "processed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "book_id": book_meta.get("book_id", ""),
        "title": book_meta.get("title", ""),
        "author": book_meta.get("author", ""),
        "domain": book_meta.get("domain", ""),
    }
    save_manifest(manifest)


# ========================================================
# 索引操作
# ========================================================

def index_documents(
    documents: List[Document],
    batch_size: int = 100,
) -> int:
    """
    将文档切片批量写入 Milvus 向量数据库。

    Args:
        documents: 切分后的 Document 列表
        batch_size: 每批写入数量

    Returns:
        成功写入的文档数量
    """
    if not documents:
        logger.info("没有文档需要索引。")
        return 0

    vectorstore = get_vectorstore()
    total = len(documents)
    indexed = 0

    exists, field_names, dynamic_enabled = _get_collection_schema_info(vectorstore.collection_name)
    if exists and not dynamic_enabled:
        unknown_keys = set(documents[0].metadata.keys()) - field_names
        if unknown_keys:
            if STRICT_BOOK_METADATA_WRITE and not AUTO_MIGRATE_MILVUS_SCHEMA:
                raise RuntimeError(
                    "当前 Milvus 集合不支持动态字段，且检测到新元数据字段："
                    f"{sorted(unknown_keys)}。"
                    "请开启 AUTO_MIGRATE_MILVUS_SCHEMA=true 或重建集合。"
                )

            logger.warning(
                "集合未启用动态字段，且关闭自动迁移；将丢弃以下字段后写入：%s",
                sorted(unknown_keys),
            )
            for doc in documents:
                safe_meta = {k: v for k, v in doc.metadata.items() if k in field_names}
                doc.metadata = safe_meta

    # 预留：后续按 source_type 分流书籍内容和个人笔记
    # 当前不启用原因：笔记链路尚未接入，先保证书籍链路稳定。
    source_type = str(documents[0].metadata.get("source_type", "book_content"))
    if source_type == NOTE_PAYLOAD_TYPE:
        logger.info("检测到笔记内容（预留分支），当前仍按统一索引流程处理。")

    if ENABLE_PARTITION:
        # 后期优化方向：根据 domain 路由 partition_name。
        # 当前不启用原因：数据量小，过滤收益高于分区维护成本。
        logger.info("ENABLE_PARTITION=True（预留逻辑），当前 langchain_milvus 流程未启用分区写入。")

    for i in range(0, total, batch_size):
        batch = documents[i : i + batch_size]
        vectorstore.add_documents(batch)
        indexed += len(batch)
        logger.info("索引进度: %s/%s", indexed, total)

    logger.info("索引完成，共写入 %s 个文档切片。", indexed)
    return indexed


def index_file(
    file_path: str | Path,
    force: bool = False,
    manual_metadata: Optional[Dict[str, Any]] = None,
) -> int:
    """
    单文件索引入口：加载 → 切分 → 向量化 → 写入 Milvus。

    Args:
        file_path: 文件路径
        force: 是否强制重新索引（忽略增量校验）

    Returns:
        写入的切片数量
    """
    from src.data_loader import parse_book_metadata
    from src.text_splitter import BookAwareTextSplitter

    file_path = Path(file_path)

    # 增量检查
    if not force and is_file_processed(file_path):
        logger.info("跳过（已处理）: %s", file_path.name)
        return 0

    if force:
        # 强制重建单文件：先删后写，避免重复向量
        delete_file(file_path)

    book_meta = parse_book_metadata(file_path, manual_overrides=manual_metadata)
    splitter = BookAwareTextSplitter()
    chunks = splitter.split_by_format(
        file_path=str(file_path),
        file_type=str(book_meta.get("file_type", file_path.suffix.lstrip("."))),
        metadata=book_meta,
    )

    if not chunks:
        logger.info("空文档或无法切分: %s", file_path.name)
        return 0

    logger.info("文件切分完成: %s, 切片=%s", file_path.name, len(chunks))

    # 索引
    count = index_documents(chunks)

    # 标记已处理
    mark_file_processed_with_meta(file_path, count, book_meta)

    return count


def index_directory(
    dir_path: str | Path,
    force: bool = False,
) -> int:
    """
    批量索引指定目录下所有支持格式的文档。

    Args:
        dir_path: 目录路径
        force: 是否强制重新索引

    Returns:
        总共写入的切片数量
    """
    from src.data_loader import SUPPORTED_EXTENSIONS

    dir_path = Path(dir_path)
    if not dir_path.is_dir():
        raise FileNotFoundError(f"目录不存在: {dir_path}")

    total = 0
    for fp in sorted(dir_path.rglob("*")):
        if fp.is_file() and fp.suffix.lower() in SUPPORTED_EXTENSIONS:
            count = index_file(fp, force=force)
            total += count

    logger.info("目录索引完成，共写入 %s 个文档切片。", total)
    return total


def index_note_text(
    note_text: str,
    book_id: str,
    note_title: str = "",
    source_book_meta: Optional[Dict[str, Any]] = None,
) -> tuple[str, int, str]:
    """
    将用户上传的个人笔记文本入库，并与书籍 book_id 关联。

    Returns:
        (note_id, chunk_count, note_file_path)
    """
    content = (note_text or "").strip()
    target_book_id = (book_id or "").strip()
    if not target_book_id:
        raise ValueError("book_id 不能为空")
    if not content:
        raise ValueError("笔记内容不能为空")

    from src.text_splitter import split_documents

    now_ms = int(time.time() * 1000)
    note_id = f"note_{target_book_id}_{now_ms}"
    safe_title = (note_title or "").strip() or f"{target_book_id} 的阅读笔记"
    note_file_name = f"{note_id}.txt"
    note_file_path = NOTE_UPLOAD_DIR / note_file_name
    note_file_path.write_text(content, encoding="utf-8")

    book_meta = source_book_meta or {}
    base_meta = {
        "source": str(note_file_path.resolve()),
        "file_name": note_file_name,
        "file_type": "txt",
        "source_type": NOTE_PAYLOAD_TYPE,
        "note_id": note_id,
        "book_id": target_book_id,
        "title": str(book_meta.get("title", safe_title)),
        "author": str(book_meta.get("author", "未知作者")),
        "domain": str(book_meta.get("domain", "")),
        "note_title": safe_title,
        "chapter_title": "个人笔记",
    }

    seed_doc = Document(page_content=content, metadata=base_meta)
    chunks = split_documents([seed_doc], clean=True)
    for idx, chunk in enumerate(chunks, start=1):
        chunk.metadata["source_type"] = NOTE_PAYLOAD_TYPE
        chunk.metadata["note_id"] = note_id
        chunk.metadata["book_id"] = target_book_id
        chunk.metadata["note_title"] = safe_title
        chunk.metadata["chunk_id"] = f"{note_id}_chunk_{idx:06d}"

    chunk_count = index_documents(chunks)

    note_manifest = load_note_manifest()
    note_manifest[note_id] = {
        "note_id": note_id,
        "book_id": target_book_id,
        "note_title": safe_title,
        "file_path": str(note_file_path.resolve()),
        "chunk_count": chunk_count,
        "processed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "title": str(book_meta.get("title", "")),
        "author": str(book_meta.get("author", "未知作者")),
        "domain": str(book_meta.get("domain", "")),
    }
    save_note_manifest(note_manifest)

    logger.info("笔记入库完成: note_id=%s, book_id=%s, chunks=%s", note_id, target_book_id, chunk_count)
    return note_id, chunk_count, str(note_file_path.resolve())


# ========================================================
# 删除操作
# ========================================================

def delete_file(file_path: str | Path) -> bool:
    """
    从 Milvus 和清单中删除指定文件的所有切片。

    Args:
        file_path: 文件路径（需与索引时一致）

    Returns:
        bool: 是否删除成功
    """
    file_path = str(Path(file_path).resolve())
    
    # 1. 从 Milvus 删除
    try:
        vectorstore = get_vectorstore()
        _ensure_milvus_connection()
        # 获取 underlying pymilvus Collection 对象
        # langchain_milvus.Milvus 实例通常将 collection 存储在 .col 或 .collection 属性中
        # 这里尝试通过 collection_name 重新获取原生 Collection 对象以确保稳健性
        from pymilvus import Collection, utility
        
        col_name = vectorstore.collection_name
        if utility.has_collection(col_name):
            col = Collection(col_name)
            # 构建删除表达式
            expr = f'source == "{file_path}"'
            # 执行删除
            col.delete(expr)
            logger.info("已从 Milvus 删除: %s", file_path)
        else:
            logger.error("集合不存在: %s", col_name)
            return False

    except Exception as e:
        logger.error("Milvus 删除失败: %s", e)
        return False

    # 2. 更新 manifest
    manifest = load_manifest()
    if file_path in manifest:
        del manifest[file_path]
        save_manifest(manifest)
        logger.info("已更新清单，移除: %s", file_path)
    
    return True


def delete_note(note_id: str) -> bool:
    """
    删除个人笔记：从 Milvus 删除对应切片，并更新 notes_manifest 与本地文件。

    Args:
        note_id: 笔记唯一ID

    Returns:
        bool: 是否删除成功
    """
    target_note_id = (note_id or "").strip()
    if not target_note_id:
        return False

    note_manifest = load_note_manifest()
    note_info = note_manifest.get(target_note_id)
    if not note_info:
        logger.error("未找到笔记: %s", target_note_id)
        return False

    # 1) 删除 Milvus 向量
    try:
        vectorstore = get_vectorstore()
        _ensure_milvus_connection()
        from pymilvus import Collection, utility

        col_name = vectorstore.collection_name
        if utility.has_collection(col_name):
            col = Collection(col_name)
            expr = f'note_id == "{target_note_id.replace("\\", "\\\\").replace("\"", "\\\"")}"'
            col.delete(expr)
            logger.info("已从 Milvus 删除笔记向量: note_id=%s", target_note_id)
        else:
            logger.error("集合不存在: %s", col_name)
            return False
    except Exception as exc:
        logger.error("Milvus 删除笔记失败: note_id=%s, error=%s", target_note_id, exc)
        return False

    # 2) 删除本地笔记文件
    file_path = str(note_info.get("file_path", "")).strip()
    if file_path:
        try:
            Path(file_path).unlink(missing_ok=True)
        except Exception as exc:
            logger.warning("删除本地笔记文件失败(可忽略): %s, error=%s", file_path, exc)

    # 3) 更新 notes manifest
    del note_manifest[target_note_id]
    save_note_manifest(note_manifest)
    logger.info("已更新笔记清单并移除: note_id=%s", target_note_id)

    return True
