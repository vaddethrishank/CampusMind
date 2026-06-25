import { useState, useEffect } from 'react';
import Chat from './Chat';
import Auth from './Auth';
import Admin from './Admin';
import './index.css';

function App() {
  const [user, setUser] = useState(null);
  const [resetToken, setResetToken] = useState(null);
  const [checkingSession, setCheckingSession] = useState(true);
  const [currentView, setCurrentView] = useState('chat'); // 'chat' or 'admin'

  useEffect(() => {
    // Check if there is an active session in local storage
    const storedUser = localStorage.getItem('campusmind_user');
    const storedSession = localStorage.getItem('campusmind_session');
    
    if (storedUser && storedSession) {
      // Validate expiration
      const session = JSON.parse(storedSession);
      const now = Math.floor(Date.now() / 1000);
      if (session.expires_at && session.expires_at > now) {
        setUser(JSON.parse(storedUser));
      } else {
        // Expired
        localStorage.removeItem('campusmind_user');
        localStorage.removeItem('campusmind_session');
      }
    }

    // Check for password reset token in the hash URL
    const hash = window.location.hash;
    if (hash) {
      const params = new URLSearchParams(hash.substring(1)); // Remove the leading '#'
      const accessToken = params.get('access_token');
      const type = params.get('type');
      if (accessToken && type === 'recovery') {
        setResetToken(accessToken);
      }
    }
    setCheckingSession(false);
  }, []);

  const handleLogout = () => {
    localStorage.removeItem('campusmind_user');
    localStorage.removeItem('campusmind_session');
    setUser(null);
  };

  if (checkingSession) {
    return <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh', color: '#94a3b8' }}>Loading...</div>;
  }

  // If there's a password reset token in progress, render the Reset Password screen
  if (resetToken) {
    return (
      <div className="auth-container">
        <Auth 
          initialResetToken={resetToken} 
          onAuthSuccess={(user) => {
            setResetToken(null);
            setUser(user);
          }} 
        />
      </div>
    );
  }

  if (!user) {
    return (
      <div className="auth-container">
        <Auth onAuthSuccess={(u) => setUser(u)} />
      </div>
    );
  }

  return (
    <div className="app-chat-layout">
      {currentView === 'admin' ? (
        <Admin onBack={() => setCurrentView('chat')} />
      ) : (
        <Chat user={user} onLogout={handleLogout} onOpenAdmin={() => setCurrentView('admin')} />
      )}
    </div>
  );
}

export default App;
