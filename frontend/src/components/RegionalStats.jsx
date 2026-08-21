import React, { useEffect, useState } from 'react';
import axios from 'axios';
import Plotly from 'plotly.js-dist-min';
import createPlotlyComponent from 'react-plotly.js/factory';

const Plot = createPlotlyComponent(Plotly);
const API_BASE = 'http://localhost:8000';

export default function RegionalStats() {
  const [region, setRegion] = useState('Arabian Sea');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    async function fetchAnalytics() {
      setLoading(true);
      try {
        const res = await axios.get(`${API_BASE}/api/region/${encodeURIComponent(region)}/analytics`);
        setData(res.data || null);
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    }
    fetchAnalytics();
  }, [region]);

  const stats = data?.stats || {};
  const climatology = data?.climatology || [];

  const months = climatology.map(c => c.month);
  const sstValues = climatology.map(c => c.avg_sst);
  const chlValues = climatology.map(c => c.avg_chl);

  const climData = [
    {
      type: 'scatter',
      x: months,
      y: sstValues,
      mode: 'lines+markers',
      name: 'SST (°C)',
      line: { color: '#E87575', width: 2 },
      marker: { size: 4, color: '#E87575' }
    },
    {
      type: 'scatter',
      x: months,
      y: chlValues,
      mode: 'lines+markers',
      name: 'CHL (mg/m³)',
      line: { color: '#1d4ed8', width: 2 },
      marker: { size: 4, color: '#1d4ed8' },
      yaxis: 'y2'
    }
  ];

  const climLayout = {
    title: { text: `${region} — Monthly Climatology (2024)`, font: { color: '#F2F4F3', size: 13 } },
    xaxis: { title: { text: 'Month', font: { color: '#858C89', size: 11 } }, tickmode: 'linear', tick0: 1, dtick: 1, gridcolor: '#1a1d1d', tickfont: { color: '#858C89' } },
    yaxis: { title: { text: 'SST (°C)', font: { color: '#E87575', size: 11 } }, color: '#E87575', gridcolor: '#1a1d1d', tickfont: { color: '#858C89' } },
    yaxis2: { title: { text: 'Chlorophyll (mg/m³)', font: { color: '#1d4ed8', size: 11 } }, overlaying: 'y', side: 'right', color: '#1d4ed8', tickfont: { color: '#858C89' } },
    height: 350,
    margin: { l: 55, r: 55, t: 45, b: 45 },
    paper_bgcolor: '#0B0D0D',
    plot_bgcolor: '#0B0D0D',
    font: { family: 'Inter, sans-serif', color: '#858C89' },
    legend: { x: 0.01, y: 0.99, font: { color: '#858C89', size: 11 } }
  };

  return (
    <div>
      <h2>Regional Ocean Summary</h2>

      <div className="st-select-group">
        <label className="st-label">Region</label>
        <select className="st-select" value={region} onChange={(e) => setRegion(e.target.value)}>
          <option value="Arabian Sea">Arabian Sea</option>
          <option value="Bay of Bengal">Bay of Bengal</option>
          <option value="Equatorial IO">Equatorial IO</option>
          <option value="Southern Ocean">Southern Ocean</option>
        </select>
      </div>

      {loading ? (
        <div className="loading-text">Loading regional stats...</div>
      ) : (
        <>
          <div className="metrics-row" style={{ gridTemplateColumns: 'repeat(6, 1fr)', marginBottom: '1.5rem' }}>
            <div className="st-metric-card">
              <span className="st-metric-label">Floats</span>
              <span className="st-metric-value">{stats.floats != null ? stats.floats : 0}</span>
            </div>
            <div className="st-metric-card">
              <span className="st-metric-label">Avg MLD</span>
              <span className="st-metric-value" style={{ color: '#1d4ed8' }}>{stats.avg_mld != null ? `${stats.avg_mld} m` : 'N/A'}</span>
            </div>
            <div className="st-metric-card">
              <span className="st-metric-label">Avg Thermocline</span>
              <span className="st-metric-value" style={{ color: '#E8C675' }}>{stats.avg_thermocline != null ? `${stats.avg_thermocline} m` : 'N/A'}</span>
            </div>
            <div className="st-metric-card">
              <span className="st-metric-label">Avg TCHP</span>
              <span className="st-metric-value" style={{ color: '#2563eb' }}>{stats.avg_tchp != null ? `${stats.avg_tchp} kJ/cm²` : 'N/A'}</span>
            </div>
            <div className="st-metric-card">
              <span className="st-metric-label">Avg Temp</span>
              <span className="st-metric-value" style={{ color: '#F2F4F3' }}>{stats.avg_temp != null ? `${stats.avg_temp} °C` : 'N/A'}</span>
            </div>
            <div className="st-metric-card">
              <span className="st-metric-label">Avg Salinity</span>
              <span className="st-metric-value" style={{ color: '#F2F4F3' }}>{stats.avg_salinity != null ? `${stats.avg_salinity} PSU` : 'N/A'}</span>
            </div>
          </div>

          {climatology.length > 0 && (
            <div style={{ width: '100%', borderRadius: '10px', overflow: 'hidden', border: '1px solid #242828' }}>
              <Plot data={climData} layout={climLayout} useResizeHandler={true} style={{ width: '100%', height: '350px' }} config={{ responsive: true, displayModeBar: false }} />
            </div>
          )}
        </>
      )}
    </div>
  );
}
