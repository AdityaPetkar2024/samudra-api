"""
Argo real-time QC tests, implemented per the Argo Quality Control Manual for
CTD and Trajectory Data v3.9 (ADMT, February 2025).

Every test takes a Profile and mutates its QC flag arrays in place. Flags are
only ever raised, never lowered, per section 2.1 of the manual.

Because these operate on the common Profile object, they run identically on
Argo floats and on CTD casts.

Implemented:
    Test 2  - Impossible date
    Test 3  - Impossible location
    Test 6  - Global range
    Test 7  - Regional range (Red Sea and Mediterranean only)
    Test 8  - Pressure increasing
    Test 9  - Spike
    Test 12 - Digit rollover
    Test 13 - Stuck value
    Test 14 - Density inversion

Computed but not applied:
    Test 11 - Gradient, declared obsolete at ADMT20 in October 2019
"""

from datetime import datetime, timezone

import numpy as np

from profile import (
    Profile,
    QC_BAD,
    QC_GOOD,
    QC_MISSING,
    QC_PROBABLY_BAD,
)

# Argo begins in 1997. CTD casts in WOD go back to the early 1900s, so the
# lower bound depends on the instrument type.
ARGO_EPOCH = datetime(1997, 1, 1)
CTD_EPOCH = datetime(1900, 1, 1)

# Test 6 thresholds, ADMT v3.9 section 2.6
TEMP_MIN, TEMP_MAX = -2.5, 40.0        # degrees C
PSAL_MIN, PSAL_MAX = 2.0, 41.0         # PSU
PRES_BAD = -5.0                        # < -5 dbar is bad
PRES_SUSPECT = -2.4                    # -5 to -2.4 dbar is probably bad

# Test 7 regions and limits, ADMT v3.9 section 2.1.2. The manual defines
# regional ranges only for the Red Sea and the Mediterranean.
RED_SEA = [(10.0, 40.0), (20.0, 50.0), (30.0, 30.0)]
MEDITERRANEAN = [(30.0, -6.0), (30.0, 40.0), (40.0, 35.0),
                 (42.0, 20.0), (50.0, 15.0), (40.0, -5.0)]
RED_SEA_TEMP, RED_SEA_PSAL = (21.0, 40.0), (2.0, 41.0)
MED_TEMP, MED_PSAL = (10.0, 40.0), (2.0, 40.0)

# Test 8, ADMT v3.9 section 2.8
PRES_REVERSAL = 20.0                   # dbar of allowed reversal

# Test 9 thresholds, ADMT v3.9 section 2.9
SPIKE_DEEP_PRES = 500.0                # dbar, boundary between the two regimes
SPIKE_TEMP_SHALLOW, SPIKE_TEMP_DEEP = 6.0, 2.0      # degrees C
SPIKE_PSAL_SHALLOW, SPIKE_PSAL_DEEP = 0.9, 0.3      # PSU

# Test 11 thresholds, ADMT v3.9 section 2.11
GRAD_TEMP_SHALLOW, GRAD_TEMP_DEEP = 9.0, 3.0        # degrees C
GRAD_PSAL_SHALLOW, GRAD_PSAL_DEEP = 1.5, 0.5        # PSU

# Test 12 thresholds, ADMT v3.9 section 2.12
ROLLOVER_TEMP = 10.0                   # degrees C between adjacent levels
ROLLOVER_PSAL = 5.0                    # PSU between adjacent levels

# Test 13
STUCK_MIN_LEVELS = 5

# Test 14, ADMT v3.9 section 2.14
DENSITY_INVERSION = 0.03               # kg/m3


def _as_naive(dt):
    """Strip timezone so comparisons against naive datetimes work."""
    if dt is None:
        return None
    if isinstance(dt, datetime) and dt.tzinfo is not None:
        return dt.replace(tzinfo=None)
    return dt


# --------------------------------------------------------------------------

def test2_impossible_date(profile: Profile) -> bool:
    """
    Test 2 - Impossible date.

    The observation date must not be in the future, and must be later than the
    earliest plausible date for the instrument: 1997 for Argo floats, 1900 for
    ship-based CTD casts.
    """
    juld = _as_naive(profile.juld)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    epoch = ARGO_EPOCH if profile.source == "argo" else CTD_EPOCH

    ok = juld is not None and epoch <= juld <= now

    profile.profile_qc["test2_date"] = QC_GOOD if ok else QC_BAD
    if not ok:
        for param in ("pres", "temp", "psal"):
            profile.raise_flag(param, np.ones(profile.n_levels, bool), QC_BAD,
                               "impossible date")
    return ok


def test3_impossible_location(profile: Profile) -> bool:
    """
    Test 3 - Impossible location.

    Latitude must lie in [-90, 90] and longitude in [-180, 180].
    """
    ok = (
        profile.lat is not None
        and profile.lon is not None
        and not np.isnan(profile.lat)
        and not np.isnan(profile.lon)
        and -90.0 <= profile.lat <= 90.0
        and -180.0 <= profile.lon <= 180.0
    )

    profile.profile_qc["test3_location"] = QC_GOOD if ok else QC_BAD
    if not ok:
        for param in ("pres", "temp", "psal"):
            profile.raise_flag(param, np.ones(profile.n_levels, bool), QC_BAD,
                               "impossible location")
    return ok


def test6_global_range(profile: Profile) -> dict:
    """
    Test 6 - Global range.

    A gross filter on pressure, temperature and salinity.

    The manual is explicit that a pressure failure carries the temperature and
    salinity at that level with it: below -5 dbar all three parameters are
    flagged bad, and between -5 and -2.4 dbar all three are flagged probably
    bad. Temperature and salinity failures flag only their own parameter.
    """
    pres_bad = profile.pres < PRES_BAD
    pres_suspect = (profile.pres >= PRES_BAD) & (profile.pres <= PRES_SUSPECT)

    for param in ("pres", "temp", "psal"):
        profile.raise_flag(param, pres_bad, QC_BAD, "pressure below -5 dbar")
        profile.raise_flag(param, pres_suspect, QC_PROBABLY_BAD,
                           "pressure between -5 and -2.4 dbar")

    temp_bad = (profile.temp < TEMP_MIN) | (profile.temp > TEMP_MAX)
    profile.raise_flag("temp", temp_bad, QC_BAD, "outside global range")

    psal_bad = (profile.psal < PSAL_MIN) | (profile.psal > PSAL_MAX)
    profile.raise_flag("psal", psal_bad, QC_BAD, "outside global range")

    return {
        "pres_bad": int(np.nansum(pres_bad)),
        "pres_suspect": int(np.nansum(pres_suspect)),
        "temp_bad": int(np.nansum(temp_bad)),
        "psal_bad": int(np.nansum(psal_bad)),
    }


def _in_polygon(lat, lon, vertices) -> bool:
    """Ray casting point-in-polygon, used for the Test 7 regions."""
    inside = False
    n = len(vertices)
    for i in range(n):
        y1, x1 = vertices[i]
        y2, x2 = vertices[(i + 1) % n]
        if (y1 > lat) != (y2 > lat):
            x_cross = x1 + (lat - y1) * (x2 - x1) / (y2 - y1)
            if lon < x_cross:
                inside = not inside
    return inside


def test7_regional_range(profile: Profile) -> dict:
    """
    Test 7 - Regional range.

    Tighter limits for two regions where conditions are known to be
    restricted. The manual defines only the Red Sea and the Mediterranean;
    there is no equivalent regional test for the open Indian Ocean, so for
    most Samudra profiles this test does not apply.
    """
    if _in_polygon(profile.lat, profile.lon, RED_SEA):
        region = "Red Sea"
        t_min, t_max = RED_SEA_TEMP
        s_min, s_max = RED_SEA_PSAL
    elif _in_polygon(profile.lat, profile.lon, MEDITERRANEAN):
        region = "Mediterranean Sea"
        t_min, t_max = MED_TEMP
        s_min, s_max = MED_PSAL
    else:
        return {"region": None, "temp_bad": 0, "psal_bad": 0}

    temp_bad = (profile.temp < t_min) | (profile.temp > t_max)
    psal_bad = (profile.psal < s_min) | (profile.psal > s_max)
    profile.raise_flag("temp", temp_bad, QC_BAD, f"outside {region} range")
    profile.raise_flag("psal", psal_bad, QC_BAD, f"outside {region} range")

    return {
        "region": region,
        "temp_bad": int(np.nansum(temp_bad)),
        "psal_bad": int(np.nansum(psal_bad)),
    }


def test8_pressure_increasing(profile: Profile) -> dict:
    """
    Test 8 - Pressure increasing.

    ADMT v3.9 section 2.1.2. The test is run outward from the middle of the
    profile in both directions. Going from the middle to the deepest level, a
    pressure fails if it equals, or falls below, the largest pressure already
    seen minus PRES_reversal. Going from the middle to the shallowest level,
    a pressure fails if it equals, or rises above, the smallest pressure
    already seen plus PRES_reversal.

    The manual flags only PRES_QC for this test, so it deliberately does not
    cascade into the temperature and salinity at that level.
    """
    pres = profile.pres
    n = len(pres)
    bad = np.zeros(n, dtype=bool)
    if n < 2:
        return {"pres_non_monotonic": 0}

    mid = n // 2

    running_max = pres[mid] if not np.isnan(pres[mid]) else -np.inf
    for i in range(mid + 1, n):
        p = pres[i]
        if np.isnan(p):
            continue
        if p == running_max or p <= running_max - PRES_REVERSAL:
            bad[i] = True
        else:
            running_max = max(running_max, p)

    running_min = pres[mid] if not np.isnan(pres[mid]) else np.inf
    for i in range(mid - 1, -1, -1):
        p = pres[i]
        if np.isnan(p):
            continue
        if p == running_min or p >= running_min + PRES_REVERSAL:
            bad[i] = True
        else:
            running_min = min(running_min, p)

    profile.raise_flag("pres", bad, QC_BAD, "pressure not increasing")
    return {"pres_non_monotonic": int(bad.sum())}


def _spike_statistic(values):
    """
    Spike statistic from ADMT v3.9 section 2.9, evaluated at every interior
    level:

        |V2 - (V3 + V1)/2| - |(V3 - V1)/2|

    Returns an array the same length as the input, with NaN at the two ends
    where the statistic is undefined.
    """
    v = np.asarray(values, dtype=float)
    out = np.full(len(v), np.nan)
    if len(v) < 3:
        return out
    v1, v2, v3 = v[:-2], v[1:-1], v[2:]
    out[1:-1] = np.abs(v2 - (v3 + v1) / 2.0) - np.abs((v3 - v1) / 2.0)
    return out


def test9_spike(profile: Profile) -> dict:
    """
    Test 9 - Spike.

    Detects a single level whose value differs sharply from its immediate
    neighbours while those neighbours agree with each other. Thresholds are
    looser in the upper 500 dbar, where real vertical structure is strong,
    and tighter below it.
    """
    result = {}
    deep = profile.pres >= SPIKE_DEEP_PRES

    for param, shallow_thr, deep_thr in (
        ("temp", SPIKE_TEMP_SHALLOW, SPIKE_TEMP_DEEP),
        ("psal", SPIKE_PSAL_SHALLOW, SPIKE_PSAL_DEEP),
    ):
        stat = _spike_statistic(getattr(profile, param))
        threshold = np.where(deep, deep_thr, shallow_thr)

        with np.errstate(invalid="ignore"):
            spike = np.greater(stat, threshold, where=~np.isnan(stat),
                               out=np.zeros(len(stat), dtype=bool))

        profile.raise_flag(param, spike, QC_BAD, "spike")
        result[f"{param}_spikes"] = int(spike.sum())

    return result


def test11_gradient(profile: Profile) -> dict:
    """
    Test 11 - Gradient.

    Declared obsolete at ADMT20 in October 2019. It is computed here for
    reference only and deliberately sets no QC flag, since applying a retired
    test would produce flags no Argo data centre would recognise.

    Test value = |V2 - (V3 + V1)/2|
    """
    result = {}
    deep = profile.pres >= SPIKE_DEEP_PRES

    for param, shallow_thr, deep_thr in (
        ("temp", GRAD_TEMP_SHALLOW, GRAD_TEMP_DEEP),
        ("psal", GRAD_PSAL_SHALLOW, GRAD_PSAL_DEEP),
    ):
        v = getattr(profile, param)
        stat = np.full(len(v), np.nan)
        if len(v) >= 3:
            stat[1:-1] = np.abs(v[1:-1] - (v[2:] + v[:-2]) / 2.0)

        threshold = np.where(deep, deep_thr, shallow_thr)
        with np.errstate(invalid="ignore"):
            steep = np.greater(stat, threshold, where=~np.isnan(stat),
                               out=np.zeros(len(stat), dtype=bool))
        result[f"{param}_gradient"] = int(steep.sum())

    return result


def test12_digit_rollover(profile: Profile) -> dict:
    """
    Test 12 - Digit rollover.

    A float stores temperature and salinity in a fixed number of bits. When
    the range is exceeded the stored value wraps round to the bottom of the
    range, which appears as an implausibly large jump between adjacent
    levels.
    """
    result = {}
    for param, threshold in (("temp", ROLLOVER_TEMP), ("psal", ROLLOVER_PSAL)):
        v = getattr(profile, param)
        bad = np.zeros(len(v), dtype=bool)
        if len(v) >= 2:
            diff = np.abs(np.diff(v))
            with np.errstate(invalid="ignore"):
                jump = np.greater(diff, threshold, where=~np.isnan(diff),
                                  out=np.zeros(len(diff), dtype=bool))
            bad[1:] = jump

        profile.raise_flag(param, bad, QC_BAD, "digit rollover")
        result[f"{param}_rollover"] = int(bad.sum())

    return result


def test13_stuck_value(profile: Profile) -> dict:
    """
    Test 13 - Stuck value.

    If every valid temperature (or salinity) value in a profile is identical,
    that parameter is flagged bad throughout. If both are stuck, the manual
    requires every observed value in the profile to be flagged, pressure
    included.

    Profiles with fewer than STUCK_MIN_LEVELS valid values are skipped, since
    a handful of equal readings is not evidence of a fault.
    """
    result = {}
    stuck_any = {}

    for param in ("temp", "psal"):
        values = getattr(profile, param)
        valid = values[~np.isnan(values)]

        stuck = len(valid) >= STUCK_MIN_LEVELS and np.all(valid == valid[0])
        stuck_any[param] = stuck
        result[f"{param}_stuck"] = bool(stuck)

        if stuck:
            profile.raise_flag(param, ~np.isnan(values), QC_BAD, "stuck value")

    if stuck_any["temp"] and stuck_any["psal"]:
        profile.raise_flag("pres", ~np.isnan(profile.pres), QC_BAD,
                           "stuck value")

    return result


def test14_density_inversion(profile: Profile) -> dict:
    """
    Test 14 - Density inversion.

    ADMT v3.9 section 2.1.2. Potential density is computed for each adjacent
    pair of valid levels, referenced to the mid-point pressure between them as
    the manual specifies, and the profile is checked in both directions: from
    top to bottom the deeper level must not be lighter than the shallower one
    by more than the threshold, and from bottom to top the shallower level
    must not be denser than the deeper one by more than the threshold.

    Both temperature and salinity at an offending level are flagged bad.
    Levels already flagged by an earlier test are excluded, so a single wild
    value does not cascade into spurious inversions.
    """
    try:
        import gsw
    except ImportError:
        return {"density_inversions": 0, "skipped": "gsw not installed"}

    usable = (
        (profile.temp_qc < QC_PROBABLY_BAD)
        & (profile.psal_qc < QC_PROBABLY_BAD)
        & ~np.isnan(profile.pres)
        & ~np.isnan(profile.temp)
        & ~np.isnan(profile.psal)
    )
    idx = np.flatnonzero(usable)
    if len(idx) < 2:
        return {"density_inversions": 0}

    p = profile.pres[idx]
    t = profile.temp[idx]
    s = profile.psal[idx]
    p_ref = (p[:-1] + p[1:]) / 2.0

    try:
        sa = gsw.SA_from_SP(s, p, profile.lon, profile.lat)
        ct = gsw.CT_from_t(sa, t, p)
        rho_upper = gsw.rho(sa[:-1], ct[:-1], p_ref)
        rho_lower = gsw.rho(sa[1:], ct[1:], p_ref)
    except Exception:
        return {"density_inversions": 0, "skipped": "gsw computation failed"}

    finite = np.isfinite(rho_upper) & np.isfinite(rho_lower)
    inversion = np.zeros(len(p) - 1, dtype=bool)
    inversion[finite] = (rho_upper[finite] - rho_lower[finite]) > DENSITY_INVERSION

    bad = np.zeros(profile.n_levels, dtype=bool)
    bad[idx[1:][inversion]] = True
    bad[idx[:-1][inversion]] = True

    for param in ("temp", "psal"):
        profile.raise_flag(param, bad, QC_BAD, "density inversion")

    return {"density_inversions": int(bad.sum())}


# --------------------------------------------------------------------------

def apply_flag_policy(profile: Profile) -> None:
    """
    General QC flag rules from ADMT v3.9 section 2.1.4.

    (b) Salinity is derived from temperature and conductivity, so a
        temperature flagged 3 or 4 forces the salinity at that level to at
        least the same flag.

    (c) Where PRES_QC is 4 or 9, every parameter at that level becomes 4,
        since a measurement at an unknown depth cannot be used.
    """
    temp_suspect = np.isin(profile.temp_qc, [QC_PROBABLY_BAD, QC_BAD])
    for flag in (QC_PROBABLY_BAD, QC_BAD):
        profile.raise_flag("psal", profile.temp_qc == flag, flag,
                           "derived from flagged temperature")

    pres_unusable = np.isin(profile.pres_qc, [QC_BAD, QC_MISSING])
    for param in ("temp", "psal"):
        profile.raise_flag(param, pres_unusable, QC_BAD,
                           "pressure unusable at this level")


def run_basic_qc(profile: Profile) -> dict:
    """
    Run the implemented tests in ADMT application order and return a summary.

    Tests 2 and 3 short-circuit: if the date or position is impossible, the
    profile is already fully flagged and the level tests add nothing.
    """
    summary = {
        "profile_id": profile.profile_id,
        "source": profile.source,
        "n_levels": profile.n_levels,
    }

    summary["test2_date_ok"] = test2_impossible_date(profile)
    summary["test3_location_ok"] = test3_impossible_location(profile)

    if summary["test2_date_ok"] and summary["test3_location_ok"]:
        # Application order follows the table in ADMT v3.9 section 2.1.3.
        summary["test6_global_range"] = test6_global_range(profile)
        summary["test7_regional_range"] = test7_regional_range(profile)
        summary["test8_pressure"] = test8_pressure_increasing(profile)
        summary["test9_spike"] = test9_spike(profile)
        summary["test12_rollover"] = test12_digit_rollover(profile)
        summary["test13_stuck"] = test13_stuck_value(profile)
        summary["test14_density"] = test14_density_inversion(profile)
        # Computed for reference only; sets no flags (obsolete since ADMT20).
        summary["test11_gradient"] = test11_gradient(profile)

        # General flag rules, applied once all tests have run.
        apply_flag_policy(profile)

        # Anything not flagged by any test so far is good data.
        for param in ("pres", "temp", "psal"):
            arr = getattr(profile, f"{param}_qc")
            arr[arr == 0] = QC_GOOD

    summary["flags"] = {
        param: profile.flag_counts(param) for param in ("pres", "temp", "psal")
    }
    return summary
