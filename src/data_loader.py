"""
文档加载解析模块（书籍增强版）

本模块负责：
1) 多格式文档加载（PDF/Markdown/TXT/EPUB/MOBI）
2) 书籍级结构化元数据自动解析
3) 预留个人笔记加载接口（后期优化）

简历亮点可描述：
- 实现书籍级元数据自动抽取（标题/作者/页数/章节）与手动校正融合流程。
"""

import hashlib
import logging
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from langchain_core.documents import Document

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import DEFAULT_BOOK_DOMAIN, LOG_LEVEL, NOTE_PAYLOAD_TYPE, VALID_DOMAINS


if not logging.getLogger().handlers:
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
logger = logging.getLogger(__name__)


# ========================================================
# PDF 加载器
# ========================================================

def load_pdf(file_path: str | Path) -> List[Document]:
    """加载 PDF 文件，每页作为一个 Document。"""
    import fitz

    file_path = Path(file_path)
    documents: List[Document] = []

    with fitz.open(str(file_path)) as pdf_doc:
        for page_num, page in enumerate(pdf_doc, start=1):
            text = page.get_text("text") or ""
            text = text.strip()
            if text:
                documents.append(Document(
                    page_content=text,
                    metadata={
                        "source": str(file_path),
                        "file_name": file_path.name,
                        "file_type": "pdf",
                        "page_num": page_num,
                    }
                ))
    logger.info("PDF加载完成: %s, 页片段=%s", file_path.name, len(documents))
    return documents


def _parse_markdown_front_matter(text: str) -> Dict[str, str]:
    """解析 Markdown 文件头 YAML Front Matter（轻量实现，无额外依赖）。"""
    if not text.startswith("---"):
        return {}

    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}

    yaml_part = parts[1]
    metadata: Dict[str, str] = {}
    for line in yaml_part.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        metadata[key.strip().lower()] = value.strip().strip("\"'")
    return metadata


def _hash_to_book_id(file_path: Path) -> str:
    """生成稳定 book_id（文件路径 + 时间戳后缀避免冲突）。"""
    base = hashlib.md5(str(file_path.resolve()).encode("utf-8")).hexdigest()[:12]
    return f"book_{base}"


def _normalize_domain(domain: str) -> str:
    """领域值标准化，超出候选值时回退默认领域。"""
    normalized = (domain or "").strip().lower()
    if normalized in VALID_DOMAINS:
        return normalized
    return DEFAULT_BOOK_DOMAIN


def parse_book_metadata(file_path: str | Path, manual_overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    自动解析书籍级元数据，并支持手动覆盖。

    返回字段：
    - book_id, title, author, domain, reading_date, total_pages, upload_time
    - source, file_name, file_type
    """
    file_path = Path(file_path)
    ext = file_path.suffix.lower()
    now_text = time.strftime("%Y-%m-%d %H:%M:%S")

    metadata: Dict[str, Any] = {
        "book_id": _hash_to_book_id(file_path),
        "title": file_path.stem,
        "author": "未知作者",
        "domain": DEFAULT_BOOK_DOMAIN,
        "reading_date": "",
        "total_pages": 0,
        "upload_time": now_text,
        "source": str(file_path.resolve()),
        "file_name": file_path.name,
        "file_type": ext.lstrip("."),
    }

    try:
        if ext == ".pdf":
            import fitz
            with fitz.open(str(file_path)) as pdf_doc:
                raw_meta = pdf_doc.metadata or {}
                metadata["title"] = (raw_meta.get("title") or metadata["title"]).strip()
                metadata["author"] = (raw_meta.get("author") or metadata["author"]).strip()
                metadata["total_pages"] = len(pdf_doc)

        elif ext in {".epub", ".mobi"}:
            if ext == ".epub":
                from ebooklib import epub
                book = epub.read_epub(str(file_path), options={"ignore_ncx": True})
                title_meta = book.get_metadata("DC", "title")
                author_meta = book.get_metadata("DC", "creator")
                if title_meta and title_meta[0]:
                    metadata["title"] = title_meta[0][0] or metadata["title"]
                if author_meta and author_meta[0]:
                    metadata["author"] = author_meta[0][0] or metadata["author"]

        elif ext in {".md", ".markdown"}:
            text = file_path.read_text(encoding="utf-8", errors="ignore")
            fm = _parse_markdown_front_matter(text)
            metadata["title"] = fm.get("title", metadata["title"])
            metadata["author"] = fm.get("author", metadata["author"])
            metadata["domain"] = fm.get("domain", metadata["domain"])
            metadata["reading_date"] = fm.get("reading_date", metadata["reading_date"])

        elif ext == ".txt":
            metadata["total_pages"] = 1

    except Exception as exc:
        logger.error("自动解析书籍元数据失败: %s, error=%s", file_path.name, exc)

    if manual_overrides:
        for key, value in manual_overrides.items():
            if value is not None and value != "":
                metadata[key] = value

    metadata["domain"] = _normalize_domain(str(metadata.get("domain", DEFAULT_BOOK_DOMAIN)))
    try:
        metadata["total_pages"] = int(metadata.get("total_pages") or 0)
    except (TypeError, ValueError):
        metadata["total_pages"] = 0

    logger.info(
        "元数据解析完成: file=%s, book_id=%s, title=%s, author=%s, domain=%s",
        file_path.name,
        metadata["book_id"],
        metadata["title"],
        metadata["author"],
        metadata["domain"],
    )
    return metadata


# ========================================================
# Markdown 加载器
# ========================================================

def load_markdown(file_path: str | Path) -> List[Document]:
    """加载 Markdown 文件，整个文件作为一个 Document。"""
    file_path = Path(file_path)
    text = file_path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    docs = [Document(
        page_content=text,
        metadata={
            "source": str(file_path),
            "file_name": file_path.name,
            "file_type": "markdown",
        }
    )]
    logger.info("Markdown加载完成: %s", file_path.name)
    return docs


# ========================================================
# TXT 加载器
# ========================================================

def load_txt(file_path: str | Path) -> List[Document]:
    """加载纯文本文件。"""
    file_path = Path(file_path)
    text = file_path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    docs = [Document(
        page_content=text,
        metadata={
            "source": str(file_path),
            "file_name": file_path.name,
            "file_type": "txt",
        }
    )]
    logger.info("TXT加载完成: %s", file_path.name)
    return docs


# ========================================================
# EPUB 加载器
# ========================================================

def load_epub(file_path: str | Path) -> List[Document]:
    """加载 EPUB 文件，每个章节作为一个 Document。"""
    import ebooklib
    from ebooklib import epub
    from bs4 import BeautifulSoup

    file_path = Path(file_path)
    book = epub.read_epub(str(file_path), options={"ignore_ncx": True})

    documents: List[Document] = []
    chapter_num = 0
    for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        content = item.get_content()
        # EPUB 内部多为 XHTML/XML，使用 xml 解析器可避免 XMLParsedAsHTMLWarning 并提高稳定性。
        soup = BeautifulSoup(content, "xml")
        text = soup.get_text(separator="\n").strip()
        if text:
            chapter_num += 1
            documents.append(Document(
                page_content=text,
                metadata={
                    "source": str(file_path),
                    "file_name": file_path.name,
                    "file_type": "epub",
                    "chapter": chapter_num,
                    "chapter_title": item.get_name() or f"章节{chapter_num}",
                }
            ))
    logger.info("EPUB加载完成: %s, 章节片段=%s", file_path.name, len(documents))
    return documents


# ========================================================
# MOBI 加载器（先转 EPUB 再解析）
# ========================================================

def load_mobi(file_path: str | Path) -> List[Document]:
    """
    加载 MOBI 文件。
    使用 mobi 库将 MOBI 解包，提取内部 HTML 内容后解析。
    """
    import mobi
    from bs4 import BeautifulSoup

    file_path = Path(file_path)

    # mobi.extract 返回 (tempdir, filepath)
    temp_dir, _ = mobi.extract(str(file_path))

    documents: List[Document] = []
    # 遍历临时目录中的 HTML 文件
    for root, _dirs, files in os.walk(temp_dir):
        for fname in sorted(files):
            if fname.lower().endswith((".html", ".htm", ".xhtml")):
                html_path = Path(root) / fname
                try:
                    html_content = html_path.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    continue
                soup = BeautifulSoup(html_content, "lxml")
                text = soup.get_text(separator="\n").strip()
                if text:
                    documents.append(Document(
                        page_content=text,
                        metadata={
                            "source": str(file_path),
                            "file_name": file_path.name,
                            "file_type": "mobi",
                            "chapter_title": html_path.stem,
                        }
                    ))
    logger.info("MOBI加载完成: %s, 文本片段=%s", file_path.name, len(documents))
    return documents


# ========================================================
# 统一加载路由
# ========================================================

# 扩展名 -> 加载函数映射
_LOADER_MAP = {
    ".pdf": load_pdf,
    ".md": load_markdown,
    ".markdown": load_markdown,
    ".txt": load_txt,
    ".epub": load_epub,
    ".mobi": load_mobi,
}

SUPPORTED_EXTENSIONS = set(_LOADER_MAP.keys())


def load_document(file_path: str | Path) -> List[Document]:
    """
    根据文件扩展名自动选择加载器，返回 Document 列表。

    Args:
        file_path: 文件路径

    Returns:
        Document 列表

    Raises:
        ValueError: 不支持的文件格式
    """
    file_path = Path(file_path)
    ext = file_path.suffix.lower()
    loader_fn = _LOADER_MAP.get(ext)
    if loader_fn is None:
        raise ValueError(
            f"不支持的文件格式: '{ext}'。"
            f"支持的格式: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )
    return loader_fn(file_path)


def load_personal_notes(note_dir: str | Path) -> List[Document]:
    """
    预留接口：加载个人阅读笔记。

    后期优化方向：
    1) 支持 md/txt/obsidian 导出的多种笔记格式。
    2) 统一映射为 source_type=personal_note 的 payload。
    3) 结合书籍 chunk 进行跨源检索增强。

    当前不启用原因：
    - 本阶段聚焦“结构化书籍专属RAG”，优先保证书籍主链路稳定。
    """
    _ = note_dir
    logger.info("个人笔记加载接口已预留，当前未启用。payload_type=%s", NOTE_PAYLOAD_TYPE)
    return []


def load_directory(dir_path: str | Path, recursive: bool = True) -> List[Document]:
    """
    批量加载指定目录下所有支持格式的文档。

    Args:
        dir_path: 目录路径
        recursive: 是否递归子目录

    Returns:
        Document 列表
    """
    dir_path = Path(dir_path)
    if not dir_path.is_dir():
        raise FileNotFoundError(f"目录不存在: {dir_path}")

    documents = []
    pattern = "**/*" if recursive else "*"
    for fp in sorted(dir_path.glob(pattern)):
        if fp.is_file() and fp.suffix.lower() in SUPPORTED_EXTENSIONS:
            try:
                docs = load_document(fp)
                documents.extend(docs)
                logger.info("已加载: %s (%s 个文档片段)", fp.name, len(docs))
            except Exception as e:
                logger.error("加载失败: %s - %s", fp.name, e)
    return documents
