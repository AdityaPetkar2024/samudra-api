from datetime import date
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

import os
from urllib.parse import urlparse

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

def compute_fishing_potential(argo: dict) -> dict:
    if not argo:
        return {
            "fishing_potential": "unknown",
            "score": 0,
            "reasons": ["No nearby Argo float data"]
        }

    score = 0
    reasons = []

    ct = argo.get("conservative_temp")
    if ct and 26 <= ct <= 30:
        score += 2
        reasons.append("optimal temperature range for tuna")

    thermo = argo.get("thermocline_depth")
    if thermo and thermo < 80:
        score += 2
        reasons.append("shallow thermocline — fish accessible")

    tchp = argo.get("tchp_kj_cm2")
    if tchp and 0 < tchp < 250 and tchp > 80:
        score += 1
        reasons.append("high ocean heat content")

    blt = argo.get("barrier_layer_thickness")
    if blt and blt > 20:
        score += 1
        reasons.append("thick barrier layer")

    strat = argo.get("stratification")
    if strat == "moderate":
        score += 1
        reasons.append("moderate stratification — productive")

    if score >= 5:
        potential = "high"
    elif score >= 3:
        potential = "medium"
    else:
        potential = "low"

    return {
        "fishing_potential": potential,
        "score":             score,
        "max_score":         7,
        "reasons":           reasons
    }


# =============================================================================
# ENDPOINTS
# =============================================================================

@app.get("/", tags=["Info"])
def root():
    return {
        "product":      "Samudra Ocean Intelligence API",
        "version":      "1.0.0",
        "docs":         "/docs",
        "coverage":     "Indian Ocean",
        "data_sources": [
            "INCOIS Argo (587 floats, 14.5M measurements)",
            "Copernicus SST/SSH/Chlorophyll",
            "IOTC Tuna Catch Records"
        ],
        "computed":  ["MLD", "ILD", "BLT", "Thermocline",
                      "D20", "TCHP", "N2", "Stratification"],
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

    try:
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
        region    = detect_region(lat, lon)
        fp        = compute_fishing_potential(argo_dict)

        result = {
            "location": {
                "lat":    lat,
                "lon":    lon,
                "region": region
            },
            "argo": None,
            "intelligence": fp,
            "metadata": {
                "argo_source":    "INCOIS GDAC 2002-2025",
                "sst_source":     "Copernicus OSTIA L4",
                "ssh_source":     "Copernicus DUACS",
                "chl_source":     "Copernicus GlobColour",
                "computed_using": "gsw TEOS-10 v3.6",
                "cite_as":        "Samudra Ocean Intelligence API v1.0 (2025). samudra.io"
            }
        }

        if argo_dict:
            mdate    = argo_dict["measurement_date"]
            age_days = (date.today() - mdate.date()).days if mdate else None

            result["argo"] = {
                "float_id":         argo_dict["float_id"],
                "distance_km":      float(argo_dict["distance_km"]),
                "measurement_date": str(mdate),
                "data_age_days":    age_days,
                "latitude":         float(argo_dict["latitude"]),
                "longitude":        float(argo_dict["longitude"]),
                "thermal_structure": {
                    "mixed_layer_depth":       argo_dict["mixed_layer_depth"],
                    "isothermal_layer_depth":  argo_dict["isothermal_layer_depth"],
                    "barrier_layer_thickness": argo_dict["barrier_layer_thickness"],
                    "thermocline_depth":       argo_dict["thermocline_depth"],
                    "d20_depth":               argo_dict["d20_depth"],
                    "tchp_kj_cm2":             argo_dict["tchp_kj_cm2"],
                    "brunt_vaisala_n2":        argo_dict["brunt_vaisala_n2"],
                    "stratification":          argo_dict["stratification"],
                },
                "water_mass": {
                    "potential_density_surface": argo_dict["potential_density_surface"],
                    "conservative_temp":         argo_dict["conservative_temp"],
                    "absolute_salinity":         argo_dict["absolute_salinity"],
                }
            }

        return result

    finally:
        cur.close()
        conn.close()


@app.get("/ocean/timeseries", tags=["Ocean Intelligence"])
def ocean_timeseries(
    lat: float,
    lon: float,
    radius_deg: float = 3.0,
    api_key: str = "test-key-samudra-v1"
):
    """
    Time series of ocean parameters for a location.
    Returns all historical Argo profiles near the coordinate.
    Useful for researchers studying temporal variability.

    - **lat**: Latitude (-70 to 30)
    - **lon**: Longitude (20 to 120)
    - **radius_deg**: Search radius in degrees (default 3.0)
    """
    verify_key(api_key)

    if not (-70 <= lat <= 30 and 20 <= lon <= 120):
        raise HTTPException(
            status_code=400,
            detail="Coordinates outside Indian Ocean bounds."
        )

    conn = get_conn()
    cur  = conn.cursor()

    try:
        cur.execute("""
            SELECT
                float_id,
                measurement_date,
                latitude,
                longitude,
                mixed_layer_depth,
                thermocline_depth,
                barrier_layer_thickness,
                d20_depth,
                tchp_kj_cm2,
                stratification,
                conservative_temp,
                absolute_salinity,
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
            ORDER BY measurement_date ASC
        """, (lat, lon, lat,
              lat - radius_deg, lat + radius_deg,
              lon - radius_deg, lon + radius_deg))

        rows = cur.fetchall()

        return {
            "query": {
                "lat":        lat,
                "lon":        lon,
                "radius_deg": radius_deg,
                "region":     detect_region(lat, lon)
            },
            "count":      len(rows),
            "timeseries": [dict(r) for r in rows],
            "cite_as":    "Samudra Ocean Intelligence API v1.0 (2025). samudra.io"
        }

    finally:
        cur.close()
        conn.close()


@app.get("/ocean/float/{float_id}", tags=["Argo Floats"])
def get_float(float_id: str, api_key: str = "test-key-samudra-v1"):
    """Get all computed profiles for a specific Argo float."""
    verify_key(api_key)
    conn = get_conn()
    cur  = conn.cursor()
    try:
        cur.execute("""
            SELECT * FROM computed_profiles
            WHERE float_id = %s
            ORDER BY measurement_date DESC
            LIMIT 20
        """, (float_id,))
        rows = cur.fetchall()
        if not rows:
            raise HTTPException(status_code=404, detail=f"Float {float_id} not found")
        return {
            "float_id":      float_id,
            "profile_count": len(rows),
            "profiles":      [dict(r) for r in rows]
        }
    finally:
        cur.close()
        conn.close()


@app.get("/ocean/region/{region}", tags=["Regional Summary"])
def get_region(region: str, api_key: str = "test-key-samudra-v1"):
    """
    Summary statistics for a region.

    Valid regions: arabian_sea, bay_of_bengal, indian_ocean, southern_ocean, equatorial
    """
    verify_key(api_key)

    regions = {
        "arabian_sea":    {"lat1": 5,   "lat2": 25,  "lon1": 50,  "lon2": 78},
        "bay_of_bengal":  {"lat1": 5,   "lat2": 22,  "lon1": 78,  "lon2": 100},
        "indian_ocean":   {"lat1": -70, "lat2": 30,  "lon1": 20,  "lon2": 120},
        "southern_ocean": {"lat1": -70, "lat2": -30, "lon1": 0,   "lon2": 150},
        "equatorial":     {"lat1": -10, "lat2": 10,  "lon1": 40,  "lon2": 110},
    }

    if region not in regions:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid region. Valid: {list(regions.keys())}"
        )

    r    = regions[region]
    conn = get_conn()
    cur  = conn.cursor()

    try:
        cur.execute("""
            SELECT
                COUNT(*)                                        as float_count,
                ROUND(AVG(mixed_layer_depth)::numeric, 2)       as avg_mld_m,
                ROUND(AVG(thermocline_depth)::numeric, 2)       as avg_thermocline_m,
                ROUND(AVG(barrier_layer_thickness)::numeric, 2) as avg_blt_m,
                ROUND(AVG(d20_depth)::numeric, 2)               as avg_d20_m,
                ROUND(AVG(tchp_kj_cm2)::numeric, 2)             as avg_tchp,
                ROUND(MAX(tchp_kj_cm2)::numeric, 2)             as max_tchp,
                ROUND(AVG(conservative_temp)::numeric, 2)       as avg_temp_c,
                ROUND(AVG(absolute_salinity)::numeric, 3)       as avg_salinity
            FROM computed_profiles
            WHERE latitude  BETWEEN %s AND %s
            AND   longitude BETWEEN %s AND %s
        """, (r['lat1'], r['lat2'], r['lon1'], r['lon2']))

        summary    = cur.fetchone()

        cur.execute("""
            SELECT stratification, COUNT(*) as count
            FROM computed_profiles
            WHERE latitude  BETWEEN %s AND %s
            AND   longitude BETWEEN %s AND %s
            GROUP BY stratification
            ORDER BY count DESC
        """, (r['lat1'], r['lat2'], r['lon1'], r['lon2']))

        strat_rows = cur.fetchall()

        return {
            "region":                   region,
            "summary":                  dict(summary) if summary else {},
            "stratification_breakdown": [dict(s) for s in strat_rows]
        }

    finally:
        cur.close()
        conn.close()


@app.get("/ocean/search", tags=["Search"])
def search_floats(
    lat: float,
    lon: float,
    radius_deg: float = 3.0,
    limit: int = 10,
    api_key: str = "test-key-samudra-v1"
):
    """Find all computed Argo profiles near a coordinate."""
    verify_key(api_key)

    conn = get_conn()
    cur  = conn.cursor()

    try:
        cur.execute("""
            SELECT float_id, latitude, longitude,
                   measurement_date, mixed_layer_depth,
                   thermocline_depth, tchp_kj_cm2,
                   stratification, conservative_temp,
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
            ORDER BY distance_km
            LIMIT %s
        """, (lat, lon, lat,
              lat - radius_deg, lat + radius_deg,
              lon - radius_deg, lon + radius_deg,
              limit))

        rows = cur.fetchall()
        return {
            "query":  {"lat": lat, "lon": lon, "radius_deg": radius_deg},
            "count":  len(rows),
            "floats": [dict(r) for r in rows]
        }

    finally:
        cur.close()
        conn.close()


@app.get("/health", tags=["Info"])
def health():
    """Check API health and data counts."""
    conn = get_conn()
    cur  = conn.cursor()
    try:
        cur.execute("SELECT COUNT(*) as c FROM computed_profiles")
        computed = cur.fetchone()['c']
        cur.execute("SELECT COUNT(*) as c FROM profiles")
        profiles = cur.fetchone()['c']
        cur.execute("SELECT COUNT(*) as c FROM measurements")
        measurements = cur.fetchone()['c']
        return {
            "status":             "ok",
            "computed_profiles":  computed,
            "total_profiles":     profiles,
            "total_measurements": measurements,
            "coverage":           "Indian Ocean 2002-2025"
        }
    finally:
        cur.close()
        conn.close()
