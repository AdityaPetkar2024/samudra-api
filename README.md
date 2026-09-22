# Samudra: Indian Ocean Intelligence API

A REST API for Indian Ocean oceanographic data, built on 90,000+ Argo float profiles from INCOIS (2002-2026) with real-time TEOS-10 parameter computation.

**[Live API](https://samudra-api.onrender.com/docs) · [Dashboard](https://samudra-api-1.onrender.com)**

> The dashboard provides interactive visualizations of Argo float trajectories, oceanographic parameter distributions, and Indian Ocean climatology across 2002–2026.

---

## Data

- 90,516 Argo float profiles (INCOIS GDAC, 2002–2026)
- 87,648 computed profiles with 11 GSW TEOS-10 parameters
- 2.4M Copernicus satellite climatology records (2024)
- 587 tracked INCOIS Argo floats

## Computed Parameters

Mixed Layer Depth · Isothermal Layer Depth · Barrier Layer Thickness · Thermocline Depth · D20 · Tropical Cyclone Heat Potential · Conservative Temperature · Absolute Salinity · Potential Density · Brunt-Väisälä N² · Stratification Index

## Key Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /ocean/intelligence` | Full oceanographic profile for a lat/lon |
| `GET /ocean/timeseries` | Historical time series for a location |
| `GET /ocean/region/{region}` | Indian Ocean regional statistics |
| `GET /ocean/float/{float_id}` | Individual Argo float data |
| `GET /health` | API status |

## Data Sources and Provenance

Argo profile data is sourced directly from INCOIS GDAC as raw NetCDF files, not from gridded products. All oceanographic parameters (MLD, thermocline depth, BLT, TCHP, conservative temperature, absolute salinity, potential density) are computed from these raw profiles using GSW TEOS-10 v3.6.

Copernicus Marine data is used in two distinct ways:
- Monthly climatology (2.4M records, 2024) serves only as a baseline for satellite anomaly calculations
- Live near-real-time SST, SSH, and chlorophyll values are pulled per query

Gridded satellite products are interpolated and extrapolated fields, not direct observations, and should not be treated as measurements.

## Data Limitations

Argo float coverage is not uniform. Floats are not deployed near continental slopes and do not survive well in those regions, so coastal and shelf areas have sparse or no direct observations. Values returned for such regions derive largely from extrapolation from the open ocean interior and should be treated with caution.

Users should not treat interpolated or gridded values as equivalent to in-situ measurements.

## Quality Control

A profile-level QC pipeline implementing the Argo Quality Control Manual v3.9 has been applied to the Argo and CTD data underlying this API. See `samudra_qc/` for the implementation and a full report of findings.

## Stack

FastAPI · PostgreSQL (Supabase) · GSW TEOS-10 · Copernicus Marine API · Streamlit

For questions or research collaboration, open an issue.
