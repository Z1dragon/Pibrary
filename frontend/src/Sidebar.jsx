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
  return (
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

      <button className="danger" onClick={onClearHistory}>
        🗑️ 清除对话历史
      </button>
    </aside>
  );
}
