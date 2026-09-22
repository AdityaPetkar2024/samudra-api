"""
Run Samudra QC across Argo and CTD profiles and report flag statistics.

Usage:
    python3 run_qc.py --argo --limit 500
    python3 run_qc.py --ctd /path/to/CTDO1007
    python3 run_qc.py --argo --ctd /path/to/CTDO1007 --limit 500
"""

import argparse
import os
from collections import Counter
from urllib.parse import urlparse

from qc_tests import run_basic_qc
from readers import iter_argo_profiles, iter_wod_ctd_profiles


def db_config_from_env():
    url = os.getenv("DATABASE_URL")
    if url:
        r = urlparse(url)
        return {
            "host": r.hostname,
            "database": r.path[1:],
            "user": r.username,
            "password": r.password,
            "port": r.port or 5432,
        }
    return {
        "host": os.getenv("DB_HOST", "localhost"),
        "database": os.getenv("DB_NAME", "argo_db12"),
        "user": os.getenv("DB_USER", "argo_user1"),
        "password": os.getenv("DB_PASSWORD", "argo123"),
        "port": int(os.getenv("DB_PORT", 5432)),
    }


class Tally:
    """Accumulate QC outcomes across many profiles."""

    def __init__(self, label):
        self.label = label
        self.n_profiles = 0
        self.n_levels = 0
        self.bad_date = 0
        self.bad_location = 0
        self.stuck_temp = 0
        self.stuck_psal = 0
        self.pres_nonmono = 0
        self.spikes_temp = 0
        self.spikes_psal = 0
        self.grad_temp = 0
        self.grad_psal = 0
        self.density_inv = 0
        self.rollover_temp = 0
        self.rollover_psal = 0
        self.flags = {p: Counter() for p in ("pres", "temp", "psal")}
        self.profiles_with_bad = 0

    def add(self, summary):
        self.n_profiles += 1
        self.n_levels += summary["n_levels"]

        if not summary["test2_date_ok"]:
            self.bad_date += 1
        if not summary["test3_location_ok"]:
            self.bad_location += 1

        stuck = summary.get("test13_stuck", {})
        if stuck.get("temp_stuck"):
            self.stuck_temp += 1
        if stuck.get("psal_stuck"):
            self.stuck_psal += 1

        self.pres_nonmono += summary.get("test8_pressure", {}).get(
            "pres_non_monotonic", 0)
        spike = summary.get("test9_spike", {})
        self.spikes_temp += spike.get("temp_spikes", 0)
        self.spikes_psal += spike.get("psal_spikes", 0)
        grad = summary.get("test11_gradient", {})
        self.grad_temp += grad.get("temp_gradient", 0)
        self.grad_psal += grad.get("psal_gradient", 0)
        self.density_inv += summary.get("test14_density", {}).get(
            "density_inversions", 0)
        roll = summary.get("test12_rollover", {})
        self.rollover_temp += roll.get("temp_rollover", 0)
        self.rollover_psal += roll.get("psal_rollover", 0)

        has_bad = False
        for param, counts in summary["flags"].items():
            for flag, n in counts.items():
                self.flags[param][flag] += n
                if flag in (3, 4):
                    has_bad = True
        if has_bad:
            self.profiles_with_bad += 1

    def report(self):
        print(f"\n{'=' * 62}")
        print(f"  {self.label}")
        print(f"{'=' * 62}")
        print(f"  Profiles processed : {self.n_profiles:,}")
        print(f"  Levels processed   : {self.n_levels:,}")

        if self.n_profiles == 0:
            return

        pct = 100.0 * self.profiles_with_bad / self.n_profiles
        print(f"  Profiles with >=1 flagged level : {self.profiles_with_bad:,} ({pct:.1f}%)")
        print()
        print("  Test 2  impossible date      : "
              f"{self.bad_date:,} profiles failed")
        print("  Test 3  impossible location  : "
              f"{self.bad_location:,} profiles failed")
        print("  Test 13 stuck temperature    : "
              f"{self.stuck_temp:,} profiles")
        print("  Test 13 stuck salinity       : "
              f"{self.stuck_psal:,} profiles")
        print("  Test 8  pressure non-monotonic : "
              f"{self.pres_nonmono:,} levels")
        print("  Test 9  temperature spikes     : "
              f"{self.spikes_temp:,} levels")
        print("  Test 9  salinity spikes        : "
              f"{self.spikes_psal:,} levels")
        print("  Test 12 temperature rollover   : "
              f"{self.rollover_temp:,} levels")
        print("  Test 12 salinity rollover      : "
              f"{self.rollover_psal:,} levels")
        print("  Test 11 gradient (obsolete, not flagged): "
              f"{self.grad_temp:,} temp / {self.grad_psal:,} psal levels")
        print("  Test 14 density inversions     : "
              f"{self.density_inv:,} levels")
        print()
        print("  Level flags (Argo QC convention):")
        names = {0: "no QC", 1: "good", 2: "prob good",
                 3: "prob bad", 4: "bad", 9: "missing"}
        header = f"    {'param':<8}" + "".join(f"{names[f]:>11}" for f in (1, 2, 3, 4, 9))
        print(header)
        for param in ("pres", "temp", "psal"):
            row = f"    {param:<8}"
            for f in (1, 2, 3, 4, 9):
                row += f"{self.flags[param].get(f, 0):>11,}"
            print(row)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--argo", action="store_true", help="run QC on Argo profiles")
    ap.add_argument("--ctd", metavar="FILE", help="run QC on a WOD CTD file")
    ap.add_argument("--limit", type=int, default=None, help="max profiles per source")
    ap.add_argument("--region", nargs=4, type=float,
                    metavar=("LATMIN", "LATMAX", "LONMIN", "LONMAX"),
                    help="restrict Argo profiles to a bounding box")
    args = ap.parse_args()

    if not args.argo and not args.ctd:
        ap.error("specify --argo and/or --ctd")

    if args.argo:
        tally = Tally("ARGO  (INCOIS GDAC via Samudra PostgreSQL)")
        for prof in iter_argo_profiles(
            db_config_from_env(), limit=args.limit, region=args.region
        ):
            tally.add(run_basic_qc(prof))
            if tally.n_profiles % 200 == 0:
                print(f"  ... {tally.n_profiles:,} Argo profiles", end="\r")
        tally.report()

    if args.ctd:
        tally = Tally(f"CTD   (World Ocean Database: {os.path.basename(args.ctd)})")
        for prof in iter_wod_ctd_profiles(args.ctd, limit=args.limit):
            tally.add(run_basic_qc(prof))
        tally.report()

    print()


if __name__ == "__main__":
    main()
