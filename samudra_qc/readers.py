"""
Readers: Argo (PostgreSQL) and CTD (World Ocean Database) -> Profile.

Both produce the same Profile object, which is the whole point: QC is written
once and runs on either source.
"""

from datetime import datetime

import numpy as np
import psycopg2
from psycopg2.extras import RealDictCursor

from profile import Profile


# --------------------------------------------------------------------------
# Argo, from the Samudra PostgreSQL database
# --------------------------------------------------------------------------

def _connect(db_config):
    return psycopg2.connect(**db_config, cursor_factory=RealDictCursor)


def read_argo_profile(db_config, float_id, profile_idx):
    """Read one Argo profile (levels + position/date) into a Profile."""
    conn = _connect(db_config)
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT latitude, longitude, measurement_date
            FROM profiles
            WHERE float_id = %s AND profile_idx = %s
            """,
            (float_id, profile_idx),
        )
        head = cur.fetchone()
        if head is None:
            return None

        cur.execute(
            """
            SELECT pressure, temperature, salinity
            FROM measurements
            WHERE float_id = %s AND profile_idx = %s
            ORDER BY pressure ASC
            """,
            (float_id, profile_idx),
        )
        rows = cur.fetchall()
        if not rows:
            return None

        return Profile(
            pres=[r["pressure"] if r["pressure"] is not None else np.nan for r in rows],
            temp=[r["temperature"] if r["temperature"] is not None else np.nan for r in rows],
            # Argo NetCDF ingestion wrote 0.0 where salinity was absent. Ocean
            # salinity is never 0 PSU, so exact zeros are missing, not measured.
            psal=[np.nan if r["salinity"] is None or r["salinity"] == 0 else r["salinity"]for r in rows],
            lat=float(head["latitude"]),
            lon=float(head["longitude"]),
            juld=head["measurement_date"],
            source="argo",
            profile_id=f"{float_id}_{profile_idx}",
        )
    finally:
        cur.close()
        conn.close()


def iter_argo_profiles(db_config, limit=None, region=None):
    """
    Yield Argo profiles one at a time.

    region: optional (lat_min, lat_max, lon_min, lon_max) to restrict the set.
    """
    conn = _connect(db_config)
    cur = conn.cursor()
    try:
        sql = """
            SELECT float_id, profile_idx, latitude, longitude, measurement_date
            FROM profiles
            WHERE latitude IS NOT NULL
              AND longitude IS NOT NULL
              AND measurement_date IS NOT NULL
        """
        params = []
        if region:
            sql += """
              AND latitude BETWEEN %s AND %s
              AND longitude BETWEEN %s AND %s
            """
            params += list(region)
        sql += " ORDER BY float_id, profile_idx"
        if limit:
            sql += " LIMIT %s"
            params.append(limit)

        cur.execute(sql, params)
        heads = cur.fetchall()

        lev = conn.cursor()
        try:
            for head in heads:
                lev.execute(
                    """
                    SELECT pressure, temperature, salinity
                    FROM measurements
                    WHERE float_id = %s AND profile_idx = %s
                    ORDER BY pressure ASC
                    """,
                    (head["float_id"], head["profile_idx"]),
                )
                rows = lev.fetchall()
                if not rows:
                    continue
                yield Profile(
                    pres=[r["pressure"] if r["pressure"] is not None else np.nan for r in rows],
                    temp=[r["temperature"] if r["temperature"] is not None else np.nan for r in rows],
                    # Argo NetCDF ingestion wrote 0.0 where salinity was absent. Ocean
                    # salinity is never 0 PSU, so exact zeros are missing, not measured.
                    psal=[np.nan if r["salinity"] is None or r["salinity"] == 0 else r["salinity"]for r in rows],
                    lat=float(head["latitude"]),
                    lon=float(head["longitude"]),
                    juld=head["measurement_date"],
                    source="argo",
                    profile_id=f"{head['float_id']}_{head['profile_idx']}",
                )
        finally:
            lev.close()
    finally:
        cur.close()
        conn.close()


# --------------------------------------------------------------------------
# CTD, from World Ocean Database ASCII files (read via wodpy)
# --------------------------------------------------------------------------

def iter_wod_ctd_profiles(filepath, limit=None):
    """
    Yield CTD profiles from a decompressed WOD file (e.g. CTDO1007).

    WOD stores depth in metres, not pressure in dbar. They are close enough
    numerically in the upper ocean (~1% apart) that the range and spike tests
    behave sensibly, but this is converted properly below using the standard
    depth-to-pressure relation so downstream tests get real dbar.
    """
    from wodpy import wod

    n = 0
    with open(filepath, "r") as fid:
        while True:
            try:
                p = wod.WodProfile(fid)
            except Exception:
                break

            z = np.asarray(p.z(), dtype=float)
            t = np.asarray(p.t(), dtype=float)
            s = np.asarray(p.s(), dtype=float)
            # WOD returns 0.0 rather than NaN for channels that were not
            # measured. Ocean salinity is never 0 PSU, so exact zeros mean
            # "not measured" and must be treated as missing, not as bad data.
            s[s == 0.0] = np.nan

            if len(z) == 0:
                if _wod_at_end(p, fid):
                    break
                continue

            lat = float(p.latitude())
            lon = float(p.longitude())

            try:
                juld = datetime(int(p.year()), int(p.month()), int(p.day()))
            except (ValueError, TypeError):
                juld = None

            if juld is not None:
                yield Profile(
                    pres=depth_to_pressure(z, lat),
                    temp=t,
                    psal=s,
                    lat=lat,
                    lon=lon,
                    juld=juld,
                    source="ctd",
                    profile_id=str(p.uid()),
                )
                n += 1
                if limit and n >= limit:
                    break

            if _wod_at_end(p, fid):
                break


def _wod_at_end(profile, fid):
    """wodpy changed this signature between versions; handle both."""
    try:
        return profile.is_last_profile_in_file(fid)
    except TypeError:
        return profile.is_last_profile_in_file()


def depth_to_pressure(depth_m, lat):
    """
    Convert depth (m) to pressure (dbar) using the Saunders (1981) formula,
    which is what UNESCO recommends and what gsw.p_from_z implements.

    Falls back to gsw if available, since that is already a Samudra dependency.
    """
    try:
        import gsw

        return gsw.p_from_z(-np.abs(np.asarray(depth_m, dtype=float)), lat)
    except Exception:
        # Saunders (1981) approximation
        d = np.asarray(depth_m, dtype=float)
        x = np.sin(np.radians(lat)) ** 2
        g = 9.780318 * (1.0 + (5.2788e-3 + 2.36e-5 * x) * x) + 1.092e-6 * d
        return ((1.0 - 5.92e-3 - 5.25e-3 * x) * d + 2.21e-6 * d ** 2) * 9.80665 / g
