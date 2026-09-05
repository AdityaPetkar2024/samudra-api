"""
Argo real-time QC tests, implemented per the Argo Quality Control Manual for
CTD and Trajectory Data v3.9 (ADMT, February 2025).

Every test takes a Profile and mutates its QC flag arrays in place. Flags are
only ever raised, never lowered, per section 2.1 of the manual.

Because these operate on the common Profile object, they run identically on
Argo floats and on CTD casts.

Implemented here (the four cheapest, highest-value tests):
    Test 2  - Impossible date
    Test 3  - Impossible location
    Test 6  - Global range
    Test 13 - Stuck value
"""

from datetime import datetime, timezone

import numpy as np

from profile import (
    Profile,
    QC_BAD,
    QC_GOOD,
    QC_PROBABLY_BAD,
)

# Argo begins in 1997; nothing earlier can be a valid Argo observation.
ARGO_EPOCH = datetime(1997, 1, 1)

# Test 6 thresholds, ADMT v3.9 section 2.6
TEMP_MIN, TEMP_MAX = -2.5, 40.0        # degrees C
PSAL_MIN, PSAL_MAX = 2.0, 41.0         # PSU
PRES_BAD = -5.0                        # < -5 dbar is bad
PRES_SUSPECT = -2.4                    # -5 to -2.4 dbar is probably bad


def _as_naive(dt):
    """Strip timezone so comparisons against naive datetimes work."""
    if dt is None:
        return None
    if isinstance(dt, datetime) and dt.tzinfo is not None:
        return dt.replace(tzinfo=None)
    return dt


# Argo begins in 1997. CTD casts in WOD go back to the early 1900s,
# so the lower bound depends on the instrument type.
ARGO_EPOCH = datetime(1997, 1, 1)
CTD_EPOCH = datetime(1900, 1, 1)


def test2_impossible_date(profile: Profile) -> bool:
    """
    Test 2 - Impossible date.

    The observation date must not be in the future, and must be later than
    the earliest plausible date for the instrument: 1997 for Argo floats,
    1900 for ship-based CTD casts.
    """
    juld = _as_naive(profile.juld)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    epoch = ARGO_EPOCH if profile.source == "argo" else CTD_EPOCH

    ok = juld is not None and epoch <= juld <= now

    profile.profile_qc["test2_date"] = QC_GOOD if ok else QC_BAD
    if not ok:
        for param in ("pres", "temp", "psal"):
            profile.raise_flag(param, np.ones(profile.n_levels, bool), QC_BAD)
    return ok


def test3_impossible_location(profile: Profile) -> bool:
    """
    Test 3 - Impossible location.

    Latitude must lie in [-90, 90] and longitude in [-180, 180].
    Failure flags the whole profile as bad.
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
            profile.raise_flag(param, np.ones(profile.n_levels, bool), QC_BAD)
    return ok


def test6_global_range(profile: Profile) -> dict:
    """
    Test 6 - Global range.

    Pressure below -5 dbar is bad; between -5 and -2.4 dbar is probably bad.
    Temperature outside -2.5 to 40 C and salinity outside 2 to 41 PSU are bad.
    Flags apply per level, not to the whole profile.
    """
    pres_bad = profile.pres < PRES_BAD
    pres_suspect = (profile.pres >= PRES_BAD) & (profile.pres < PRES_SUSPECT)
    profile.raise_flag("pres", pres_bad, QC_BAD)
    profile.raise_flag("pres", pres_suspect, QC_PROBABLY_BAD)

    temp_bad = (profile.temp < TEMP_MIN) | (profile.temp > TEMP_MAX)
    profile.raise_flag("temp", temp_bad, QC_BAD)

    psal_bad = (profile.psal < PSAL_MIN) | (profile.psal > PSAL_MAX)
    profile.raise_flag("psal", psal_bad, QC_BAD)

    return {
        "pres_bad": int(np.nansum(pres_bad)),
        "pres_suspect": int(np.nansum(pres_suspect)),
        "temp_bad": int(np.nansum(temp_bad)),
        "psal_bad": int(np.nansum(psal_bad)),
    }


# Test 13 needs enough levels for "all identical" to mean anything.
# Two identical values in a 2-level profile is not evidence of a stuck
# sensor, so require a minimum before the test can fire.
STUCK_MIN_LEVELS = 5


def test13_stuck_value(profile: Profile) -> dict:
    """
    Test 13 - Stuck value.

    If every temperature (or every salinity) value in a profile is identical,
    the sensor is stuck and the whole parameter is flagged bad. Profiles with
    fewer than STUCK_MIN_LEVELS valid values are skipped, since a handful of
    equal readings is not evidence of a fault.
    """
    result = {}
    for param in ("temp", "psal"):
        values = getattr(profile, param)
        valid = values[~np.isnan(values)]

        stuck = len(valid) >= STUCK_MIN_LEVELS and np.all(valid == valid[0])
        result[f"{param}_stuck"] = bool(stuck)

        if stuck:
            profile.raise_flag(param, ~np.isnan(values), QC_BAD)

    return result

# --------------------------------------------------------------------------

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
        summary["test6_global_range"] = test6_global_range(profile)
        summary["test13_stuck"] = test13_stuck_value(profile)

        # Anything not flagged by any test so far is good data.
        for param in ("pres", "temp", "psal"):
            arr = getattr(profile, f"{param}_qc")
            arr[arr == 0] = QC_GOOD

    summary["flags"] = {
        param: profile.flag_counts(param) for param in ("pres", "temp", "psal")
    }
    return summary
