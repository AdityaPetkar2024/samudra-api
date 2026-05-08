from datetime import date
import datetime
import os
import numpy as np
from urllib.parse import urlparse
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import psycopg2
from psycopg2.extras import RealDictCursor

app = FastAPI(
    title="Samudra Ocean Intelligence API",
    description="Unified Indian Ocean intelligence — Argo + Copernicus + IOTC",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL:
    result = urlparse(DATABASE_URL)
    DB_CONFIG = {
        "host":     result.hostname,
        "database": result.path[1:],
        "user":     result.username,
        "password": result.password,
        "port":     result.port
    }
else:
    DB_CONFIG = {
        "host":     "localhost",
        "database": "argo_db12",
        "user":     "argo_user1",
        "password": "argo123"
    }

COPERNICUS_USER = os.getenv("COPERNICUS_USERNAME")
COPERNICUS_PASS = os.getenv("COPERNICUS_PASSWORD")

API_KEYS = {"test-key-samudra-v1": "free"}

def get_conn():
    return psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)

def verify_key(api_key: str):
    if api_key not in API_KEYS:
        raise HTTPException(status_code=401, detail="Invalid API key. Get one at samudra.io")
    return api_key

def detect_region(lat: float, lon: float) -> str:
    if 5 <= lat <= 25 and 50 <= lon <= 78:
        return "Arabian Sea"
    elif 5 <= lat <= 22 and 78 <= lon <= 100:
        return "Bay of Bengal"
    elif -70 <= lat <= -30:
        return "Southern Ocean"
    elif -10 <= lat <= 10 and 40 <= lon <= 110:
        return "Equatorial Indian Ocean"
    elif 5 <= lat <= 15 and 70 <= lon <= 78:
        return "Lakshadweep Sea"
    else:
        return "Indian Ocean"

def safe_round(val, digits):
    try:
        v = float(val)
        if np.isnan(v):
            return None
        return round(v, digits)
    except:
        return None

def get_live_copernicus(lat: float, lon: float) -> dict:
    if not COPERNICUS_USER or not COPERNICUS_PASS:
        return {}
    try:
        import copernicusmarine
        result = {}

        # SST
        try:
            ds = copernicusmarine.open_dataset(
                dataset_id="cmems_mod_glo_phy-thetao_anfc_0.083deg_P1D-m",
                username=COPERNICUS_USER,
                password=COPERNICUS_PASS,
                minimum_latitude=lat - 0.1,
                maximum_latitude=lat + 0.1,
                minimum_longitude=lon - 0.1,
                maximum_longitude=lon + 0.1,
                minimum_depth=0,
                maximum_depth=1,
            )
            sst = float(ds["thetao"].isel(time=-1, depth=0).mean().values)
            result["sst_value"] = safe_round(sst, 2)
            result["sst_date"]  = str(ds.time.values[-1])[:10]
        except Exception:
            pass

        # SSH
        try:
            ds = copernicusmarine.open_dataset(
                dataset_id="cmems_mod_glo_phy_anfc_0.083deg_P1D-m",
                username=COPERNICUS_USER,
                password=COPERNICUS_PASS,
                minimum_latitude=lat - 0.1,
                maximum_latitude=lat + 0.1,
                minimum_longitude=lon - 0.1,
                maximum_longitude=lon + 0.1,
            )
            ssh = float(ds["zos"].isel(time=-1).mean().values)
            result["ssh_value"] = safe_round(ssh, 3)
        except Exception:
            pass

        # SST anomaly
        try:
            ds = copernicusmarine.open_dataset(
                dataset_id="cmems_mod_glo_phy_anfc_0.083deg-sst-anomaly_P1D-m",
                username=COPERNICUS_USER,
                password=COPERNICUS_PASS,
                minimum_latitude=lat - 0.1,
                maximum_latitude=lat + 0.1,
                minimum_longitude=lon - 0.1,
                maximum_longitude=lon + 0.1,
            )
            anom = float(ds["sea_surface_temperature_anomaly"].isel(time=-1).mean().values)
            result["sst_anomaly"] = safe_round(anom, 3)
        except Exception:
            pass

        # CHL
        try:
            ds = copernicusmarine.open_dataset(
                dataset_id="cmems_obs-oc_glo_bgc-plankton_nrt_l4-gapfree-multi-4km_P1D",
                username=COPERNICUS_USER,
                password=COPERNICUS_PASS,
                minimum_latitude=lat - 0.3,
                maximum_latitude=lat + 0.3,
                minimum_longitude=lon - 0.3,
                maximum_longitude=lon + 0.3,
            )
            for i in range(-1, -8, -1):
                chl = float(ds["CHL"].isel(time=i).mean().values)
                if not np.isnan(chl):
                    result["chlorophyll_value"] = safe_round(chl, 4)
                    result["chl_date"] = str(ds.time.values[i])[:10]
                    break
        except Exception:
            pass

        return result
    except Exception:
        return {}


# =============================================================================
# ENDPOINTS
# =============================================================================

@app.get("/", tags=["Info"])
def root():
    return {
        "product":      "Samudra Ocean Intelligence API",
        "version":      "1.0.0",
        "docs":         "/docs",
        "coverage":     "Northern Indian Ocean (Arabian Sea, Bay of Bengal, Central IO)",
        "data_sources": [
            "INCOIS Argo (587 floats, 14.5M measurements, 2002-2026)",
            "Copernicus SST/SSH/Chlorophyll NRT (live)",
            "IOTC Tuna Catch Records"
        ],
        "computed": [
            "MLD", "ILD", "BLT", "Thermocline", "D20",
            "TCHP", "SST", "SST Anomaly", "SSH", "Chlorophyll",
            "Upwelling Index", "Productivity Index"
        ],
        "free_tier": "100 calls/day — api_key: test-key-samudra-v1"
    }


@app.get("/ocean/intelligence", tags=["Ocean Intelligence"])
def ocean_intelligence(
    lat: float,
    lon: float,
    api_key: str = "test-key-samudra-v1"
):
    """
    Main endpoint. Returns unified ocean intelligence for any Indian Ocean coordinate.

    - **lat**: Latitude (-70 to 30)
    - **lon**: Longitude (20 to 120)
    - **api_key**: Your API key
    """
    verify_key(api_key)

    if not (-70 <= lat <= 30 and 20 <= lon <= 120):
        raise HTTPException(
            status_code=400,
            detail="Coordinates outside Indian Ocean bounds. lat: -70 to 30, lon: 20 to 120"
        )

    conn = get_conn()
    cur  = conn.cursor()
    current_month = datetime.date.today().month

    try:
        # ── 1. Nearest Argo float ──
        cur.execute("""
            SELECT *,
                ROUND((
                    6371 * acos(LEAST(1.0,
                        cos(radians(%s)) * cos(radians(latitude)) *
                        cos(radians(longitude) - radians(%s)) +
                        sin(radians(%s)) * sin(radians(latitude))
                    ))
                )::numeric, 1) as distance_km
            FROM computed_profiles
            WHERE latitude  BETWEEN %s AND %s
            AND   longitude BETWEEN %s AND %s
            AND   measurement_date >= NOW() - INTERVAL '365 days'
            ORDER BY distance_km
            LIMIT 1
        """, (lat, lon, lat,
              lat - 5, lat + 5,
              lon - 5, lon + 5))

        argo      = cur.fetchone()
        argo_dict = dict(argo) if argo else None
        if argo_dict and float(argo_dict["distance_km"]) > 300:
            argo_dict = None

        # ── 2. Live Copernicus ──
        live = get_live_copernicus(lat, lon)

        # ── 3. Monthly climatology fallback ──
        cur.execute("""
            SELECT avg_sst as sst, avg_ssh as ssh
            FROM copernicus_monthly
            WHERE month = %s
            AND latitude  BETWEEN %s AND %s
            AND longitude BETWEEN %s AND %s
            LIMIT 1
        """, (current_month, lat - 0.1, lat + 0.1, lon - 0.1, lon + 0.1))
        clim = dict(cur.fetchone() or {})

        cur.execute("""
            SELECT avg_chl as chl
            FROM copernicus_monthly
            WHERE month = %s
            AND latitude  BETWEEN %s AND %s
            AND longitude BETWEEN %s AND %s
            AND avg_chl IS NOT NULL
            LIMIT 1
        """, (current_month, lat - 0.3, lat + 0.3, lon - 0.3, lon + 0.3))
        clim_chl = dict(cur.fetchone() or {})

        # ── 4. Build satellite block ──
        satellite = {}
        satellite["sst_value"]        = live.get("sst_value")        or safe_round(clim.get("sst"), 2)
        satellite["sst_anomaly"]       = live.get("sst_anomaly")
        satellite["ssh_value"]         = live.get("ssh_value")        or safe_round(clim.get("ssh"), 3)
        satellite["chlorophyll_value"] = live.get("chlorophyll_value") or safe_round(clim_chl.get("chl"), 4)
        satellite["data_date"]         = live.get("sst_date", f"climatology-month-{current_month}")

        # SSH anomaly from climatology
        if live.get("ssh_value") and clim.get("ssh"):
            satellite["ssh_anomaly"] = safe_round(live["ssh_value"] - float(clim["ssh"]), 3)

        # CHL anomaly from climatology
        if live.get("chlorophyll_value") and clim_chl.get("chl"):
            satellite["chlorophyll_anomaly"] = safe_round(live["chlorophyll_value"] - float(clim_chl["chl"]), 4)

        # ── 5. Compute indices ──
        sst_anom = satellite.get("sst_anomaly")
        ssh_anom = satellite.get("ssh_anomaly")
        ssh_val  = satellite.get("ssh_value")
        chl_val  = satellite.get("chlorophyll_value")
        chl_anom = satellite.get("chlorophyll_anomaly")

        upwelling_index    = None
        productivity_index = None

        if sst_anom is not None and ssh_anom is not None:
            raw = (-sst_anom * 0.5) + (-ssh_anom * 10)
            upwelling_index = safe_round(max(0.0, min(1.0, (raw + 2) / 4)), 3)
        elif ssh_val is not None:
            raw = (-ssh_val * 10)
            upwelling_index = safe_round(max(0.0, min(1.0, (raw + 2) / 4)), 3)

        if chl_anom is not None and upwelling_index is not None:
            raw = (chl_anom * 0.4) + (upwelling_index * 0.6)
            productivity_index = safe_round(max(0.0, min(1.0, (raw + 1) / 2)), 3)
        elif chl_val is not None:
            productivity_index = safe_round(min(1.0, chl_val / 1.0), 3)

        satellite["upwelling_index"]    = upwelling_index
        satellite["productivity_index"] = productivity_index

        # ── 6. Response ──
        region = detect_region(lat, lon)
        result = {
            "location":  {"lat": lat, "lon": lon, "region": region},
            "satellite": satellite if any(v is not None for v in satellite.values()) else None,
            "argo":      None,
            "metadata": {
                "argo_source":    "INCOIS GDAC 2002-2026",
                "sst_source":     "Copernicus OSTIA L4 NRT",
                "ssh_source":     "Copernicus DUACS NRT",
                "chl_source":     "Copernicus GlobColour NRT",
                "computed_using": "gsw TEOS-10 v3.6",
                "cite_as":        "Samudra Ocean Intelligence API v1.0 (2025). samudra.io"
            }
        }

        if argo_dict:
            mdate    = argo_dict["measurement_date"]
            age_days = (date.today() - mdate.date()).days if mdate else None
            result["argo"] = {
                "float_id":         argo_dict["float_id"],
                "distance_km":      safe_round(argo_dict["distance_km"], 1),
                "measurement_date": str(mdate),
                "data_age_days":    age_days,
                "latitude":         safe_round(argo_dict["latitude"], 4),
                "longitude":        safe_round(argo_dict["longitude"], 4),
                "thermal_structure": {
                    "mixed_layer_depth":       safe_round(argo_dict["mixed_layer_depth"], 1),
                    "isothermal_layer_depth":  safe_round(argo_dict["isothermal_layer_depth"], 1),
                    "barrier_layer_thickness": safe_round(argo_dict["barrier_layer_thickness"], 1),
                    "thermocline_depth":       safe_round(argo_dict["thermocline_depth"], 1),
                    "d20_depth":               safe_round(argo_dict["d20_depth"], 1),
                    "tchp_kj_cm2":             safe_round(argo_dict["tchp_kj_cm2"], 2),
                },
                "water_mass": {
                    "potential_density_surface": safe_round(argo_dict["potential_density_surface"], 4),
                    "conservative_temp":         safe_round(argo_dict["conservative_temp"], 3),
                    "absolute_salinity":         safe_round(argo_dict["absolute_salinity"], 4),
                }
            }
        else:
            result["argo_note"] = "No INCOIS float within 300km. Coverage is densest in Arabian Sea and Bay of Bengal."

        return result

    finally:
        cur.close()
        conn.close()


@app.get("/ocean/timeseries", tags=["Ocean Intelligence"])
def ocean_timeseries(lat: float, lon: float, radius_deg: float = 3.0, api_key: str = "test-key-samudra-v1"):
    """Time series of Argo profiles near a coordinate."""
    verify_key(api_key)
    if not (-70 <= lat <= 30 and 20 <= lon <= 120):
        raise HTTPException(status_code=400, detail="Coordinates outside Indian Ocean bounds.")
    conn = get_conn()
    cur  = conn.cursor()
    try:
        cur.execute("""
            SELECT float_id, measurement_date, latitude, longitude,
                mixed_layer_depth, thermocline_depth, barrier_layer_thickness,
                d20_depth, tchp_kj_cm2, conservative_temp, absolute_salinity,
                ROUND((6371 * acos(LEAST(1.0,
                    cos(radians(%s)) * cos(radians(latitude)) *
                    cos(radians(longitude) - radians(%s)) +
                    sin(radians(%s)) * sin(radians(latitude))
                )))::numeric, 1) as distance_km
            FROM computed_profiles
            WHERE latitude BETWEEN %s AND %s AND longitude BETWEEN %s AND %s
            ORDER BY measurement_date ASC
        """, (lat, lon, lat, lat-radius_deg, lat+radius_deg, lon-radius_deg, lon+radius_deg))
        rows = cur.fetchall()
        return {"query": {"lat": lat, "lon": lon, "radius_deg": radius_deg, "region": detect_region(lat, lon)},
                "count": len(rows), "timeseries": [dict(r) for r in rows],
                "cite_as": "Samudra Ocean Intelligence API v1.0 (2025). samudra.io"}
    finally:
        cur.close()
        conn.close()


@app.get("/ocean/float/{float_id}", tags=["Argo Floats"])
def get_float(float_id: str, api_key: str = "test-key-samudra-v1"):
    """Get computed profiles for a specific Argo float."""
    verify_key(api_key)
    conn = get_conn()
    cur  = conn.cursor()
    try:
        cur.execute("SELECT * FROM computed_profiles WHERE float_id = %s ORDER BY measurement_date DESC LIMIT 20", (float_id,))
        rows = cur.fetchall()
        if not rows:
            raise HTTPException(status_code=404, detail=f"Float {float_id} not found")
        return {"float_id": float_id, "profile_count": len(rows), "profiles": [dict(r) for r in rows]}
    finally:
        cur.close()
        conn.close()


@app.get("/ocean/region/{region}", tags=["Regional Summary"])
def get_region(region: str, api_key: str = "test-key-samudra-v1"):
    """Summary statistics for a named region."""
    verify_key(api_key)
    regions = {
        "arabian_sea":    {"lat1": 5,   "lat2": 25,  "lon1": 50,  "lon2": 78},
        "bay_of_bengal":  {"lat1": 5,   "lat2": 22,  "lon1": 78,  "lon2": 100},
        "indian_ocean":   {"lat1": -70, "lat2": 30,  "lon1": 20,  "lon2": 120},
        "southern_ocean": {"lat1": -70, "lat2": -30, "lon1": 0,   "lon2": 150},
        "equatorial":     {"lat1": -10, "lat2": 10,  "lon1": 40,  "lon2": 110},
    }
    if region not in regions:
        raise HTTPException(status_code=400, detail=f"Invalid region. Valid: {list(regions.keys())}")
    r = regions[region]
    conn = get_conn()
    cur  = conn.cursor()
    try:
        cur.execute("""
            SELECT COUNT(*) as float_count,
                ROUND(AVG(mixed_layer_depth)::numeric, 2) as avg_mld_m,
                ROUND(AVG(thermocline_depth)::numeric, 2) as avg_thermocline_m,
                ROUND(AVG(barrier_layer_thickness)::numeric, 2) as avg_blt_m,
                ROUND(AVG(d20_depth)::numeric, 2) as avg_d20_m,
                ROUND(AVG(tchp_kj_cm2)::numeric, 2) as avg_tchp,
                ROUND(MAX(tchp_kj_cm2)::numeric, 2) as max_tchp,
                ROUND(AVG(conservative_temp)::numeric, 2) as avg_temp_c,
                ROUND(AVG(absolute_salinity)::numeric, 3) as avg_salinity
            FROM computed_profiles
            WHERE latitude BETWEEN %s AND %s AND longitude BETWEEN %s AND %s
        """, (r['lat1'], r['lat2'], r['lon1'], r['lon2']))
        summary = cur.fetchone()
        cur.execute("""
            SELECT stratification, COUNT(*) as count FROM computed_profiles
            WHERE latitude BETWEEN %s AND %s AND longitude BETWEEN %s AND %s
            GROUP BY stratification ORDER BY count DESC
        """, (r['lat1'], r['lat2'], r['lon1'], r['lon2']))
        strat_rows = cur.fetchall()
        return {"region": region, "summary": dict(summary) if summary else {},
                "stratification_breakdown": [dict(s) for s in strat_rows]}
    finally:
        cur.close()
        conn.close()


@app.get("/ocean/search", tags=["Search"])
def search_floats(lat: float, lon: float, radius_deg: float = 3.0, limit: int = 10, api_key: str = "test-key-samudra-v1"):
    """Find Argo profiles near a coordinate."""
    verify_key(api_key)
    conn = get_conn()
    cur  = conn.cursor()
    try:
        cur.execute("""
            SELECT float_id, latitude, longitude, measurement_date,
                mixed_layer_depth, thermocline_depth, tchp_kj_cm2, conservative_temp,
                ROUND((6371 * acos(LEAST(1.0,
                    cos(radians(%s)) * cos(radians(latitude)) *
                    cos(radians(longitude) - radians(%s)) +
                    sin(radians(%s)) * sin(radians(latitude))
                )))::numeric, 1) as distance_km
            FROM computed_profiles
            WHERE latitude BETWEEN %s AND %s AND longitude BETWEEN %s AND %s
            ORDER BY distance_km LIMIT %s
        """, (lat, lon, lat, lat-radius_deg, lat+radius_deg, lon-radius_deg, lon+radius_deg, limit))
        rows = cur.fetchall()
        return {"query": {"lat": lat, "lon": lon, "radius_deg": radius_deg},
                "count": len(rows), "floats": [dict(r) for r in rows]}
    finally:
        cur.close()
        conn.close()


@app.get("/health", tags=["Info"])
def health():
    """API health check."""
    conn = get_conn()
    cur  = conn.cursor()
    status = {"status": "ok", "tables": {}}
    try:
        for table in ["computed_profiles", "profiles", "floats", "copernicus_monthly"]:
            try:
                cur.execute(f"SELECT COUNT(*) as c FROM {table}")
                status["tables"][table] = cur.fetchone()["c"]
            except Exception as e:
                status["tables"][table] = f"unavailable: {str(e).split(chr(10))[0]}"
        status["copernicus_live"] = "enabled" if COPERNICUS_USER else "disabled"
        status["coverage"] = "Indian Ocean 2002-2026"
        return status
    finally:
        cur.close()
        conn.close()
