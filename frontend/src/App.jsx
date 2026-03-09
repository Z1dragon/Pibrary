import { useEffect, useMemo, useRef, useState } from "react";

async function request(url, options = {}) {
  const res = await fetch(url, options);
  if (!res.ok) {
    let message = `请求失败: ${res.status}`;
    try {
      const err = await res.json();
      message = err.detail || message;
    } catch (_err) {
      message = message;
    }
    throw new Error(message);
  }
  return res.json();
}

function nowPrefix(text) {
  return `[${new Date().toLocaleTimeString()}] ${text}`;
}

function escapeHtml(text) {
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function renderInlineMarkdown(text) {
  return text
    .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>')
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/__([^_]+)__/g, "<strong>$1</strong>")
    .replace(/\*([^*]+)\*/g, "<em>$1</em>")
    .replace(/_([^_]+)_/g, "<em>$1</em>")
    .replace(/`([^`]+)`/g, "<code>$1</code>");
}

function markdownToHtml(markdown) {
  const source = String(markdown || "").replace(/\r\n/g, "\n");

  const codeBlocks = [];
  let text = source.replace(/```([\s\S]*?)```/g, (_m, code) => {
    const idx = codeBlocks.length;
    codeBlocks.push(`<pre><code>${escapeHtml(code.trim())}</code></pre>`);
    return `@@CODE_BLOCK_${idx}@@`;
  });

  const lines = text.split("\n");
  const html = [];
  let inUl = false;
  let inOl = false;

  const closeLists = () => {
    if (inUl) {
      html.push("</ul>");
      inUl = false;
    }
    if (inOl) {
      html.push("</ol>");
      inOl = false;
    }
  };

  for (const rawLine of lines) {
    const line = rawLine.trim();

    if (!line) {
      closeLists();
      continue;
    }

    if (/^@@CODE_BLOCK_\d+@@$/.test(line)) {
      closeLists();
      html.push(line);
      continue;
    }

    const escaped = escapeHtml(line);
    const heading = escaped.match(/^(#{1,6})\s+(.+)$/);
    if (heading) {
      closeLists();
      const level = heading[1].length;
      html.push(`<h${level}>${renderInlineMarkdown(heading[2])}</h${level}>`);
      continue;
    }

    const ul = escaped.match(/^[-*]\s+(.+)$/);
    if (ul) {
      if (inOl) {
        html.push("</ol>");
        inOl = false;
      }
      if (!inUl) {
        html.push("<ul>");
        inUl = true;
      }
      html.push(`<li>${renderInlineMarkdown(ul[1])}</li>`);
      continue;
    }

    const ol = escaped.match(/^\d+\.\s+(.+)$/);
    if (ol) {
      if (inUl) {
        html.push("</ul>");
        inUl = false;
      }
      if (!inOl) {
        html.push("<ol>");
        inOl = true;
      }
      html.push(`<li>${renderInlineMarkdown(ol[1])}</li>`);
      continue;
    }

    closeLists();
    html.push(`<p>${renderInlineMarkdown(escaped)}</p>`);
  }

  closeLists();

  text = html.join("\n");
  codeBlocks.forEach((block, idx) => {
    text = text.replace(`@@CODE_BLOCK_${idx}@@`, block);
  });

  return text;
}

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

const SESSION_STORAGE_KEY = "rag_chat_session_id";

function loadSessionId() {
  try {
    return localStorage.getItem(SESSION_STORAGE_KEY) || "";
  } catch (_err) {
    return "";
  }
}

function saveSessionId(sessionId) {
  try {
    if (!sessionId) {
      localStorage.removeItem(SESSION_STORAGE_KEY);
      return;
    }
    localStorage.setItem(SESSION_STORAGE_KEY, sessionId);
  } catch (_err) {
    // ignore
  }
}

export default function App() {
  const [config, setConfig] = useState(null);
  const [files, setFiles] = useState([]);
  const [metadataMap, setMetadataMap] = useState({});
  const [manifestItems, setManifestItems] = useState([]);
  const [noteItems, setNoteItems] = useState([]);
  const [messages, setMessages] = useState([]);
  const [sessionId, setSessionId] = useState(() => loadSessionId());

  const [forceRebuild, setForceRebuild] = useState(false);
  const [buildSubmitting, setBuildSubmitting] = useState(false);
  const [noteSubmitting, setNoteSubmitting] = useState(false);

  const [buildLogs, setBuildLogs] = useState([]);
  const [noteLogs, setNoteLogs] = useState([]);

  const [noteBookId, setNoteBookId] = useState("");
  const [noteTitle, setNoteTitle] = useState("");
  const [noteText, setNoteText] = useState("");

  const [questionInput, setQuestionInput] = useState("");
  const [filterBookId, setFilterBookId] = useState("");
  const [filterTitle, setFilterTitle] = useState("");
  const [filterAuthor, setFilterAuthor] = useState("");
  const [filterDomain, setFilterDomain] = useState("");
  const [enablePageRange, setEnablePageRange] = useState(false);
  const [minPage, setMinPage] = useState(1);
  const [maxPage, setMaxPage] = useState(10);
  const [useReranker, setUseReranker] = useState(true);
  const [recallTopK, setRecallTopK] = useState(10);
  const [rerankTopK, setRerankTopK] = useState(3);
  const [copiedMsgKey, setCopiedMsgKey] = useState("");

  const buildLogRef = useRef(null);
  const noteLogRef = useRef(null);
  const chatBoxRef = useRef(null);

  async function copyMarkdownRaw(content, msgKey) {
    const text = String(content || "");
    try {
      if (navigator?.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
      } else {
        throw new Error("clipboard not available");
      }
    } catch (_err) {
      const textarea = document.createElement("textarea");
      textarea.value = text;
      textarea.style.position = "fixed";
      textarea.style.opacity = "0";
      document.body.appendChild(textarea);
      textarea.focus();
      textarea.select();
      document.execCommand("copy");
      document.body.removeChild(textarea);
    }

    setCopiedMsgKey(msgKey);
    window.setTimeout(() => {
      setCopiedMsgKey((current) => (current === msgKey ? "" : current));
    }, 1500);
  }

  const books = useMemo(() => manifestItems || [], [manifestItems]);

  function appendBuildLog(text) {
    setBuildLogs((prev) => [...prev, nowPrefix(text)]);
  }

  function appendNoteLog(text) {
    setNoteLogs((prev) => [...prev, nowPrefix(text)]);
  }

  async function loadManifest() {
    const data = await request("/api/kb/manifest");
    setManifestItems(data.items || []);
  }

  async function loadNoteManifest() {
    const data = await request("/api/notes/manifest");
    setNoteItems(data.items || []);
  }

  async function loadChatHistory(targetSessionId) {
    const normalizedSessionId = String(targetSessionId || "").trim();
    if (!normalizedSessionId) {
      setMessages([]);
      return;
    }

    const data = await request(`/api/chat/history?session_id=${encodeURIComponent(normalizedSessionId)}`);
    const historyMessages = Array.isArray(data.messages) ? data.messages : [];
    const normalizedMessages = historyMessages.map((message) => ({
      role: message.role === "assistant" ? "assistant" : "user",
      content: String(message.content || ""),
      sources: [],
    }));
    setMessages(normalizedMessages);
  }

  async function initConfig() {
    const conf = await request("/api/config");
    setConfig(conf);
    setRecallTopK(Number(conf.default_recall_top_k || 10));
    setRerankTopK(Number(conf.default_rerank_top_k || 3));
    setUseReranker(Boolean(conf.default_use_reranker));
  }

  async function parseMetadataForFiles(selectedFiles) {
    const nextMap = {};
    for (const file of selectedFiles) {
      const formData = new FormData();
      formData.append("file", file);
      try {
        const result = await request("/api/meta/parse", { method: "POST", body: formData });
        nextMap[file.name] = result.metadata || {};
        appendBuildLog(`✓ ${file.name} 元数据解析成功`);
      } catch (err) {
        nextMap[file.name] = {};
        appendBuildLog(`✗ ${file.name} 元数据解析失败: ${err.message}`);
      }
    }
    setMetadataMap(nextMap);
  }

  function updateMetaField(fileName, field, value) {
    setMetadataMap((prev) => ({
      ...prev,
      [fileName]: {
        ...(prev[fileName] || {}),
        [field]: value,
      },
    }));
  }

  async function onBuild() {
    if (!files.length) {
      alert("请先选择文档");
      return;
    }

    const formData = new FormData();
    files.forEach((file) => formData.append("files", file));
    formData.append("metadata_json", JSON.stringify(metadataMap));
    formData.append("force_rebuild", String(forceRebuild));

    setBuildSubmitting(true);
    appendBuildLog("开始构建知识库...");
    try {
      const result = await request("/api/kb/build", { method: "POST", body: formData });
      (result.results || []).forEach((item) => {
        if (item.success) {
          appendBuildLog(`✓ ${item.file_name}: 入库 ${item.chunk_count} 个切片`);
        } else {
          appendBuildLog(`✗ ${item.file_name}: ${item.error || "未知错误"}`);
        }
      });
      appendBuildLog(`✅ 构建完成，总切片: ${result.total_chunks}`);
      await loadManifest();
      await loadNoteManifest();
    } catch (err) {
      appendBuildLog(`❌ 构建失败: ${err.message}`);
    } finally {
      setBuildSubmitting(false);
    }
  }

  async function onDeleteFile(item) {
    try {
      await request(`/api/kb/file?file_path=${encodeURIComponent(item.file_path)}`, { method: "DELETE" });
      appendBuildLog(`✅ 已删除 ${item.file_name}`);
      await loadManifest();
    } catch (err) {
      alert(err.message);
    }
  }

  async function onUploadNote() {
    const bookId = (noteBookId || "").trim();
    const text = (noteText || "").trim();
    const title = (noteTitle || "").trim();

    if (!bookId) {
      alert("请先选择要关联的书籍(book_id)");
      return;
    }
    if (!text) {
      alert("请输入笔记内容");
      return;
    }

    const formData = new FormData();
    formData.append("book_id", bookId);
    formData.append("note_text", text);
    formData.append("note_title", title);

    setNoteSubmitting(true);
    appendNoteLog("开始上传笔记...");
    try {
      const result = await request("/api/notes/upload", {
        method: "POST",
        body: formData,
      });
      appendNoteLog(`✅ 上传成功: note_id=${result.note_id}, 入库切片=${result.chunk_count}`);
      setNoteText("");
      await loadNoteManifest();
    } catch (err) {
      appendNoteLog(`❌ 上传失败: ${err.message}`);
    } finally {
      setNoteSubmitting(false);
    }
  }

  async function onDeleteNote(item) {
    try {
      await request(`/api/notes?note_id=${encodeURIComponent(item.note_id)}`, { method: "DELETE" });
      appendNoteLog(`✅ 已删除笔记: ${item.note_id}`);
      await loadNoteManifest();
    } catch (err) {
      alert(err.message);
    }
  }

  function buildChatPayload(question) {
    const filters = {};
    if (filterBookId.trim()) filters.book_id = filterBookId.trim();
    if (filterTitle.trim()) filters.title = filterTitle.trim();
    if (filterAuthor.trim()) filters.author = filterAuthor.trim();
    if (filterDomain.trim()) filters.domain = filterDomain.trim();

    const payload = {
      question,
      session_id: sessionId || undefined,
      use_reranker: useReranker,
      recall_top_k: Number(recallTopK),
      rerank_top_k: Number(rerankTopK),
      filters,
    };

    if (enablePageRange) {
      payload.page_num_range = {
        min_page: Number(minPage),
        max_page: Number(maxPage),
      };
    }

    return payload;
  }

  async function onAsk(event) {
    event.preventDefault();
    const question = questionInput.trim();
    if (!question) return;

    setQuestionInput("");
    setMessages((prev) => [...prev, { role: "user", content: question, sources: [] }]);

    try {
      const payload = buildChatPayload(question);
      const result = await request("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      const nextSessionId = (result.session_id || "").trim();
      if (nextSessionId && nextSessionId !== sessionId) {
        setSessionId(nextSessionId);
        saveSessionId(nextSessionId);
      }

      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: result.answer || "",
          sources: result.sources || [],
        },
      ]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: `❌ ${err.message}`, sources: [] },
      ]);
    }
  }

  useEffect(() => {
    let mounted = true;

    async function bootstrap() {
      try {
        await initConfig();
        await loadManifest();
        await loadNoteManifest();
        await loadChatHistory(sessionId);
      } catch (err) {
        if (mounted) {
          alert(`初始化失败: ${err.message}`);
        }
      }
    }

    bootstrap();
    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    if (books.length && !noteBookId) {
      setNoteBookId(books[0].book_id || "");
    }
    if (!books.length) {
      setNoteBookId("");
    }
  }, [books, noteBookId]);

  useEffect(() => {
    if (buildLogRef.current) {
      buildLogRef.current.scrollTop = buildLogRef.current.scrollHeight;
    }
  }, [buildLogs]);

  useEffect(() => {
    if (noteLogRef.current) {
      noteLogRef.current.scrollTop = noteLogRef.current.scrollHeight;
    }
  }, [noteLogs]);

  useEffect(() => {
    if (chatBoxRef.current) {
      chatBoxRef.current.scrollTop = chatBoxRef.current.scrollHeight;
    }
  }, [messages]);

  useEffect(() => {
    saveSessionId(sessionId);
  }, [sessionId]);

  return (
    <div className="layout">
      <aside className="sidebar">
        <h2>📁 知识库管理</h2>

        <section className="card">
          <h3>📚 书籍上传</h3>
          <p className="hint">支持格式：{(config?.supported_extensions || []).join(", ")}</p>
          <input
            type="file"
            multiple
            onChange={async (event) => {
              const selectedFiles = Array.from(event.target.files || []);
              setFiles(selectedFiles);
              setMetadataMap({});
              setBuildLogs([]);
              if (!selectedFiles.length) {
                return;
              }
              await parseMetadataForFiles(selectedFiles);
            }}
          />
          <label className="checkbox-line">
            <input
              type="checkbox"
              checked={forceRebuild}
              onChange={(event) => setForceRebuild(event.target.checked)}
            />
            强制重建同名文档（先删后建）
          </label>

          <div className="meta-forms">
            {files.map((file) => {
              const meta = metadataMap[file.name] || {};
              const domains = config?.valid_domains || [];
              const selectedDomain = meta.domain || domains[0] || "";
              return (
                <div className="meta-item" key={file.name}>
                  <h4>元数据编辑：{file.name}</h4>
                  <div className="meta-grid">
                    <input
                      value={meta.book_id || ""}
                      placeholder="book_id"
                      onChange={(e) => updateMetaField(file.name, "book_id", e.target.value)}
                    />
                    <input
                      value={meta.title || file.name}
                      placeholder="书名(title)"
                      onChange={(e) => updateMetaField(file.name, "title", e.target.value)}
                    />
                    <input
                      value={meta.author || "未知作者"}
                      placeholder="作者(author)"
                      onChange={(e) => updateMetaField(file.name, "author", e.target.value)}
                    />
                    <select
                      value={selectedDomain}
                      onChange={(e) => updateMetaField(file.name, "domain", e.target.value)}
                    >
                      {domains.map((domain) => (
                        <option key={domain} value={domain}>
                          {domain}
                        </option>
                      ))}
                    </select>
                    <input
                      value={meta.reading_date || ""}
                      placeholder="阅读日期(reading_date)"
                      onChange={(e) => updateMetaField(file.name, "reading_date", e.target.value)}
                    />
                    <input
                      type="number"
                      min="0"
                      value={Number(meta.total_pages || 0)}
                      placeholder="总页数(total_pages)"
                      onChange={(e) => updateMetaField(file.name, "total_pages", e.target.value)}
                    />
                  </div>
                </div>
              );
            })}
          </div>

          <button className="primary" disabled={buildSubmitting} onClick={onBuild}>
            📥 构建知识库
          </button>
          <pre ref={buildLogRef} className="log">
            {buildLogs.join("\n")}
          </pre>
        </section>

        <section className="card">
          <h3>📝 笔记上传</h3>
          <select value={noteBookId} onChange={(e) => setNoteBookId(e.target.value)}>
            {!books.length ? (
              <option value="">请先上传并构建书籍</option>
            ) : (
              books.map((book, index) => (
                <option key={`${book.book_id || ""}_${book.file_name || ""}_${index}`} value={book.book_id || ""}>
                  {`${book.title || book.file_name} (${book.book_id || ""})`}
                </option>
              ))
            )}
          </select>
          <input
            placeholder="笔记标题(可选)"
            value={noteTitle}
            onChange={(e) => setNoteTitle(e.target.value)}
          />
          <textarea
            rows="5"
            placeholder="请输入与书籍对应的个人阅读笔记..."
            value={noteText}
            onChange={(e) => setNoteText(e.target.value)}
          />
          <button className="primary" disabled={noteSubmitting} onClick={onUploadNote}>
            📌 上传笔记并入库
          </button>
          <pre ref={noteLogRef} className="log">
            {noteLogs.join("\n")}
          </pre>
        </section>

        <section className="card">
          <h3>📊 知识库状态</h3>
          <div className="manifest-list">
            {!manifestItems.length ? (
              <div className="manifest-item">知识库为空，请先上传文档。</div>
            ) : (
              manifestItems.map((item) => (
                <div className="manifest-item" key={item.file_path}>
                  <div className="title">{item.title || item.file_name}</div>
                  <div>
                    {`book_id=${item.book_id || ""} | author=${item.author || "未知作者"} | domain=${item.domain || ""}`}
                  </div>
                  <div>{`文件=${item.file_name} | ${item.chunk_count} 切片 | ${item.processed_at || ""}`}</div>
                  <button onClick={() => onDeleteFile(item)}>🗑️ 删除</button>
                </div>
              ))
            )}
          </div>
        </section>

        <section className="card">
          <h3>🗂️ 笔记状态</h3>
          <div className="manifest-list">
            {!noteItems.length ? (
              <div className="manifest-item">暂无个人笔记。</div>
            ) : (
              noteItems.map((item) => (
                <div className="manifest-item" key={item.note_id}>
                  <div className="title">{item.note_title || item.note_id}</div>
                  <div>{`book_id=${item.book_id || ""} | title=${item.title || ""}`}</div>
                  <div>{`${item.chunk_count || 0} 切片 | ${item.processed_at || ""}`}</div>
                  <button onClick={() => onDeleteNote(item)}>🗑️ 删除笔记</button>
                </div>
              ))
            )}
          </div>
        </section>

        <section className="card">
          <h3>🎯 元数据过滤</h3>
          <input placeholder="book_id" value={filterBookId} onChange={(e) => setFilterBookId(e.target.value)} />
          <input placeholder="书名(title)" value={filterTitle} onChange={(e) => setFilterTitle(e.target.value)} />
          <input placeholder="作者(author)" value={filterAuthor} onChange={(e) => setFilterAuthor(e.target.value)} />
          <select value={filterDomain} onChange={(e) => setFilterDomain(e.target.value)}>
            <option value="">全部领域</option>
            {(config?.valid_domains || []).map((domain) => (
              <option key={domain} value={domain}>
                {domain}
              </option>
            ))}
          </select>

          <label className="checkbox-line">
            <input
              type="checkbox"
              checked={enablePageRange}
              onChange={(e) => setEnablePageRange(e.target.checked)}
            />
            启用页码范围过滤
          </label>
          <div className="range-row">
            <input
              type="number"
              min="1"
              value={minPage}
              disabled={!enablePageRange}
              onChange={(e) => setMinPage(Number(e.target.value))}
            />
            <span>到</span>
            <input
              type="number"
              min="1"
              value={maxPage}
              disabled={!enablePageRange}
              onChange={(e) => setMaxPage(Number(e.target.value))}
            />
          </div>
        </section>

        <section className="card">
          <h3>⚙️ 检索参数</h3>
          <label className="checkbox-line">
            <input
              type="checkbox"
              checked={useReranker}
              onChange={(e) => setUseReranker(e.target.checked)}
            />
            启用重排序 (Reranker)
          </label>
          <label>
            向量召回数量 <span>{recallTopK}</span>
          </label>
          <input
            type="range"
            min="3"
            max="30"
            value={recallTopK}
            onChange={(e) => setRecallTopK(Number(e.target.value))}
          />
          <label>
            最终返回文档数 <span>{rerankTopK}</span>
          </label>
          <input
            type="range"
            min="1"
            max="10"
            value={rerankTopK}
            onChange={(e) => setRerankTopK(Number(e.target.value))}
          />
        </section>

        <button
          className="danger"
          onClick={async () => {
            const currentSessionId = (sessionId || "").trim();
            if (currentSessionId) {
              try {
                await request(`/api/chat/history?session_id=${encodeURIComponent(currentSessionId)}`, {
                  method: "DELETE",
                });
              } catch (_err) {
                // ignore
              }
            }
            setMessages([]);
            setSessionId("");
          }}
        >
          🗑️ 清除对话历史
        </button>
      </aside>

      <main className="main">
        <header className="header">
          <h1>📚 中文 RAG 知识库问答系统</h1>
          <p>基于 LangChain + Milvus + GLM | 支持 PDF / Markdown / TXT / EPUB / MOBI</p>
        </header>

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
                  <div className="markdown-body">
                    <div
                      dangerouslySetInnerHTML={{
                        __html: markdownToHtml(msg.content),
                      }}
                    />
                  </div>
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
      </main>
    </div>
  );
}
