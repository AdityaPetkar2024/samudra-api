import React, { useEffect, useState } from 'react';
import axios from 'axios';
import Plotly from 'plotly.js-dist-min';
import createPlotlyComponent from 'react-plotly.js/factory';

const Plot = createPlotlyComponent(Plotly);
const API_BASE = 'http://localhost:8000';

export default function FloatMap() {
  const [positions, setPositions] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchPositions() {
      try {
        const res = await axios.get(`${API_BASE}/api/floats/positions`);
        setPositions(res.data || []);
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    }
    fetchPositions();
  }, []);

  if (loading) {
    return <div className="loading-text">Loading float positions...</div>;
  }

  if (positions.length === 0) {
    return <div className="warning-box">No float data available.</div>;
  }

  const lats = positions.map(p => p.latitude);
  const lons = positions.map(p => p.longitude);
  const temps = positions.map(p => p.surface_temp);
  const text = positions.map(p => `Float ${p.float_id}<br>SST: ${p.surface_temp}°C`);

  const plotData = [
    {
      type: 'scattergeo',
      lat: lats,
      lon: lons,
      mode: 'markers',
      marker: {
        size: 7,
        color: temps,
        colorscale: [
          [0, '#1d4ed8'],
          [0.35, '#2563eb'],
          [0.65, '#F2F4F3'],
          [0.85, '#E8C675'],
          [1, '#E87575']
        ],
        showscale: true,
        colorbar: {
          title: { text: 'SST (°C)', font: { color: '#858C89', size: 11 } },
          thickness: 10,
          len: 0.5,
          tickfont: { color: '#858C89', size: 10 },
          bordercolor: '#242828',
          outlinecolor: '#242828'
        },
        opacity: 0.9
      },
      text: text,
      hoverinfo: 'text'
    }
  ];

  const plotLayout = {
    height: 580,
    margin: { l: 0, r: 0, t: 0, b: 0 },
    paper_bgcolor: '#ffffff',
    geo: {
      center: { lat: 5, lon: 75 },
      showland: true,
      landcolor: '#d4e6f1',
      showocean: true,
      oceancolor: '#b3e5fc',
      showcoastlines: true,
      coastlinecolor: '#0d47a1',
      showcountries: true,
      countrycolor: '#90caf9',
      showframe: false,
      resolution: 40
    },
    font: { family: 'Inter, sans-serif', color: '#212121' }
  };

  return (
    <div className="map-dark-mode">
      <h2>All INCOIS Argo Floats — Indian Ocean</h2>
      <div style={{ width: '100%', borderRadius: '10px', overflow: 'hidden', border: '1px solid #242828' }}>
        <Plot
          data={plotData}
          layout={plotLayout}
          useResizeHandler={true}
          style={{ width: '100%', height: '580px' }}
          config={{ responsive: true, displayModeBar: false }}
        />
      </div>
      <div className="st-caption">{positions.length} floats shown. Color = surface temperature.</div>
    </div>
  );
}
