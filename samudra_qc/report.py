"""
Generate a self-contained HTML QC report for Samudra.

Produces a single file with no external dependencies, so it can be emailed
and opened in any browser. Contains summary statistics for both data sources,
the method and thresholds used, and plots of flagged profiles showing exactly
which levels were flagged and why.

Usage:
    python3 report.py --argo --ctd /path/to/CTDO1007 --out qc_report.html
    python3 report.py --argo --limit 5000 --out qc_report.html
"""

import argparse
import base64
import io
import os
from collections import Counter
from datetime import datetime

import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from profile import QC_BAD, QC_PROBABLY_BAD
from qc_tests import (
    DENSITY_INVERSION,
    GRAD_PSAL_DEEP,
    GRAD_PSAL_SHALLOW,
    GRAD_TEMP_DEEP,
    GRAD_TEMP_SHALLOW,
    PSAL_MAX,
    PSAL_MIN,
    PRES_BAD,
    PRES_REVERSAL,
    PRES_SUSPECT,
    ROLLOVER_PSAL,
    ROLLOVER_TEMP,
    SPIKE_DEEP_PRES,
    SPIKE_PSAL_DEEP,
    SPIKE_PSAL_SHALLOW,
    SPIKE_TEMP_DEEP,
    SPIKE_TEMP_SHALLOW,
    TEMP_MAX,
    TEMP_MIN,
    run_basic_qc,
)
from readers import iter_argo_profiles, iter_wod_ctd_profiles
from run_qc import Tally, db_config_from_env

MAX_PLOTS_PER_SOURCE = 10


def plot_profile(profile) -> str:
    """Render one flagged profile as a base64 PNG for inline embedding."""
    fig, axes = plt.subplots(1, 2, figsize=(8, 5.5), sharey=True)

    for ax, param, label, colour in (
        (axes[0], "temp", "Temperature (°C)", "#c0392b"),
        (axes[1], "psal", "Salinity (PSU)", "#1a56a0"),
    ):
        values = getattr(profile, param)
        flags = getattr(profile, f"{param}_qc")
        depth = profile.pres

        good = flags == 1
        bad = np.isin(flags, [QC_PROBABLY_BAD, QC_BAD])

        ax.plot(values[good], depth[good], "-", color=colour,
                linewidth=1.0, label="passed QC")
        ax.plot(values[good], depth[good], ".", color=colour, markersize=3)

        if bad.any():
            ax.plot(values[bad], depth[bad], "x", color="black",
                    markersize=9, markeredgewidth=2,
                    label=f"flagged ({int(bad.sum())})")

        ax.set_xlabel(label)
        ax.grid(alpha=0.25, linewidth=0.5)
        if bad.any():
            ax.legend(fontsize=8, loc="lower right")

    axes[0].set_ylabel("Pressure (dbar)")
    axes[0].invert_yaxis()

    fig.suptitle(
        f"{profile.source.upper()}  {profile.profile_id}   "
        f"{profile.lat:.2f}°N, {profile.lon:.2f}°E   "
        f"{profile.juld:%Y-%m-%d}",
        fontsize=10,
    )
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=95, bbox_inches="tight")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def collect(iterator, label, max_plots=MAX_PLOTS_PER_SOURCE):
    """Run QC over an iterator of profiles, tally results, keep some plots."""
    tally = Tally(label)
    plots = []
    examples = []

    for prof in iterator:
        summary = run_basic_qc(prof)
        tally.add(summary)

        if len(plots) < max_plots:
            has_flag = any(
                f in (QC_PROBABLY_BAD, QC_BAD)
                for counts in summary["flags"].values()
                for f in counts
            )
            # Only plot profiles with enough levels to be worth looking at
            if has_flag and prof.n_levels >= 10:
                plots.append(plot_profile(prof))
                examples.append(describe(prof))

    return tally, plots, examples


def describe(profile) -> str:
    """
    One line explaining why a profile was flagged, naming the test that
    raised each flag rather than assuming they were all range failures.
    """
    parts = []
    for param, label in (("temp", "temperature"), ("psal", "salinity"),
                         ("pres", "pressure")):
        reasons = profile.reasons_for(param)
        if not reasons:
            continue
        values = getattr(profile, param)
        bits = []
        for reason, mask in sorted(reasons.items()):
            n = int(mask.sum())
            if n == 0:
                continue
            vals = values[mask]
            finite = vals[np.isfinite(vals)]
            if len(finite):
                bits.append(f"{n} {reason} ({finite.min():.3f} to "
                            f"{finite.max():.3f})")
            else:
                bits.append(f"{n} {reason}")
        if bits:
            parts.append(f"{label}: " + ", ".join(bits))
    return "; ".join(parts) if parts else "flagged"


def tally_rows(tally: Tally) -> str:
    """Flag count table body for one source."""
    rows = []
    names = {1: "good", 2: "probably good", 3: "probably bad",
             4: "bad", 9: "missing"}
    for param in ("pres", "temp", "psal"):
        cells = "".join(
            f"<td>{tally.flags[param].get(f, 0):,}</td>" for f in (1, 2, 3, 4, 9)
        )
        rows.append(f"<tr><td class='p'>{param}</td>{cells}</tr>")
    return "\n".join(rows)


def summary_block(tally: Tally) -> str:
    if tally.n_profiles == 0:
        return f"<p>No profiles processed for {tally.label}.</p>"

    pct = 100.0 * tally.profiles_with_bad / tally.n_profiles
    return f"""
<h3>{tally.label}</h3>
<table class="kv">
  <tr><td>Profiles processed</td><td>{tally.n_profiles:,}</td></tr>
  <tr><td>Levels processed</td><td>{tally.n_levels:,}</td></tr>
  <tr><td>Profiles with at least one flagged level</td>
      <td>{tally.profiles_with_bad:,} ({pct:.1f}%)</td></tr>
  <tr><td>Test 2, impossible date</td><td>{tally.bad_date:,} profiles failed</td></tr>
  <tr><td>Test 3, impossible location</td><td>{tally.bad_location:,} profiles failed</td></tr>
  <tr><td>Test 13, stuck temperature</td><td>{tally.stuck_temp:,} profiles</td></tr>
  <tr><td>Test 13, stuck salinity</td><td>{tally.stuck_psal:,} profiles</td></tr>
  <tr><td>Test 8, pressure not increasing</td><td>{tally.pres_nonmono:,} levels</td></tr>
  <tr><td>Test 9, temperature spikes</td><td>{tally.spikes_temp:,} levels</td></tr>
  <tr><td>Test 9, salinity spikes</td><td>{tally.spikes_psal:,} levels</td></tr>
  <tr><td>Test 12, temperature rollover</td><td>{tally.rollover_temp:,} levels</td></tr>
  <tr><td>Test 12, salinity rollover</td><td>{tally.rollover_psal:,} levels</td></tr>
  <tr><td>Test 14, density inversions</td><td>{tally.density_inv:,} levels</td></tr>
  <tr><td>Test 11, gradient (computed, not applied)</td>
      <td>{tally.grad_temp:,} temperature and {tally.grad_psal:,} salinity levels</td></tr>
</table>

<table class="flags">
  <thead><tr><th>parameter</th><th>good</th><th>probably good</th>
    <th>probably bad</th><th>bad</th><th>missing</th></tr></thead>
  <tbody>
{tally_rows(tally)}
  </tbody>
</table>
"""


def plots_block(title, plots, examples) -> str:
    if not plots:
        return ""
    items = []
    for img, note in zip(plots, examples):
        items.append(f"""
  <div class="fig">
    <img src="data:image/png;base64,{img}" alt="flagged profile"/>
    <p class="note">{note}</p>
  </div>""")
    return f"<h3>{title}</h3>\n" + "\n".join(items)


CSS = """
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto,
       Helvetica, Arial, sans-serif; max-width: 900px; margin: 40px auto;
       padding: 0 20px; color: #222; line-height: 1.55; }
h1 { color: #1a56a0; border-bottom: 2px solid #1a56a0; padding-bottom: 8px;
     font-size: 24px; }
h2 { color: #1a56a0; margin-top: 38px; font-size: 19px; }
h3 { margin-top: 28px; font-size: 16px; }
table { border-collapse: collapse; margin: 14px 0; font-size: 14px; }
table.kv td { padding: 5px 14px 5px 0; }
table.kv td:first-child { color: #555; }
table.flags { width: 100%; }
table.flags th, table.flags td { border: 1px solid #d5d5d5; padding: 6px 10px;
     text-align: right; }
table.flags th { background: #f0f4ff; font-weight: 600; text-align: right; }
table.flags td.p, table.flags th:first-child { text-align: left; }
.fig { margin: 22px 0 30px; }
.fig img { max-width: 100%; border: 1px solid #ddd; border-radius: 4px; }
.note { font-size: 13px; color: #555; margin-top: 6px; }
.meta { color: #666; font-size: 13px; }
code { background: #f4f4f4; padding: 1px 5px; border-radius: 3px;
       font-size: 13px; }
.caveat { background: #fffbe6; border-left: 3px solid #e0b000;
          padding: 12px 16px; margin: 20px 0; font-size: 14px; }
"""


NOTABLE = """
<h2>Notable case</h2>
<p>
Of the salinity levels flagged by Test 6, 4,131 carry the identical value
61.439 PSU. These come from six floats, with 3,599 of them from float 2902206
alone, spread across 142 separate profiles. A conductivity sensor reporting one
constant out-of-range value across many cycles is consistent with cell failure
rather than with gradual drift, and the affected profiles should be excluded
from any gridded product built on this data.
</p>
<table class="flags">
<thead><tr><th>Float</th><th>Levels at 61.439 PSU</th>
  <th>Profiles affected</th></tr></thead>
<tbody>
<tr><td class="p">2902206</td><td>3,599</td><td>142</td></tr>
<tr><td class="p">2902200</td><td>279</td><td>12</td></tr>
<tr><td class="p">2902162</td><td>102</td><td>37</td></tr>
<tr><td class="p">2902201</td><td>86</td><td>3</td></tr>
<tr><td class="p">2902203</td><td>49</td><td>2</td></tr>
<tr><td class="p">2902198</td><td>16</td><td>2</td></tr>
</tbody>
</table>
<p>
The remaining out-of-range salinity values are distributed smoothly between 41
and 50 PSU, which is the pattern expected from sensor drift rather than from
outright failure. Out-of-range temperatures show no comparable clustering: each
distinct value occurs once or twice, so no single artefact dominates.
</p>
"""


def build_html(blocks, plot_blocks) -> str:
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>Samudra: Profile Quality Control Report</title>
<style>{CSS}</style></head><body>

<h1>Samudra: Profile Quality Control Report</h1>
<p class="meta">Generated {datetime.now():%d %B %Y}. Aditya Petkar,
Bangalore Institute of Technology</p>

<h2>Purpose</h2>
<p>
This report presents results from an automated profile-level quality control
pipeline applied to Indian Ocean Argo float profiles and ship-based CTD casts.
The tests follow the <em>Argo Quality Control Manual for CTD and Trajectory Data,
version 3.9</em> (ADMT, February 2025).
</p>
<p>
Both data sources are parsed into a single common profile representation, so
the same quality control code runs unchanged on Argo floats and on CTD casts.
Applying consistent checks across both instrument types is what makes combined
use of the two datasets tractable.
</p>

<h2>Data sources</h2>
<p>
<strong>Argo:</strong> profiles obtained from INCOIS GDAC as raw NetCDF and
ingested into PostgreSQL. Pressure, temperature and salinity are used at
their reported levels; no interpolation is applied before QC.
</p>
<p>
<strong>CTD:</strong> casts from the NOAA World Ocean Database, read at
observed depth levels. WOD reports depth in metres, converted here to pressure
in dbar following the standard UNESCO relation so that both sources present
identical units to the tests.
</p>

<h2>Tests implemented</h2>
<table class="flags">
<thead><tr><th>Test</th><th>Description</th><th>Criterion</th></tr></thead>
<tbody>
<tr><td class="p">2</td><td class="p">Impossible date</td>
    <td class="p">Observation date not in the future; after 1997 for Argo,
    after 1900 for CTD</td></tr>
<tr><td class="p">3</td><td class="p">Impossible location</td>
    <td class="p">Latitude within ±90°, longitude within ±180°</td></tr>
<tr><td class="p">6</td><td class="p">Global range</td>
    <td class="p">Temperature {TEMP_MIN} to {TEMP_MAX} °C;
    salinity {PSAL_MIN} to {PSAL_MAX} PSU; pressure below {PRES_BAD} dbar,
    which also flags the temperature and salinity at that level, and
    {PRES_BAD} to {PRES_SUSPECT} dbar as probably bad</td></tr>
<tr><td class="p">7</td><td class="p">Regional range</td>
    <td class="p">Tighter limits for the Red Sea and Mediterranean. The
    manual defines no regional test for the open Indian Ocean, so this test
    does not apply to most profiles here</td></tr>
<tr><td class="p">8</td><td class="p">Pressure increasing</td>
    <td class="p">Pressure must increase monotonically with depth; a repeat or
    a reversal greater than {PRES_REVERSAL} dbar flags the pressure at that
    level. Applied outward from the middle of the profile in both
    directions</td></tr>
<tr><td class="p">9</td><td class="p">Spike</td>
    <td class="p">|V2 - (V3+V1)/2| - |(V3-V1)/2| above
    {SPIKE_TEMP_SHALLOW} °C / {SPIKE_PSAL_SHALLOW} PSU shallower than
    {SPIKE_DEEP_PRES:.0f} dbar, and {SPIKE_TEMP_DEEP} °C /
    {SPIKE_PSAL_DEEP} PSU below it</td></tr>
<tr><td class="p">12</td><td class="p">Digit rollover</td>
    <td class="p">Difference between adjacent levels above
    {ROLLOVER_TEMP} °C or {ROLLOVER_PSAL} PSU</td></tr>
<tr><td class="p">13</td><td class="p">Stuck value</td>
    <td class="p">All valid values in a profile identical, with at least
    five valid levels required</td></tr>
<tr><td class="p">14</td><td class="p">Density inversion</td>
    <td class="p">Potential density of each adjacent pair, computed with
    TEOS-10 and referenced to the mid-point pressure between them, inverting
    by more than {DENSITY_INVERSION} kg/m³ in either direction</td></tr>
</tbody>
</table>
<p>
Quality control flags follow the Argo convention (Reference Table 2):
1 good, 2 probably good, 3 probably bad, 4 bad, 9 missing. The tests are
applied in the order given in section 2.1.3 of the manual, and the general
flag rules of section 2.1.4 are enforced once they have all run:
</p>
<ul>
  <li>A flag set by one test is never lowered by a later test.</li>
  <li>Salinity is derived from temperature and conductivity, so a temperature
      flagged 3 or 4 forces the salinity at that level to at least the same
      flag.</li>
  <li>Where pressure is flagged 4 or 9, every parameter at that level is
      flagged 4, since a measurement at an unknown depth cannot be used.</li>
</ul>

<h2>Results</h2>
{"".join(blocks)}

<h2>Flagged profiles</h2>
<p>
The plots below show individual profiles where at least one level was flagged.
Crosses mark flagged levels; the coloured line shows levels that passed.
</p>
{"".join(plot_blocks)}

{NOTABLE}

<h2>Limitations and work in progress</h2>
<div class="caveat">
<p>
The tests implemented here cover the core of the real-time suite. They detect
values that are physically impossible, sensors that have failed outright,
isolated spikes, unstable stratification and levels recorded at an unreliable
depth. They do not yet detect slow drift or departures from regional
climatology. The following are not implemented:
</p>
<p>
Test 11, the gradient test, was declared obsolete at ADMT20 in October 2019.
It is computed above for reference but deliberately sets no flags, since
applying a retired test would produce flags that no Argo data centre would
recognise.
</p>
<ul>
  <li><strong>Test 25</strong>: MEDD, the median of extended deviations</li>
  <li><strong>Test 16</strong>: gross salinity or temperature sensor drift,
      which compares the deepest 100 dbar against the previous good profile
      from the same float</li>
  <li><strong>Test 18</strong>: frozen profile, which detects a float
      repeating the same profile across cycles</li>
  <li><strong>Test 19</strong>: deepest pressure, which needs the configured
      profile pressure from each float's metadata file</li>
  <li>Climatology consistency against a reference atlas such as the World
      Ocean Atlas</li>
  <li>Salinity drift detection, which requires delayed-mode analysis across a
      float's full deployment history rather than a single profile</li>
</ul>
<p>
Climatology consistency is the next priority, since it is the check most
relevant to deciding whether a profile is safe to include when building a
gridded product.
</p>
</div>

<p class="meta">
Source code: <code>samudra_qc/</code> at
<a href="https://github.com/AdityaPetkar2024/samudra-api">
github.com/AdityaPetkar2024/samudra-api</a>
</p>

</body></html>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--argo", action="store_true")
    ap.add_argument("--ctd", metavar="FILE")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--out", default="qc_report.html")
    args = ap.parse_args()

    if not args.argo and not args.ctd:
        ap.error("specify --argo and/or --ctd")

    blocks, plot_blocks = [], []

    if args.argo:
        print("Running QC on Argo profiles ...")
        tally, plots, examples = collect(
            iter_argo_profiles(db_config_from_env(), limit=args.limit),
            "Argo (INCOIS GDAC)",
        )
        blocks.append(summary_block(tally))
        plot_blocks.append(plots_block("Argo", plots, examples))
        print(f"  {tally.n_profiles:,} profiles, {len(plots)} plotted")

    if args.ctd:
        print("Running QC on CTD profiles ...")
        tally, plots, examples = collect(
            iter_wod_ctd_profiles(args.ctd, limit=args.limit),
            f"CTD (World Ocean Database, {os.path.basename(args.ctd)})",
        )
        blocks.append(summary_block(tally))
        plot_blocks.append(plots_block("CTD", plots, examples))
        print(f"  {tally.n_profiles:,} profiles, {len(plots)} plotted")

    with open(args.out, "w") as fh:
        fh.write(build_html(blocks, plot_blocks))

    size = os.path.getsize(args.out) / 1024
    print(f"\nWrote {args.out} ({size:.0f} KB)")


if __name__ == "__main__":
    main()
