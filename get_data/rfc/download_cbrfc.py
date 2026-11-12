"""Download and parse CBRFC official ESP forecasts."""

import os
import re
import glob
from datetime import datetime, timedelta

import pandas as pd

ARCHIVE_ROOT = os.environ.get("WSF_ARCHIVE_ROOT", os.path.expanduser("~/wsf_archive_v1.0"))
RAW_DIR = f"{ARCHIVE_ROOT}/source_data/rfc/cbrfc_esp"
OUT_CSV = f"{ARCHIVE_ROOT}/source_data/rfc/cbrfc_wsf.csv"
PUB_MONTHS = [1, 2, 3, 4]

SITE_RFC = {
    "PDAC2": "ARBRFC", "DRGC2": "CBRFC", "MBLC2": "CBRFC", "TPIC2": "CBRFC", "DIRC2": "CBRFC",
    "RURC2": "CBRFC", "GBRW4": "CBRFC", "OAWU1": "CBRFC", "VIRU1": "CBRFC",
    "TOSM8N": "MBRFC", "SBDW4N": "MBRFC", "PCON5": "WGRFC",
}


def download():
    import requests

    os.makedirs(RAW_DIR, exist_ok=True)
    years = range(2000, 2025)
    for site in SITE_RFC:
        for year in years:
            url = f"https://www.cbrfc.noaa.gov/wsup/graph/esptxt.py?id={site}&year={year}&qpf=0&db="
            outfn = os.path.join(RAW_DIR, f"{site}_{year}.txt")
            print(f"Downloading {site} {year} ... ", end="")
            try:
                r = requests.get(url, timeout=10)
                r.raise_for_status()
                with open(outfn, "w") as f:
                    f.write(r.text)
                print("done.")
            except Exception as e:
                print(f"FAILED: {e}")


def extract_period(txt):
    m = re.search(r"(\w+\-\w+),", txt)
    if m:
        return m.group(1)
    m = re.search(r"(\w+\-\w+)\s", txt)
    if m:
        return m.group(1)
    return "Unknown"


def extract_esp_table(txt):
    lines = txt.splitlines()
    table_start = None
    for i, line in enumerate(lines):
        if "ESP Forecasts" in line:
            table_start = i + 1
            break
    if table_start is None:
        return None
    table_lines = []
    for line in lines[table_start:]:
        if not line.strip():
            break
        table_lines.append(line)
    return table_lines


def parse_esp_df(table_lines):
    # The table is fixed-width with right-aligned values, and rows often leave
    # the ESP columns (max/p10/.../min) blank and fill only the official
    # coordinated columns (crx/c30/cmp/c70/crn). Splitting on whitespace shifted
    # those official values left into the ESP columns, so every such row parsed
    # as NaN official -- all of 2009-2021 at most CBRFC sites. Assign each value
    # to the header column whose right edge is nearest the value's right edge.
    header_line = table_lines[0].replace("\xa0", " ")
    col_ends = [(m.group(), m.end()) for m in re.finditer(r"\S+", header_line)]
    if len(col_ends) > 1 and col_ends[0][0] == "Run" and col_ends[1][0] == "Date":
        col_ends = [("Run Date", col_ends[1][1])] + col_ends[2:]
    columns = [c for c, _ in col_ends]
    value_cols = col_ends[1:]
    data = []
    for line in table_lines[1:]:
        line = line.replace("\xa0", " ")
        if not line.strip() or set(line.strip()) == set("-"):
            continue
        m_date = re.match(r"\s*(\S+)", line)
        row = {c: None for c in columns}
        row["Run Date"] = m_date.group(1)
        for m in re.finditer(r"\S+", line[m_date.end():]):
            end = m.end() + m_date.end()
            col = min(value_cols, key=lambda ce: abs(ce[1] - end))[0]
            row[col] = m.group()
        # WY2015 files print the older 3-value official row (max / most probable
        # / min) under the newer 5-column header, so the values land in the first
        # three official slots (crx, c30, cmp). Their middle value matches NRCS's
        # coordinated median, confirming the layout. Re-seat them as crx/cmp/crn.
        if ("c30" in row and "c70" in row and all(row[c] is not None for c in ("crx", "c30", "cmp"))
                and row["c70"] is None and row["crn"] is None):
            row["cmp"], row["crn"], row["c30"] = row["c30"], row["cmp"], None
        data.append(row)
    df = pd.DataFrame(data, columns=columns)
    if "Run Date" in df.columns:
        df["Run Date"] = pd.to_datetime(df["Run Date"], errors="coerce")
    for col in ["crx", "c30", "cmp", "c70", "crn"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def find_closest_forecast(df, year, month):
    pub_date = datetime(year, month, 1)
    week_ago = pub_date - timedelta(days=7)
    df_window = df[(df["Run Date"] <= pub_date) & (df["Run Date"] >= week_ago)]
    if df_window.empty:
        return None
    idx = (pub_date - df_window["Run Date"]).abs().idxmin()
    closest = df_window.loc[idx].copy()
    closest["publication_date"] = pub_date
    return closest


def extract_start_end_month(period):
    try:
        sm, em = period.split("-")
        return sm[:3].upper(), em[:3].upper()
    except Exception:
        return "", ""


MONTH_STR_TO_NUM = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}


def get_forecast_period_dates(year, start_month_str, end_month_str):
    import calendar

    if start_month_str not in MONTH_STR_TO_NUM or end_month_str not in MONTH_STR_TO_NUM:
        return "", ""
    start_month = MONTH_STR_TO_NUM[start_month_str]
    end_month = MONTH_STR_TO_NUM[end_month_str]
    start_date = f"{year}-{start_month:02d}-01"
    last_day = calendar.monthrange(year, end_month)[1]
    end_date = f"{year}-{end_month:02d}-{last_day:02d}"
    return start_date, end_date


def parse():
    rows = []
    for file in glob.glob(os.path.join(RAW_DIR, "*.txt")):
        site_year = os.path.basename(file).split(".")[0]
        parts = site_year.split("_")
        if len(parts) != 2:
            continue
        site, year = parts[0], int(parts[1])
        with open(file, "r") as f:
            txt = f.read()
        period = extract_period(txt)
        table_lines = extract_esp_table(txt)
        if not table_lines:
            continue
        df = parse_esp_df(table_lines)
        start_month, end_month = extract_start_end_month(period)
        forecast_start_date, forecast_end_date = get_forecast_period_dates(year, start_month, end_month)
        for m in PUB_MONTHS:
            row = find_closest_forecast(df, year, m)
            if row is not None:
                rows.append({
                    "site": site,
                    "publicationDate": row["publication_date"].strftime("%Y-%m-%d"),
                    "issueDate": row["Run Date"].strftime("%Y-%m-%d") if pd.notnull(row["Run Date"]) else "",
                    "forecastPeriodStart": forecast_start_date,
                    "forecastPeriodEnd": forecast_end_date,
                    "forecast_90": row["crx"] if "crx" in row else None,
                    "forecast_70": row["c30"] if "c30" in row else None,
                    "forecast_50": row["cmp"] if "cmp" in row else None,
                    "forecast_30": row["c70"] if "c70" in row else None,
                    "forecast_10": row["crn"] if "crn" in row else None,
                    "source": "CBRFC_official",
                })

    df_all = pd.DataFrame(rows).sort_values(["site", "issueDate"]).reset_index(drop=True)
    df_all.to_csv(OUT_CSV, index=False)
    print(f"Saved {len(df_all)} rows to {OUT_CSV}")
    return df_all


if __name__ == "__main__":
    # download()  # raw files already present in RAW_DIR; uncomment to refresh
    parse()
