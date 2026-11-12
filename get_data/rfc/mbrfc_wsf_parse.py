"""Parse MBRFC ESPKRF bulletins for Boysen Reservoir (SBDW4N) and Toston (TOSM8N)."""

import re
import os
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from tqdm import tqdm

ARCHIVE_ROOT = os.environ.get("WSF_ARCHIVE_ROOT", os.path.expanduser("~/wsf_archive_v1.0"))
RAW_DIR = f"{ARCHIVE_ROOT}/source_data/rfc/mbrfc_esp"
OUT_CSV = f"{ARCHIVE_ROOT}/source_data/rfc/mbrfc_wsf.csv"

LOCATIONS = {
    "SBDW4N": ["Boysen Resvr Inflow", "Boysen Reservoir Inflow"],
    "TOSM8N": ["Missouri R at Toston"],
}


def get_pubdate_from_fname(fname):
    m = re.match(r"ESPKRF\.(\d{4})\.(\d{4})", fname)
    if not m:
        m = re.match(r"ESPKRF\.(\d{4})\.(\d{2,4})", fname)
    if not m:
        m = re.match(r"ESPKRF\.(\d{4})\.(\d{4})", fname)
    if m:
        mmdd, yyyy = m.group(1), m.group(2)
        if len(mmdd) == 4:
            month, day, year = int(mmdd[:2]), int(mmdd[2:]), int(yyyy)
            return f"{year}-{month:02d}-{day:02d}"
    return None


def get_prior_first(pub_date):
    d = datetime.strptime(pub_date, "%Y-%m-%d")
    first = d.replace(day=1)
    prior_month = first - timedelta(days=1)
    return f"{prior_month.year}-{prior_month.month:02d}-01"


def parse():
    files = [f for f in os.listdir(RAW_DIR) if f.startswith("ESPKRF.")]
    records = []

    for fname in tqdm(files):
        with open(os.path.join(RAW_DIR, fname)) as f:
            lines = [line.rstrip("\n") for line in f]

        pub_date = None
        for line in lines:
            m = re.search(r"([A-Za-z]+)\s+(\d{1,2})[,]?\s+(\d{4})", line)
            if m and "cst" in line.lower():
                try:
                    month = datetime.strptime(m.group(1), "%B").month
                    day, year = int(m.group(2)), int(m.group(3))
                    pub_date = f"{year}-{month:02d}-{day:02d}"
                except Exception:
                    pass

        if pub_date is None:
            pub_date = get_pubdate_from_fname(fname)
        if pub_date is None:
            print(f"Warning: could not get publication date for file {fname}")
            continue

        issue_date = get_prior_first(pub_date)

        for i, line in enumerate(lines):
            for code, names in LOCATIONS.items():
                if code in line:
                    for j in range(i - 1, max(i - 7, -1), -1):
                        if re.search(r"Apr[- ]Sep", lines[j]):
                            tokens = lines[j].split()
                            try:
                                idx = [k for k, x in enumerate(tokens) if re.match(r"Apr[- ]Sep", x)][0]
                                val_50 = float(tokens[idx + 1])
                                val_10 = float(tokens[idx + 3])
                                val_90 = float(tokens[idx + 4])
                            except Exception:
                                print(f"Could not parse line in file {fname}: {lines[j]}")
                                continue
                            records.append({
                                "site": code,
                                "publicationDate": pub_date,
                                "issueDate": issue_date,
                                "forecastPeriodStart": f"{issue_date[:4]}-04-01",
                                "forecastPeriodEnd": f"{issue_date[:4]}-09-30",
                                "forecast_90": val_90,
                                "forecast_70": np.nan,
                                "forecast_50": val_50,
                                "forecast_30": np.nan,
                                "forecast_10": val_10,
                                "source": "MBRFC_official",
                            })
                            break

    print(f"Records found: {len(records)}")
    if not records:
        print("No records extracted.")
        return pd.DataFrame()

    cols = ["site", "publicationDate", "issueDate", "forecastPeriodStart", "forecastPeriodEnd",
            "forecast_90", "forecast_70", "forecast_50", "forecast_30", "forecast_10", "source"]
    df_out = pd.DataFrame.from_records(records)[cols]
    df_out.to_csv(OUT_CSV, index=False)
    print(f"Saved {len(df_out)} rows to {OUT_CSV}")
    return df_out


if __name__ == "__main__":
    parse()
