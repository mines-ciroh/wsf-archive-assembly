"""Aggregate NWRFC ESP archives for sites without a native volumetric product.

NOTE: raw input directory (chps_agency ESP archive) is not present anywhere
in the current archive tree -- only this script's already-computed output
(nwrfc_wsf.esp_agg.csv) survives. Cannot be rerun as-is; kept for reference.
"""

import os
import numpy as np
import pandas as pd

ARCHIVE_ROOT = os.environ.get("WSF_ARCHIVE_ROOT", os.path.expanduser("~/wsf_archive_v1.0"))
OUT_FILE = f"{ARCHIVE_ROOT}/source_data/rfc/nwrfc_wsf.esp_agg.csv"
BASE_PATH = f"{ARCHIVE_ROOT}/source_data/rfc/nwrfc_esp_archives/rfc_data/ARCHIVE/chps_agency"  # missing

SITES = {
    "HHDW1": {"usgs_id": "12105900", "start": "0401", "end": "0731"},
    "DETO3": {"usgs_id": "14181500", "start": "0401", "end": "0630"},
    "RODW1": {"usgs_id": "NaN", "start": "0401", "end": "0731"},
}
FORECAST_DATES = ["0101", "0201", "0301", "0401"]
YEAR_LIST = range(2015, 2026)

MONTH_MAP = {
    "01": "JAN", "02": "FEB", "03": "MAR", "04": "APR",
    "05": "MAY", "06": "JUN", "07": "JUL", "08": "AUG",
    "09": "SEP", "10": "OCT", "11": "NOV", "12": "DEC",
}


def safe_float(val):
    try:
        return float(val)
    except Exception:
        return np.nan


def get_percentile(row, target_pct):
    pcts_avail = []
    for col in row.index:
        if col.startswith("esp_"):
            try:
                pcts_avail.append((int(col.split("_")[1]), col))
            except Exception:
                pass
    if not pcts_avail:
        return np.nan
    pcts_avail = sorted(pcts_avail, key=lambda x: x[0])
    pcts_list = [p[0] for p in pcts_avail]
    vals = [safe_float(row[p[1]]) for p in pcts_avail]
    if target_pct in pcts_list:
        return vals[pcts_list.index(target_pct)]
    arr_pcts = np.array(pcts_list)
    arr_vals = np.array(vals)
    if (target_pct < arr_pcts[0]) or (target_pct > arr_pcts[-1]):
        return np.nan
    return np.interp(target_pct, arr_pcts, arr_vals)


def mmdd_to_month_abbr(mmdd):
    return MONTH_MAP.get(mmdd[:2], "UNK")


def parse():
    records = []
    for year in YEAR_LIST:
        for fcast_date in FORECAST_DATES:
            agency_path = f"{BASE_PATH}/{year}/espagency.Nat{year}.{year}{fcast_date}.10"
            if not os.path.exists(agency_path):
                print(f"Missing: {agency_path}")
                continue

            df = pd.read_csv(agency_path)
            for rfc_site_id, site_info in SITES.items():
                start_month = mmdd_to_month_abbr(site_info["start"])
                end_month = mmdd_to_month_abbr(site_info["end"])
                df_period = df[(df["WS_startmonth"] == start_month) & (df["WS_endmonth"] == end_month)]
                row = df_period[df_period["id"] == rfc_site_id]
                if row.empty:
                    print(f"Missing {start_month}-{end_month} entry for {rfc_site_id} in {year} {fcast_date}")
                    continue
                row = row.iloc[0]

                issue_str = f"{year}-{fcast_date[:2]}-01"
                period_start = f"{year}-{site_info['start'][:2]}-{site_info['start'][2:]}"
                period_end = f"{year}-{site_info['end'][:2]}-{site_info['end'][2:]}"

                records.append({
                    "site": rfc_site_id,
                    "publicationDate": issue_str,
                    "issueDate": issue_str,
                    "forecastPeriodStart": period_start,
                    "forecastPeriodEnd": period_end,
                    "forecast_90": round(get_percentile(row, 90), 3),
                    "forecast_70": round(get_percentile(row, 70), 3),
                    "forecast_50": round(get_percentile(row, 50), 3),
                    "forecast_30": round(get_percentile(row, 30), 3),
                    "forecast_10": round(get_percentile(row, 10), 3),
                    "source": "NWRFC_official",
                })

    cols = ["site", "publicationDate", "issueDate", "forecastPeriodStart", "forecastPeriodEnd",
            "forecast_90", "forecast_70", "forecast_50", "forecast_30", "forecast_10", "source"]
    df_out = pd.DataFrame.from_records(records)[cols] if records else pd.DataFrame(columns=cols)
    df_out = df_out.sort_values(["site", "issueDate"])
    df_out.to_csv(OUT_FILE, index=False)
    print(f"Saved {len(df_out)} rows to {OUT_FILE}")
    return df_out


if __name__ == "__main__":
    parse()
