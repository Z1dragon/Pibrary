"""
书籍感知切分模块

核心目标：
1) 按书籍格式使用差异化切分策略，保留章节语义完整性。
2) 为每个 Chunk 注入结构化元数据（book_id/chunk_id/page_num/chapter_title/source_type）。

简历亮点可描述：
- 构建 BookAwareTextSplitter，实现格式自适应切分与可追溯元数据注入。
"""

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from langchain_core.documents import Document
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import (
    BOOK_MD_EPUB_CHUNK_OVERLAP,
    BOOK_MD_EPUB_CHUNK_SIZE,
    BOOK_PDF_CHUNK_OVERLAP,
    BOOK_PDF_CHUNK_SIZE,
    BOOK_PAYLOAD_TYPE,
    BOOK_TXT_CHUNK_OVERLAP,
    BOOK_TXT_CHUNK_SIZE,
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    LOG_LEVEL,
)


if not logging.getLogger().handlers:
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
logger = logging.getLogger(__name__)


# ========================================================
# 中文文本切分器
# ========================================================

# 中文友好的分隔符优先级列表（从粗粒度到细粒度）
_CHINESE_SEPARATORS = [
    "\n\n",      # 段落间空行
    "\n",        # 换行
    "。",        # 中文句号
    "！",        # 中文感叹号
    "？",        # 中文问号
    "；",        # 中文分号
    "……",       # 省略号
    "…",         # 省略号（单）
    ".",          # 英文句号
    "!",          # 英文感叹号
    "?",          # 英文问号
    ";",          # 英文分号
    "，",        # 中文逗号
    ",",          # 英文逗号
    "、",        # 顿号
    " ",          # 空格
    "",           # 字符级兜底
]


def _clean_text(text: str) -> str:
    """清洗文本：去除多余空白，保留必要换行结构。"""
    # 合并3个及以上连续换行为2个
    text = re.sub(r"\n{3,}", "\n\n", text)
    # 去除行首尾空白
    lines = [line.strip() for line in text.split("\n")]
    text = "\n".join(lines)
    # 去除首尾空白
    return text.strip()


def create_text_splitter(
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
) -> RecursiveCharacterTextSplitter:
    """
    创建中文友好的文本切分器实例。

    Args:
        chunk_size: 切片大小（字符数），默认读取配置
        chunk_overlap: 切片重叠大小（字符数），默认读取配置

    Returns:
        RecursiveCharacterTextSplitter 实例
    """
    return RecursiveCharacterTextSplitter(
        separators=_CHINESE_SEPARATORS,
        chunk_size=chunk_size or CHUNK_SIZE,
        chunk_overlap=chunk_overlap or CHUNK_OVERLAP,
        length_function=len,
        is_separator_regex=False,
        keep_separator=True,
    )


class BookAwareTextSplitter:
    """书籍场景切分器：按格式选择策略并补齐结构化元数据。"""

    def __init__(self) -> None:
        self._pdf_splitter = create_text_splitter(BOOK_PDF_CHUNK_SIZE, BOOK_PDF_CHUNK_OVERLAP)
        self._txt_splitter = create_text_splitter(BOOK_TXT_CHUNK_SIZE, BOOK_TXT_CHUNK_OVERLAP)
        self._md_epub_splitter = create_text_splitter(BOOK_MD_EPUB_CHUNK_SIZE, BOOK_MD_EPUB_CHUNK_OVERLAP)

    def split_by_format(self, file_path: str, file_type: str, metadata: Dict[str, Any]) -> List[Document]:
        """
        根据文件类型进行书籍感知切分。

        Args:
            file_path: 书籍文件路径
            file_type: 文件类型（pdf/markdown/txt/epub/mobi）
            metadata: 书籍级元数据

        Returns:
            注入完整元数据的切片列表
        """
        from src.data_loader import load_document

        raw_docs: List[Document] = load_document(file_path)
        if not raw_docs:
            return []

        normalized_type = file_type.lower()
        if normalized_type in {"md", "markdown"}:
            split_docs = self._split_markdown(Path(file_path), raw_docs)
        elif normalized_type in {"epub", "mobi"}:
            split_docs = self._split_epub(raw_docs)
        elif normalized_type == "pdf":
            split_docs = self._split_pdf(raw_docs)
        else:
            split_docs = self._split_txt(raw_docs)

        self._inject_book_metadata(split_docs, metadata)
        logger.info("切分完成: %s, raw=%s, chunk=%s", Path(file_path).name, len(raw_docs), len(split_docs))
        return split_docs

    def _split_markdown(self, file_path: Path, raw_docs: List[Document]) -> List[Document]:
        """Markdown 优先按二/三级标题切分，再做递归切分兜底。"""
        text = "\n\n".join(doc.page_content for doc in raw_docs if doc.page_content)
        text = _clean_text(text)
        if not text:
            return []

        splitter_h2 = MarkdownHeaderTextSplitter(headers_to_split_on=[("##", "section_h2")], strip_headers=False)
        h2_docs = splitter_h2.split_text(text)

        final_docs: List[Document] = []
        for h2_doc in h2_docs:
            chapter_title = h2_doc.metadata.get("section_h2")
            h2_content = h2_doc.page_content

            if len(h2_content) <= BOOK_MD_EPUB_CHUNK_SIZE:
                final_docs.append(Document(page_content=h2_content, metadata={"chapter_title": chapter_title or ""}))
                continue

            splitter_h3 = MarkdownHeaderTextSplitter(headers_to_split_on=[("###", "section_h3")], strip_headers=False)
            h3_docs = splitter_h3.split_text(h2_content)
            for h3_doc in h3_docs:
                h3_title = h3_doc.metadata.get("section_h3") or chapter_title or ""
                seed_doc = Document(page_content=h3_doc.page_content, metadata={"chapter_title": h3_title})
                sub_chunks = self._md_epub_splitter.split_documents([seed_doc])
                final_docs.extend(sub_chunks)

        if not final_docs:
            base_doc = Document(page_content=text, metadata={})
            final_docs = self._md_epub_splitter.split_documents([base_doc])

        return self._with_common_source(final_docs, str(file_path), file_path.name, "markdown")

    def _split_epub(self, raw_docs: List[Document]) -> List[Document]:
        """EPUB/MOBI 按章节内容切分，并保留章节标题。"""
        final_docs: List[Document] = []
        for doc in raw_docs:
            chapter_title = doc.metadata.get("chapter_title") or f"章节{doc.metadata.get('chapter', '')}"
            seed_doc = Document(
                page_content=_clean_text(doc.page_content),
                metadata={
                    "source": doc.metadata.get("source", ""),
                    "file_name": doc.metadata.get("file_name", ""),
                    "file_type": doc.metadata.get("file_type", "epub"),
                    "chapter_title": chapter_title,
                },
            )
            if len(seed_doc.page_content) <= BOOK_MD_EPUB_CHUNK_SIZE:
                final_docs.append(seed_doc)
                continue
            final_docs.extend(self._md_epub_splitter.split_documents([seed_doc]))
        return final_docs

    def _split_pdf(self, raw_docs: List[Document]) -> List[Document]:
        """PDF 优先按页保留，再按中文友好递归切分。"""
        final_docs: List[Document] = []
        for doc in raw_docs:
            content = _clean_text(doc.page_content)
            if not content:
                continue
            page_num = doc.metadata.get("page_num") or doc.metadata.get("page")
            chapter_title = self._guess_pdf_chapter_title(content)
            seed_doc = Document(
                page_content=content,
                metadata={
                    "source": doc.metadata.get("source", ""),
                    "file_name": doc.metadata.get("file_name", ""),
                    "file_type": "pdf",
                    "page_num": page_num,
                    "chapter_title": chapter_title,
                },
            )
            if len(content) <= BOOK_PDF_CHUNK_SIZE:
                final_docs.append(seed_doc)
            else:
                final_docs.extend(self._pdf_splitter.split_documents([seed_doc]))
        return final_docs

    def _split_txt(self, raw_docs: List[Document]) -> List[Document]:
        """TXT 走通用递归切分。"""
        cleaned: List[Document] = []
        for doc in raw_docs:
            cleaned.append(Document(page_content=_clean_text(doc.page_content), metadata=doc.metadata.copy()))
        return self._txt_splitter.split_documents(cleaned)

    @staticmethod
    def _guess_pdf_chapter_title(text: str) -> str:
        """从 PDF 页面文本中猜测章节标题（启发式）。"""
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        for line in lines[:8]:
            if re.search(r"^(第[一二三四五六七八九十百千0-9]+章|Chapter\s+\d+)", line):
                return line[:120]
            if re.search(r"^[0-9]+\.[0-9A-Za-z\u4e00-\u9fa5\s]{2,}", line):
                return line[:120]
        return ""

    @staticmethod
    def _with_common_source(docs: List[Document], source: str, file_name: str, file_type: str) -> List[Document]:
        """补齐基础 source 信息。"""
        new_docs: List[Document] = []
        for doc in docs:
            meta = doc.metadata.copy()
            meta.setdefault("source", source)
            meta.setdefault("file_name", file_name)
            meta.setdefault("file_type", file_type)
            new_docs.append(Document(page_content=doc.page_content, metadata=meta))
        return new_docs

    @staticmethod
    def _inject_book_metadata(docs: List[Document], book_meta: Dict[str, Any]) -> None:
        """向每个切片注入统一的书籍与Chunk级元数据。"""
        book_id = str(book_meta.get("book_id", "book_unknown"))
        for idx, doc in enumerate(docs, start=1):
            chunk_id = f"{book_id}_chunk_{idx:06d}"
            doc.metadata["book_id"] = book_id
            doc.metadata["chunk_id"] = chunk_id
            doc.metadata["source_type"] = BOOK_PAYLOAD_TYPE

            doc.metadata["title"] = str(book_meta.get("title", ""))
            doc.metadata["author"] = str(book_meta.get("author", ""))
            doc.metadata["domain"] = str(book_meta.get("domain", ""))
            doc.metadata["reading_date"] = str(book_meta.get("reading_date", ""))
            doc.metadata["total_pages"] = int(book_meta.get("total_pages", 0) or 0)
            doc.metadata["upload_time"] = str(book_meta.get("upload_time", ""))

            doc.metadata["page_num"] = int(doc.metadata.get("page_num") or 0)
            doc.metadata["chapter_title"] = str(doc.metadata.get("chapter_title", ""))
            doc.metadata["chunk_index"] = idx - 1


def split_documents(
    documents: List[Document],
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
    clean: bool = True,
) -> List[Document]:
    """
    对 Document 列表进行切分。

    Args:
        documents: 原始 Document 列表
        chunk_size: 切片大小
        chunk_overlap: 切片重叠大小
        clean: 是否预清洗文本

    Returns:
        切分后的 Document 列表，metadata 中追加 chunk_index
    """
    # 向后兼容：保留原函数供旧流程调用
    if clean:
        for doc in documents:
            doc.page_content = _clean_text(doc.page_content)

    splitter = create_text_splitter(chunk_size, chunk_overlap)
    split_docs: List[Document] = splitter.split_documents(documents)

    source_chunk_count: Dict[str, int] = {}
    for doc in split_docs:
        source = str(doc.metadata.get("source", ""))
        idx = source_chunk_count.get(source, 0)
        doc.metadata["chunk_index"] = idx
        source_chunk_count[source] = idx + 1

    return split_docs
