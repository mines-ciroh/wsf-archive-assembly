"""Download NWRFC Apr-Jul volumetric ESP forecasts, plus pre-2011 regression WSFs."""

import os
import re
import glob
import calendar
from datetime import datetime
from io import StringIO

import numpy as np
import pandas as pd

ARCHIVE_ROOT = os.environ.get("WSF_ARCHIVE_ROOT", os.path.expanduser("~/wsf_archive_v1.0"))
RAW_DIR = f"{ARCHIVE_ROOT}/source_data/rfc/nwrfc_esp"
OUT_CSV = f"{ARCHIVE_ROOT}/source_data/rfc/nwrfc_wsf.csv"
REGR_INPUT_CSV = f"{ARCHIVE_ROOT}/source_data/rfc/nwrfc_vol_fcst_reg.csv"
REGR_OUT_CSV = f"{ARCHIVE_ROOT}/source_data/rfc/nwrfc_wsf.regr.csv"

SITES = ["HHWM8", "HEII1", "LYDM8", "LUCI1", "HHDW1", "STHW1", "DETO3", "RODW1", "OWYO3", "KTFW1"]
PUB_MONTHS = [1, 2, 3, 4]
MONTH_STR_TO_NUM = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}



# 30%/70% exceedance from 25%/75%, interpolated in standard-normal quantile space between
# the median and the 25%/75% value (z(0.70)/z(0.75) = 0.7777); same approach as the other
# derived quantiles in the archive (Pecos, NWRFC legacy tails).
Z_25_TO_30 = 0.5244005 / 0.6744898


def q30_from_25(f50, f25):
    return f50 + Z_25_TO_30 * (f25 - f50)

def download():
    import requests

    os.makedirs(RAW_DIR, exist_ok=True)
    years = range(2000, 2025)
    fcst_type = "ESP10"
    prob = 0

    for site in SITES:
        period = "APR-JUN" if site == "DETO3" else "APR-JUL"
        for year in years:
            if site in ("KTFW1", "DETO3"):
                url = f"https://www.nwrfc.noaa.gov/natural/plot/nat_text.cgi?id={site}&wy={year}&per={period}"
            else:
                url = (
                    f"https://www.nwrfc.noaa.gov/water_supply/ws_text.cgi?"
                    f"id={site}&wy={year}&per={period}&type={fcst_type}&prob={prob}"
                )
            print(f"Downloading: {url}")
            try:
                resp = requests.get(url, timeout=10)
                resp.raise_for_status()
                with open(os.path.join(RAW_DIR, f"{site}_{year}.txt"), "w") as f:
                    f.write(resp.text)
            except Exception as e:
                print(f"Failed for {site} {year}: {e}")


def get_forecast_period_dates(year, start_month_str, end_month_str):
    if start_month_str not in MONTH_STR_TO_NUM or end_month_str not in MONTH_STR_TO_NUM:
        return "", ""
    start_month = MONTH_STR_TO_NUM[start_month_str]
    end_month = MONTH_STR_TO_NUM[end_month_str]
    start_date = f"{year}-{start_month:02d}-01"
    last_day = calendar.monthrange(year, end_month)[1]
    end_date = f"{year}-{end_month:02d}-{last_day:02d}"
    return start_date, end_date


def find_closest_forecast(df, year, month, max_days_back=7):
    pub_date = datetime(year, month, 1)
    df_before = df[df["Ensemble Date"] <= pub_date]
    if df_before.empty:
        return None
    df_before = df_before.assign(days_back=(pub_date - df_before["Ensemble Date"]).dt.days)
    df_recent = df_before[df_before["days_back"] <= max_days_back]
    if df_recent.empty:
        return None
    idx = df_recent["days_back"].idxmin()
    out = df_recent.loc[idx].copy()
    out["publication_date"] = pub_date
    return out


def parse_esp():
    """Combine WSFs into a single file. NOTE: skip HEII1 before 2012 as data looks wrong."""
    rows = []
    for file in glob.glob(os.path.join(RAW_DIR, "*.txt")):
        basename = os.path.basename(file)
        match = re.match(r"([A-Z0-9]+)_(\d{4})\.txt", basename)
        if not match:
            continue
        site, wy = match.group(1), int(match.group(2))

        with open(file, "r") as f:
            txt = f.read()
        lines = txt.replace("<br>", "\n").splitlines()

        header_idx = None
        for i, line in enumerate(lines):
            if "Ensemble Date" in line and "ID" in line:
                header_idx = i
                break
        if header_idx is None:
            continue

        csv_lines = []
        for l in lines[header_idx:]:
            ls = l.strip()
            if ls.startswith("ID") and csv_lines:
                continue
            if ls.startswith("#") or ls == "" or ls.startswith("</pre>"):
                continue
            csv_lines.append(ls)
        csv_text = "\n".join(csv_lines)

        try:
            df = pd.read_csv(StringIO(csv_text))
        except Exception as e:
            print(f"Failed to parse {file}: {e}")
            continue

        if "Ensemble Date" not in df.columns or len(df) == 0:
            continue

        try:
            df["Ensemble Date"] = pd.to_datetime(df["Ensemble Date"], errors="coerce")
            df["Issuance Date"] = pd.to_datetime(df["Issuance Date"], errors="coerce")
        except Exception as e:
            print(f"Date conversion issue in {file}: {e}")
            continue

        for m in PUB_MONTHS:
            row = find_closest_forecast(df, wy, m)
            if row is not None:
                if site == "HEII1" and wy <= 2011:
                    continue
                start_month, end_month = row["Start Month"], row["End Month"]
                fc_start, fc_end = get_forecast_period_dates(wy, str(start_month).upper(), str(end_month).upper())
                rows.append({
                    "site": site,
                    "publicationDate": row["publication_date"].strftime("%Y-%m-%d"),
                    "issueDate": row["Ensemble Date"].strftime("%Y-%m-%d") if pd.notnull(row["Ensemble Date"]) else "",
                    "forecastPeriodStart": fc_start,
                    "forecastPeriodEnd": fc_end,
                    "forecast_90": row["90% FCST"] if "90% FCST" in row else None,
                    "forecast_70": row["70% FCST"] if "70% FCST" in row else (
                        q30_from_25(row["50% FCST"], row["75% FCST"]) if "75% FCST" in row else None),
                    "forecast_50": row["50% FCST"] if "50% FCST" in row else None,
                    "forecast_30": row["30% FCST"] if "30% FCST" in row else (
                        q30_from_25(row["50% FCST"], row["25% FCST"]) if "25% FCST" in row else None),
                    "forecast_10": row["10% FCST"] if "10% FCST" in row else None,
                    "source": "NWRFC_official",
                })

    if rows:
        all_df = pd.DataFrame(rows).sort_values(["site", "issueDate"]).reset_index(drop=True)
        all_df.to_csv(OUT_CSV, index=False)
        print(f"Saved {len(all_df)} rows to {OUT_CSV}")
        return all_df
    print("No forecasts found.")
    return pd.DataFrame()


def interpolate_percentile(x0, y0, x1, y1, x):
    if np.isnan(y0) or np.isnan(y1):
        return np.nan
    return y0 + (y1 - y0) * (x - x0) / (x1 - x0)


def parse_regression():
    """Pre-2011 NWRFC regression-based WSF (separate product, no ESP archive)."""
    df = pd.read_csv(REGR_INPUT_CSV)
    df = df[(df["lid"].isin(SITES)) & (df["sper"] == "APR") & (df["eper"] == "JUL")]
    df["fdate"] = pd.to_datetime(df["fdate"])
    df = df[df["fdate"].dt.month.isin([1, 2, 3, 4])]
    df = df[df["fdate"].dt.day == 1]

    records = []
    for _, row in df.iterrows():
        try:
            f95 = float(row["f95"])
        except Exception:
            f95 = np.nan
        try:
            f50 = float(row["f50"])
        except Exception:
            f50 = np.nan
        try:
            f05 = float(row["f05"])
        except Exception:
            f05 = np.nan

        forecast_90 = interpolate_percentile(95, f95, 50, f50, 90)
        forecast_10 = interpolate_percentile(50, f50, 5, f05, 10)

        records.append({
            "site": row["lid"],
            "publicationDate": row["fdate"].strftime("%Y-%m-%d"),
            "issueDate": row["fdate"].strftime("%Y-%m-%d"),
            "forecastPeriodStart": f"{int(row['fwy'])}-04-01",
            "forecastPeriodEnd": f"{int(row['fwy'])}-07-31",
            "forecast_90": round(forecast_90, 3) if not np.isnan(forecast_90) else np.nan,
            "forecast_50": f50,
            "forecast_10": round(forecast_10, 3) if not np.isnan(forecast_10) else np.nan,
            "source": "NWRFC_official",
        })

    df_out = pd.DataFrame.from_records(records).sort_values(["site", "issueDate"])
    df_out.to_csv(REGR_OUT_CSV, index=False)
    print(f"Saved {len(df_out)} rows to {REGR_OUT_CSV}")
    return df_out


if __name__ == "__main__":
    # download()  # raw files already present in RAW_DIR; uncomment to refresh
    parse_esp()
    # parse_regression()  # requires REGR_INPUT_CSV, not confirmed present -- check before running
