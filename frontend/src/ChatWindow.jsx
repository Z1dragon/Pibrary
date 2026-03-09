import MarkdownRenderer from "./MarkdownRenderer";

function getSourceLocation(src) {
  const idx = Number(src.chunk_index || 0) + 1;
  if (src.page_num) {
    return `页码 ${src.page_num} | 片段 ${idx}`;
  }
  if (src.chapter_title) {
    return `章节 ${src.chapter_title} | 片段 ${idx}`;
  }
  return `片段 ${idx}`;
}

export default function ChatWindow({
  chatBoxRef,
  messages,
  copiedMsgKey,
  copyMarkdownRaw,
  questionInput,
  setQuestionInput,
  onAsk,
}) {
  return (
    <>
      <section ref={chatBoxRef} className="chat-box">
        {messages.map((msg, idx) => (
          <div key={`${msg.role}_${idx}`} className={`msg ${msg.role}`}>
            {msg.role === "assistant" ? (
              <>
                <div className="msg-toolbar">
                  <button
                    type="button"
                    className="copy-btn"
                    onClick={() => copyMarkdownRaw(msg.content, `${msg.role}_${idx}`)}
                  >
                    {copiedMsgKey === `${msg.role}_${idx}` ? "已复制 Markdown" : "复制回答 Markdown 原文"}
                  </button>
                </div>
                <MarkdownRenderer content={msg.content} />
              </>
            ) : (
              <div className="plain-content">{msg.content}</div>
            )}
            {msg.role === "assistant" && (msg.sources || []).length > 0 && (
              <div className="sources">
                <strong>📖 参考来源</strong>
                {(msg.sources || []).map((src, sidx) => (
                  <div className="source-item" key={`${idx}_${sidx}`}>
                    <div>
                      <strong>{src.title || src.file_name || "未知书籍"}</strong>
                    </div>
                    <div>
                      {`book_id=${src.book_id || ""} | author=${src.author || "未知作者"} | domain=${src.domain || ""}`}
                    </div>
                    <div>
                      {`来源类型=${src.source_type || "book_content"}${src.note_id ? ` | note_id=${src.note_id}` : ""}${src.note_title ? ` | 笔记标题=${src.note_title}` : ""}`}
                    </div>
                    <div>{getSourceLocation(src)}</div>
                    <div>{`文件: ${src.file_name || "未知文件"}`}</div>
                    <div>{src.preview || ""}</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
      </section>

      <form className="chat-form" onSubmit={onAsk}>
        <input
          placeholder="请输入您的问题..."
          autoComplete="off"
          value={questionInput}
          onChange={(e) => setQuestionInput(e.target.value)}
        />
        <button type="submit" className="primary">
          发送
        </button>
      </form>
    </>
  );
}
