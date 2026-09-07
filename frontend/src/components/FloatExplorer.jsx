import React, { useEffect, useState } from 'react';
import axios from 'axios';
import Plotly from 'plotly.js-dist-min';
import createPlotlyComponent from 'react-plotly.js/factory';

const Plot = createPlotlyComponent(Plotly);
const API_BASE = 'http://localhost:8000';

const LIGHT_LAYOUT = {
  paper_bgcolor: '#ffffff',
  plot_bgcolor: '#f8f9fa',
  font: { family: 'Inter, sans-serif', color: '#212122', size: 11 },
  xaxis: { gridcolor: '#e0e0e0', zerolinecolor: '#bdbdbd', tickfont: { color: '#212122' } },
  yaxis: { gridcolor: '#e0e0e0', zerolinecolor: '#bdbdbd', tickfont: { color: '#212122' } },
};

export default function FloatExplorer() {
  const [floatList, setFloatList] = useState([]);
  const [selectedFloat, setSelectedFloat] = useState('');
  const [profiles, setProfiles] = useState([]);
  const [computed, setComputed] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    async function loadFloatList() {
      try {
        const res = await axios.get(`${API_BASE}/api/floats`);
        const list = res.data || [];
        setFloatList(list);
        if (list.length > 0) setSelectedFloat(list[0].float_id);
      } catch (err) {
        console.error(err);
      }
    }
    loadFloatList();
  }, []);

  useEffect(() => {
    if (!selectedFloat) return;
    async function fetchFloatDetails() {
      setLoading(true);
      try {
        const [trackRes, layerRes] = await Promise.all([
          axios.get(`${API_BASE}/api/floats/${selectedFloat}/track`),
          axios.get(`${API_BASE}/api/floats/${selectedFloat}/layer-depths`)
        ]);
        setProfiles(trackRes.data || []);
        setComputed(layerRes.data || null);
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    }
    fetchFloatDetails();
  }, [selectedFloat]);

  const mld = computed?.mixed_layer_depth && computed.mixed_layer_depth < 450 ? computed.mixed_layer_depth : null;
  const therm = computed?.thermocline_depth && computed.thermocline_depth < 900 ? computed.thermocline_depth : null;
  const blt = computed?.barrier_layer_thickness != null ? computed.barrier_layer_thickness : null;
  const tchp = computed?.tchp_kj_cm2 != null ? computed.tchp_kj_cm2 : null;
  const ild = computed?.isothermal_layer_depth && computed.isothermal_layer_depth < 900 ? computed.isothermal_layer_depth : null;
  const d20 = computed?.d20_depth != null ? computed.d20_depth : null;

  const trackData = [
    {
      type: 'scattergeo',
      lat: profiles.map(p => p.latitude),
      lon: profiles.map(p => p.longitude),
      mode: 'lines+markers',
      line: { width: 1.5, color: '#1d4ed8' },
      marker: {
        size: 5,
        color: profiles.map(p => p.surface_temp),
        colorscale: [[0, '#1d4ed8'], [0.5, '#F2F4F3'], [1, '#E87575']],
        showscale: true,
        colorbar: { title: { text: 'SST °C', font: { color: '#858C89', size: 10 } }, thickness: 8, len: 0.5, tickfont: { color: '#858C89', size: 9 } }
      },
      text: profiles.map(p => `Profile ${p.profile_idx}<br>${p.measurement_date}<br>SST: ${Number(p.surface_temp).toFixed(1)}°C`),
      hoverinfo: 'text'
    }
  ];

  const trackLayout = {
    height: 350,
    margin: { l: 0, r: 0, t: 30, b: 0 },
    title: { text: `Float ${selectedFloat} Track`, font: { color: '#212122', size: 13 } },
    paper_bgcolor: '#ffffff',
    font: { family: 'Inter, sans-serif', color: '#212122' },
    geo: {
      fitbounds: 'locations',
      showland: true, landcolor: '#d4e6f1',
      showocean: true, oceancolor: '#b3e5fc',
      showcoastlines: true, coastlinecolor: '#0d47a1',
      showcountries: true, countrycolor: '#90caf9', showframe: false,
      bgcolor: '#ffffff', lakecolor: '#ffffff', resolution: 40
    }
  };

  const tsData = [
    {
      type: 'scatter',
      x: profiles.map(p => p.measurement_date),
      y: profiles.map(p => p.surface_temp),
      mode: 'lines+markers',
      line: { color: '#2563eb', width: 1.5 },
      marker: { size: 3, color: '#2563eb' },
      name: 'SST'
    }
  ];

  const tsLayout = {
    ...LIGHT_LAYOUT,
    title: { text: `Float ${selectedFloat} — Surface Temperature`, font: { color: '#212122', size: 13 } },
    xaxis: { ...LIGHT_LAYOUT.xaxis, title: { text: 'Date', font: { color: '#212122', size: 11 } } },
    yaxis: { ...LIGHT_LAYOUT.yaxis, title: { text: 'SST (°C)', font: { color: '#212122', size: 11 } } },
    height: 350,
    margin: { l: 50, r: 20, t: 40, b: 40 },
  };

  const layers = [
    { name: 'Mixed Layer', depth: mld, color: '#1d4ed8' },
    { name: 'Isothermal Layer', depth: ild, color: '#2563eb' },
    { name: 'Thermocline', depth: therm, color: '#E8C675' },
    { name: 'D20', depth: d20, color: '#E87575' }
  ].filter(l => l.depth !== null && l.depth !== undefined);

  const barData = layers.map(l => ({
    type: 'bar',
    x: [l.depth],
    y: [l.name],
    orientation: 'h',
    marker: { color: l.color },
    name: l.name,
    text: [`${Number(l.depth).toFixed(1)} m`],
    textposition: 'outside',
    textfont: { color: '#858C89', size: 11 }
  }));

  const barLayout = {
    ...LIGHT_LAYOUT,
    title: { text: 'Ocean Layer Depths (latest profile)', font: { color: '#212122', size: 13 } },
    xaxis: { ...LIGHT_LAYOUT.xaxis, title: { text: 'Depth (m)', font: { color: '#212122', size: 11 } } },
    yaxis: { ...LIGHT_LAYOUT.yaxis },
    height: 250,
    margin: { l: 130, r: 60, t: 40, b: 40 },
    showlegend: false
  };

  return (
    <div>
      <h2>Explore Individual Float</h2>

      <div className="st-select-group">
        <label className="st-label">Select Float</label>
        <select className="st-select" value={selectedFloat} onChange={(e) => setSelectedFloat(e.target.value)}>
          {floatList.map(f => (
            <option key={f.float_id} value={f.float_id}>
              Float {f.float_id} ({f.profile_count} profiles)
            </option>
          ))}
        </select>
      </div>

      {loading ? (
        <div className="loading-text">Loading float details...</div>
      ) : profiles.length === 0 ? (
        <div className="warning-box">No profiles found.</div>
      ) : (
        <>
          <div className="st-two-columns" style={{ marginBottom: '2rem' }}>
            <div style={{ borderRadius: '10px', overflow: 'hidden', border: '1px solid #242828' }}>
              <Plot data={trackData} layout={trackLayout} useResizeHandler={true} style={{ width: '100%', height: '350px' }} config={{ responsive: true, displayModeBar: false }} className="map-dark-mode" />
            </div>
            <div style={{ borderRadius: '10px', overflow: 'hidden', border: '1px solid #242828' }}>
              <Plot data={tsData} layout={tsLayout} useResizeHandler={true} style={{ width: '100%', height: '350px' }} config={{ responsive: true, displayModeBar: false }} className="map-dark-mode" />
            </div>
          </div>

          <h2>Ocean Layer Structure</h2>
          <div className="metrics-row" style={{ gridTemplateColumns: 'repeat(4, 1fr)', marginBottom: '1.5rem' }}>
            <div className="st-metric-card">
              <span className="st-metric-label">Mixed Layer Depth</span>
              <span className="st-metric-value" style={{ color: '#1d4ed8' }}>{mld != null ? `${Number(mld).toFixed(1)} m` : 'N/A'}</span>
            </div>
            <div className="st-metric-card">
              <span className="st-metric-label">Thermocline Depth</span>
              <span className="st-metric-value" style={{ color: '#E8C675' }}>{therm != null ? `${Number(therm).toFixed(1)} m` : 'N/A'}</span>
            </div>
            <div className="st-metric-card">
              <span className="st-metric-label">Barrier Layer</span>
              <span className="st-metric-value" style={{ color: '#2563eb' }}>{blt != null ? `${Number(blt).toFixed(1)} m` : 'N/A'}</span>
            </div>
            <div className="st-metric-card">
              <span className="st-metric-label">TCHP</span>
              <span className="st-metric-value" style={{ color: '#F2F4F3' }}>{tchp != null ? `${Number(tchp).toFixed(2)} kJ/cm²` : 'N/A'}</span>
            </div>
          </div>

          <div style={{ width: '100%', borderRadius: '10px', overflow: 'hidden', border: '1px solid #242828' }}>
            <Plot data={barData} layout={barLayout} useResizeHandler={true} style={{ width: '100%', height: '250px' }} config={{ responsive: true, displayModeBar: false }} />
          </div>
        </>
      )}
    </div>
  );
}
