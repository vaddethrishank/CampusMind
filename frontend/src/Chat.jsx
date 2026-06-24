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
  
  // Chat History State
  const [chatSessions, setChatSessions] = useState([]);
  const [activeChatId, setActiveChatId] = useState(null);

  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  useEffect(() => {
    fetchChats();
  }, [user.id]);

  const fetchChats = async () => {
    try {
      const response = await fetch(`http://127.0.0.1:8000/api/chats?user_id=${user.id}`);
      if (response.ok) {
        const data = await response.json();
        setChatSessions(data);
      }
    } catch (e) {
      console.error('Failed to fetch chats', e);
    }
  };

  const loadChat = async (chatId) => {
    setActiveChatId(chatId);
    setMessages([]);
    setIsLoading(true);
    try {
      const response = await fetch(`http://127.0.0.1:8000/api/chats/${chatId}/messages`);
      if (response.ok) {
        const data = await response.json();
        setMessages(data);
      }
    } catch (e) {
      console.error('Failed to load chat messages', e);
    } finally {
      setIsLoading(false);
    }
  };

  const handleNewChat = () => {
    setActiveChatId(null);
    setMessages([]);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!input.trim()) return;

    const userMessage = { role: 'user', content: input };
    setMessages((prev) => [...prev, userMessage]);
    setInput('');
    setIsLoading(true);

    const metadata_filter = selectedSource ? { source: selectedSource } : null;

    try {
      const payload = { 
        query: input, 
        metadata_filter, 
        user_info: user 
      };
      if (activeChatId) {
        payload.chat_id = activeChatId;
      }

      const response = await fetch('http://127.0.0.1:8000/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
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

      if (!activeChatId && data.chat_id) {
        setActiveChatId(data.chat_id);
        fetchChats();
      }
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
    <>
      <div className="sidebar">
        <button className="new-chat-btn" onClick={handleNewChat}>
          + New Chat
        </button>
        <div className="chat-history-list">
          {chatSessions.map((chat) => (
            <div 
              key={chat.id} 
              className={`history-item ${activeChatId === chat.id ? 'active' : ''}`}
              onClick={() => loadChat(chat.id)}
              title={chat.title}
            >
              {chat.title}
            </div>
          ))}
        </div>
        <div className="user-profile-header" style={{ marginTop: 'auto', borderBottom: 'none', paddingTop: '1rem', borderTop: '1px solid var(--surface-border)' }}>
          <div className="user-info">
            <div className="user-avatar">
              {user?.name ? user.name.charAt(0) : '?'}
            </div>
            <div className="user-details" style={{ overflow: 'hidden' }}>
              <span className="user-name" style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{user?.name || 'User'}</span>
            </div>
          </div>
          <button onClick={onLogout} className="logout-btn" style={{ padding: '0.5rem' }}>
            Out
          </button>
        </div>
      </div>

      <div className="main-chat-area">
        <div className="chat-container">
          <header className="chat-header">
            <h1>CampusMind Assistant</h1>
          </header>

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
            {messages.length === 0 && !isLoading && (
              <div style={{ textAlign: 'center', marginTop: 'auto', marginBottom: 'auto', color: 'var(--surface-border)' }}>
                <h2>How can I help you today?</h2>
              </div>
            )}
            {messages.map((msg, idx) => (
              <div key={idx} className={`message-wrapper ${msg.role}`}>
                <div className={`message ${msg.role}`}>
                  <p style={{ whiteSpace: 'pre-wrap' }}>{msg.content}</p>
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
    </>
  );
}
