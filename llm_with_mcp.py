"""
Samudra LLM Chat — Dynamic SQL approach.
Instead of 21 hardcoded tools, the LLM writes SQL directly.
Uses OpenAI GPT-4o-mini. Falls back gracefully on errors.
"""

import json
import os
import re
import psycopg2
from psycopg2.extras import RealDictCursor
from urllib.parse import urlparse
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut
from openai import OpenAI

# ── DB config ────────────────────────────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL:
    r = urlparse(DATABASE_URL)
    DB_CONFIG = {
        "host": r.hostname, "database": r.path[1:],
        "user": r.username, "password": r.password, "port": r.port
    }
else:
    DB_CONFIG = {
        "host": "localhost", "database": "argo_db12",
        "user": "argo_user1", "password": "argo123"
    }

# ── OpenAI client ─────────────────────────────────────────────────────────────
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

geolocator = Nominatim(user_agent="samudra_v1")

# ── Schema context for the LLM ───────────────────────────────────────────────
SCHEMA = """
PostgreSQL database schema:

TABLE floats
  float_id VARCHAR PRIMARY KEY

TABLE profiles
  float_id VARCHAR, profile_idx INT,
  latitude FLOAT, longitude FLOAT,
  surface_temp FLOAT,        -- degrees C
  surface_salinity FLOAT,    -- PSU
  max_depth FLOAT,           -- metres
  measurement_date TIMESTAMP

TABLE computed_profiles
  float_id VARCHAR, profile_idx INT,
  latitude FLOAT, longitude FLOAT,
  measurement_date TIMESTAMP,
  mixed_layer_depth FLOAT,          -- metres
  isothermal_layer_depth FLOAT,     -- metres
  barrier_layer_thickness FLOAT,    -- metres
  thermocline_depth FLOAT,          -- metres
  d20_depth FLOAT,                  -- depth of 20°C isotherm, metres
  tchp_kj_cm2 FLOAT,                -- tropical cyclone heat potential
  conservative_temp FLOAT,          -- degrees C (GSW TEOS-10)
  absolute_salinity FLOAT,          -- g/kg (GSW TEOS-10)
  potential_density_surface FLOAT,  -- kg/m³

TABLE copernicus_monthly
  month INT (1-12),
  latitude FLOAT, longitude FLOAT,
  avg_sst FLOAT,   -- sea surface temperature °C
  avg_ssh FLOAT,   -- sea surface height metres
  avg_chl FLOAT    -- chlorophyll mg/m³

Region bounding boxes:
  Arabian Sea:    lat 5-25,  lon 50-78
  Bay of Bengal:  lat 5-22,  lon 78-100
  Equatorial IO:  lat -10-10, lon 40-110
  Southern Ocean: lat -70--30, lon 0-150
  Indian Ocean:   lat -70-30, lon 20-120
"""

SYSTEM_PROMPT = f"""You are an expert oceanographic data assistant for the Samudra Indian Ocean API.

You have access to a PostgreSQL database. When the user asks a question, generate a SQL SELECT query to answer it.

{SCHEMA}

Rules:
- Only generate SELECT queries. Never UPDATE, DELETE, DROP, INSERT.
- Always LIMIT results to 20 rows maximum.
- Round floats to 2-3 decimal places using ROUND().
- For distance queries use: 6371 * acos(LEAST(1.0, cos(radians(lat1)) * cos(radians(lat2)) * cos(radians(lon2) - radians(lon1)) + sin(radians(lat1)) * sin(radians(lat2)))) AS distance_km
- Use computed_profiles for oceanographic parameters (MLD, thermocline, TCHP etc.)
- Use profiles for surface temp, salinity, basic float info
- Use copernicus_monthly for satellite SST/SSH/CHL data

Respond in JSON format:
{{"sql": "SELECT ...", "explanation": "one line explaining what this query does"}}

If the question cannot be answered with SQL (e.g. general knowledge), respond:
{{"sql": null, "explanation": "reason why", "answer": "direct answer here"}}
"""


def get_conn():
    return psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)


def geocode_place(place_name: str):
    try:
        loc = geolocator.geocode(place_name, timeout=10)
        if loc:
            return loc.latitude, loc.longitude, loc.address
    except (GeocoderTimedOut, Exception):
        pass
    return None, None, None


def execute_sql(query: str) -> list:
    """Execute a SELECT query safely, return list of dicts."""
    q = query.strip().upper()
    for banned in ["DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "CREATE", "TRUNCATE"]:
        if banned in q:
            return [{"error": f"Query contains forbidden keyword: {banned}"}]
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(query)
        return [dict(r) for r in cur.fetchall()]
    except Exception as e:
        return [{"error": str(e)}]
    finally:
        cur.close()
        conn.close()


def llm_call(messages: list) -> str:
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        temperature=0.1,
        max_tokens=1000,
        response_format={"type": "json_object"},
    )
    return response.choices[0].message.content


def chat_with_tools(user_message: str, history: list = []) -> str:
    # Step 1 — extract and geocode any place name
    geo_context = ""
    place_extract = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content":
            f"Extract any place name from this text. Reply ONLY 'PLACE: <name>' or 'NO_PLACE'.\nText: {user_message}"}],
        max_tokens=30,
        temperature=0,
    ).choices[0].message.content.strip()

    if place_extract.startswith("PLACE:"):
        place = place_extract.replace("PLACE:", "").strip()
        lat, lon, addr = geocode_place(place)
        if lat:
            geo_context = f"\n[GEOCODED: '{place}' → lat={lat:.4f}, lon={lon:.4f}]"
        else:
            geo_context = f"\n[GEOCODE FAILED for '{place}']"

    # Step 2 — ask LLM to generate SQL
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    
    # Include last 3 exchanges for context
    for msg in history[-6:]:
        messages.append(msg)
    
    messages.append({"role": "user", "content": f"{user_message}{geo_context}"})

    plan_raw = llm_call(messages)

    # Step 3 — parse and execute
    try:
        plan = json.loads(plan_raw)
    except Exception:
        match = re.search(r'\{.*\}', plan_raw, re.DOTALL)
        plan = json.loads(match.group()) if match else {}

    sql = plan.get("sql")
    explanation = plan.get("explanation", "")
    direct_answer = plan.get("answer")

    if direct_answer:
        return direct_answer

    if not sql:
        return f"I couldn't generate a query for that. {explanation}"

    # Step 4 — execute SQL
    results = execute_sql(sql)

    if results and "error" in results[0]:
        return f"Database error: {results[0]['error']}\n\nQuery attempted:\n```sql\n{sql}\n```"

    if not results:
        return f"No data found. {explanation}"

    # Step 5 — synthesise natural language answer
    synthesis_messages = [
        {"role": "system", "content":
            "You are an expert oceanographic assistant. Answer clearly using only the data provided. "
            "Include specific numbers. Never invent values. Be concise."},
        {"role": "user", "content":
            f"Question: {user_message}{geo_context}\n\n"
            f"Query explanation: {explanation}\n\n"
            f"Results ({len(results)} rows):\n{json.dumps(results[:20], indent=2, default=str)}\n\n"
            f"Give a clear, concise answer using these results."}
    ]

    return client.chat.completions.create(
        model="gpt-4o-mini",
        messages=synthesis_messages,
        temperature=0.2,
        max_tokens=600,
    ).choices[0].message.content
