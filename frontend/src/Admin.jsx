import { useState, useEffect, useRef } from 'react';

export default function Admin({ onBack }) {
  const [documents, setDocuments] = useState([]);
  const [isLoadingDocs, setIsLoadingDocs] = useState(true);
  const [selectedFile, setSelectedFile] = useState(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadStep, setUploadStep] = useState('');
  const [alertMsg, setAlertMsg] = useState(null); // { type: 'success' | 'error', text: '' }

  const fileInputRef = useRef(null);

  useEffect(() => {
    fetchDocuments();
  }, []);

  const fetchDocuments = async () => {
    setIsLoadingDocs(true);
    try {
      const res = await fetch('http://127.0.0.1:8000/api/admin/documents');
      if (res.ok) {
        const data = await res.json();
        setDocuments(data);
      }
    } catch (e) {
      console.error('Failed to load documents', e);
    } finally {
      setIsLoadingDocs(false);
    }
  };

  const handleFileSelect = (e) => {
    const file = e.target.files?.[0];
    if (file) {
      if (!file.name.toLowerCase().endsWith('.pdf')) {
        setAlertMsg({ type: 'error', text: 'Please select a valid PDF document.' });
        return;
      }
      setSelectedFile(file);
      setAlertMsg(null);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    const file = e.dataTransfer.files?.[0];
    if (file) {
      if (!file.name.toLowerCase().endsWith('.pdf')) {
        setAlertMsg({ type: 'error', text: 'Only PDF documents are accepted.' });
        return;
      }
      setSelectedFile(file);
      setAlertMsg(null);
    }
  };

  const handleDragOver = (e) => {
    e.preventDefault();
  };

  const handleUpload = async () => {
    if (!selectedFile) return;

    setIsUploading(true);
    setAlertMsg(null);
    setUploadStep('📤 Uploading file to server...');

    const formData = new FormData();
    formData.append('file', selectedFile);

    try {
      const progressTimer1 = setTimeout(() => setUploadStep('🔍 Detecting content type (text vs tabular)...'), 1000);
      const progressTimer2 = setTimeout(() => setUploadStep('📊 Extracting & converting table rows to natural language...'), 2500);
      const progressTimer3 = setTimeout(() => setUploadStep('🔧 Google Gemini generating 3072-dim vector embeddings...'), 5000);
      const progressTimer4 = setTimeout(() => setUploadStep('☁️ Indexing chunks into Supabase pgvector database...'), 9000);

      const res = await fetch('http://127.0.0.1:8000/api/admin/upload', {
        method: 'POST',
        body: formData,
      });

      clearTimeout(progressTimer1);
      clearTimeout(progressTimer2);
      clearTimeout(progressTimer3);
      clearTimeout(progressTimer4);

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Upload failed');
      }

      const data = await res.json();
      const typeLabel = data.content_type_detected === 'tabular' ? '📊 Tabular (row-by-row NL)' : '📝 Text (paragraph chunks)';
      setAlertMsg({
        type: 'success',
        text: `🎉 Ingested '${selectedFile.name}' — ${typeLabel} | ${data.chunks_created} vector chunks indexed!`,
      });
      setSelectedFile(null);
      if (fileInputRef.current) fileInputRef.current.value = '';
      fetchDocuments();
    } catch (err) {
      setAlertMsg({ type: 'error', text: err.message });
    } finally {
      setIsUploading(false);
      setUploadStep('');
    }
  };

  const handleDelete = async (filename) => {
    if (!window.confirm(`Are you sure you want to remove '${filename}' from the RAG knowledge base?`)) return;

    try {
      const res = await fetch(`http://127.0.0.1:8000/api/admin/documents/${encodeURIComponent(filename)}`, {
        method: 'DELETE',
      });
      if (res.ok) {
        setAlertMsg({ type: 'success', text: `🗑️ Removed '${filename}' from database.` });
        fetchDocuments();
      } else {
        throw new Error('Failed to delete document');
      }
    } catch (err) {
      setAlertMsg({ type: 'error', text: err.message });
    }
  };

  return (
    <div className="admin-portal-container">
      <header className="admin-header">
        <div className="admin-header-left">
          <div className="admin-badge-icon">🛡️</div>
          <div>
            <h1>Institutional Knowledge Admin Portal</h1>
            <p>Upload, vectorize, and manage RAG institutional documents</p>
          </div>
        </div>
        <button type="button" className="admin-back-btn" onClick={onBack}>
          ← Back to Chat Assistant
        </button>
      </header>

      <div className="admin-content-grid">
        {/* Upload Card */}
        <section className="admin-card upload-card">
          <h2>📤 Ingest New PDF Document</h2>
          <p className="card-desc">Documents uploaded here are automatically processed by LangChain, embedded via Gemini, and indexed into Supabase.</p>

          {alertMsg && (
            <div className={`admin-alert ${alertMsg.type}`}>
              <span>{alertMsg.text}</span>
              <button type="button" onClick={() => setAlertMsg(null)}>×</button>
            </div>
          )}

          <div 
            className={`dropzone ${selectedFile ? 'has-file' : ''}`}
            onDrop={handleDrop}
            onDragOver={handleDragOver}
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
                <strong>Drag & Drop PDF document here</strong>
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

        {/* Repository Table Card */}
        <section className="admin-card repo-card">
          <div className="repo-header-row">
            <div>
              <h2>📚 Ingested Knowledge Base Repository</h2>
              <p className="card-desc">Currently searchable documents in Supabase pgvector</p>
            </div>
            <button type="button" className="refresh-repo-btn" onClick={fetchDocuments} title="Refresh List" disabled={isLoadingDocs}>
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
                      <td>
                        <span className="chunk-pill">{doc.chunks} chunks</span>
                      </td>
                      <td>
                        <span className="status-badge active">🟢 Searchable</span>
                      </td>
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
    </div>
  );
}
