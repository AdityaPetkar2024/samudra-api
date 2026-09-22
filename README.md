# Samudra:Indian Ocean Intelligence API

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

## Stack

FastAPI · PostgreSQL (Supabase) · GSW TEOS-10 · Copernicus Marine API · Streamlit

## Data Source

Argo float data sourced from [INCOIS GDAC](https://incois.gov.in/portal/argo/argo.jsp). Publicly available but requires local ingestion — see the [Argo data access guide](https://argo.ucsd.edu/data/data-from-gdacs/) for setup.

For questions or research collaboration, open an issue.
