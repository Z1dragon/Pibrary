"""
全局配置管理模块
统一读取 .env 环境变量，所有参数不得硬编码。
"""

import os
from pathlib import Path
from typing import List
from dotenv import load_dotenv

# ---------- 加载 .env ----------
PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env")


# ========================================================
# 辅助函数
# ========================================================

def _get_env(key: str, default: str | None = None, required: bool = False) -> str:
    """安全读取环境变量，缺失时按策略处理。"""
    value = os.getenv(key, default)
    if required and not value:
        raise EnvironmentError(f"必需的环境变量 '{key}' 未设置，请检查 .env 文件。")
    return value or ""


def _get_int(key: str, default: int) -> int:
    raw = _get_env(key, str(default))
    return int(raw)


def _get_float(key: str, default: float) -> float:
    raw = _get_env(key, str(default))
    return float(raw)


def _get_bool(key: str, default: bool) -> bool:
    raw = _get_env(key, str(default)).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _get_list(key: str, default: List[str]) -> List[str]:
    raw = _get_env(key, ",".join(default)).strip()
    if not raw:
        return default
    return [item.strip() for item in raw.split(",") if item.strip()]


# ========================================================
# 智谱 AI GLM 大语言模型
# ========================================================

GLM_API_KEY: str = _get_env("GLM_API_KEY", "test-key-for-ci")
GLM_MODEL_NAME: str = _get_env("GLM_MODEL_NAME", "glm-5")
GLM_API_BASE: str = _get_env("GLM_API_BASE", "https://open.bigmodel.cn/api/paas/v4")
GLM_TEMPERATURE: float = _get_float("GLM_TEMPERATURE", 0.1)
GLM_MAX_TOKENS: int = _get_int("GLM_MAX_TOKENS", 64000)


# ========================================================
# Milvus 向量数据库
# ========================================================

MILVUS_HOST: str = _get_env("MILVUS_HOST", "localhost")
MILVUS_PORT: int = _get_int("MILVUS_PORT", 19530)
MILVUS_COLLECTION_NAME: str = _get_env("MILVUS_COLLECTION_NAME", "rag_knowledge_base")
MILVUS_USER: str = _get_env("MILVUS_USER", "")
MILVUS_PASSWORD: str = _get_env("MILVUS_PASSWORD", "")
MILVUS_URI: str = f"http://{MILVUS_HOST}:{MILVUS_PORT}"


# ========================================================
# Embedding 向量化模型
# ========================================================

EMBEDDING_MODEL_NAME: str = _get_env("EMBEDDING_MODEL_NAME", "models/bge-small-zh-v1.5")
EMBEDDING_DEVICE: str = _get_env("EMBEDDING_DEVICE", "mps")
EMBEDDING_DIMENSION: int = _get_int("EMBEDDING_DIMENSION", 512)


# ========================================================
# Reranker 重排序模型
# ========================================================

RERANKER_MODEL_NAME: str = _get_env("RERANKER_MODEL_NAME", "models/bge-reranker-base")
RERANKER_TOP_K: int = _get_int("RERANKER_TOP_K", 3)


# ========================================================
# 文档处理
# ========================================================

CHUNK_SIZE: int = _get_int("CHUNK_SIZE", 500)
CHUNK_OVERLAP: int = _get_int("CHUNK_OVERLAP", 100)

# 书籍场景切分参数（本次优化重点）
BOOK_MD_EPUB_CHUNK_SIZE: int = _get_int("BOOK_MD_EPUB_CHUNK_SIZE", 1000)
BOOK_MD_EPUB_CHUNK_OVERLAP: int = _get_int("BOOK_MD_EPUB_CHUNK_OVERLAP", 150)
BOOK_PDF_CHUNK_SIZE: int = _get_int("BOOK_PDF_CHUNK_SIZE", 1000)
BOOK_PDF_CHUNK_OVERLAP: int = _get_int("BOOK_PDF_CHUNK_OVERLAP", 100)
BOOK_TXT_CHUNK_SIZE: int = _get_int("BOOK_TXT_CHUNK_SIZE", 500)
BOOK_TXT_CHUNK_OVERLAP: int = _get_int("BOOK_TXT_CHUNK_OVERLAP", 100)

# 书籍结构化元数据
DEFAULT_BOOK_DOMAIN: str = _get_env("DEFAULT_BOOK_DOMAIN", "computer_science")

RAW_DATA_DIR: Path = PROJECT_ROOT / _get_env("RAW_DATA_DIR", "data/raw")
PROCESSED_DATA_DIR: Path = PROJECT_ROOT / _get_env("PROCESSED_DATA_DIR", "data/processed")
NOTE_UPLOAD_DIR: Path = PROJECT_ROOT / _get_env("NOTE_UPLOAD_DIR", "data/notes")
NOTE_PAYLOAD_TYPE: str = _get_env("NOTE_PAYLOAD_TYPE", "personal_note")

# 书籍内容 payload 类型（固定）
BOOK_PAYLOAD_TYPE: str = _get_env("BOOK_PAYLOAD_TYPE", "book_content")


# ========================================================
# 检索配置
# ========================================================

RETRIEVER_TOP_K: int = _get_int("RETRIEVER_TOP_K", 10)
SIMILARITY_THRESHOLD: float = _get_float("SIMILARITY_THRESHOLD", 0.3)

# 可选领域与分区（后期优化预留）
VALID_DOMAINS: List[str] = _get_list(
    "VALID_DOMAINS",
    ["computer_science", "literature", "history", "philosophy"],
)
ENABLE_PARTITION: bool = _get_bool("ENABLE_PARTITION", False)

# Schema 迁移策略（用于从旧集合升级到支持结构化元数据的集合）
# 默认开启：检测到旧集合未启用动态字段时自动重建集合。
AUTO_MIGRATE_MILVUS_SCHEMA: bool = _get_bool("AUTO_MIGRATE_MILVUS_SCHEMA", True)

# 若关闭自动迁移，则仅保留旧字段写入，避免插入报错（会损失部分结构化元数据）。
STRICT_BOOK_METADATA_WRITE: bool = _get_bool("STRICT_BOOK_METADATA_WRITE", True)


# ========================================================
# 日志配置
# ========================================================

LOG_LEVEL: str = _get_env("LOG_LEVEL", "INFO")


# ========================================================
# 确保数据目录存在
# ========================================================

RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)
NOTE_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
