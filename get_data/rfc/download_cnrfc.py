"""Download and parse CNRFC official ESP forecasts (FRAC1, POHC1, FOLC1).

Paths point at the actual flat source_data/rfc/ layout on disk (the archive
was reorganized at some point; the old raw_data/working_data subfolder
convention no longer exists).
"""

import os
import re
import glob
from datetime import datetime

import numpy as np
import pandas as pd

ARCHIVE_ROOT = os.environ.get("WSF_ARCHIVE_ROOT", os.path.expanduser("~/wsf_archive_v1.0"))
RAW_DIR = f"{ARCHIVE_ROOT}/source_data/rfc/cnrfc_esp"
OUT_CSV = f"{ARCHIVE_ROOT}/source_data/rfc/cnrfc_wsf.csv"
SITES = ["FRAC1", "POHC1", "FOLC1"]

# -------- 1. DOWNLOAD (raw files already present on disk; re-run only to refresh) --------
def download():
    import requests
    from time import sleep

    os.makedirs(RAW_DIR, exist_ok=True)
    years = range(2011, 2026)
    base_url = "https://www.cnrfc.noaa.gov/ensembleProductTabular.php?id={site}&prodID=7&year={year}"
    for site in SITES:
        for year in years:
            url = base_url.format(site=site, year=year)
            outfn = os.path.join(RAW_DIR, f"{site}_{year}.txt")
            print(f"Downloading {url} -> {outfn}")
            try:
                resp = requests.get(url, timeout=15)
                resp.raise_for_status()
                with open(outfn, "w") as f:
                    f.write(resp.text)
            except Exception as e:
                print(f"Failed to download {url}: {e}")
            sleep(1)


# -------- 2. PARSE --------
# Forecast rows are matched by regex (date at line start). Quantile columns are mapped
# from each file's own header: through WY2022 the layout is 90/75/50/25/10% exceedance
# (+ NWS forecast, obs), from WY2023 it is Min/90/75/50/25/10/Max. Only the 90/50/10%
# (+ 75/25%) exceedance columns are used; the archive's 30%/70% levels are interpolated
# from 25%/75% (see q30_from_25).
KEEP = {"90%": "forecast_90", "75%": "forecast_75", "50%": "forecast_50",
        "25%": "forecast_25", "10%": "forecast_10"}
# 30%/70% exceedance from 25%/75%, interpolated in standard-normal quantile space between
# the median and the 25%/75% value (z(0.70)/z(0.75) = 0.7777); same approach as the other
# derived quantiles in the archive (Pecos, NWRFC legacy tails).
Z_25_TO_30 = 0.5244005 / 0.6744898


def q30_from_25(f50, f25):
    return f50 + Z_25_TO_30 * (f25 - f50)



def extract_year_from_filename(fname):
    m = re.search(r"_(\d{4})\.txt$", fname)
    return int(m.group(1)) if m else None


def header_labels(lines):
    """Column labels (e.g. ['Min','90%',...,'Max']) from the first header line with '50%'."""
    for line in lines:
        if line.startswith("#") and "50%" in line:
            return line.lstrip("#").split()
    raise ValueError("no quantile header line found")


def parse():
    all_rows = []
    for site in SITES:
        files = sorted(glob.glob(os.path.join(RAW_DIR, f"{site}_*.txt")))
        for file in files:
            with open(file, "r") as f:
                lines = f.readlines()

            year = extract_year_from_filename(file)
            if not year:
                continue
            forecastPeriodStart = f"{year}-04-01"
            forecastPeriodEnd = f"{year}-07-31"
            labels = header_labels(lines)
            col = {KEEP[lab]: i + 1 for i, lab in enumerate(labels) if lab in KEEP}
            assert len(col) == 5, f"{file}: header {labels}"

            forecast_lines = []
            for line in lines:
                if re.match(r"^\s*\d{2}/\d{2}/\d{4}", line):
                    row = line.strip().split()
                    try:
                        date = datetime.strptime(row[0], "%m/%d/%Y").date()
                    except Exception:
                        continue

                    def val(i):
                        if len(row) > i and not row[i].startswith("<"):
                            return float(row[i])
                        return np.nan

                    fl = {"date": date, **{k: val(i) for k, i in col.items()}}
                    if not np.isnan(fl["forecast_50"]):  # skip "Missing" days
                        forecast_lines.append(fl)

            # Jan-Apr 1st: use the exact date, or the latest available up to 7 days prior
            for month in range(1, 5):
                wanted = datetime(year, month, 1).date()
                candidates = [fl for fl in forecast_lines if 0 <= (wanted - fl["date"]).days <= 7]
                best = max(candidates, key=lambda fl: fl["date"]) if candidates else {}
                all_rows.append({
                    "site": site,
                    # concat_wsf.all_methods.py keys on publicationDate == the 1st
                    "publicationDate": wanted,
                    "issueDate": wanted,
                    "forecastPeriodStart": forecastPeriodStart,
                    "forecastPeriodEnd": forecastPeriodEnd,
                    "forecast_90": best.get("forecast_90", np.nan),
                    "forecast_70": q30_from_25(best.get("forecast_50", np.nan), best.get("forecast_75", np.nan)),
                    "forecast_50": best.get("forecast_50", np.nan),
                    "forecast_30": q30_from_25(best.get("forecast_50", np.nan), best.get("forecast_25", np.nan)),
                    "forecast_10": best.get("forecast_10", np.nan),
                    "source": "CNRFC_official",
                    "bulletin_date": best.get("date", np.nan),
                })

    df = pd.DataFrame(all_rows)
    df.to_csv(OUT_CSV, index=False)
    print(f"Saved {len(df)} rows to {OUT_CSV}")
    return df


if __name__ == "__main__":
    # download()  # raw files already present in RAW_DIR; uncomment to refresh from CNRFC
    df = parse()
    print(df.dropna(subset=["forecast_50"]).groupby("site")["issueDate"].count())
