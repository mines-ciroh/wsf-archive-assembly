"""Backfill CNRFC official water-supply-outlook forecasts for WY2004-2012 (the bulletin is absent from IEM from WY2013)
(FOLC1, FRAC1, POHC1) from the Iowa Environmental Mesonet (IEM) AFOS text
archive, PIL ESPRSA.

The existing wsf-archive-assembly/get_data/rfc/download_cnrfc.py script pulls
CNRFC's own ensembleProductTabular.php web page, which only has data back to
~2011. Before that, the only surviving source of the monthly CNRFC "Water
Supply Outlook" bulletin is the raw AFOS text product, archived by IEM back
to the mid-1990s. This script downloads the raw ESPRSA bulletins covering
Dec 2003 - May 2012 from IEM, saves one file per bulletin (unmodified), and
parses out the three sites' Apr-Jul forecasts for the WY2004-2012 Jan/Feb/
Mar/Apr issuances.

Usage:
    python3 download_cnrfc_iem_backfill.py           # download raw + parse
    python3 download_cnrfc_iem_backfill.py --parse-only   # re-parse only

Output: $ARCHIVE_ROOT/source_data/rfc/cnrfc_wsf.iem_2004_2012.csv
"""
import os
import re
import sys
import glob
from datetime import datetime, date
from time import sleep

import numpy as np
import pandas as pd

ARCHIVE_ROOT = os.environ.get("WSF_ARCHIVE_ROOT", os.path.expanduser("~/wsf_archive_v1.0"))
RAW_DIR = f"{ARCHIVE_ROOT}/source_data/rfc/cnrfc_esp_iem"
OUT_CSV = f"{ARCHIVE_ROOT}/source_data/rfc/cnrfc_wsf.iem_2004_2012.csv"

IEM_URL = (
    "https://mesonet.agron.iastate.edu/cgi-bin/afos/retrieve.py"
    "?pil=ESPRSA&fmt=text&sdate=2003-12-01T00:00Z&edate=2012-05-10T00:00Z"
    "&limit=500&order=asc"
)

# Site -> exact printed line-label prefix in the ESPRSA product body.
# Matched with .startswith() after stripping leading whitespace, because the
# product's label text is not perfectly stable across years (e.g. "Folsom
# Reservoir Inflow" in most years vs bare "Folsom Reservoir" in Mar 2011).
SITE_LABELS = {
    "FOLC1": "Folsom Reservoir",              # American River above Folsom Reservoir
    "FRAC1": "Millerton Lk",                  # San Joaquin River -> Millerton Lake / Friant
    "POHC1": "Pohono Bridge, at, Yosemite",   # Merced River at Pohono Bridge, Yosemite
}

MONTH_MAP = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
}


def download():
    import requests

    os.makedirs(RAW_DIR, exist_ok=True)
    print(f"Downloading {IEM_URL}")
    resp = requests.get(IEM_URL, timeout=60)
    resp.raise_for_status()
    text = resp.text

    # Split into individual bulletins. AFOS record-separator lines before the
    # WMO header vary (seen "000", "304", "591", "566", ... -- an AFOS
    # sequence number, not a fixed literal), so split directly on the WMO
    # header line itself (site/date/time group), which is a stable anchor.
    # Each bulletin's raw text (unmodified from that header onward) is saved
    # as its own file, e.g. FGUS66_KRSA_070414.txt -- mirrors the "one file
    # per product, raw" convention used elsewhere in this repo.
    blocks = re.split(r"\n(?=FGUS\d\d KRSA \d{6}\n)", text)
    n_saved = 0
    for block in blocks:
        m = re.search(r"^(FGUS\d\d KRSA \d{6})", block, re.M)
        if not m:
            continue
        tag = m.group(1).replace(" ", "_")
        outfn = os.path.join(RAW_DIR, f"{tag}.txt")
        with open(outfn, "w") as f:
            f.write(block)
        n_saved += 1
    print(f"Saved {n_saved} raw bulletin files to {RAW_DIR}")
    sleep(1)  # polite pause (single bulk request, but keep the convention)


def parse_bulletin(text, fname):
    """Return (bulletin_date, {site: {q: value}}) for one ESPRSA bulletin,
    or (None, None) if it isn't a recognizable Water Supply Outlook."""
    m = re.search(
        r"WATER SUPPLY OUTLOOK\s+([A-Za-z]{3})\s+(\d{1,2})\s+(\d{4})",
        text,
    )
    if not m:
        return None, None
    mon = MONTH_MAP.get(m.group(1).upper())
    day = int(m.group(2))
    year = int(m.group(3))
    if mon is None:
        return None, None
    bulletin_date = date(year, mon, day)

    def fnum(s):
        s = s.rstrip("*")
        try:
            return float(s)
        except ValueError:
            return np.nan

    out = {}
    for line in text.splitlines():
        stripped = line.strip()
        for site, label in SITE_LABELS.items():
            if stripped.startswith(label):
                tokens = stripped.split()
                # The line label itself can carry a variable number of extra
                # words after the matched prefix (e.g. "Folsom Reservoir
                # Inflow" vs "Folsom Reservoir"; "Pohono Bridge, at,
                # Yosemite, n"), so anchor on the fixed-width DATA columns
                # from the right instead: Period MP MP% RMAX RMIN AVG(*).
                if len(tokens) < 6:
                    continue
                period, mp, mp_pct, rmax, rmin, avg = tokens[-6:]
                out[site] = {
                    "period": period,
                    "forecast_50": fnum(mp),
                    "forecast_10": fnum(rmax),  # 10% chance of exceeding -> wet/high
                    "forecast_90": fnum(rmin),  # 90% chance of exceeding -> dry/low
                }
    return bulletin_date, out


def parse():
    files = sorted(glob.glob(os.path.join(RAW_DIR, "*.txt")))
    if not files:
        sys.exit(f"No raw bulletin files found in {RAW_DIR} -- run download() first.")

    # Collect all bulletins, keyed by nominal bulletin_date, keeping every
    # transmission (dedup logic + duplicate-values check happens after).
    by_date = {}  # bulletin_date -> list of (fname, parsed_dict)
    for fn in files:
        with open(fn) as f:
            text = f.read()
        bdate, parsed = parse_bulletin(text, fn)
        if bdate is None or not parsed:
            continue
        by_date.setdefault(bdate, []).append((os.path.basename(fn), parsed))

    dup_log = []
    rows = []
    wanted_months = {1, 2, 3, 4}
    for bdate, entries in sorted(by_date.items()):
        if bdate.month not in wanted_months:
            continue
        if bdate.year < 2004 or bdate.year > 2012:
            continue

        # Map this bulletin's own printed date to the issueDate slot it
        # represents. Per task convention: only accept if the printed date
        # literally IS the 1st, or is within 10 days after / 5 days before.
        target_first = date(bdate.year, bdate.month, 1)
        offset_days = (bdate - target_first).days
        if not (-5 <= offset_days <= 10):
            print(f"SKIP {bdate}: offset {offset_days}d from {target_first} out of window")
            continue

        # Dedup multiple transmissions of the same nominal bulletin date:
        # keep the first (earliest-filed) transmission; log + compare if
        # any later transmission's values for our 3 sites differ.
        first_fname, first_vals = entries[0]
        if len(entries) > 1:
            for other_fname, other_vals in entries[1:]:
                if other_vals != first_vals:
                    dup_log.append(
                        f"{bdate} MISMATCH between {first_fname} and {other_fname}: "
                        f"{first_vals} vs {other_vals}"
                    )
                else:
                    dup_log.append(
                        f"{bdate}: {len(entries)} identical transmissions "
                        f"(kept {first_fname}, dropped {other_fname})"
                    )

        for site, vals in first_vals.items():
            period = vals.get("period", "")
            if period != "Apr-Jul":
                # Predictand is Apr-Jul only; drop (never relabel) anything else.
                print(f"SKIP {site} {bdate}: period={period!r} != Apr-Jul")
                continue
            row = {
                "site": site,
                "publicationDate": target_first.isoformat(),
                "issueDate": target_first.isoformat(),
                "forecastPeriodStart": f"{bdate.year}-04-01",
                "forecastPeriodEnd": f"{bdate.year}-07-31",
                "forecast_90": vals["forecast_90"],
                "forecast_70": np.nan,
                "forecast_50": vals["forecast_50"],
                "forecast_30": np.nan,
                "forecast_10": vals["forecast_10"],
                "source": "CNRFC_official",
                "bulletin_date": bdate.isoformat(),
                "coordinated": False,
            }
            rows.append(row)

    cols = [
        "site", "publicationDate", "issueDate", "forecastPeriodStart",
        "forecastPeriodEnd", "forecast_90", "forecast_70", "forecast_50",
        "forecast_30", "forecast_10", "source", "bulletin_date", "coordinated",
    ]
    df = pd.DataFrame(rows, columns=cols)
    df = df.sort_values(["site", "issueDate"]).reset_index(drop=True)
    df.to_csv(OUT_CSV, index=False)
    print(f"\nSaved {len(df)} rows to {OUT_CSV}")
    print(df.groupby("site").size())

    print("\n--- duplicate-transmission log ---")
    for line in dup_log:
        print(line)

    # Ordering check
    bad_order = df[~((df["forecast_10"] >= df["forecast_50"]) & (df["forecast_50"] >= df["forecast_90"]))]
    print(f"\nRows violating forecast_10 >= forecast_50 >= forecast_90: {len(bad_order)}")
    if len(bad_order):
        print(bad_order)

    return df


if __name__ == "__main__":
    if "--parse-only" not in sys.argv:
        download()
    parse()
