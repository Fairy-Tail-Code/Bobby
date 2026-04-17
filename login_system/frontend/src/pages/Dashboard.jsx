import { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { authAPI, tasksAPI } from '../api';
import { useAuth } from '../context/AuthContext';

export default function Dashboard() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [userInfo, setUserInfo] = useState(null);
  const [loading, setLoading] = useState(true);
  const [taskStats, setTaskStats] = useState(null);

  useEffect(() => {
    fetchUserInfo();
    fetchTaskStats();
  }, []);

  const fetchUserInfo = async () => {
    try {
      const res = await authAPI.getMe();
      setUserInfo(res.data);
    } catch (err) {
      console.error('Failed to fetch user info:', err);
    } finally {
      setLoading(false);
    }
  };

  const fetchTaskStats = async () => {
    try {
      const res = await tasksAPI.listTasks();
      setTaskStats(res.data);
    } catch (err) {
      console.error('Failed to fetch task stats:', err);
    }
  };

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  if (loading) {
    return (
      <div style={styles.container}>
        <div style={styles.loading}>Loading...</div>
      </div>
    );
  }

  return (
    <div style={styles.container}>
      {/* Navbar */}
      <nav style={styles.navbar}>
        <div style={styles.navContent}>
          <span style={styles.logo}>🏠 Celery Login</span>
          <button onClick={handleLogout} style={styles.logoutBtn}>Sign Out</button>
        </div>
      </nav>

      <div style={styles.main}>
        {/* User Info Card */}
        <div style={styles.card}>
          <div style={styles.cardHeader}>
            <h2 style={styles.cardTitle}>👤 User Profile</h2>
          </div>
          <div style={styles.cardBody}>
            <div style={styles.infoRow}>
              <span style={styles.infoLabel}>Email</span>
              <span style={styles.infoValue}>{userInfo?.email || user?.email}</span>
            </div>
            <div style={styles.infoRow}>
              <span style={styles.infoLabel}>Status</span>
              <span style={{
                ...styles.infoValue,
                color: userInfo?.is_verified ? '#16a34a' : '#f59e0b',
              }}>
                {userInfo?.is_verified ? '✅ Verified' : '⏳ Unverified'}
              </span>
            </div>
            <div style={styles.infoRow}>
              <span style={styles.infoLabel}>Registered</span>
              <span style={styles.infoValue}>
                {userInfo?.created_at ? new Date(userInfo.created_at).toLocaleString() : 'N/A'}
              </span>
            </div>
            <div style={styles.infoRow}>
              <span style={styles.infoLabel}>User ID</span>
              <span style={{ ...styles.infoValue, fontFamily: 'monospace', fontSize: '13px' }}>
                {userInfo?.id || 'N/A'}
              </span>
            </div>
          </div>
        </div>

        {/* Celery Task Info Card */}
        <div style={styles.card}>
          <div style={styles.cardHeader}>
            <h2 style={styles.cardTitle}>⚡ Celery Task Info</h2>
            <span style={styles.badge}>Learning</span>
          </div>
          <div style={styles.cardBody}>
            <p style={styles.taskDesc}>
              Celery tasks are used for async email sending. Below shows the current worker status.
            </p>
            {taskStats ? (
              <div>
                <div style={styles.infoRow}>
                  <span style={styles.infoLabel}>Active Workers</span>
                  <span style={styles.infoValue}>
                    {taskStats.worker_stats ? Object.keys(taskStats.worker_stats).length : 0}
                  </span>
                </div>
                <div style={styles.infoRow}>
                  <span style={styles.infoLabel}>Active Tasks</span>
                  <span style={styles.infoValue}>
                    {taskStats.active_tasks
                      ? Object.values(taskStats.active_tasks).flat().length
                      : 0}
                  </span>
                </div>
                <div style={styles.infoRow}>
                  <span style={styles.infoLabel}>Broker</span>
                  <span style={{ ...styles.infoValue, color: '#dc2626' }}>Redis</span>
                </div>
              </div>
            ) : (
              <div style={styles.taskInfo}>
                <p>📡 No Celery worker connected. Start a worker to see task information.</p>
                <code style={styles.code}>
                  celery -A app.celery_worker worker --loglevel=info --pool=solo
                </code>
              </div>
            )}
          </div>
        </div>

        {/* Architecture Info Card */}
        <div style={styles.card}>
          <div style={styles.cardHeader}>
            <h2 style={styles.cardTitle}>🏗️ Architecture</h2>
            <span style={styles.badge}>Learning</span>
          </div>
          <div style={styles.cardBody}>
            <div style={styles.archFlow}>
              <div style={styles.archBox}>FastAPI<br /><small>HTTP Handler</small></div>
              <div style={styles.archArrow}>→</div>
              <div style={styles.archBox}>Celery<br /><small>Task Queue</small></div>
              <div style={styles.archArrow}>→</div>
              <div style={styles.archBox}>Redis<br /><small>Broker</small></div>
              <div style={styles.archArrow}>→</div>
              <div style={styles.archBox}>SMTP<br /><small>Email Send</small></div>
            </div>
            <div style={{ marginTop: '20px' }}>
              <h4 style={{ color: '#374151', marginBottom: '8px' }}>Key Concepts:</h4>
              <ul style={{ color: '#6b7280', fontSize: '14px', lineHeight: '2', paddingLeft: '20px' }}>
                <li><strong>Producer</strong>: FastAPI route calls <code>.delay()</code> to enqueue tasks</li>
                <li><strong>Broker (Redis)</strong>: Stores task messages in queues</li>
                <li><strong>Worker (Celery)</strong>: Picks up and executes tasks asynchronously</li>
                <li><strong>Backend (Redis)</strong>: Stores task results and status</li>
              </ul>
            </div>
          </div>
        </div>

        {/* Task Status Lookup */}
        <div style={styles.card}>
          <div style={styles.cardHeader}>
            <h2 style={styles.cardTitle}>🔍 Task Status Lookup</h2>
          </div>
          <div style={styles.cardBody}>
            <TaskLookup />
          </div>
        </div>
      </div>
    </div>
  );
}

function TaskLookup() {
  const [taskId, setTaskId] = useState('');
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  const lookup = async () => {
    if (!taskId.trim()) return;
    setLoading(true);
    try {
      const res = await tasksAPI.getTaskStatus(taskId);
      setResult(res.data);
    } catch (err) {
      setResult({ error: 'Failed to fetch task status' });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <div style={{ display: 'flex', gap: '8px' }}>
        <input
          type="text"
          value={taskId}
          onChange={(e) => setTaskId(e.target.value)}
          placeholder="Enter task ID"
          style={{ ...styles.input, flex: 1 }}
        />
        <button onClick={lookup} style={styles.lookupBtn} disabled={loading}>
          {loading ? '...' : 'Lookup'}
        </button>
      </div>
      {result && !result.error && (
        <div style={{ marginTop: '16px', padding: '12px', background: '#f9fafb', borderRadius: '8px' }}>
          <div style={{ marginBottom: '4px' }}><strong>Status:</strong> {result.status}</div>
          <div style={{ marginBottom: '4px' }}><strong>Result:</strong> {result.result || 'N/A'}</div>
          {result.date_done && <div><strong>Completed:</strong> {result.date_done}</div>}
        </div>
      )}
      {result?.error && (
        <div style={{ marginTop: '16px', padding: '12px', background: '#fef2f2', borderRadius: '8px', color: '#dc2626' }}>
          {result.error}
        </div>
      )}
    </div>
  );
}

const styles = {
  container: {
    minHeight: '100vh',
    background: '#f8fafc',
  },
  navbar: {
    background: '#ffffff',
    borderBottom: '1px solid #e2e8f0',
    padding: '0 24px',
    height: '60px',
    display: 'flex',
    alignItems: 'center',
    boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
  },
  navContent: {
    maxWidth: '960px',
    width: '100%',
    margin: '0 auto',
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  logo: {
    fontSize: '18px',
    fontWeight: '700',
    color: '#2563eb',
  },
  logoutBtn: {
    padding: '8px 16px',
    background: '#f1f5f9',
    color: '#475569',
    border: '1px solid #e2e8f0',
    borderRadius: '6px',
    cursor: 'pointer',
    fontSize: '14px',
    fontWeight: '500',
  },
  main: {
    maxWidth: '960px',
    margin: '0 auto',
    padding: '32px 24px',
  },
  loading: {
    textAlign: 'center',
    padding: '100px 0',
    fontSize: '18px',
    color: '#6b7280',
  },
  card: {
    background: '#ffffff',
    borderRadius: '12px',
    border: '1px solid #e2e8f0',
    marginBottom: '24px',
    overflow: 'hidden',
  },
  cardHeader: {
    padding: '20px 24px',
    borderBottom: '1px solid #f1f5f9',
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  cardTitle: {
    fontSize: '18px',
    fontWeight: '600',
    color: '#111827',
    margin: 0,
  },
  badge: {
    background: '#eff6ff',
    color: '#2563eb',
    padding: '4px 12px',
    borderRadius: '12px',
    fontSize: '12px',
    fontWeight: '600',
  },
  cardBody: {
    padding: '24px',
  },
  infoRow: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: '12px 0',
    borderBottom: '1px solid #f1f5f9',
  },
  infoLabel: {
    fontSize: '14px',
    fontWeight: '500',
    color: '#6b7280',
  },
  infoValue: {
    fontSize: '14px',
    fontWeight: '500',
    color: '#111827',
  },
  taskDesc: {
    fontSize: '14px',
    color: '#6b7280',
    lineHeight: '1.6',
    marginBottom: '16px',
  },
  taskInfo: {
    padding: '16px',
    background: '#fffbeb',
    borderRadius: '8px',
    border: '1px solid #fde68a',
  },
  code: {
    display: 'block',
    marginTop: '8px',
    padding: '8px',
    background: '#1e293b',
    color: '#e2e8f0',
    borderRadius: '6px',
    fontSize: '12px',
    fontFamily: 'monospace',
  },
  archFlow: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '8px',
    flexWrap: 'wrap',
  },
  archBox: {
    padding: '12px 16px',
    background: '#eff6ff',
    border: '1px solid #bfdbfe',
    borderRadius: '8px',
    textAlign: 'center',
    fontSize: '14px',
    fontWeight: '600',
    color: '#2563eb',
  },
  archArrow: {
    fontSize: '20px',
    color: '#9ca3af',
    fontWeight: 'bold',
  },
  input: {
    padding: '10px 14px',
    border: '1px solid #d1d5db',
    borderRadius: '8px',
    fontSize: '14px',
    outline: 'none',
    boxSizing: 'border-box',
  },
  lookupBtn: {
    padding: '10px 20px',
    background: '#2563eb',
    color: '#ffffff',
    border: 'none',
    borderRadius: '8px',
    fontSize: '14px',
    fontWeight: '600',
    cursor: 'pointer',
  },
};
