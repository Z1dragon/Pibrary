import MarkdownRenderer from "./MarkdownRenderer";

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
    <div className="chat-window">
      <div className="panel-title-row">
        <h2>对话交互</h2>
        <span className="muted-text">支持多轮上下文</span>
      </div>

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
                {(msg.sources || []).length > 0 && (
                  <div className="msg-citations">{`引用来源 ${msg.sources.length} 条（右侧查看）`}</div>
                )}
              </>
            ) : (
              <div className="plain-content">{msg.content}</div>
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
    </div>
  );
}
