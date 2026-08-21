import React, { useState, useEffect } from 'react';
import axios from 'axios';
import FloatMap from './components/FloatMap';
import FloatExplorer from './components/FloatExplorer';
import RegionalStats from './components/RegionalStats';
import AskSamudra from './components/AskSamudra';
import './index.css';

const API_BASE = 'http://localhost:8000';

function App() {
  const [activeTab, setActiveTab] = useState('tab1');
  const [theme, setTheme] = useState(() => {
    const saved = localStorage.getItem('samudra-theme');
    return saved || 'dark';
  });
  const [stats, setStats] = useState({ floats_count: 0, profiles_count: 0, computed_count: 0 });
  const [error, setError] = useState(null);

  useEffect(() => {
    const root = document.documentElement;
    if (theme === 'dark') {
      root.classList.add('dark-mode');
    } else {
      root.classList.remove('dark-mode');
    }
    localStorage.setItem('samudra-theme', theme);
  }, [theme]);

  const toggleTheme = () => {
    setTheme(prev => prev === 'dark' ? 'light' : 'dark');
  };

  useEffect(() => {
    async function fetchStats() {
      try {
        const res = await axios.get(`${API_BASE}/api/stats`);
        setStats(res.data || { floats_count: 0, profiles_count: 0, computed_count: 0 });
      } catch (err) {
        console.error(err);
        setError(`DB connection error: ${err.message}`);
      }
    }
    fetchStats();
  }, []);

  return (
    <div className={theme === 'dark' ? 'dark-app' : 'light-app'}>
      <h1>🌊 Samudra</h1>
      <div className="subtitle">INCOIS Argo floats · Copernicus satellite · IOTC tuna catch</div>

      {error ? (
        <div className="error-box">{error}</div>
      ) : (
        <div className="metrics-row" style={{ gridTemplateColumns: 'repeat(3, 1fr)' }}>
          <div className="st-metric-card">
            <span className="st-metric-label">Argo Floats</span>
            <span className="st-metric-value" style={{ color: '#2563eb' }}>{stats.floats_count.toLocaleString()}</span>
          </div>
          <div className="st-metric-card">
            <span className="st-metric-label">Profiles</span>
            <span className="st-metric-value" style={{ color: '#2563eb' }}>{stats.profiles_count.toLocaleString()}</span>
          </div>
          <div className="st-metric-card">
            <span className="st-metric-label">Computed Profiles</span>
            <span className="st-metric-value" style={{ color: '#2563eb' }}>{stats.computed_count.toLocaleString()}</span>
          </div>
        </div>
      )}

      <hr className="st-divider" />

      <div className="st-tabs-bar">
        <button className={`st-tab-btn ${activeTab === 'tab1' ? 'active' : ''}`} onClick={() => setActiveTab('tab1')}>
          🗺️ Float Map
        </button>
        <button className={`st-tab-btn ${activeTab === 'tab2' ? 'active' : ''}`} onClick={() => setActiveTab('tab2')}>
          🔍 Float Explorer
        </button>
        <button className={`st-tab-btn ${activeTab === 'tab3' ? 'active' : ''}`} onClick={() => setActiveTab('tab3')}>
          📊 Regional Stats
        </button>
        <button className={`st-tab-btn ${activeTab === 'tab4' ? 'active' : ''}`} onClick={() => setActiveTab('tab4')}>
          🤖 Ask Samudra
        </button>
      </div>

      {activeTab === 'tab1' && <FloatMap />}
      {activeTab === 'tab2' && <FloatExplorer />}
      {activeTab === 'tab3' && <RegionalStats />}
      {activeTab === 'tab4' && <AskSamudra />}

      <hr className="st-divider" />
      <div className="st-caption">
        Samudra v1.0 · INCOIS Argo · Copernicus Marine · IOTC · GSW TEOS-10
      </div>
    </div>
  );
}

export default App;