import { useState, useRef, useEffect } from 'react';

// Known PDF sources — extend this list to match your ingested files
const KNOWN_SOURCES = [
  { label: 'All Sources', value: null },
  { label: 'Syllabus', value: 'syllabus.pdf' },
  { label: 'Notes', value: 'notes.pdf' },
  { label: 'Handbook', value: 'handbook.pdf' },
];

export default function Chat({ user, onLogout, onOpenAdmin }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [selectedSource, setSelectedSource] = useState(null);
  
  // Chat History State
  const [chatSessions, setChatSessions] = useState([]);
  const [activeChatId, setActiveChatId] = useState(null);

  // Notification Center State
  const [showNotifications, setShowNotifications] = useState(false);
  const [notifFilter, setNotifFilter] = useState('all');
  const [notifications, setNotifications] = useState([]);
  const [notifLoading, setNotifLoading] = useState(false);
  const notifPollRef = useRef(null);

  // Fetch notifications from the DB
  const fetchNotifications = async () => {
    if (!user?.id) return;
    try {
      const res = await fetch(`http://127.0.0.1:8000/api/notifications?user_id=${user.id}`);
      if (res.ok) {
        const data = await res.json();
        // Map DB shape to component shape
        setNotifications(data.map(n => ({
          id:      n.id,
          title:   n.notification_title,
          message: n.notification_message,
          time:    formatNotifTime(n.created_at),
          unread:  !n.is_read,
          icon:    n.icon || '📢',
        })));
      }
    } catch (e) {
      console.error('Failed to fetch notifications', e);
    }
  };

  const formatNotifTime = (iso) => {
    if (!iso) return '';
    const diff = Date.now() - new Date(iso).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return 'Just now';
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    return `${Math.floor(hrs / 24)}d ago`;
  };

  // Initial fetch + 30s polling
  useEffect(() => {
    fetchNotifications();
    notifPollRef.current = setInterval(fetchNotifications, 30000);
    return () => clearInterval(notifPollRef.current);
  }, [user?.id]);

  const notifRef = useRef(null);

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (notifRef.current && !notifRef.current.contains(event.target)) {
        setShowNotifications(false);
      }
    };
    if (showNotifications) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [showNotifications]);

  const unreadCount = notifications.filter(n => n.unread).length;
  const filteredNotifs = notifFilter === 'all' 
    ? notifications 
    : notifications.filter(n => n.unread);

  const markAllRead = async () => {
    // Optimistic UI update
    setNotifications(prev => prev.map(n => ({ ...n, unread: false })));
    try {
      await fetch(`http://127.0.0.1:8000/api/notifications/read-all?user_id=${user.id}`, { method: 'PATCH' });
    } catch (e) {
      console.error('Failed to mark all read', e);
    }
  };

  const toggleRead = async (id) => {
    const notif = notifications.find(n => n.id === id);
    if (!notif) return;
    // Optimistic update
    setNotifications(prev => prev.map(n => n.id === id ? { ...n, unread: !n.unread } : n));
    // Only call API to mark as read (we don't support un-read via API)
    if (notif.unread) {
      try {
        await fetch(`http://127.0.0.1:8000/api/notifications/${id}/read`, { method: 'PATCH' });
      } catch (e) {
        console.error('Failed to mark notification read', e);
      }
    }
  };

  const deleteNotif = (e, id) => {
    e.stopPropagation();
    // Only remove from local state (no delete API needed — just hide it)
    setNotifications(prev => prev.filter(n => n.id !== id));
  };

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

  const handleDeleteChat = async (e, chatId) => {
    e.stopPropagation();
    if (!window.confirm("Are you sure you want to delete this chat conversation?")) return;

    try {
      const res = await fetch(`http://127.0.0.1:8000/api/chats/${chatId}`, { method: 'DELETE' });
      if (res.ok) {
        setChatSessions((prev) => prev.filter((c) => c.id !== chatId));
        if (activeChatId === chatId) {
          handleNewChat();
        }
      }
    } catch (err) {
      console.error("Failed to delete chat", err);
    }
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
        <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem' }}>
          <button className="new-chat-btn" onClick={handleNewChat} style={{ flex: 1, marginBottom: 0 }}>
            + New Chat
          </button>
          <button 
            type="button" 
            onClick={onOpenAdmin} 
            className="admin-nav-btn"
            title="Institutional Admin Portal"
          >
            🛡️ Admin
          </button>
        </div>
        <div className="chat-history-list">
          {chatSessions.map((chat) => (
            <div 
              key={chat.id} 
              className={`history-item ${activeChatId === chat.id ? 'active' : ''}`}
              onClick={() => loadChat(chat.id)}
              title={chat.title}
              style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}
            >
              <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {chat.title}
              </span>
              <button
                type="button"
                className="delete-chat-btn"
                onClick={(e) => handleDeleteChat(e, chat.id)}
                title="Delete Chat"
              >
                🗑️
              </button>
            </div>
          ))}
        </div>
        <div className="user-profile-header" style={{ marginTop: 'auto', borderBottom: 'none', paddingTop: '1rem', borderTop: '1px solid var(--surface-border)', position: 'relative' }} ref={notifRef}>
          <div className="user-info">
            <div className="user-avatar">
              {user?.name ? user.name.charAt(0) : '?'}
            </div>
            <div className="user-details" style={{ overflow: 'hidden' }}>
              <span className="user-name" style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{user?.name || 'User'}</span>
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
            <button 
              type="button"
              className={`notif-bell-btn ${showNotifications ? 'active' : ''}`}
              onClick={() => setShowNotifications(!showNotifications)}
              title="Notifications"
              aria-label="Notification Center"
            >
              <svg className="bell-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"></path>
                <path d="M13.73 21a2 2 0 0 1-3.46 0"></path>
              </svg>
              {unreadCount > 0 && (
                <span className="notif-badge">
                  <span className="notif-badge-ping"></span>
                  <span className="notif-badge-dot">{unreadCount}</span>
                </span>
              )}
            </button>

            <button onClick={onLogout} className="logout-btn" style={{ padding: '0.5rem' }}>
              Out
            </button>
          </div>

          {showNotifications && (
            <div className="notif-popover">
              <div className="notif-popover-header">
                <div className="notif-header-top">
                  <div className="notif-header-title">
                    <span>Notifications</span>
                    {unreadCount > 0 && <span className="notif-count-pill">{unreadCount} new</span>}
                  </div>
                  {unreadCount > 0 && (
                    <button type="button" className="notif-mark-read-btn" onClick={markAllRead}>
                      Mark all read
                    </button>
                  )}
                </div>
                <div className="notif-tabs">
                  <button 
                    type="button" 
                    className={`notif-tab ${notifFilter === 'all' ? 'active' : ''}`}
                    onClick={() => setNotifFilter('all')}
                  >
                    All ({notifications.length})
                  </button>
                  <button 
                    type="button" 
                    className={`notif-tab ${notifFilter === 'unread' ? 'active' : ''}`}
                    onClick={() => setNotifFilter('unread')}
                  >
                    Unread ({unreadCount})
                  </button>
                </div>
              </div>

              <div className="notif-list">
                {filteredNotifs.length === 0 ? (
                  <div className="notif-empty">
                    <span style={{ fontSize: '1.5rem' }}>🔕</span>
                    <span>No notifications</span>
                    <button 
                      type="button" 
                      onClick={(e) => { e.stopPropagation(); setNotifications(DEFAULT_NOTIFICATIONS); }}
                      style={{ marginTop: '0.6rem', background: 'rgba(59, 130, 246, 0.15)', border: '1px solid rgba(59, 130, 246, 0.4)', color: '#60a5fa', padding: '0.35rem 0.75rem', borderRadius: '6px', fontSize: '0.78rem', cursor: 'pointer', fontWeight: 600, transition: 'all 0.15s' }}
                    >
                      🔄 Restore sample alerts
                    </button>
                  </div>
                ) : (
                  filteredNotifs.map(n => (
                    <div 
                      key={n.id} 
                      className={`notif-item ${n.unread ? 'unread' : ''}`}
                      onClick={() => toggleRead(n.id)}
                    >
                      <div className="notif-item-icon">{n.icon}</div>
                      <div className="notif-item-body">
                        <div className="notif-item-title-row">
                          <span className="notif-item-title">{n.title}</span>
                          <span className="notif-item-time">{n.time}</span>
                        </div>
                        <div className="notif-item-msg">{n.message}</div>
                      </div>
                      {n.unread && <div className="notif-unread-dot"></div>}
                      <button 
                        type="button" 
                        className="notif-dismiss-btn" 
                        onClick={(e) => deleteNotif(e, n.id)}
                        title="Dismiss"
                      >
                        ×
                      </button>
                    </div>
                  ))
                )}
              </div>

              <div className="notif-popover-footer">
                <a className="notif-footer-link" onClick={() => { setShowNotifications(false); setInput('Show academic calendar and important notices'); }}>
                  ✨ Ask AI for Campus Updates
                </a>
              </div>
            </div>
          )}
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
