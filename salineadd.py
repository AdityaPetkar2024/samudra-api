"""
Samudra Dashboard — Streamlit
Uses Railway PostgreSQL + live Copernicus API + OpenAI chat
"""

import streamlit as st
import plotly.graph_objects as go
import pandas as pd
import numpy as np
import os
from sqlalchemy import create_engine
from llm_with_mcp import chat_with_tools

st.set_page_config(page_title="Samudra — Indian Ocean Intelligence", page_icon="🌊", layout="wide")

st.markdown("""<style>
.stMetric { background: #0d1b2a; padding: 10px; border-radius: 8px; }
h1 { color: #4a9eff; }
h2 { color: #4a9eff; }
</style>""", unsafe_allow_html=True)

st.title("🌊 Samudra — Indian Ocean Intelligence")
st.markdown("INCOIS Argo floats · Copernicus satellite · IOTC tuna catch")

# ── DB connection ─────────────────────────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://argo_user1:argo123@localhost/argo_db12")

@st.cache_resource
def get_engine():
    return create_engine(DATABASE_URL)

@st.cache_data(ttl=3600)
def get_stats():
    engine = get_engine()
    with engine.connect() as conn:
        f = pd.read_sql("SELECT COUNT(*) as c FROM floats", conn)['c'][0]
        p = pd.read_sql("SELECT COUNT(*) as c FROM profiles", conn)['c'][0]
        cp = pd.read_sql("SELECT COUNT(*) as c FROM computed_profiles", conn)['c'][0]
    return f, p, cp

@st.cache_data(ttl=3600)
def get_float_positions():
    engine = get_engine()
    with engine.connect() as conn:
        df = pd.read_sql("""
            SELECT p.float_id, p.latitude, p.longitude, p.surface_temp, p.max_depth
            FROM profiles p
            INNER JOIN (
                SELECT float_id, MAX(profile_idx) as latest
                FROM profiles GROUP BY float_id
            ) l ON p.float_id = l.float_id AND p.profile_idx = l.latest
            WHERE p.latitude IS NOT NULL AND p.longitude IS NOT NULL
        """, conn)
    return df

@st.cache_data(ttl=3600)
def get_float_list():
    engine = get_engine()
    with engine.connect() as conn:
        return pd.read_sql(
            "SELECT float_id, COUNT(*) as profile_count FROM profiles GROUP BY float_id ORDER BY profile_count DESC",
            conn
        )

@st.cache_data(ttl=3600)
def get_float_profiles(float_id):
    engine = get_engine()
    with engine.connect() as conn:
        return pd.read_sql("""
            SELECT profile_idx, latitude, longitude,
                   surface_temp, surface_salinity, max_depth, measurement_date
            FROM profiles WHERE float_id = %(fid)s ORDER BY profile_idx
        """, conn, params={"fid": float_id})

@st.cache_data(ttl=3600)
def get_computed_profile(float_id, profile_idx):
    engine = get_engine()
    with engine.connect() as conn:
        return pd.read_sql("""
            SELECT mixed_layer_depth, isothermal_layer_depth, barrier_layer_thickness,
                   thermocline_depth, d20_depth, tchp_kj_cm2,
                   conservative_temp, absolute_salinity, potential_density_surface
            FROM computed_profiles
            WHERE float_id = %(fid)s AND profile_idx = %(pid)s
        """, conn, params={"fid": float_id, "pid": int(profile_idx)})

@st.cache_data(ttl=3600)
def get_region_stats(region):
    bounds = {
        "Arabian Sea":    (5, 25, 50, 78),
        "Bay of Bengal":  (5, 22, 78, 100),
        "Equatorial IO":  (-10, 10, 40, 110),
        "Southern Ocean": (-70, -30, 0, 150),
    }
    lat1, lat2, lon1, lon2 = bounds[region]
    engine = get_engine()
    with engine.connect() as conn:
        return pd.read_sql("""
            SELECT COUNT(DISTINCT float_id) as floats,
                   ROUND(AVG(mixed_layer_depth)::numeric, 1) as avg_mld,
                   ROUND(AVG(thermocline_depth)::numeric, 1) as avg_thermocline,
                   ROUND(AVG(tchp_kj_cm2)::numeric, 2) as avg_tchp,
                   ROUND(AVG(conservative_temp)::numeric, 2) as avg_temp,
                   ROUND(AVG(absolute_salinity)::numeric, 3) as avg_salinity
            FROM computed_profiles
            WHERE latitude BETWEEN %(lat1)s AND %(lat2)s
            AND longitude BETWEEN %(lon1)s AND %(lon2)s
        """, conn, params={"lat1": lat1, "lat2": lat2, "lon1": lon1, "lon2": lon2})

# ── Header stats ──────────────────────────────────────────────────────────────
try:
    floats_count, profiles_count, computed_count = get_stats()
    c1, c2, c3 = st.columns(3)
    c1.metric("Argo Floats", f"{floats_count:,}")
    c2.metric("Profiles", f"{profiles_count:,}")
    c3.metric("Computed Profiles", f"{computed_count:,}")
except Exception as e:
    st.error(f"DB connection error: {e}")
    st.stop()

st.divider()

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs(["🗺️ Float Map", "🔍 Float Explorer", "📊 Regional Stats", "🤖 Ask Samudra"])

# ── Tab 1: Float Map ──────────────────────────────────────────────────────────
with tab1:
    st.subheader("All INCOIS Argo Floats — Indian Ocean")
    positions = get_float_positions()

    fig = go.Figure()
    fig.add_trace(go.Scattergeo(
        lat=positions['latitude'],
        lon=positions['longitude'],
        mode='markers',
        marker=dict(
            size=7,
            color=positions['surface_temp'],
            colorscale='Plasma',
            showscale=True,
            colorbar=dict(title="SST (°C)", thickness=12, len=0.6),
            opacity=0.85,
            line=dict(width=0.3, color='white')
        ),
        text=[f"Float {r['float_id']}<br>SST: {r['surface_temp']:.1f}°C<br>Max depth: {r['max_depth']:.0f}m"
              for _, r in positions.iterrows()],
        hoverinfo='text',
    ))
    fig.update_geos(
        center=dict(lat=-5, lon=75), projection_scale=3,
        projection_type='natural earth',
        showland=True, landcolor='#1a1a2e',
        showocean=True, oceancolor='#0d2137',
        showcoastlines=True, coastlinecolor='#4a9eff',
        showcountries=True, countrycolor='#2a2a4a',
        showframe=False
    )
    fig.update_layout(height=580, margin=dict(l=0, r=0, t=0, b=0), paper_bgcolor='rgba(0,0,0,0)')
    st.plotly_chart(fig, use_container_width=True)
    st.caption(f"{len(positions)} floats shown. Color = surface temperature.")

# ── Tab 2: Float Explorer ─────────────────────────────────────────────────────
with tab2:
    st.subheader("Explore Individual Float")
    floats_df = get_float_list()
    selected = st.selectbox(
        "Select Float",
        floats_df['float_id'].tolist(),
        format_func=lambda x: f"Float {x} ({floats_df[floats_df['float_id']==x]['profile_count'].values[0]} profiles)"
    )

    profiles_df = get_float_profiles(selected)
    if profiles_df.empty:
        st.warning("No profiles found.")
    else:
        col1, col2 = st.columns(2)

        # Track map
        with col1:
            fig_track = go.Figure()
            fig_track.add_trace(go.Scattergeo(
                lat=profiles_df['latitude'], lon=profiles_df['longitude'],
                mode='lines+markers',
                line=dict(width=1.5, color='#4a9eff'),
                marker=dict(size=5, color=profiles_df['surface_temp'],
                            colorscale='Plasma', showscale=True,
                            colorbar=dict(title="SST °C", thickness=10, len=0.5)),
                text=[f"Profile {r['profile_idx']}<br>{r['measurement_date']}<br>SST: {r['surface_temp']:.1f}°C"
                      for _, r in profiles_df.iterrows()],
                hoverinfo='text'
            ))
            fig_track.update_geos(
                fitbounds="locations", showland=True, landcolor='#1a1a2e',
                showocean=True, oceancolor='#0d2137',
                showcoastlines=True, coastlinecolor='#4a9eff', showframe=False
            )
            fig_track.update_layout(height=350, margin=dict(l=0,r=0,t=30,b=0),
                                    title=f"Float {selected} Track",
                                    paper_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig_track, use_container_width=True)

        # SST time series
        with col2:
            fig_ts = go.Figure()
            fig_ts.add_trace(go.Scatter(
                x=profiles_df['measurement_date'], y=profiles_df['surface_temp'],
                mode='lines+markers', line=dict(color='#ff6b6b', width=1.5),
                marker=dict(size=4), name='SST'
            ))
            fig_ts.update_layout(
                title=f"Float {selected} — Surface Temperature",
                xaxis_title="Date", yaxis_title="SST (°C)",
                height=350, paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='#0d1117', font=dict(color='white')
            )
            st.plotly_chart(fig_ts, use_container_width=True)

        # Computed profile depths
        st.subheader("Ocean Layer Structure")
        latest_idx = profiles_df['profile_idx'].max()
        computed = get_computed_profile(selected, latest_idx)

        if not computed.empty:
            row = computed.iloc[0]
            d1, d2, d3, d4 = st.columns(4)
            d1.metric("Mixed Layer Depth", f"{row['mixed_layer_depth']:.1f} m")
            d2.metric("Thermocline Depth", f"{row['thermocline_depth']:.1f} m")
            d3.metric("Barrier Layer", f"{row['barrier_layer_thickness']:.1f} m")
            d4.metric("TCHP", f"{row['tchp_kj_cm2']:.2f} kJ/cm²")

            # Depth structure visualization
            fig_depth = go.Figure()
            layers = {
                "Mixed Layer": row['mixed_layer_depth'],
                "Isothermal Layer": row['isothermal_layer_depth'],
                "Thermocline": row['thermocline_depth'],
                "D20": row['d20_depth'],
            }
            colors = ['#4a9eff', '#45b7d1', '#ff9f43', '#ff6b6b']
            for (name, depth), color in zip(layers.items(), colors):
                if depth and not pd.isna(depth):
                    fig_depth.add_trace(go.Bar(
                        x=[float(depth)], y=[name], orientation='h',
                        marker_color=color, name=name,
                        text=[f"{depth:.1f} m"], textposition='outside'
                    ))
            fig_depth.update_layout(
                title="Ocean Layer Depths (latest profile)",
                xaxis_title="Depth (m)", height=250,
                paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='#0d1117',
                font=dict(color='white'), showlegend=False
            )
            st.plotly_chart(fig_depth, use_container_width=True)

# ── Tab 3: Regional Stats ─────────────────────────────────────────────────────
with tab3:
    st.subheader("Regional Ocean Summary")
    region = st.selectbox("Region", ["Arabian Sea", "Bay of Bengal", "Equatorial IO", "Southern Ocean"])

    stats = get_region_stats(region)
    if not stats.empty:
        r = stats.iloc[0]
        c1, c2, c3, c4, c5, c6 = st.columns(6)
        c1.metric("Floats", f"{int(r['floats'])}")
        c2.metric("Avg MLD", f"{r['avg_mld']} m")
        c3.metric("Avg Thermocline", f"{r['avg_thermocline']} m")
        c4.metric("Avg TCHP", f"{r['avg_tchp']} kJ/cm²")
        c5.metric("Avg Temp", f"{r['avg_temp']} °C")
        c6.metric("Avg Salinity", f"{r['avg_salinity']} PSU")

    # Copernicus monthly climatology for this region
    region_bounds = {
        "Arabian Sea":    (15, 65),
        "Bay of Bengal":  (15, 88),
        "Equatorial IO":  (0, 75),
        "Southern Ocean": (-40, 75),
    }
    lat_c, lon_c = region_bounds[region]

    engine = get_engine()
    with engine.connect() as conn:
        clim = pd.read_sql("""
            SELECT month, avg_sst, avg_ssh, avg_chl
            FROM copernicus_monthly
            WHERE latitude BETWEEN %(lat)s AND %(lat2)s
            AND longitude BETWEEN %(lon)s AND %(lon2)s
            ORDER BY month
        """, conn, params={"lat": lat_c-0.2, "lat2": lat_c+0.2,
                           "lon": lon_c-0.2, "lon2": lon_c+0.2})

    if not clim.empty:
        fig_clim = go.Figure()
        fig_clim.add_trace(go.Scatter(
            x=clim['month'], y=clim['avg_sst'],
            mode='lines+markers', name='SST (°C)',
            line=dict(color='#ff6b6b', width=2)
        ))
        fig_clim.add_trace(go.Scatter(
            x=clim['month'], y=clim['avg_chl'],
            mode='lines+markers', name='CHL (mg/m³)',
            line=dict(color='#2ecc71', width=2),
            yaxis='y2'
        ))
        fig_clim.update_layout(
            title=f"{region} — Monthly Climatology (2024)",
            xaxis=dict(title="Month", tickmode='linear', tick0=1, dtick=1),
            yaxis=dict(title="SST (°C)", color='#ff6b6b'),
            yaxis2=dict(title="Chlorophyll (mg/m³)", overlaying='y', side='right', color='#2ecc71'),
            height=350, paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='#0d1117', font=dict(color='white'),
            legend=dict(x=0.01, y=0.99)
        )
        st.plotly_chart(fig_clim, use_container_width=True)

# ── Tab 4: Chat ───────────────────────────────────────────────────────────────
with tab4:
    st.subheader("Ask Samudra")
    st.caption("Ask anything about Argo floats, ocean conditions, or tuna catch data")

    examples = [
        "Which float has the deepest thermocline?",
        "Average MLD in Arabian Sea this year",
        "Floats near Chennai",
        "Warmest surface temp recorded",
        "Compare Arabian Sea vs Bay of Bengal salinity",
        "Top 5 floats by profile count",
    ]

    st.markdown("**Try these:**")
    cols = st.columns(3)
    for i, q in enumerate(examples):
        if cols[i % 3].button(q, key=f"ex_{i}"):
            st.session_state.chat_input = q

    if "messages" not in st.session_state:
        st.session_state.messages = []

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Handle example button clicks
    prefill = st.session_state.pop("chat_input", None)

    prompt = st.chat_input("Ask anything...") or prefill
    if prompt:
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant"):
            with st.spinner("Querying database..."):
                try:
                    answer = chat_with_tools(prompt, st.session_state.messages[:-1])
                    st.markdown(answer)
                    st.session_state.messages.append({"role": "assistant", "content": answer})
                except Exception as e:
                    st.error(f"Error: {e}")

st.divider()
st.caption("Samudra v1.0 · INCOIS Argo · Copernicus Marine · IOTC · GSW TEOS-10")
