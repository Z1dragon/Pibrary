"""
问答链模块
适配智谱 AI GLM API（兼容 OpenAI 接口），组装 RAG 全链路。
内置防幻觉 Prompt 模板，确保回答严格基于检索到的文档内容。
"""

from typing import List, Optional

from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from langchain_openai import ChatOpenAI

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import (
    GLM_API_KEY,
    GLM_API_BASE,
    GLM_MODEL_NAME,
    GLM_TEMPERATURE,
    GLM_MAX_TOKENS,
)


# ========================================================
# 防幻觉 RAG Prompt 模板
# ========================================================

RAG_SYSTEM_PROMPT = """你是一个专业的**个人结构化阅读知识库智能助手**，专门帮助用户管理和回顾已阅读的书籍内容。请严格基于下方提供的【参考文档片段】及对应的【书籍元数据】，准确、清晰地回答用户问题。

---

## 核心回答规则
### 1. 内容准确性（最高优先级）
- **严格基于参考资料**：所有回答必须100%来自【参考文档片段】，不得编造、引申文档外的信息，不得依赖模型自身的通识知识（除非明确说明）。
- **若资料不足**：如果参考文档中没有足够信息回答问题，请直接告知：「根据现有知识库中的书籍内容，无法回答该问题。你可以尝试补充相关书籍或调整提问范围。」

### 2. 结构化呈现（利用书籍元数据）
- **来源精准标注**：在回答的关键事实、观点、数据后，**必须使用元数据标注来源**，格式为：
  - 有明确章节：`[《书名》- 章节名]`
  - 仅页码信息：`[《书名》第X页]`
  - 示例：`RAG的核心流程包括检索和生成两个阶段[《深度学习实战》- 第10章 RAG技术]`
- **结构清晰组织**：优先使用 Markdown 列表、分点呈现答案；若参考文档有明确章节逻辑，可按章节顺序组织回答。

### 3. 语言与内容要求
- **语言自然专业**：用通俗易懂的中文重新组织表述，避免生硬摘抄原文，但要保留专业术语的准确性。
- **综合相关信息**：如果多个参考文档片段（来自同一本书的不同章节/页码）包含相关信息，请将它们综合整理，不要遗漏重要细节。
- **避免无关内容**：不回答与参考书籍无关的闲聊，不主动扩展文档外的知识。

---

## 【参考文档片段】（含书籍元数据）
{context}

---

"""

RAG_HUMAN_PROMPT = "{question}"


_rag_prompt = ChatPromptTemplate.from_messages([
    ("system", RAG_SYSTEM_PROMPT),
    ("human", RAG_HUMAN_PROMPT),
])


# ========================================================
# LLM 实例
# ========================================================

_llm_instance: Optional[ChatOpenAI] = None


def get_llm() -> ChatOpenAI:
    """获取 GLM 大语言模型实例（兼容 OpenAI 接口）。"""
    global _llm_instance
    if _llm_instance is None:
        _llm_instance = ChatOpenAI(
            model=GLM_MODEL_NAME,
            openai_api_key=GLM_API_KEY,
            openai_api_base=GLM_API_BASE,
            temperature=GLM_TEMPERATURE,
            max_tokens=GLM_MAX_TOKENS,
        )
        print(f"✓ LLM 已初始化: {GLM_MODEL_NAME}")
    return _llm_instance


# ========================================================
# 格式化检索文档
# ========================================================

def format_docs(docs: List[Document]) -> str:
    """
    将检索到的文档格式化为 Prompt 可用的上下文文本。
    包含来源元信息，方便溯源。
    """
    if not docs:
        return "（未找到相关文档）"

    formatted_parts = []
    for i, doc in enumerate(docs, start=1):
        meta = doc.metadata
        source_info_parts = []

        # 文件名
        file_name = meta.get("file_name", "未知文件")
        source_info_parts.append(f"来源: {file_name}")

        # 页码（PDF）
        if "page" in meta:
            source_info_parts.append(f"第{meta['page']}页")

        # 章节（EPUB）
        if "chapter" in meta:
            source_info_parts.append(f"第{meta['chapter']}章")

        # 切片索引
        if "chunk_index" in meta:
            source_info_parts.append(f"片段{meta['chunk_index'] + 1}")

        source_line = " | ".join(source_info_parts)
        formatted_parts.append(
            f"---\n[文档{i}] {source_line}\n{doc.page_content}\n"
        )

    return "\n".join(formatted_parts)


# ========================================================
# RAG 问答链
# ========================================================

def create_rag_chain():
    """
    创建 RAG 问答链。
    检索 → 格式化文档 → 填充 Prompt → LLM 生成 → 输出解析

    Returns:
        可调用的 RAG 链
    """
    llm = get_llm()

    chain = (
        _rag_prompt
        | llm
        | StrOutputParser()
    )
    return chain


def ask(
    question: str,
    use_reranker: bool = True,
    recall_top_k: int | None = None,
    rerank_top_k: int | None = None,
) -> dict:
    """
    RAG 问答入口函数。

    Args:
        question: 用户问题
        use_reranker: 是否使用重排序
        recall_top_k: 向量召回数量
        rerank_top_k: 重排后返回数量

    Returns:
        {
            "answer": str,        # 模型回答
            "source_documents": List[Document],  # 参考文档
            "context": str,       # 格式化后的上下文
        }
    """
    from src.retriever import retrieve

    # 检索相关文档
    docs = retrieve(
        query=question,
        recall_top_k=recall_top_k,
        rerank_top_k=rerank_top_k,
        use_reranker=use_reranker,
    )

    # 格式化上下文
    context = format_docs(docs)

    # 构建问答链并执行
    print(f"📡 正在向 {GLM_MODEL_NAME} 发送请求，检索到 {len(docs)} 个相关文档...")
    chain = create_rag_chain()
    answer = chain.invoke({
        "context": context,
        "question": question,
    })

    return {
        "answer": answer,
        "source_documents": docs,
        "context": context,
    }
