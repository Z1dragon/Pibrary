import { useEffect, useMemo, useRef, useState } from "react";
import ChatWindow from "./ChatWindow";
import Sidebar from "./Sidebar";
import SourcePanel from "./SourcePanel";

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
  const [leftExpanded, setLeftExpanded] = useState(false);
  const [rightExpanded, setRightExpanded] = useState(false);

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
  const activeSources = useMemo(() => {
    for (let index = messages.length - 1; index >= 0; index -= 1) {
      const current = messages[index];
      if (current.role === "assistant" && Array.isArray(current.sources) && current.sources.length > 0) {
        return current.sources;
      }
    }
    return [];
  }, [messages]);

  function toggleLeftPanel() {
    setLeftExpanded((prev) => {
      const next = !prev;
      if (next) setRightExpanded(false);
      return next;
    });
  }

  function toggleRightPanel() {
    setRightExpanded((prev) => {
      const next = !prev;
      if (next) setLeftExpanded(false);
      return next;
    });
  }

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

  useEffect(() => {
    function onKeyDown(event) {
      if (event.key === "Escape") {
        setLeftExpanded(false);
        setRightExpanded(false);
        return;
      }
      if (event.key === "[") {
        event.preventDefault();
        toggleLeftPanel();
      }
      if (event.key === "]") {
        event.preventDefault();
        toggleRightPanel();
      }
    }

    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
    };
  }, []);

  async function onClearHistory() {
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
  }

  return (
    <div className="app-shell">
      <header className="top-nav">
        <div className="brand-area">
          <h1>LibraryOS</h1>
          <p>AI 知识检索工作台</p>
        </div>
        <div className="nav-actions">
          <span className="session-chip">{sessionId ? `会话: ${sessionId}` : "新会话"}</span>
          <button type="button" className="btn-dark" onClick={onClearHistory}>
            清空对话
          </button>
        </div>
      </header>

      <div
        className={`workspace-grid ${leftExpanded ? "left-open" : "left-closed"} ${rightExpanded ? "right-open" : "right-closed"}`}
      >
        <aside className={`panel side-panel panel-left ${leftExpanded ? "expanded" : "collapsed"}`}>
          <button
            type="button"
            className="side-tab"
            onClick={toggleLeftPanel}
            aria-expanded={leftExpanded}
            aria-label="切换知识库面板"
          >
            <span className="side-tab-icon" aria-hidden="true" />
            <span className="side-tab-text">知识库</span>
            <span className="side-tab-count">{manifestItems.length + noteItems.length}</span>
          </button>
          <div className="side-drawer-content">
            <Sidebar
              config={config}
              files={files}
              metadataMap={metadataMap}
              forceRebuild={forceRebuild}
              buildSubmitting={buildSubmitting}
              noteSubmitting={noteSubmitting}
              buildLogs={buildLogs}
              noteLogs={noteLogs}
              noteBookId={noteBookId}
              noteTitle={noteTitle}
              noteText={noteText}
              filterBookId={filterBookId}
              filterTitle={filterTitle}
              filterAuthor={filterAuthor}
              filterDomain={filterDomain}
              enablePageRange={enablePageRange}
              minPage={minPage}
              maxPage={maxPage}
              useReranker={useReranker}
              recallTopK={recallTopK}
              rerankTopK={rerankTopK}
              manifestItems={manifestItems}
              noteItems={noteItems}
              books={books}
              buildLogRef={buildLogRef}
              noteLogRef={noteLogRef}
              setFiles={setFiles}
              setMetadataMap={setMetadataMap}
              setBuildLogs={setBuildLogs}
              parseMetadataForFiles={parseMetadataForFiles}
              setForceRebuild={setForceRebuild}
              updateMetaField={updateMetaField}
              onBuild={onBuild}
              setNoteBookId={setNoteBookId}
              setNoteTitle={setNoteTitle}
              setNoteText={setNoteText}
              onUploadNote={onUploadNote}
              onDeleteFile={onDeleteFile}
              onDeleteNote={onDeleteNote}
              setFilterBookId={setFilterBookId}
              setFilterTitle={setFilterTitle}
              setFilterAuthor={setFilterAuthor}
              setFilterDomain={setFilterDomain}
              setEnablePageRange={setEnablePageRange}
              setMinPage={setMinPage}
              setMaxPage={setMaxPage}
              setUseReranker={setUseReranker}
              setRecallTopK={setRecallTopK}
              setRerankTopK={setRerankTopK}
              onClearHistory={onClearHistory}
            />
          </div>
        </aside>

        <main className="panel panel-center chat-dominant">
          <ChatWindow
            chatBoxRef={chatBoxRef}
            messages={messages}
            copiedMsgKey={copiedMsgKey}
            copyMarkdownRaw={copyMarkdownRaw}
            questionInput={questionInput}
            setQuestionInput={setQuestionInput}
            onAsk={onAsk}
          />
        </main>

        <aside className={`panel side-panel panel-right ${rightExpanded ? "expanded" : "collapsed"}`}>
          <button
            type="button"
            className="side-tab"
            onClick={toggleRightPanel}
            aria-expanded={rightExpanded}
            aria-label="切换来源面板"
          >
            <span className="side-tab-icon" aria-hidden="true" />
            <span className="side-tab-text">来源</span>
            <span className="side-tab-count">{activeSources.length}</span>
          </button>
          <div className="side-drawer-content">
            <SourcePanel sources={activeSources} />
          </div>
        </aside>
      </div>
    </div>
  );
}
