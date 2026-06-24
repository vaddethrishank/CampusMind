import { useState, useRef, useEffect } from 'react';

// Known PDF sources — extend this list to match your ingested files
const KNOWN_SOURCES = [
  { label: 'All Sources', value: null },
  { label: 'Syllabus', value: 'syllabus.pdf' },
  { label: 'Notes', value: 'notes.pdf' },
  { label: 'Handbook', value: 'handbook.pdf' },
];

export default function Chat({ user, onLogout }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [selectedSource, setSelectedSource] = useState(null);
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!input.trim()) return;

    const userMessage = { role: 'user', content: input };
    setMessages((prev) => [...prev, userMessage]);
    setInput('');
    setIsLoading(true);

    // Build metadata filter — only include when a source is selected
    const metadata_filter = selectedSource ? { source: selectedSource } : null;

    try {
      const response = await fetch('http://127.0.0.1:8000/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: input, metadata_filter, user_info: user }),
      });

      if (!response.ok) throw new Error('Network response was not ok');

      const data = await response.json();

      const botMessage = {
        role: 'bot',
        content: data.answer,
        context: data.context,
        metadata: data.metadata,
      };

      setMessages((prev) => [...prev, botMessage]);
    } catch (error) {
      console.error('Error:', error);
      const errorMessage = {
        role: 'bot',
        content: 'Sorry, I encountered an error. Please try again later. Is the backend running?',
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div className="user-profile-header">
        <div className="user-info">
          <div className="user-avatar">
            {user?.name ? user.name.charAt(0) : '?'}
          </div>
          <div className="user-details">
            <span className="user-name">{user?.name || 'User'}</span>
            <span className="user-scholar">ID: {user?.scholar_id || 'N/A'}</span>
          </div>
        </div>
        <button onClick={onLogout} className="logout-btn">
          Logout
        </button>
      </div>

      <div className="chat-container">
        <header className="chat-header">
          <h1>CampusMind Assistant</h1>
        </header>

      {/* ── Metadata filter pill row ── */}
      <div className="filter-bar" role="group" aria-label="Filter by source document">
        <span className="filter-label">Filter:</span>
        {KNOWN_SOURCES.map((src) => (
          <button
            key={src.label}
            type="button"
            className={`filter-chip ${selectedSource === src.value ? 'active' : ''}`}
            onClick={() => setSelectedSource(src.value)}
            aria-pressed={selectedSource === src.value}
          >
            {src.label}
          </button>
        ))}
      </div>

      <div className="chat-messages">
        {messages.map((msg, idx) => (
          <div key={idx} className={`message-wrapper ${msg.role}`}>
            <div className={`message ${msg.role}`}>
              <p>{msg.content}</p>
              {msg.metadata && msg.metadata.length > 0 && (
                <div className="sources">
                  <strong>Sources:</strong>
                  <ul>
                    {msg.metadata.map((meta, i) => {
                      const fileName = meta.source
                        ? meta.source.split(/[\\/]/).pop()
                        : 'Unknown';
                      const page = meta.page != null ? ` · p.${meta.page + 1}` : '';
                      return (
                        <li key={i}>
                          <span className="source-chip">
                            📄 {fileName}{page}
                          </span>
                          <span className="source-snippet">
                            {msg.context?.[i]?.substring(0, 100)}…
                          </span>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              )}
            </div>
          </div>
        ))}
        {isLoading && (
          <div className="message-wrapper bot">
            <div className="message bot loading">Thinking...</div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      <form className="chat-input-form" onSubmit={handleSubmit}>
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={
            selectedSource
              ? `Ask about ${selectedSource}…`
              : 'Ask me anything…'
          }
          disabled={isLoading}
        />
        <button type="submit" disabled={isLoading || !input.trim()}>
          Send
        </button>
      </form>
    </div>
    </div>
  );
}
