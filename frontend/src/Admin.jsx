import { useState, useEffect, useRef } from 'react';

const NOTICE_TYPE_LABELS = {
  holiday:        { label: 'Holiday',        icon: '🏖️', color: '#10b981' },
  exam_notice:    { label: 'Exam Notice',    icon: '📝', color: '#f59e0b' },
  fee_notice:     { label: 'Fee Notice',     icon: '💰', color: '#ef4444' },
  student_notice: { label: 'Student Notice', icon: '📢', color: '#6366f1' },
  scholarship:    { label: 'Scholarship',    icon: '🎓', color: '#8b5cf6' },
  internship:     { label: 'Internship',     icon: '💼', color: '#0ea5e9' },
  event_notice:   { label: 'Event',          icon: '📅', color: '#ec4899' },
  general:        { label: 'General',        icon: '📄', color: '#64748b' },
};

export default function Admin({ onBack }) {
  const [activeTab, setActiveTab] = useState('upload'); // 'upload' | 'notice'

  // ── Upload PDF state ───────────────────────────────────────────────────────
  const [documents, setDocuments] = useState([]);
  const [isLoadingDocs, setIsLoadingDocs] = useState(true);
  const [selectedFile, setSelectedFile] = useState(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadStep, setUploadStep] = useState('');
  const [uploadAlert, setUploadAlert] = useState(null);
  const [agentResult, setAgentResult] = useState(null);
  const fileInputRef = useRef(null);

  // ── Post Notice state ──────────────────────────────────────────────────────
  const [noticeTitle, setNoticeTitle] = useState('');
  const [noticeContent, setNoticeContent] = useState('');
  const [isPostingNotice, setIsPostingNotice] = useState(false);
  const [noticeAlert, setNoticeAlert] = useState(null);
  const [noticeResult, setNoticeResult] = useState(null);
  const [postedNotices, setPostedNotices] = useState([]);
  const [isLoadingNotices, setIsLoadingNotices] = useState(false);

  useEffect(() => {
    fetchDocuments();
    fetchPostedNotices();
  }, []);

  // ── Fetch functions ────────────────────────────────────────────────────────
  const fetchDocuments = async () => {
    setIsLoadingDocs(true);
    try {
      const res = await fetch('http://127.0.0.1:8000/api/admin/documents');
      if (res.ok) setDocuments(await res.json());
    } catch (e) {
      console.error('Failed to load documents', e);
    } finally {
      setIsLoadingDocs(false);
    }
  };

  const fetchPostedNotices = async () => {
    setIsLoadingNotices(true);
    try {
      const res = await fetch('http://127.0.0.1:8000/api/admin/notices-list');
      if (res.ok) setPostedNotices(await res.json());
    } catch (e) {
      console.error('Failed to load notices', e);
    } finally {
      setIsLoadingNotices(false);
    }
  };

  // ── Upload handlers ────────────────────────────────────────────────────────
  const handleFileSelect = (e) => {
    const file = e.target.files?.[0];
    if (file) {
      if (!file.name.toLowerCase().endsWith('.pdf')) {
        setUploadAlert({ type: 'error', text: 'Please select a valid PDF document.' });
        return;
      }
      setSelectedFile(file);
      setUploadAlert(null);
      setAgentResult(null);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    const file = e.dataTransfer.files?.[0];
    if (file) {
      if (!file.name.toLowerCase().endsWith('.pdf')) {
        setUploadAlert({ type: 'error', text: 'Only PDF documents are accepted.' });
        return;
      }
      setSelectedFile(file);
      setUploadAlert(null);
      setAgentResult(null);
    }
  };

  const handleUpload = async () => {
    if (!selectedFile) return;
    setIsUploading(true);
    setUploadAlert(null);
    setAgentResult(null);
    setUploadStep('📤 Uploading file to server...');

    const formData = new FormData();
    formData.append('file', selectedFile);

    try {
      const t1 = setTimeout(() => setUploadStep('🔍 Detecting content type (text vs tabular)...'), 1000);
      const t2 = setTimeout(() => setUploadStep('📊 Extracting & chunking content...'), 2500);
      const t3 = setTimeout(() => setUploadStep('🔧 Generating Gemini vector embeddings...'), 5000);
      const t4 = setTimeout(() => setUploadStep('☁️ Indexing into Supabase pgvector...'), 9000);
      const t5 = setTimeout(() => setUploadStep('🤖 Running agentic classifier pipeline...'), 13000);

      const res = await fetch('http://127.0.0.1:8000/api/admin/upload', {
        method: 'POST',
        body: formData,
      });

      [t1, t2, t3, t4, t5].forEach(clearTimeout);

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Upload failed');
      }

      const data = await res.json();
      const typeLabel = data.content_type_detected === 'tabular'
        ? '📊 Tabular (row-by-row NL)'
        : '📝 Text (paragraph chunks)';

      setUploadAlert({
        type: 'success',
        text: `🎉 Ingested '${selectedFile.name}' — ${typeLabel} | ${data.chunks_created} chunks indexed!`,
      });

      if (data.agent) {
        setAgentResult(data.agent);
      }

      setSelectedFile(null);
      if (fileInputRef.current) fileInputRef.current.value = '';
      fetchDocuments();
      fetchPostedNotices();
    } catch (err) {
      setUploadAlert({ type: 'error', text: err.message });
    } finally {
      setIsUploading(false);
      setUploadStep('');
    }
  };

  const handleDelete = async (filename) => {
    if (!window.confirm(`Remove '${filename}' from the RAG knowledge base?`)) return;
    try {
      const res = await fetch(`http://127.0.0.1:8000/api/admin/documents/${encodeURIComponent(filename)}`, {
        method: 'DELETE',
      });
      if (res.ok) {
        setUploadAlert({ type: 'success', text: `🗑️ Removed '${filename}' from database.` });
        fetchDocuments();
      } else {
        throw new Error('Failed to delete document');
      }
    } catch (err) {
      setUploadAlert({ type: 'error', text: err.message });
    }
  };

  // ── Notice handlers ────────────────────────────────────────────────────────
  const handlePostNotice = async (e) => {
    e.preventDefault();
    if (!noticeTitle.trim() || !noticeContent.trim()) {
      setNoticeAlert({ type: 'error', text: 'Both title and content are required.' });
      return;
    }
    setIsPostingNotice(true);
    setNoticeAlert(null);
    setNoticeResult(null);

    try {
      const res = await fetch('http://127.0.0.1:8000/api/admin/notices', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: noticeTitle, content: noticeContent }),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Failed to post notice');
      }

      const data = await res.json();
      setNoticeResult(data);
      setNoticeAlert({ type: 'success', text: '✅ Notice posted and pipeline completed!' });
      setNoticeTitle('');
      setNoticeContent('');
      fetchPostedNotices();
    } catch (err) {
      setNoticeAlert({ type: 'error', text: err.message });
    } finally {
      setIsPostingNotice(false);
    }
  };

  const formatDate = (iso) => {
    if (!iso) return '';
    return new Date(iso).toLocaleString('en-IN', {
      day: '2-digit', month: 'short', year: 'numeric',
      hour: '2-digit', minute: '2-digit',
    });
  };

  return (
    <div className="admin-portal-container">
      <header className="admin-header">
        <div className="admin-header-left">
          <div className="admin-badge-icon">🛡️</div>
          <div>
            <h1>Institutional Knowledge Admin Portal</h1>
            <p>Upload documents, post notices, and manage the AI knowledge base</p>
          </div>
        </div>
        <button type="button" className="admin-back-btn" onClick={onBack}>
          ← Back to Chat Assistant
        </button>
      </header>

      {/* Tab navigation */}
      <div className="admin-tabs">
        <button
          type="button"
          className={`admin-tab-btn ${activeTab === 'upload' ? 'active' : ''}`}
          onClick={() => setActiveTab('upload')}
        >
          📤 Upload PDF
        </button>
        <button
          type="button"
          className={`admin-tab-btn ${activeTab === 'notice' ? 'active' : ''}`}
          onClick={() => setActiveTab('notice')}
        >
          📢 Post Notice
        </button>
      </div>

      {/* ── Tab: Upload PDF ─────────────────────────────────────────────── */}
      {activeTab === 'upload' && (
        <div className="admin-content-grid">
          {/* Upload Card */}
          <section className="admin-card upload-card">
            <h2>📤 Ingest New PDF Document</h2>
            <p className="card-desc">
              Documents are automatically processed, embedded via Gemini, and indexed into Supabase.
              The AI agent will classify the document and dispatch notifications if it's a notice or circular.
            </p>

            {uploadAlert && (
              <div className={`admin-alert ${uploadAlert.type}`}>
                <span>{uploadAlert.text}</span>
                <button type="button" onClick={() => setUploadAlert(null)}>×</button>
              </div>
            )}

            {/* Agent result panel */}
            {agentResult && (
              <div className="agent-result-panel">
                <div className="agent-result-header">🤖 Agentic Pipeline Result</div>
                <div className="agent-result-body">
                  <div className="agent-stat">
                    <span className="agent-stat-label">Document Type</span>
                    <span className="agent-stat-value">
                      {NOTICE_TYPE_LABELS[agentResult.doc_type]?.icon || '📄'}{' '}
                      {NOTICE_TYPE_LABELS[agentResult.doc_type]?.label || agentResult.doc_type}
                    </span>
                  </div>
                  <div className="agent-stat">
                    <span className="agent-stat-label">Notifications Sent</span>
                    <span className="agent-stat-value" style={{ color: agentResult.notifications_sent > 0 ? '#10b981' : '#94a3b8' }}>
                      {agentResult.notification_skipped
                        ? '—  Skipped (general doc)'
                        : `✅ ${agentResult.notifications_sent} students notified`}
                    </span>
                  </div>
                </div>
              </div>
            )}

            <div
              className={`dropzone ${selectedFile ? 'has-file' : ''}`}
              onDrop={handleDrop}
              onDragOver={(e) => e.preventDefault()}
              onClick={() => !isUploading && fileInputRef.current?.click()}
            >
              <input
                type="file"
                ref={fileInputRef}
                onChange={handleFileSelect}
                accept=".pdf"
                style={{ display: 'none' }}
                disabled={isUploading}
              />
              {selectedFile ? (
                <div className="file-preview-info">
                  <span className="file-icon">📄</span>
                  <div className="file-details">
                    <strong>{selectedFile.name}</strong>
                    <span>{(selectedFile.size / (1024 * 1024)).toFixed(2)} MB</span>
                  </div>
                </div>
              ) : (
                <div className="dropzone-empty">
                  <div className="upload-cloud-icon">☁️</div>
                  <strong>Drag &amp; Drop PDF document here</strong>
                  <span>or click to browse local filesystem</span>
                </div>
              )}
            </div>

            {selectedFile && !isUploading && (
              <div className="upload-actions-row">
                <button type="button" className="cancel-file-btn" onClick={(e) => { e.stopPropagation(); setSelectedFile(null); }}>
                  Cancel
                </button>
                <button type="button" className="start-ingest-btn" onClick={handleUpload}>
                  🚀 Start Vector Ingestion
                </button>
              </div>
            )}

            {isUploading && (
              <div className="ingest-progress-box">
                <div className="progress-spinner"></div>
                <span className="progress-step-text">{uploadStep}</span>
              </div>
            )}
          </section>

          {/* Repository Table */}
          <section className="admin-card repo-card">
            <div className="repo-header-row">
              <div>
                <h2>📚 Ingested Knowledge Base Repository</h2>
                <p className="card-desc">Currently searchable documents in Supabase pgvector</p>
              </div>
              <button type="button" className="refresh-repo-btn" onClick={fetchDocuments} disabled={isLoadingDocs}>
                🔄 Refresh
              </button>
            </div>
            <div className="repo-table-wrapper">
              {isLoadingDocs ? (
                <div className="repo-loading">Fetching vector knowledge store...</div>
              ) : documents.length === 0 ? (
                <div className="repo-empty">No indexed documents found in database.</div>
              ) : (
                <table className="admin-repo-table">
                  <thead>
                    <tr>
                      <th>Source Document</th>
                      <th>Vector Chunks</th>
                      <th>Status</th>
                      <th style={{ textAlign: 'right' }}>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {documents.map((doc) => (
                      <tr key={doc.filename}>
                        <td className="doc-name-cell">
                          <span className="doc-icon">📄</span>
                          <span>{doc.filename}</span>
                        </td>
                        <td><span className="chunk-pill">{doc.chunks} chunks</span></td>
                        <td><span className="status-badge active">🟢 Searchable</span></td>
                        <td style={{ textAlign: 'right' }}>
                          <button
                            type="button"
                            className="delete-doc-btn"
                            onClick={() => handleDelete(doc.filename)}
                            title="Delete document & chunks"
                          >
                            🗑️ Remove
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </section>
        </div>
      )}

      {/* ── Tab: Post Notice ────────────────────────────────────────────── */}
      {activeTab === 'notice' && (
        <div className="admin-content-grid">
          {/* Notice Form Card */}
          <section className="admin-card upload-card">
            <h2>📢 Post a Notice</h2>
            <p className="card-desc">
              Write a notice targeting specific students or broadcast to all.
              Include 7-digit scholar IDs in the notice text — the AI agent will
              extract them automatically and send personalized in-app notifications.
              The notice is also indexed into the RAG knowledge base.
            </p>

            <div className="notice-hint-box">
              <strong>💡 Tips</strong>
              <ul>
                <li>Include scholar IDs (7 digits) for <strong>targeted</strong> notifications</li>
                <li>No scholar IDs → notice is <strong>broadcast</strong> to all students</li>
                <li>AI classifies notice type automatically (holiday, exam, fee, etc.)</li>
                <li>Notice is indexed so students can search it in the chat</li>
              </ul>
            </div>

            {noticeAlert && (
              <div className={`admin-alert ${noticeAlert.type}`}>
                <span>{noticeAlert.text}</span>
                <button type="button" onClick={() => setNoticeAlert(null)}>×</button>
              </div>
            )}

            {/* Agent pipeline result */}
            {noticeResult && (
              <div className="agent-result-panel">
                <div className="agent-result-header">🤖 Agentic Pipeline Result</div>
                <div className="agent-result-body">
                  <div className="agent-stat">
                    <span className="agent-stat-label">Notice Type</span>
                    <span className="agent-stat-value">
                      {noticeResult.icon} {NOTICE_TYPE_LABELS[noticeResult.notice_type]?.label || noticeResult.notice_type}
                    </span>
                  </div>
                  <div className="agent-stat">
                    <span className="agent-stat-label">Audience</span>
                    <span className="agent-stat-value">
                      {noticeResult.is_broadcast ? '📡 All Students (Broadcast)' : `🎯 ${noticeResult.scholar_ids_found.length} targeted`}
                    </span>
                  </div>
                  <div className="agent-stat">
                    <span className="agent-stat-label">Notifications Sent</span>
                    <span className="agent-stat-value" style={{ color: '#10b981' }}>
                      ✅ {noticeResult.students_notified} students
                    </span>
                  </div>
                  {noticeResult.scholar_ids_not_found?.length > 0 && (
                    <div className="agent-stat">
                      <span className="agent-stat-label">⚠️ IDs Not Found</span>
                      <span className="agent-stat-value" style={{ color: '#f59e0b' }}>
                        {noticeResult.scholar_ids_not_found.join(', ')}
                      </span>
                    </div>
                  )}
                  <div className="agent-stat">
                    <span className="agent-stat-label">RAG Indexed</span>
                    <span className="agent-stat-value" style={{ color: '#6366f1' }}>
                      📚 {noticeResult.rag_chunks_indexed} chunk(s)
                    </span>
                  </div>
                </div>
              </div>
            )}

            <form onSubmit={handlePostNotice} className="notice-form">
              <div className="notice-field">
                <label htmlFor="notice-title">Notice Title</label>
                <input
                  id="notice-title"
                  type="text"
                  placeholder="e.g. Fee Payment Reminder – July 2026"
                  value={noticeTitle}
                  onChange={(e) => setNoticeTitle(e.target.value)}
                  disabled={isPostingNotice}
                />
              </div>
              <div className="notice-field">
                <label htmlFor="notice-content">Notice Content</label>
                <textarea
                  id="notice-content"
                  rows={7}
                  placeholder={`Write your notice here.\n\nExample:\nStudents with scholar IDs 2023001, 2023002, and 2023003 are required to submit their internship forms by July 15, 2026. Failure to do so will result in a fine.`}
                  value={noticeContent}
                  onChange={(e) => setNoticeContent(e.target.value)}
                  disabled={isPostingNotice}
                />
              </div>
              <button type="submit" className="start-ingest-btn" disabled={isPostingNotice}>
                {isPostingNotice ? (
                  <><span className="btn-spinner"></span> Processing Notice Pipeline...</>
                ) : (
                  '🚀 Post Notice & Dispatch Notifications'
                )}
              </button>
            </form>
          </section>

          {/* Posted Notices List */}
          <section className="admin-card repo-card">
            <div className="repo-header-row">
              <div>
                <h2>📋 Posted Notices</h2>
                <p className="card-desc">All notices dispatched through the agentic pipeline</p>
              </div>
              <button type="button" className="refresh-repo-btn" onClick={fetchPostedNotices} disabled={isLoadingNotices}>
                🔄 Refresh
              </button>
            </div>
            <div className="repo-table-wrapper">
              {isLoadingNotices ? (
                <div className="repo-loading">Loading notices...</div>
              ) : postedNotices.length === 0 ? (
                <div className="repo-empty">No notices posted yet.</div>
              ) : (
                <div className="notices-list">
                  {postedNotices.map((notice) => {
                    const typeInfo = NOTICE_TYPE_LABELS[notice.notice_type] || NOTICE_TYPE_LABELS.general;
                    return (
                      <div key={notice.id} className="notice-list-item">
                        <div className="notice-list-icon" style={{ background: `${typeInfo.color}22`, color: typeInfo.color }}>
                          {typeInfo.icon}
                        </div>
                        <div className="notice-list-body">
                          <div className="notice-list-title">{notice.title}</div>
                          <div className="notice-list-meta">
                            <span className="notice-type-chip" style={{ background: `${typeInfo.color}22`, color: typeInfo.color }}>
                              {typeInfo.label}
                            </span>
                            <span className="notice-source-chip">
                              {notice.source_type === 'pdf' ? '📄 PDF' : '✏️ Text'}
                            </span>
                            {notice.is_broadcast ? (
                              <span className="notice-audience-chip broadcast">📡 All Students</span>
                            ) : (
                              <span className="notice-audience-chip targeted">🎯 {notice.scholar_ids?.length || 0} targeted</span>
                            )}
                            <span className="notice-sent-chip">
                              ✅ {notice.notified_count} notified
                            </span>
                          </div>
                          <div className="notice-list-date">{formatDate(notice.created_at)}</div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
