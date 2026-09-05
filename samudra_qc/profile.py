"""
Common profile representation for Samudra QC.

Both Argo (INCOIS GDAC, via PostgreSQL) and CTD (World Ocean Database, via
wodpy) parse into this single object, so every QC test is written once and
runs identically on both sources.

QC flags follow the Argo convention (Argo QC Manual v3.9, Reference Table 2):
    0 = no QC performed
    1 = good data
    2 = probably good data
    3 = probably bad data (potentially correctable)
    4 = bad data
    9 = missing value
"""

from dataclasses import dataclass, field
from datetime import datetime

import numpy as np

# Argo QC flag values
QC_NO_QC = 0
QC_GOOD = 1
QC_PROBABLY_GOOD = 2
QC_PROBABLY_BAD = 3
QC_BAD = 4
QC_MISSING = 9

QC_MEANINGS = {
    0: "no QC performed",
    1: "good data",
    2: "probably good data",
    3: "probably bad data",
    4: "bad data",
    9: "missing value",
}


@dataclass
class Profile:
    """A single vertical profile of pressure, temperature and salinity."""

    pres: np.ndarray            # dbar
    temp: np.ndarray            # degrees Celsius (ITS-90)
    psal: np.ndarray            # PSU (PSS-78)
    lat: float                  # decimal degrees, -90 to 90
    lon: float                  # decimal degrees, -180 to 180
    juld: datetime              # observation date/time
    source: str                 # 'argo' or 'ctd'
    profile_id: str             # e.g. '2902086_14' (argo) or WOD uid (ctd)

    pres_qc: np.ndarray = None
    temp_qc: np.ndarray = None
    psal_qc: np.ndarray = None

    # Flags that apply to the whole profile rather than a single level
    # (Tests 2 and 3 set these). Kept separate so level flags stay level flags.
    profile_qc: dict = field(default_factory=dict)

    def __post_init__(self):
        self.pres = np.asarray(self.pres, dtype=float)
        self.temp = np.asarray(self.temp, dtype=float)
        self.psal = np.asarray(self.psal, dtype=float)

        n = len(self.pres)
        if len(self.temp) != n or len(self.psal) != n:
            raise ValueError(
                f"{self.profile_id}: pres/temp/psal length mismatch "
                f"({n}/{len(self.temp)}/{len(self.psal)})"
            )

        # Start every level at "no QC performed", then mark NaNs as missing.
        for name in ("pres_qc", "temp_qc", "psal_qc"):
            if getattr(self, name) is None:
                setattr(self, name, np.full(n, QC_NO_QC, dtype=int))
            else:
                setattr(self, name, np.asarray(getattr(self, name), dtype=int))

        self.pres_qc[np.isnan(self.pres)] = QC_MISSING
        self.temp_qc[np.isnan(self.temp)] = QC_MISSING
        self.psal_qc[np.isnan(self.psal)] = QC_MISSING

    @property
    def n_levels(self) -> int:
        return len(self.pres)

    def raise_flag(self, param: str, mask, flag: int):
        """
        Raise the QC flag for the given parameter where `mask` is True.

        Per the Argo QC manual, a flag set by one test must not be lowered by
        a later test, so this only ever increases a flag value. Missing values
        (flag 9) are left alone.
        """
        arr = getattr(self, f"{param}_qc")
        mask = np.asarray(mask, dtype=bool)
        target = mask & (arr != QC_MISSING) & (arr < flag)
        arr[target] = flag

    def flag_counts(self, param: str) -> dict:
        """Count of levels at each flag value for one parameter."""
        arr = getattr(self, f"{param}_qc")
        return {int(f): int((arr == f).sum()) for f in np.unique(arr)}

    def __repr__(self):
        return (
            f"Profile({self.source}:{self.profile_id}, {self.n_levels} levels, "
            f"lat={self.lat:.3f}, lon={self.lon:.3f}, "
            f"{self.juld:%Y-%m-%d})"
        )
