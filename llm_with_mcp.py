"""
Samudra LLM Chat — Dynamic SQL approach.
Uses OpenAI GPT-4o-mini + auto SQL fixer.
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

# ── DB config ─────────────────────────────────────────────────────────────────
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

client     = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
geolocator = Nominatim(user_agent="samudra_v1")

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
  mixed_layer_depth FLOAT,
  isothermal_layer_depth FLOAT,
  barrier_layer_thickness FLOAT,
  thermocline_depth FLOAT,
  d20_depth FLOAT,
  tchp_kj_cm2 FLOAT,
  conservative_temp FLOAT,
  absolute_salinity FLOAT,
  potential_density_surface FLOAT

TABLE copernicus_monthly
  month INT (1-12),
  latitude FLOAT, longitude FLOAT,
  avg_sst FLOAT, avg_ssh FLOAT, avg_chl FLOAT

Region bounding boxes:
  Arabian Sea:    lat 5-25,  lon 50-78
  Bay of Bengal:  lat 5-22,  lon 78-100
  Equatorial IO:  lat -10-10, lon 40-110
  Southern Ocean: lat -70--30, lon 0-150
  Indian Ocean:   lat -70-30, lon 20-120

CRITICAL SQL RULES:
- Cast AFTER aggregation: ROUND(AVG(col)::numeric, 2) NOT ROUND(AVG(col::numeric, 2))
- Cast bare columns:      ROUND(col::numeric, 2)
- Always LIMIT 20 rows maximum
- For multi-region comparisons use CASE WHEN
- Always apply valid range filters in WHERE:
    surface_temp BETWEEN -2 AND 35
    surface_salinity BETWEEN 20 AND 45
    mixed_layer_depth BETWEEN 1 AND 450
    isothermal_layer_depth BETWEEN 1 AND 450
    barrier_layer_thickness BETWEEN 0 AND 200
    thermocline_depth BETWEEN 1 AND 900
    d20_depth BETWEEN 1 AND 800
    tchp_kj_cm2 BETWEEN 0 AND 250
    conservative_temp BETWEEN -2 AND 35
    absolute_salinity BETWEEN 20 AND 45
    max_depth BETWEEN 1 AND 6000

Example queries:
Q: Compare Arabian Sea vs Bay of Bengal salinity
SQL: SELECT CASE WHEN latitude BETWEEN 5 AND 25 AND longitude BETWEEN 50 AND 78 THEN 'Arabian Sea' ELSE 'Bay of Bengal' END as region, ROUND(AVG(absolute_salinity)::numeric, 3) as avg_salinity, COUNT(*) as profiles FROM computed_profiles WHERE ((latitude BETWEEN 5 AND 25 AND longitude BETWEEN 50 AND 78) OR (latitude BETWEEN 5 AND 22 AND longitude BETWEEN 78 AND 100)) AND absolute_salinity BETWEEN 20 AND 45 GROUP BY region;

Q: Warmest surface temp recorded
SQL: SELECT float_id, ROUND(surface_temp::numeric, 2) as surface_temp, measurement_date FROM profiles WHERE surface_temp BETWEEN -2 AND 35 ORDER BY surface_temp DESC LIMIT 1;

Q: Saltiest water recorded
SQL: SELECT float_id, ROUND(surface_salinity::numeric, 3) as salinity, measurement_date FROM profiles WHERE surface_salinity BETWEEN 20 AND 45 ORDER BY surface_salinity DESC LIMIT 1;

Q: Floats near Chennai
SQL: SELECT float_id, ROUND(latitude::numeric, 3) as lat, ROUND(longitude::numeric, 3) as lon, ROUND((6371 * acos(LEAST(1.0, cos(radians(13.08)) * cos(radians(latitude)) * cos(radians(longitude) - radians(80.27)) + sin(radians(13.08)) * sin(radians(latitude)))))::numeric, 1) as distance_km FROM computed_profiles WHERE latitude BETWEEN 8 AND 18 AND longitude BETWEEN 75 AND 90 ORDER BY distance_km LIMIT 10;

Q: Average MLD in Arabian Sea
SQL: SELECT ROUND(AVG(mixed_layer_depth)::numeric, 1) as avg_mld_m FROM computed_profiles WHERE latitude BETWEEN 5 AND 25 AND longitude BETWEEN 50 AND 78 AND mixed_layer_depth BETWEEN 1 AND 450;

Q: MLD trend in Arabian Sea from 2010 to 2020
SQL: SELECT EXTRACT(YEAR FROM measurement_date) as year, ROUND(AVG(mixed_layer_depth)::numeric, 1) as avg_mld FROM computed_profiles WHERE latitude BETWEEN 5 AND 25 AND longitude BETWEEN 50 AND 78 AND mixed_layer_depth BETWEEN 1 AND 450 AND measurement_date BETWEEN '2010-01-01' AND '2020-12-31' GROUP BY year ORDER BY year;
"""

SYSTEM_PROMPT = f"""You are an expert oceanographic data assistant for the Samudra Indian Ocean API.

You have access to a PostgreSQL database. When the user asks a question, generate a SQL SELECT query to answer it.

{SCHEMA}

Respond in JSON format:
{{"sql": "SELECT ...", "explanation": "one line explaining what this query does"}}

If the question cannot be answered with SQL, respond:
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


def fix_sql(query: str) -> str:
    """Auto-fix common LLM SQL mistakes."""

    # Fix: ROUND(AVG(col::numeric, N)) → ROUND(AVG(col)::numeric, N)
    query = re.sub(
        r'ROUND\((AVG|SUM|MIN|MAX|COUNT)\((\w+)::numeric,\s*(\d+)\)\)',
        r'ROUND(\1(\2)::numeric, \3)',
        query
    )

    # Fix: ROUND(col, N) → ROUND(col::numeric, N) for bare column names
    query = re.sub(
        r'ROUND\(([a-zA-Z_][a-zA-Z0-9_]*),\s*(\d+)\)',
        r'ROUND(\1::numeric, \2)',
        query
    )

    return query


def execute_sql(query: str) -> list:
    q = query.strip().upper()
    for banned in ["DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "CREATE", "TRUNCATE"]:
        if banned in q:
            return [{"error": f"Forbidden keyword: {banned}"}]

    query = fix_sql(query)

    conn = get_conn()
    cur  = conn.cursor()
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
    # Step 1 — geocode place names
    geo_context   = ""
    place_extract = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content":
            f"Extract any place name from this text. Reply ONLY 'PLACE: <name>' or 'NO_PLACE'.\nText: {user_message}"}],
        max_tokens=30, temperature=0,
    ).choices[0].message.content.strip()

    if place_extract.startswith("PLACE:"):
        place = place_extract.replace("PLACE:", "").strip()
        lat, lon, _ = geocode_place(place)
        if lat:
            geo_context = f"\n[GEOCODED: '{place}' -> lat={lat:.4f}, lon={lon:.4f}]"
        else:
            geo_context = f"\n[GEOCODE FAILED for '{place}']"

    # Step 2 — generate SQL
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for msg in history[-6:]:
        messages.append(msg)
    messages.append({"role": "user", "content": f"{user_message}{geo_context}"})

    plan_raw = llm_call(messages)

    # Step 3 — parse
    try:
        plan = json.loads(plan_raw)
    except Exception:
        match = re.search(r'\{.*\}', plan_raw, re.DOTALL)
        plan  = json.loads(match.group()) if match else {}

    sql           = plan.get("sql")
    explanation   = plan.get("explanation", "")
    direct_answer = plan.get("answer")

    if direct_answer:
        return direct_answer
    if not sql:
        return f"I couldn't generate a query for that. {explanation}"

    # Step 4 — execute (with auto-fix)
    results = execute_sql(sql)

    if results and "error" in results[0]:
        return f"Database error: {results[0]['error']}\n\nQuery attempted:\n```sql\n{sql}\n```"
    if not results:
        return f"No data found. {explanation}"

    # Step 5 — synthesise
    synthesis = [
        {"role": "system", "content":
            "You are an expert oceanographic assistant. Answer clearly using only the data provided. "
            "Include specific numbers. Never invent values. Be concise."},
        {"role": "user", "content":
            f"Question: {user_message}{geo_context}\n\n"
            f"Query: {explanation}\n\n"
            f"Results ({len(results)} rows):\n{json.dumps(results[:20], indent=2, default=str)}\n\n"
            f"Give a clear, concise answer."}
    ]

    return client.chat.completions.create(
        model="gpt-4o-mini",
        messages=synthesis,
        temperature=0.2,
        max_tokens=600,
    ).choices[0].message.content
