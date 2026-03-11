import { useState } from "react";

function getSourceLocation(src) {
  const idx = Number(src.chunk_index || 0) + 1;
  if (src.page_num) {
    return `页码 ${src.page_num} · 片段 ${idx}`;
  }
  if (src.chapter_title) {
    return `章节 ${src.chapter_title} · 片段 ${idx}`;
  }
  return `片段 ${idx}`;
}

export default function SourcePanel({ sources }) {
  const [expandedKey, setExpandedKey] = useState("");

  return (
    <div className="source-panel">
      <div className="panel-title-row">
        <h2>检索来源</h2>
        <span className="source-count">{sources.length}</span>
      </div>

      {!sources.length ? (
        <div className="source-empty">提问后将在此展示相关文档片段与引用标注。</div>
      ) : (
        <div className="source-list">
          {sources.map((src, index) => {
            const key = `${src.file_name || "unknown"}_${src.chunk_index || index}_${index}`;
            const isExpanded = expandedKey === key;
            const sourceText = String(src.content || src.preview || "暂无片段预览");

            return (
              <article className="source-card" key={key}>
                <div className="source-head">
                  <span className="cite-tag">[{index + 1}]</span>
                  <strong>{src.title || src.file_name || "未知文档"}</strong>
                </div>
                <div className="source-meta">{`book_id=${src.book_id || ""} · author=${src.author || "未知作者"}`}</div>
                <div className="source-meta">{`domain=${src.domain || ""} · ${getSourceLocation(src)}`}</div>
                <button
                  type="button"
                  className="source-preview-trigger"
                  onClick={() => setExpandedKey((prev) => (prev === key ? "" : key))}
                  aria-expanded={isExpanded}
                >
                  <p className={`source-preview ${isExpanded ? "expanded" : "collapsed"}`}>{sourceText}</p>
                  <span className="source-preview-hint">{isExpanded ? "收起全文" : "点击查看全文"}</span>
                </button>
              </article>
            );
          })}
        </div>
      )}
    </div>
  );
}
