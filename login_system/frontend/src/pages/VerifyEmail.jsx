import { useState, useEffect } from 'react';
import { useSearchParams, Link } from 'react-router-dom';
import { authAPI } from '../api';

export default function VerifyEmail() {
  const [searchParams] = useSearchParams();
  const [status, setStatus] = useState('loading'); // loading, success, error
  const [message, setMessage] = useState('');
  const [email, setEmail] = useState('');
  const [resendLoading, setResendLoading] = useState(false);
  const [resendMessage, setResendMessage] = useState('');

  useEffect(() => {
    const token = searchParams.get('token');
    if (!token) {
      setStatus('error');
      setMessage('No verification token found in the URL.');
      return;
    }

    verifyToken(token);
  }, [searchParams]);

  const verifyToken = async (token) => {
    try {
      const res = await authAPI.verifyEmail(token);
      setStatus('success');
      setMessage(res.data.message);
    } catch (err) {
      setStatus('error');
      setMessage(err.response?.data?.detail || 'Verification failed.');
    }
  };

  const handleResend = async (e) => {
    e.preventDefault();
    setResendLoading(true);
    setResendMessage('');

    try {
      const res = await authAPI.resendVerification({ email });
      setResendMessage(res.data.message);
    } catch (err) {
      setResendMessage(err.response?.data?.detail || 'Failed to resend verification email.');
    } finally {
      setResendLoading(false);
    }
  };

  return (
    <div style={styles.container}>
      <div style={styles.card}>
        {status === 'loading' && (
          <div style={styles.header}>
            <div style={styles.spinner}>⏳</div>
            <h1 style={styles.title}>Verifying your email...</h1>
            <p style={styles.subtitle}>Please wait a moment.</p>
          </div>
        )}

        {status === 'success' && (
          <div style={styles.header}>
            <div style={styles.icon}>✅</div>
            <h1 style={{ ...styles.title, color: '#16a34a' }}>Email Verified!</h1>
            <p style={styles.subtitle}>{message}</p>
            <Link to="/login" style={styles.button}>Sign In Now</Link>
          </div>
        )}

        {status === 'error' && (
          <div>
            <div style={styles.header}>
              <div style={styles.icon}>❌</div>
              <h1 style={{ ...styles.title, color: '#dc2626' }}>Verification Failed</h1>
              <p style={styles.subtitle}>{message}</p>
            </div>

            <div style={{ marginTop: '24px', padding: '20px', background: '#f9fafb', borderRadius: '8px' }}>
              <p style={{ fontSize: '14px', color: '#374151', marginBottom: '12px' }}>
                Request a new verification email:
              </p>
              <form onSubmit={handleResend}>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="Enter your email"
                  style={{ ...styles.input, marginBottom: '12px' }}
                  required
                />
                <button type="submit" style={styles.button} disabled={resendLoading}>
                  {resendLoading ? 'Sending...' : 'Resend Verification Email'}
                </button>
              </form>
              {resendMessage && (
                <p style={{ marginTop: '12px', fontSize: '14px', color: '#2563eb' }}>
                  {resendMessage}
                </p>
              )}
            </div>

            <div style={{ textAlign: 'center', marginTop: '16px' }}>
              <Link to="/login" style={styles.link}>Back to login</Link>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

const styles = {
  container: {
    minHeight: '100vh',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    background: 'linear-gradient(135deg, #eff6ff 0%, #dbeafe 50%, #bfdbfe 100%)',
    padding: '20px',
  },
  card: {
    background: '#ffffff',
    borderRadius: '16px',
    padding: '48px',
    width: '100%',
    maxWidth: '440px',
    boxShadow: '0 4px 24px rgba(37, 99, 235, 0.1)',
    textAlign: 'center',
  },
  header: {
    textAlign: 'center',
  },
  icon: {
    fontSize: '48px',
    marginBottom: '16px',
  },
  spinner: {
    fontSize: '48px',
    marginBottom: '16px',
  },
  title: {
    fontSize: '24px',
    fontWeight: '700',
    color: '#111827',
    margin: '0 0 8px 0',
  },
  subtitle: {
    fontSize: '15px',
    color: '#6b7280',
    margin: 0,
    lineHeight: '1.6',
  },
  input: {
    width: '100%',
    padding: '12px 16px',
    border: '1px solid #d1d5db',
    borderRadius: '8px',
    fontSize: '15px',
    outline: 'none',
    boxSizing: 'border-box',
  },
  button: {
    display: 'inline-block',
    padding: '12px 32px',
    background: '#2563eb',
    color: '#ffffff',
    border: 'none',
    borderRadius: '8px',
    fontSize: '16px',
    fontWeight: '600',
    cursor: 'pointer',
    textDecoration: 'none',
    marginTop: '16px',
  },
  link: {
    color: '#2563eb',
    textDecoration: 'none',
    fontWeight: '500',
    fontSize: '14px',
  },
};
