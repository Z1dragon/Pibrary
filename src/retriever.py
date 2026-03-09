"""
检索模块
实现向量检索 + 重排序两阶段检索架构。
增强能力：支持元数据过滤检索，预留分区检索扩展。
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from langchain_core.documents import Document

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import (
    ENABLE_PARTITION,
    LOG_LEVEL,
    RETRIEVER_TOP_K,
    RERANKER_MODEL_NAME,
    RERANKER_TOP_K,
    SIMILARITY_THRESHOLD,
)


if not logging.getLogger().handlers:
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
logger = logging.getLogger(__name__)


def _escape_expr(value: str) -> str:
    """Milvus 表达式字符串转义。"""
    return value.replace("\\", "\\\\").replace("\"", "\\\"")


def _build_filter_expr(
    filters: Optional[Dict[str, Any]] = None,
    page_num_range: Optional[Tuple[int, int]] = None,
) -> Optional[str]:
    """
    构建 Milvus 过滤表达式。

    支持字段：book_id/title/author/domain/source_type/page_num范围。
    """
    parts: List[str] = []
    filters = filters or {}

    for field in ["book_id", "title", "author", "domain", "source_type"]:
        value = filters.get(field)
        if value:
            parts.append(f'{field} == "{_escape_expr(str(value))}"')

    if page_num_range:
        low, high = page_num_range
        parts.append(f"page_num >= {int(low)}")
        parts.append(f"page_num <= {int(high)}")

    if not parts:
        return None
    return " and ".join(parts)


def _prune_filters_by_collection_schema(filters: Optional[Dict[str, Any]], page_num_range: Optional[Tuple[int, int]]) -> tuple[Optional[Dict[str, Any]], Optional[Tuple[int, int]]]:
    """按集合 schema 裁剪过滤条件，避免旧集合字段不存在导致查询失败。"""
    from src.indexer import get_vectorstore, _get_collection_schema_info

    safe_filters: Dict[str, Any] = dict(filters or {})
    safe_range = page_num_range

    vectorstore = get_vectorstore()
    exists, field_names, _dynamic_enabled = _get_collection_schema_info(vectorstore.collection_name)
    if not exists:
        return safe_filters, safe_range

    for key in list(safe_filters.keys()):
        if key not in field_names:
            logger.warning("过滤字段 %s 不在当前集合 schema 中，已自动忽略。", key)
            safe_filters.pop(key)

    if safe_range and "page_num" not in field_names:
        logger.warning("page_num 不在当前集合 schema 中，页码范围过滤已自动忽略。")
        safe_range = None

    return safe_filters, safe_range


# ========================================================
# 第一阶段：向量检索（召回）
# ========================================================

def vector_search(
    query: str,
    top_k: int | None = None,
    filters: Optional[Dict[str, Any]] = None,
    page_num_range: Optional[Tuple[int, int]] = None,
) -> List[Tuple[Document, float]]:
    """
    基于 Milvus 的向量相似度检索。

    Args:
        query: 用户查询文本
        top_k: 召回数量

    Returns:
        [(Document, score), ...] 按相似度降序
    """
    from src.indexer import get_vectorstore

    vectorstore = get_vectorstore()
    k = top_k or RETRIEVER_TOP_K
    filters, page_num_range = _prune_filters_by_collection_schema(filters, page_num_range)
    expr = _build_filter_expr(filters=filters, page_num_range=page_num_range)

    if ENABLE_PARTITION:
        # 预留分区检索逻辑：后续按 domain 动态路由 partition_names。
        # 当前不启用原因：数据规模较小，payload过滤已足够。
        logger.info("ENABLE_PARTITION=True（预留逻辑），当前仍使用 payload 过滤检索。")

    results = vectorstore.similarity_search_with_score(query, k=k, expr=expr)

    # 过滤低分文档
    filtered = [
        (doc, score)
        for doc, score in results
        if score >= SIMILARITY_THRESHOLD
    ]

    logger.info("向量召回完成: query=%s, raw=%s, filtered=%s, expr=%s", query[:50], len(results), len(filtered), expr)

    return filtered


# ========================================================
# 第二阶段：重排序（Rerank）
# ========================================================

_reranker_instance = None


def _get_reranker():
    """懒加载重排序模型单例。"""
    global _reranker_instance
    if _reranker_instance is None:
        try:
            from sentence_transformers import CrossEncoder
            _reranker_instance = CrossEncoder(
                RERANKER_MODEL_NAME,
                max_length=512,
            )
            logger.info("重排序模型已加载: %s", RERANKER_MODEL_NAME)
        except Exception as e:
            logger.error("重排序模型加载失败: %s，将跳过重排序阶段。", e)
            _reranker_instance = None
    return _reranker_instance


def rerank(
    query: str,
    documents: List[Document],
    top_k: int | None = None,
) -> List[Tuple[Document, float]]:
    """
    使用 CrossEncoder 对候选文档进行重排序。

    Args:
        query: 用户查询
        documents: 候选文档列表
        top_k: 重排后返回的文档数量

    Returns:
        [(Document, rerank_score), ...] 按重排分数降序
    """
    if not documents:
        return []

    reranker = _get_reranker()
    k = top_k or RERANKER_TOP_K

    if reranker is None:
        # 重排序模型不可用，直接截取前 K 个
        return [(doc, 0.0) for doc in documents[:k]]

    # 构建 query-doc 对
    pairs = [(query, doc.page_content) for doc in documents]
    scores = reranker.predict(pairs)

    # 按分数降序排列
    scored_docs = list(zip(documents, scores))
    scored_docs.sort(key=lambda x: x[1], reverse=True)

    return scored_docs[:k]


# ========================================================
# 两阶段检索入口
# ========================================================

def retrieve(
    query: str,
    recall_top_k: int | None = None,
    rerank_top_k: int | None = None,
    use_reranker: bool = True,
    filters: Optional[Dict[str, Any]] = None,
    page_num_range: Optional[Tuple[int, int]] = None,
) -> List[Document]:
    """
    两阶段检索：向量召回 → 重排序精排。

    Args:
        query: 用户查询
        recall_top_k: 向量召回数量
        rerank_top_k: 重排后返回数量
        use_reranker: 是否启用重排序

    Returns:
        最终检索到的 Document 列表
    """
    # 第一阶段：向量召回
    recall_results = vector_search(
        query,
        top_k=recall_top_k,
        filters=filters,
        page_num_range=page_num_range,
    )
    if not recall_results:
        return []

    candidates = [doc for doc, _score in recall_results]

    if use_reranker:
        # 第二阶段：重排序
        reranked = rerank(query, candidates, top_k=rerank_top_k)
        logger.info("重排序完成: candidates=%s, top=%s", len(candidates), len(reranked))
        return [doc for doc, _score in reranked]
    else:
        k = rerank_top_k or RERANKER_TOP_K
        logger.info("跳过重排序: candidates=%s, top=%s", len(candidates), k)
        return candidates[:k]


# ========================================================
# 预留扩展：混合检索接口
# ========================================================

def hybrid_retrieve(
    query: str,
    recall_top_k: int | None = None,
    rerank_top_k: int | None = None,
    bm25_weight: float = 0.3,
    vector_weight: float = 0.7,
) -> List[Document]:
    """
    混合检索接口（预留）。
    当前仅实现向量检索 + 重排序，后续可集成 BM25 稀疏检索。

    TODO: 集成 Elasticsearch / BM25 稀疏检索
    TODO: 实现 RRF (Reciprocal Rank Fusion) 融合策略

    Args:
        query: 用户查询
        recall_top_k: 召回数量
        rerank_top_k: 最终返回数量
        bm25_weight: BM25 检索权重
        vector_weight: 向量检索权重

    Returns:
        检索到的 Document 列表
    """
    # 当前退化为纯向量检索 + 重排序
    return retrieve(
        query=query,
        recall_top_k=recall_top_k,
        rerank_top_k=rerank_top_k,
        use_reranker=True,
    )
