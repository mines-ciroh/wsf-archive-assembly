"""Backfill NWRFC coordinated Water Supply Forecast Text products (WY2005-2013).

Source: https://www.nwrfc.noaa.gov/ws/wsFcstText.cgi?date=YYYYMMDD -- the legacy
"Water Supply Forecasts" text bulletin, coordinated among NWS/NRCS/BC Hydro,
archived back to 2004-06-17. Unlike the modern ESP CSV export
(nwrfc_wsf.csv, parsed from ws_text.cgi), this text product exists for the
whole WY2005-2013 pre-ESP-archive gap and lets several sites' NWRFC_official
coverage be extended back from 2011/2013 to 2005.

Sites requested (RFC id / USGS id / product station name):
    HEII1 13037500  "HEISE NR, ID"            APR-JUL  -- OK, backfilled
    LUCI1 13202000  "BOISE NR, ID"            APR-JUL  -- OK, backfilled
    OWYO3 13183000  -- NOT backfilled. The only APR-JUL Owyhee line is
                      "OWYHEE RES OUTFLOW" (regulated release; f/obs 0.03-0.32),
                      not the naturalized inflow the archive scores; the
                      "OWYHEE RES INFLOW" line is MAR-JUL (wrong season).
    STHW1 12451000  "STEHEKIN - AT STEHEKIN"  APR-JUL  -- OK from WY2012 only
                      (station absent before WY2012; becomes APR-AUG from
                      WY2013 onward and is dropped from that point)
    HHWM8 12362500  "HUNGRY HORSE RES IN, MT" -- NO APR-JUL row in ANY
                      vintage checked (WY2005-2013): only JAN-JUL and
                      (in some vintages) APR-SEP appear. Per the Apr-Jul-only
                      predictand rule, nothing to backfill for this site from
                      this product.
    LYDM8 12301933  "LIBBY RES INFLOW, MT"    -- same story as HHWM8: only
                      JAN-JUL (and sometimes APR-AUG/SEP) appear, never
                      APR-JUL. Nothing to backfill.

Column definitions: the legacy text bulletin's own header only labels the
"%" columns as percent-of-1971-2000-average, not exceedance probability, and
no footnote in this bulletin itself defines PROBABLE/MAXIMUM/MINIMUM in terms
of exceedance percentage. However NWRFC's modern water-supply summary product
(https://www.nwrfc.noaa.gov/water_supply/ws_summary.cgi), which reports the
same three values for the same stations, explicitly labels its three columns
"90% Exceedence KAF", "50% Exceedence KAF", "10% Exceedence KAF" in that
order (low->mid->high value = 90%->50%->10% exceedance). Cross-referencing
column order and value ordering (Minimum < Probable < Maximum, low-to-high)
against that confirms: PROBABLE == 50% exceedance, MAXIMUM (the wet/high
value) == 10% exceedance, MINIMUM (the dry/low value) == 90% exceedance.
This is the assumed mapping given in the task and is corroborated, not
found as an explicit in-bulletin footnote -- flagged in the backfill report.

Units: bulletin states "All forecasts are in thousands of acre-feet" i.e.
already KAF -- no conversion needed.
"""

import os
import re
import time
import glob
from datetime import datetime, timedelta

import pandas as pd

ARCHIVE_ROOT = os.environ.get("WSF_ARCHIVE_ROOT", os.path.expanduser("~/wsf_archive_v1.0"))
RAW_DIR = f"{ARCHIVE_ROOT}/source_data/rfc/nwrfc_wsfcsttext"
OUT_CSV = f"{ARCHIVE_ROOT}/source_data/rfc/nwrfc_wsf.wsfcsttext_2005_2013.csv"

BASE_URL = "https://www.nwrfc.noaa.gov/ws/wsFcstText.cgi"

# MAXIMUM/MINIMUM conventions (analysis/rfc_source_search_20260928/nwrfc_bulletin_maxmin_convention.md):
# - Legacy coordinated bulletins (footer "selected from those prepared by ... NWS / NRCS /
#   B.C. Hydro"; through Mar 2011): MAXIMUM/MINIMUM equal NWRFC's regression table's labelled
#   5%/95% exceedance values to rounding. That regression error distribution is normal
#   (5/95 symmetric about the median), so 10%/90% are median +/- Z_SCALE * half-width.
# - "Ensemble Date" ESP bulletins (from Dec 2011, NWRFC-only, no interagency footer):
#   MAXIMUM/MINIMUM = 10%/90%, as in NWRFC's current product (lineage, not a printed legend).
# - The first three WY2005 bulletins (before LEGACY_TAILS_FROM) have tails that match
#   neither 5/95 nor 10/90 relative to the regression table; they are dropped.
Z_SCALE = 1.2815516 / 1.6448536  # z(0.90) / z(0.95)
LEGACY_TAILS_FROM = datetime(2005, 3, 15)

# site -> (keyword(s) that must all appear in the station name field, required period)
SITE_MATCH = {
    "HEII1": (["HEISE NR"], "APR-JUL"),
    "LUCI1": (["BOISE NR"], "APR-JUL"),
    "STHW1": (["STEHEKIN"], "APR-JUL"),
    "HHWM8": (["HUNGRY HORSE RES IN"], "APR-JUL"),
    "LYDM8": (["LIBBY RES INFLOW"], "APR-JUL"),
}

WY_RANGE = range(2005, 2014)  # WY2005-2013
PUB_MONTHS = [1, 2, 3, 4]

OUT_COLS = [
    "site", "publicationDate", "issueDate", "forecastPeriodStart", "forecastPeriodEnd",
    "forecast_90", "forecast_70", "forecast_50", "forecast_30", "forecast_10",
    "source", "bulletin_date", "coordinated", "quantile_method",
]

DATA_LINE_RE = re.compile(
    r"^(?P<name>.+?)\s{2,}(?P<period>[A-Z]{3}-[A-Z]{3})\s+"
    r"(?P<probable>[\d,]+\.\d+)\s+-?\d+\s+"
    r"(?P<maximum>[\d,]+\.\d+)\s+-?\d+\s+"
    r"(?P<minimum>[\d,]+\.\d+)\s+-?\d+"
)


def enumerate_dropdown_dates(sample_html_path):
    """Extract every date the NWRFC page's own dropdown lists as archived."""
    with open(sample_html_path) as f:
        t = f.read()
    dates = sorted(set(re.findall(r'value="(\d{8})"', t)))
    return [datetime.strptime(d, "%Y%m%d") for d in dates]


def pick_target_dates(all_dates, wy_range=WY_RANGE, months=PUB_MONTHS,
                       max_days_after=10, max_days_before=5):
    """For each (WY, month), pick the archived date closest to that month's 1st,
    among dates within [1st - max_days_before, 1st + max_days_after]."""
    selected = {}
    for year in wy_range:
        for month in months:
            target = datetime(year, month, 1)
            window = [d for d in all_dates
                      if target - timedelta(days=max_days_before) <= d <= target + timedelta(days=max_days_after)]
            if not window:
                continue
            best = min(window, key=lambda d: abs((d - target).days))
            selected[(year, month)] = best
    return selected


def download(target_dates=None):
    import requests

    os.makedirs(RAW_DIR, exist_ok=True)

    if target_dates is None:
        # Bootstrap: fetch one page to read its date dropdown, then compute targets.
        bootstrap_path = os.path.join(RAW_DIR, "_bootstrap.html")
        resp = requests.get(BASE_URL, params={"date": "20050401"}, timeout=20)
        resp.raise_for_status()
        with open(bootstrap_path, "w") as f:
            f.write(resp.text)
        all_dates = enumerate_dropdown_dates(bootstrap_path)
        os.remove(bootstrap_path)
        target_dates = sorted(pick_target_dates(all_dates).values())

    for d in target_dates:
        dstr = d.strftime("%Y%m%d")
        out_path = os.path.join(RAW_DIR, f"wsFcstText_{dstr}.html")
        if os.path.exists(out_path):
            continue
        url = f"{BASE_URL}?date={dstr}"
        print(f"Downloading: {url}")
        try:
            resp = requests.get(url, timeout=20)
            resp.raise_for_status()
            with open(out_path, "w") as f:
                f.write(resp.text)
        except Exception as e:
            print(f"Failed for {dstr}: {e}")
        time.sleep(1)


def extract_pre_text(html_text):
    m = re.search(r"<pre>(.*?)</pre>", html_text, re.S)
    if not m:
        return ""
    pre = m.group(1)
    pre = re.sub(r"<[^>]+>", " ", pre)
    pre = pre.replace("&nbsp", " ")
    return pre


def month_end(year, month):
    import calendar
    return calendar.monthrange(year, month)[1]


def parse():
    rows = []
    files = sorted(glob.glob(os.path.join(RAW_DIR, "wsFcstText_*.html")))
    if not files:
        print(f"No raw files found in {RAW_DIR}")
        return pd.DataFrame(columns=OUT_COLS)

    for path in files:
        basename = os.path.basename(path)
        m = re.match(r"wsFcstText_(\d{8})\.html", basename)
        if not m:
            continue
        bulletin_date_str = m.group(1)
        bulletin_date = datetime.strptime(bulletin_date_str, "%Y%m%d")

        with open(path) as f:
            html_text = f.read()

        issued_match = re.search(r"Forecast Issued: (\d{8})", html_text)
        if issued_match:
            bulletin_date = datetime.strptime(issued_match.group(1), "%Y%m%d")

        pre = extract_pre_text(html_text)
        ensemble_fmt = "Ensemble Date" in html_text
        lines = pre.splitlines()

        # Publication month: closest 1st-of-month (Jan/Feb/Mar/Apr) to bulletin_date,
        # matching the same window rule used to pick which dates to download.
        candidates = []
        for year_guess in (bulletin_date.year, bulletin_date.year + 1):
            for month in PUB_MONTHS:
                target = datetime(year_guess, month, 1)
                delta = (target - bulletin_date).days
                if -10 <= delta <= 5:  # bulletin_date within 10 days before / 5 after target -> symmetric of the pick rule
                    candidates.append((abs(delta), year_guess, month))
        if not candidates:
            print(f"Skipping {basename}: bulletin date {bulletin_date_str} doesn't map to a Jan/Feb/Mar/Apr 1st within window")
            continue
        candidates.sort()
        _, pub_year, pub_month = candidates[0]
        pub_date_str = f"{pub_year}-{pub_month:02d}-01"

        # Water year for forecastPeriod is the same calendar year as the Jan-Apr
        # publication month (Apr-Jul forecast period always falls in that same year).
        fcst_period_start = f"{pub_year}-04-01"
        fcst_period_end = f"{pub_year}-07-31"

        for site, (keywords, period_req) in SITE_MATCH.items():
            found = None
            for line in lines:
                dm = DATA_LINE_RE.match(line.strip().lstrip(";").strip())
                if not dm:
                    continue
                name = dm.group("name").strip().upper()
                period = dm.group("period").strip().upper()
                if all(kw in name for kw in keywords) and period == period_req:
                    found = dm
                    break
            if found is None:
                continue

            def to_float(s):
                return float(s.replace(",", ""))

            p50 = to_float(found.group("probable"))
            vmax, vmin = to_float(found.group("maximum")), to_float(found.group("minimum"))
            if ensemble_fmt:
                f10, f90, qmethod, coordinated = vmax, vmin, "native_10_90", False
            elif bulletin_date < LEGACY_TAILS_FROM:
                print(f"Dropping {site} {basename}: early-WY2005 tails match neither 5/95 nor 10/90")
                continue
            else:
                f10 = round(p50 + Z_SCALE * (vmax - p50), 1)
                f90 = round(p50 - Z_SCALE * (p50 - vmin), 1)
                qmethod, coordinated = "normal_scaled_from_5_95", True

            rows.append({
                "site": site,
                "publicationDate": pub_date_str,
                "issueDate": pub_date_str,
                "forecastPeriodStart": fcst_period_start,
                "forecastPeriodEnd": fcst_period_end,
                "forecast_90": f90,
                "forecast_70": "",
                "forecast_50": p50,
                "forecast_30": "",
                "forecast_10": f10,
                "source": "NWRFC_official",
                "bulletin_date": bulletin_date.strftime("%Y-%m-%d"),
                "coordinated": coordinated,
                "quantile_method": qmethod,
            })

    if not rows:
        print("No forecasts found.")
        return pd.DataFrame(columns=OUT_COLS)

    df = pd.DataFrame(rows)[OUT_COLS]
    df = df.sort_values(["site", "publicationDate"]).drop_duplicates(
        subset=["site", "publicationDate"], keep="first"
    ).reset_index(drop=True)
    df.to_csv(OUT_CSV, index=False)
    print(f"Saved {len(df)} rows to {OUT_CSV}")
    return df


if __name__ == "__main__":
    # download()  # raw files already fetched under RAW_DIR; uncomment to refresh
    parse()
