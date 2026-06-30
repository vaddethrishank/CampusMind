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
  const [activeTab, setActiveTab] = useState('upload'); // 'upload' | 'notice' | 'complaints'

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

  // ── Complaints state ───────────────────────────────────────────────────────
  const [complaints, setComplaints] = useState([]);
  const [isLoadingComplaints, setIsLoadingComplaints] = useState(false);
  const [complaintStatusFilter, setComplaintStatusFilter] = useState('');
  const [complaintCategoryFilter, setComplaintCategoryFilter] = useState('');
  const [updatingComplaintId, setUpdatingComplaintId] = useState(null);

  useEffect(() => {
    fetchDocuments();
    fetchPostedNotices();
    fetchComplaints();
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

  const fetchComplaints = async (status = '', category = '') => {
    setIsLoadingComplaints(true);
    try {
      const params = new URLSearchParams();
      if (status)   params.append('status',   status);
      if (category) params.append('category', category);
      const res = await fetch(`http://127.0.0.1:8000/api/admin/complaints?${params}`);
      if (res.ok) setComplaints(await res.json());
    } catch (e) {
      console.error('Failed to load complaints', e);
    } finally {
      setIsLoadingComplaints(false);
    }
  };

  const updateComplaintStatus = async (complaintId, newStatus) => {
    setUpdatingComplaintId(complaintId);
    try {
      const res = await fetch(`http://127.0.0.1:8000/api/admin/complaints/${complaintId}/status`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: newStatus }),
      });
      if (res.ok) {
        // Optimistic UI update
        setComplaints(prev => prev.map(c =>
          c.id === complaintId
            ? { ...c, status: newStatus,
                status_icon: newStatus === 'open' ? '🔴' : newStatus === 'in_progress' ? '🟡' : newStatus === 'resolved' ? '🟢' : '⚫',
                status_label: newStatus === 'open' ? 'Open' : newStatus === 'in_progress' ? 'In Progress' : newStatus === 'resolved' ? 'Resolved' : 'Dismissed' }
            : c
        ));
      }
    } catch (e) {
      console.error('Failed to update status', e);
    } finally {
      setUpdatingComplaintId(null);
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
        <button
          type="button"
          className={`admin-tab-btn ${activeTab === 'complaints' ? 'active' : ''}`}
          onClick={() => { setActiveTab('complaints'); fetchComplaints(complaintStatusFilter, complaintCategoryFilter); }}
        >
          🚨 Complaints
          {complaints.filter(c => c.status === 'open').length > 0 && (
            <span className="admin-tab-badge">{complaints.filter(c => c.status === 'open').length}</span>
          )}
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

      {/* ── Tab: Complaints ─────────────────────────────────────────────── */}
      {activeTab === 'complaints' && (
        <div className="admin-content-grid" style={{ gridTemplateColumns: '1fr' }}>
          <section className="admin-card" style={{ gridColumn: '1 / -1' }}>
            <div className="repo-header-row">
              <div>
                <h2>🚨 Student Complaints</h2>
                <p className="card-desc">All complaints submitted through the chat portal</p>
              </div>
              <button type="button" className="refresh-repo-btn"
                onClick={() => fetchComplaints(complaintStatusFilter, complaintCategoryFilter)}
                disabled={isLoadingComplaints}
              >🔄 Refresh</button>
            </div>

            {/* Filters */}
            <div className="complaint-filters">
              <div className="complaint-filter-group">
                <span className="filter-label">Status:</span>
                {['', 'open', 'in_progress', 'resolved', 'dismissed'].map(s => (
                  <button
                    key={s}
                    type="button"
                    className={`filter-chip ${complaintStatusFilter === s ? 'active' : ''}`}
                    onClick={() => { setComplaintStatusFilter(s); fetchComplaints(s, complaintCategoryFilter); }}
                  >
                    {s === '' ? 'All' : s === 'in_progress' ? 'In Progress' : s.charAt(0).toUpperCase() + s.slice(1)}
                  </button>
                ))}
              </div>
              <div className="complaint-filter-group">
                <span className="filter-label">Category:</span>
                {['', 'hostel', 'academic', 'admin', 'facility', 'mess', 'transport', 'general'].map(c => (
                  <button
                    key={c}
                    type="button"
                    className={`filter-chip ${complaintCategoryFilter === c ? 'active' : ''}`}
                    onClick={() => { setComplaintCategoryFilter(c); fetchComplaints(complaintStatusFilter, c); }}
                  >
                    {c === '' ? 'All' : c.charAt(0).toUpperCase() + c.slice(1)}
                  </button>
                ))}
              </div>
            </div>

            {/* Complaints List */}
            <div className="complaints-list">
              {isLoadingComplaints ? (
                <div className="repo-loading">Loading complaints...</div>
              ) : complaints.length === 0 ? (
                <div className="repo-empty">No complaints found.</div>
              ) : (
                complaints.map(c => (
                  <div key={c.id} className={`complaint-admin-card complaint-status-${c.status}`}>
                    <div className="complaint-admin-card-header">
                      <div className="complaint-admin-card-left">
                        <span className="complaint-admin-category-icon">{c.category_icon}</span>
                        <div>
                          <div className="complaint-admin-title">{c.title}</div>
                          <div className="complaint-admin-meta">
                            <span className="complaint-status-badge" data-status={c.status}>
                              {c.status_icon} {c.status_label}
                            </span>
                            <span className="complaint-admin-scholar">
                              🎓 {c.scholar_id || 'Unknown'}
                            </span>
                            <span className="complaint-admin-student">{c.student_name}</span>
                            <span className="complaint-vote-pill">👥 {c.vote_count} {c.vote_count === 1 ? 'student' : 'students'}</span>
                            <span className="complaint-admin-date">{formatDate(c.created_at)}</span>
                          </div>
                        </div>
                      </div>
                    </div>

                    <p className="complaint-admin-description">{c.description}</p>

                    {/* Hostel details if available */}
                    {c.hostel_details && Object.keys(c.hostel_details).filter(k => !['raw_chunk','source_doc'].includes(k)).length > 0 && (
                      <div className="complaint-admin-hostel">
                        <div className="complaint-hostel-title">🏠 Hostel Details (auto-enriched)</div>
                        <div className="complaint-hostel-grid">
                          {Object.entries(c.hostel_details)
                            .filter(([k]) => !['raw_chunk', 'source_doc'].includes(k))
                            .slice(0, 6)
                            .map(([k, v]) => (
                              <div key={k} className="complaint-hostel-item">
                                <span className="complaint-hostel-key">{k.replace(/_/g, ' ')}</span>
                                <span className="complaint-hostel-val">{v}</span>
                              </div>
                            ))}
                        </div>
                      </div>
                    )}

                    {/* Status action buttons */}
                    <div className="complaint-admin-actions">
                      {c.status !== 'in_progress' && c.status !== 'resolved' && c.status !== 'dismissed' && (
                        <button
                          type="button"
                          className="complaint-action-btn in-progress"
                          onClick={() => updateComplaintStatus(c.id, 'in_progress')}
                          disabled={updatingComplaintId === c.id}
                        >
                          🟡 Mark In Progress
                        </button>
                      )}
                      {c.status !== 'resolved' && c.status !== 'dismissed' && (
                        <button
                          type="button"
                          className="complaint-action-btn resolve"
                          onClick={() => updateComplaintStatus(c.id, 'resolved')}
                          disabled={updatingComplaintId === c.id}
                        >
                          🟢 Resolve
                        </button>
                      )}
                      {c.status !== 'dismissed' && c.status !== 'resolved' && (
                        <button
                          type="button"
                          className="complaint-action-btn dismiss"
                          onClick={() => updateComplaintStatus(c.id, 'dismissed')}
                          disabled={updatingComplaintId === c.id}
                        >
                          ⚫ Dismiss
                        </button>
                      )}
                      {(c.status === 'resolved' || c.status === 'dismissed') && (
                        <button
                          type="button"
                          className="complaint-action-btn reopen"
                          onClick={() => updateComplaintStatus(c.id, 'open')}
                          disabled={updatingComplaintId === c.id}
                        >
                          🔴 Reopen
                        </button>
                      )}
                    </div>
                  </div>
                ))
              )}
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
