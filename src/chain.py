"""
问答链模块（结构化书籍RAG）

说明：
- 基于 GLM API + 两阶段检索。
- 强化来源溯源展示（book_id/title/author/domain/page/chapter）。

简历亮点可描述：
- 构建结构化元数据可追溯问答链，支持按书籍维度的精准检索与回答归因。
"""

import logging
import threading
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from langchain_core.documents import Document
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_openai import ChatOpenAI

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import (
    GLM_API_BASE,
    GLM_API_KEY,
    GLM_MAX_TOKENS,
    GLM_MODEL_NAME,
    GLM_TEMPERATURE,
    LOG_LEVEL,
)


if not logging.getLogger().handlers:
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
logger = logging.getLogger(__name__)


RAG_SYSTEM_PROMPT = """你是一个专业的中文书籍知识库助手。请基于【参考文档】回答问题。

回答要求：
1. 严格依据参考文档，不得编造。
2. 优先给出结构化回答（小标题 + 列表）。
3. 对关键事实标注来源，如：[文档1]。
4. 当信息不足时，明确说明“根据现有知识库内容，无法回答该问题”。
5. 若存在冲突信息，先列出冲突点，再给出保守结论。
6. 若参考文档中包含个人笔记（source_type=personal_note），请与书籍内容联合归纳，但优先以书籍原文为准。

溯源要求：
- 在回答末尾添加“来源摘要”，至少包含 book_id、书名、作者、页码或章节；若使用了个人笔记，还需标明 note_id 或 note_title。

# 预留说明（后期优化方向）
# 后续可加入“结合个人阅读笔记（source_type=personal_note）进行联合回答”的规则。
# 当前不启用原因：优先保证书籍主链路稳定与可解释性。

【参考文档】
{context}
"""

RAG_HUMAN_PROMPT = "{question}"


_rag_prompt = ChatPromptTemplate.from_messages([
    ("system", RAG_SYSTEM_PROMPT),
    MessagesPlaceholder(variable_name="chat_history"),
    ("human", RAG_HUMAN_PROMPT),
])

_llm_instance: Optional[ChatOpenAI] = None
_history_lock = threading.Lock()
_max_history_turns = 6
_session_histories: Dict[str, deque[BaseMessage]] = defaultdict(deque)


def _get_chat_history(session_id: str) -> List[BaseMessage]:
    with _history_lock:
        return list(_session_histories[session_id])


def _append_turn(session_id: str, question: str, answer: str) -> None:
    with _history_lock:
        history = _session_histories[session_id]
        history.append(HumanMessage(content=question))
        history.append(AIMessage(content=answer))

        max_messages = _max_history_turns * 2
        while len(history) > max_messages:
            history.popleft()


def get_session_messages(session_id: str) -> List[Dict[str, str]]:
    normalized_session_id = (session_id or "default").strip() or "default"
    with _history_lock:
        history = list(_session_histories[normalized_session_id])

    messages: List[Dict[str, str]] = []
    for message in history:
        role = "assistant"
        if isinstance(message, HumanMessage):
            role = "user"
        messages.append({
            "role": role,
            "content": str(message.content),
        })
    return messages


def clear_session_history(session_id: str) -> None:
    normalized_session_id = (session_id or "default").strip() or "default"
    with _history_lock:
        _session_histories.pop(normalized_session_id, None)


def _build_retrieval_query(question: str, chat_history: List[BaseMessage]) -> str:
    recent_user_question = None
    for message in reversed(chat_history):
        if isinstance(message, HumanMessage):
            recent_user_question = str(message.content).strip()
            break

    if recent_user_question:
        return f"上一轮问题：{recent_user_question}\n当前问题：{question}"
    return question


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
        logger.info(
            "LLM 已初始化: model=%s, api_base=%s, temperature=%s, max_tokens=%s",
            GLM_MODEL_NAME,
            GLM_API_BASE,
            GLM_TEMPERATURE,
            GLM_MAX_TOKENS,
        )
    return _llm_instance


def format_docs(docs: List[Document]) -> str:
    """将检索文档格式化为 Prompt 上下文。"""
    if not docs:
        return "（未找到相关文档）"

    formatted_parts: List[str] = []
    for i, doc in enumerate(docs, start=1):
        meta = doc.metadata
        source_line = (
            f"book_id={meta.get('book_id', '')} | "
            f"title={meta.get('title', meta.get('file_name', '未知'))} | "
            f"author={meta.get('author', '未知作者')} | "
            f"domain={meta.get('domain', '')} | "
            f"source_type={meta.get('source_type', 'book_content')} | "
            f"note_id={meta.get('note_id', '')} | "
            f"note_title={meta.get('note_title', '')} | "
            f"page_num={meta.get('page_num', 0)} | "
            f"chapter_title={meta.get('chapter_title', '')} | "
            f"chunk_id={meta.get('chunk_id', '')}"
        )
        formatted_parts.append(f"---\n[文档{i}] {source_line}\n{doc.page_content}\n")
    return "\n".join(formatted_parts)


def create_rag_chain():
    """创建 RAG 问答链。"""
    llm = get_llm()
    return _rag_prompt | llm | StrOutputParser()


def ask(
    question: str,
    use_reranker: bool = True,
    recall_top_k: Optional[int] = None,
    rerank_top_k: Optional[int] = None,
    filters: Optional[Dict[str, Any]] = None,
    page_num_range: Optional[Tuple[int, int]] = None,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    """RAG 问答入口。"""
    from src.retriever import retrieve

    normalized_session_id = (session_id or "default").strip() or "default"
    chat_history = _get_chat_history(normalized_session_id)
    retrieval_query = _build_retrieval_query(question, chat_history)

    docs = retrieve(
        query=retrieval_query,
        recall_top_k=recall_top_k,
        rerank_top_k=rerank_top_k,
        use_reranker=use_reranker,
        filters=filters,
        page_num_range=page_num_range,
    )
    context = format_docs(docs)

    logger.info(
        "向 LLM 发送请求: model=%s, docs=%s, prompt_chars=%s, session_id=%s",
        GLM_MODEL_NAME,
        len(docs),
        len(context) + len(question),
        normalized_session_id,
    )
    chain = create_rag_chain()
    answer = chain.invoke({
        "context": context,
        "question": question,
        "chat_history": chat_history,
    })
    _append_turn(normalized_session_id, question, answer)

    logger.info("LLM 返回完成: answer_chars=%s", len(answer))

    return {
        "answer": answer,
        "source_documents": docs,
        "context": context,
        "session_id": normalized_session_id,
    }
