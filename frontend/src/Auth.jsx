import { useState } from 'react';

export default function Auth({ onAuthSuccess, initialResetToken = null }) {
  const [view, setView] = useState(initialResetToken ? 'reset-password' : 'login');
  const [email, setEmail] = useState('');
  const [username, setUsername] = useState('');
  const [name, setName] = useState('');
  const [scholarId, setScholarId] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [identifier, setIdentifier] = useState(''); // email or username for login
  const [isLoading, setIsLoading] = useState(false);
  const [message, setMessage] = useState({ type: '', text: '' });

  const clearMessage = () => setMessage({ type: '', text: '' });

  const handleSignIn = async (e) => {
    e.preventDefault();
    if (!identifier.trim() || !password.trim()) return;

    setIsLoading(true);
    clearMessage();

    try {
      const response = await fetch('http://127.0.0.1:8000/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ identifier, password }),
      });

      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || 'Failed to login');
      }

      // Save session in local storage
      localStorage.setItem('campusmind_session', JSON.stringify(data.session));
      localStorage.setItem('campusmind_user', JSON.stringify(data.user));
      
      setMessage({ type: 'success', text: 'Login successful!' });
      setTimeout(() => {
        onAuthSuccess(data.user);
      }, 1000);
    } catch (error) {
      setMessage({ type: 'error', text: error.message });
    } finally {
      setIsLoading(false);
    }
  };

  const handleSignUp = async (e) => {
    e.preventDefault();
    if (!name.trim() || !email.trim() || !username.trim() || !scholarId.trim() || !password.trim()) {
      setMessage({ type: 'error', text: 'All fields are required.' });
      return;
    }

    if (!/^\d{7}$/.test(scholarId)) {
      setMessage({ type: 'error', text: 'Scholar ID must be exactly 7 digits.' });
      return;
    }

    setIsLoading(true);
    clearMessage();

    try {
      const response = await fetch('http://127.0.0.1:8000/api/auth/signup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, email, username, scholar_id: scholarId, password }),
      });

      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || 'Failed to sign up');
      }

      setMessage({ type: 'success', text: data.message || 'Signup successful! Please check your email.' });
      // Clear signup form
      setName('');
      setEmail('');
      setUsername('');
      setScholarId('');
      setPassword('');
    } catch (error) {
      setMessage({ type: 'error', text: error.message });
    } finally {
      setIsLoading(false);
    }
  };

  const handleForgotPassword = async (e) => {
    e.preventDefault();
    if (!identifier.trim()) return;

    setIsLoading(true);
    clearMessage();

    try {
      const response = await fetch('http://127.0.0.1:8000/api/auth/forgot-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ identifier }),
      });

      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || 'Request failed');
      }

      setMessage({ type: 'success', text: data.message });
    } catch (error) {
      setMessage({ type: 'error', text: error.message });
    } finally {
      setIsLoading(false);
    }
  };

  const handleResetPassword = async (e) => {
    e.preventDefault();
    if (!password.trim()) {
      setMessage({ type: 'error', text: 'Password cannot be empty.' });
      return;
    }
    if (password !== confirmPassword) {
      setMessage({ type: 'error', text: 'Passwords do not match.' });
      return;
    }

    setIsLoading(true);
    clearMessage();

    try {
      const response = await fetch('http://127.0.0.1:8000/api/auth/reset-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ access_token: initialResetToken, password }),
      });

      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || 'Reset failed');
      }

      setMessage({ type: 'success', text: 'Password reset successful! Redirecting to login...' });
      setTimeout(() => {
        // Clean URL hash
        window.history.replaceState(null, null, ' ');
        setView('login');
      }, 2000);
    } catch (error) {
      setMessage({ type: 'error', text: error.message });
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="auth-card">
      <div className="auth-header">
        <h2>CampusMind</h2>
        <p className="auth-subtitle">
          {view === 'login' && 'Sign in to access your dashboard'}
          {view === 'signup' && 'Create your account to get started'}
          {view === 'forgot-password' && 'Recover your account password'}
          {view === 'reset-password' && 'Enter your new password'}
        </p>
      </div>

      {message.text && (
        <div className={`auth-alert ${message.type}`}>
          {message.text}
        </div>
      )}

      {view === 'login' && (
        <form onSubmit={handleSignIn} className="auth-form">
          <div className="form-group">
            <label htmlFor="identifier">Email or Username</label>
            <input
              type="text"
              id="identifier"
              placeholder="Enter your email or username"
              value={identifier}
              onChange={(e) => setIdentifier(e.target.value)}
              required
            />
          </div>
          <div className="form-group">
            <label htmlFor="password">Password</label>
            <input
              type="password"
              id="password"
              placeholder="••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>
          <button type="submit" className="auth-submit-btn" disabled={isLoading}>
            {isLoading ? 'Signing In...' : 'Sign In'}
          </button>
          <div className="auth-footer">
            <button type="button" className="auth-link-btn" onClick={() => { setView('forgot-password'); clearMessage(); }}>
              Forgot Password?
            </button>
            <span>•</span>
            <button type="button" className="auth-link-btn" onClick={() => { setView('signup'); clearMessage(); }}>
              Create Account
            </button>
          </div>
        </form>
      )}

      {view === 'signup' && (
        <form onSubmit={handleSignUp} className="auth-form">
          <div className="form-group">
            <label htmlFor="name">Full Name</label>
            <input
              type="text"
              id="name"
              placeholder="John Doe"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
            />
          </div>
          <div className="form-group">
            <label htmlFor="username">Username</label>
            <input
              type="text"
              id="username"
              placeholder="johndoe"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
            />
          </div>
          <div className="form-group">
            <label htmlFor="email">Email Address</label>
            <input
              type="email"
              id="email"
              placeholder="john@university.edu"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </div>
          <div className="form-group">
            <label htmlFor="scholarId">Scholar ID (7-digit)</label>
            <input
              type="text"
              id="scholarId"
              placeholder="1234567"
              maxLength={7}
              value={scholarId}
              onChange={(e) => setScholarId(e.target.value.replace(/\D/g, ''))}
              required
            />
          </div>
          <div className="form-group">
            <label htmlFor="password">Password</label>
            <input
              type="password"
              id="password"
              placeholder="••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>
          <button type="submit" className="auth-submit-btn" disabled={isLoading}>
            {isLoading ? 'Creating Account...' : 'Sign Up'}
          </button>
          <div className="auth-footer">
            <button type="button" className="auth-link-btn" onClick={() => { setView('login'); clearMessage(); }}>
              Already have an account? Sign In
            </button>
          </div>
        </form>
      )}

      {view === 'forgot-password' && (
        <form onSubmit={handleForgotPassword} className="auth-form">
          <div className="form-group">
            <label htmlFor="forgot-identifier">Email or Username</label>
            <input
              type="text"
              id="forgot-identifier"
              placeholder="Enter your email or username"
              value={identifier}
              onChange={(e) => setIdentifier(e.target.value)}
              required
            />
          </div>
          <button type="submit" className="auth-submit-btn" disabled={isLoading}>
            {isLoading ? 'Sending Link...' : 'Send Reset Link'}
          </button>
          <div className="auth-footer">
            <button type="button" className="auth-link-btn" onClick={() => { setView('login'); clearMessage(); }}>
              Back to Sign In
            </button>
          </div>
        </form>
      )}

      {view === 'reset-password' && (
        <form onSubmit={handleResetPassword} className="auth-form">
          <div className="form-group">
            <label htmlFor="new-password">New Password</label>
            <input
              type="password"
              id="new-password"
              placeholder="••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>
          <div className="form-group">
            <label htmlFor="confirm-password">Confirm Password</label>
            <input
              type="password"
              id="confirm-password"
              placeholder="••••••••"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              required
            />
          </div>
          <button type="submit" className="auth-submit-btn" disabled={isLoading}>
            {isLoading ? 'Resetting Password...' : 'Reset Password'}
          </button>
        </form>
      )}
    </div>
  );
}
