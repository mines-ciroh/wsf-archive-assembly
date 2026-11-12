"""Re-derive NRCS 10%/90% exceedance for forecasts NRCS published at 5/30/50/70/95%.

Several Pacific Northwest forecast points (e.g. Libby, Hungry Horse, Howard Hanson,
Boise, Detroit) are published by NRCS at 5/30/50/70/95% exceedance. parse_nrcs_fcsts.py
filled f10/f90 by interpolating linearly in probability between 5% and 30% (70% and
95%). The archive's other derived quantiles are interpolated in standard-normal quantile
space; this script applies the same rule to these NRCS forecasts:

    f10 = f05 + W * (f30 - f05),   f90 = f95 + W * (f70 - f95),
    W = (z(0.95) - z(0.90)) / (z(0.95) - z(0.70))

Source: the NRCS AWDB forecasts API, saved for the archive's sites under
source_data/nrcs/api_json_wsf_sites/ (download_nrcs_api_wsf_sites()). The original
per-state JSON behind parse_nrcs_fcsts.py was not preserved.

A row is updated only if (a) the API forecast with the same station, issue date and
period has 5/30/50/70/95 and no 10/90, (b) its 30/50/70 equal the CSV's, and (c) the old
linear rule reproduces the CSV's f10/f90 -- i.e. it is the same forecast and its tails
were interpolated. All other rows are left unchanged.
"""

import glob
import json
import os
import subprocess
import sys
import time

import numpy as np
import pandas as pd
from scipy.stats import norm

ARCHIVE_ROOT = os.environ.get("WSF_ARCHIVE_ROOT", os.path.expanduser("~/wsf_archive_v1.0"))
API_DIR = f"{ARCHIVE_ROOT}/source_data/nrcs/api_json_wsf_sites"
NRCS_CSV = f"{ARCHIVE_ROOT}/source_data/nrcs/nrcs_fcst_obs.all_sites_yrs.wsf_rodeo.csv"
API_URL = ("https://wcc.sc.egov.usda.gov/awdbRestApi/services/v1/forecasts"
           "?stationTriplets={t}&elementCodes=SRVO&beginPublicationDate=1900-01-01"
           "&endPublicationDate=2025-09-30")

W = (norm.ppf(0.95) - norm.ppf(0.90)) / (norm.ppf(0.95) - norm.ppf(0.70))
W_LINEAR = (10 - 5) / (30 - 5)


def download_nrcs_api_wsf_sites():
    os.makedirs(API_DIR, exist_ok=True)
    trips = sorted(pd.read_csv(NRCS_CSV, dtype=str, usecols=["stationTriplet"]).stationTriplet.unique())
    for t in trips:
        out = subprocess.run(["curl", "-s", API_URL.format(t=t)], capture_output=True, text=True).stdout
        with open(f"{API_DIR}/{t.replace(':', '_')}.json", "w") as fh:
            fh.write(out)
        time.sleep(0.5)


def load_api():
    recs = {}
    for f in glob.glob(f"{API_DIR}/*.json"):
        for st in json.load(open(f)):
            for x in st.get("data", []):
                start, end = x["forecastPeriod"]
                recs[(st["stationTriplet"], x["issueDate"], start, end)] = {
                    k: float(v) for k, v in x.get("forecastValues", {}).items() if v is not None}
    return recs


def harmonize():
    api = load_api()
    df = pd.read_csv(NRCS_CSV, dtype={"stationTriplet": str})
    n_5_95 = n_updated = 0
    failed = []
    for i, r in df.iterrows():
        key = (r.stationTriplet, r.issueDate, r.forecastPeriodStart[5:], r.forecastPeriodEnd[5:])
        v = api.get(key)
        if not v or not {"5", "30", "50", "70", "95"} <= v.keys() or "10" in v or "90" in v:
            continue
        n_5_95 += 1
        same_mid = all(np.isclose(v[k], r[f"forecast_{k}"], atol=0.051) for k in ("30", "50", "70"))
        lin10 = v["5"] + W_LINEAR * (v["30"] - v["5"])
        lin90 = v["95"] + W_LINEAR * (v["70"] - v["95"])
        was_linear = np.isclose(lin10, r.forecast_10, atol=0.06) and np.isclose(lin90, r.forecast_90, atol=0.06)
        if not (same_mid and was_linear):
            failed.append((key, dict(r[[c for c in df.columns if c.startswith("forecast_")]]), v))
            continue
        df.at[i, "forecast_10"] = round(v["5"] + W * (v["30"] - v["5"]), 3)
        df.at[i, "forecast_90"] = round(v["95"] + W * (v["70"] - v["95"]), 3)
        n_updated += 1
    print(f"CSV rows whose API forecast is 5/30/50/70/95: {n_5_95}; updated: {n_updated}; "
          f"failed the match gate (left unchanged): {len(failed)}")
    for f in failed[:10]:
        print("  gate failure:", f)
    df.to_csv(NRCS_CSV, index=False)
    return df


if __name__ == "__main__":
    if "--download" in sys.argv:
        download_nrcs_api_wsf_sites()
    harmonize()
