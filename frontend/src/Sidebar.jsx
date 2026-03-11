import { useRef, useState } from "react";

export default function Sidebar({
  config,
  files,
  metadataMap,
  forceRebuild,
  buildSubmitting,
  noteSubmitting,
  buildLogs,
  noteLogs,
  noteBookId,
  noteTitle,
  noteText,
  filterBookId,
  filterTitle,
  filterAuthor,
  filterDomain,
  enablePageRange,
  minPage,
  maxPage,
  useReranker,
  recallTopK,
  rerankTopK,
  manifestItems,
  noteItems,
  books,
  buildLogRef,
  noteLogRef,
  setFiles,
  setMetadataMap,
  setBuildLogs,
  parseMetadataForFiles,
  setForceRebuild,
  updateMetaField,
  onBuild,
  setNoteBookId,
  setNoteTitle,
  setNoteText,
  onUploadNote,
  onDeleteFile,
  onDeleteNote,
  setFilterBookId,
  setFilterTitle,
  setFilterAuthor,
  setFilterDomain,
  setEnablePageRange,
  setMinPage,
  setMaxPage,
  setUseReranker,
  setRecallTopK,
  setRerankTopK,
  onClearHistory,
}) {
  const fileInputRef = useRef(null);
  const [isDragging, setIsDragging] = useState(false);
  const [activeCategory, setActiveCategory] = useState("all");

  async function handleSelectedFiles(selectedFiles) {
    setFiles(selectedFiles);
    setMetadataMap({});
    setBuildLogs([]);
    if (!selectedFiles.length) {
      return;
    }
    await parseMetadataForFiles(selectedFiles);
  }

  async function onFileInputChange(event) {
    const selectedFiles = Array.from(event.target.files || []);
    await handleSelectedFiles(selectedFiles);
  }

  async function onDropFiles(event) {
    event.preventDefault();
    event.stopPropagation();
    setIsDragging(false);
    const selectedFiles = Array.from(event.dataTransfer.files || []);
    await handleSelectedFiles(selectedFiles);
  }

  const fileCategoryItems = [
    ...manifestItems.map((item) => ({
      key: `book_${item.file_path}`,
      category: "book",
      title: item.title || item.file_name,
      subtitle: `${item.author || "未知作者"} · ${item.domain || ""}`,
      extra: `${item.chunk_count} 切片`,
      action: () => onDeleteFile(item),
      actionLabel: "删除",
    })),
    ...noteItems.map((item) => ({
      key: `note_${item.note_id}`,
      category: "note",
      title: item.note_title || item.note_id,
      subtitle: `${item.title || "未关联书名"} · ${item.book_id || ""}`,
      extra: `${item.chunk_count || 0} 切片`,
      action: () => onDeleteNote(item),
      actionLabel: "删除",
    })),
  ];

  const visibleCategoryItems = fileCategoryItems.filter((item) => {
    if (activeCategory === "all") return true;
    if (activeCategory === "book") return item.category === "book";
    return item.category === "note";
  });

  return (
    <div className="left-panel-body">
      <section className="ui-card">
        <div className="panel-title-row">
          <h2>知识库文件</h2>
          <span className="muted-text">{fileCategoryItems.length}</span>
        </div>
        <p className="muted-text">支持格式：{(config?.supported_extensions || []).join(", ")}</p>

        <div
          className={`dropzone ${isDragging ? "is-dragging" : ""}`}
          onClick={() => fileInputRef.current?.click()}
          onDragEnter={(event) => {
            event.preventDefault();
            event.stopPropagation();
            setIsDragging(true);
          }}
          onDragOver={(event) => {
            event.preventDefault();
            event.stopPropagation();
          }}
          onDragLeave={(event) => {
            event.preventDefault();
            event.stopPropagation();
            setIsDragging(false);
          }}
          onDrop={onDropFiles}
          role="button"
          tabIndex={0}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") {
              fileInputRef.current?.click();
            }
          }}
        >
          <div className="dropzone-icon" aria-hidden="true" />
          <p>拖拽文件到此处，或点击上传</p>
        </div>
        <input ref={fileInputRef} type="file" multiple className="hidden-input" onChange={onFileInputChange} />

        <label className="checkbox-line">
          <input
            type="checkbox"
            checked={forceRebuild}
            onChange={(event) => setForceRebuild(event.target.checked)}
          />
          强制重建同名文档
        </label>
        <button className="btn-dark" disabled={buildSubmitting} onClick={onBuild}>
          构建知识库
        </button>
      </section>

      {!!files.length && (
        <section className="ui-card">
          <h3>元数据编辑</h3>
          <div className="meta-forms">
            {files.map((file) => {
              const meta = metadataMap[file.name] || {};
              const domains = config?.valid_domains || [];
              const selectedDomain = meta.domain || domains[0] || "";
              return (
                <div className="meta-item" key={file.name}>
                  <h4>{file.name}</h4>
                  <div className="meta-grid">
                    <input
                      value={meta.book_id || ""}
                      placeholder="book_id"
                      onChange={(e) => updateMetaField(file.name, "book_id", e.target.value)}
                    />
                    <input
                      value={meta.title || file.name}
                      placeholder="标题"
                      onChange={(e) => updateMetaField(file.name, "title", e.target.value)}
                    />
                    <input
                      value={meta.author || "未知作者"}
                      placeholder="作者"
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
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      )}

      <section className="ui-card">
        <div className="category-tabs">
          <button
            type="button"
            className={activeCategory === "all" ? "tab-btn active" : "tab-btn"}
            onClick={() => setActiveCategory("all")}
          >
            全部
          </button>
          <button
            type="button"
            className={activeCategory === "book" ? "tab-btn active" : "tab-btn"}
            onClick={() => setActiveCategory("book")}
          >
            文档
          </button>
          <button
            type="button"
            className={activeCategory === "note" ? "tab-btn active" : "tab-btn"}
            onClick={() => setActiveCategory("note")}
          >
            笔记
          </button>
        </div>

        <div className="manifest-list">
          {!visibleCategoryItems.length ? (
            <div className="manifest-item">暂无可展示文件</div>
          ) : (
            visibleCategoryItems.map((item) => (
              <div className="manifest-item" key={item.key}>
                <div className="title">{item.title}</div>
                <div>{item.subtitle}</div>
                <div>{item.extra}</div>
                <button type="button" className="btn-ghost" onClick={item.action}>
                  {item.actionLabel}
                </button>
              </div>
            ))
          )}
        </div>
      </section>

      <section className="ui-card">
        <h3>笔记上传</h3>
        <select value={noteBookId} onChange={(e) => setNoteBookId(e.target.value)}>
          {!books.length ? (
            <option value="">请先构建书籍文档</option>
          ) : (
            books.map((book, index) => (
              <option key={`${book.book_id || ""}_${book.file_name || ""}_${index}`} value={book.book_id || ""}>
                {`${book.title || book.file_name} (${book.book_id || ""})`}
              </option>
            ))
          )}
        </select>
        <input placeholder="笔记标题" value={noteTitle} onChange={(e) => setNoteTitle(e.target.value)} />
        <textarea
          rows="4"
          placeholder="输入与书籍关联的笔记内容"
          value={noteText}
          onChange={(e) => setNoteText(e.target.value)}
        />
        <button className="btn-dark" disabled={noteSubmitting} onClick={onUploadNote}>
          上传笔记
        </button>
      </section>

      <details className="ui-card compact-card">
        <summary>检索参数与过滤</summary>
        <div className="form-stack">
          <input placeholder="book_id" value={filterBookId} onChange={(e) => setFilterBookId(e.target.value)} />
          <input placeholder="标题" value={filterTitle} onChange={(e) => setFilterTitle(e.target.value)} />
          <input placeholder="作者" value={filterAuthor} onChange={(e) => setFilterAuthor(e.target.value)} />
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

          <label className="checkbox-line">
            <input
              type="checkbox"
              checked={useReranker}
              onChange={(e) => setUseReranker(e.target.checked)}
            />
            启用重排序
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
          <button type="button" className="btn-ghost" onClick={onClearHistory}>
            清除会话历史
          </button>
        </div>
      </details>

      <details className="ui-card compact-card">
        <summary>系统日志</summary>
        <pre ref={buildLogRef} className="log">
          {buildLogs.join("\n")}
        </pre>
        <pre ref={noteLogRef} className="log">
          {noteLogs.join("\n")}
        </pre>
      </details>
    </div>
  );
}
