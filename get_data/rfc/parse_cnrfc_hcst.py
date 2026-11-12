"""Parse CNRFC HEFS water supply hindcasts (WY1990-2023) into Apr-Jul volume quantiles by site/init.

Raw input: CNRFC's HEFS hindcast seasonal-volume statistics, shared by CNRFC (Brett Whitin,
Google Drive "vol_stats"; see readme.txt), one CSV per daily issuance:
    $WSF_RAW_RFC_HCST_ROOT/cnrfc_wsf/hcst_vol_stats/<SITE>/<YYYYMMDD>12_<SITE>[F]_hefs_csv_stats.csv
On the issue-date row, the QCSF* columns are the Apr-Jul seasonal volume statistics (KAF):
H9/HH/H5/HG/H1 = 10/25/50/75/90% exceedance (HC/HW/HM = min/max/mean, unused).
These are CNRFC's data and are not redistributed with the archive; only OUT_CSV is.
"""

import os
from datetime import datetime

import numpy as np
import pandas as pd

ARCHIVE_ROOT = os.environ.get("WSF_ARCHIVE_ROOT", os.path.expanduser("~/wsf_archive_v1.0"))
RAW_ROOT = os.environ.get("WSF_RAW_RFC_HCST_ROOT",
                          os.path.expanduser("~/aw-ciroh/common/datasets/rfc_wsf"))
BASE_DIR = f"{RAW_ROOT}/cnrfc_wsf/hcst_vol_stats"
OUT_CSV = f"{ARCHIVE_ROOT}/source_data/rfc/cnrfc_wsf.hcst_1989_2023.csv"

SITES = ["FOLC1", "POHC1", "FRAC1"]
YEARS = range(1989, 2024)
MONTHS = [1, 2, 3, 4]
Z_25_TO_30 = 0.5244005 / 0.6744898  # z(0.70) / z(0.75)


def parse():
    out_rows = []
    for site in SITES:
        for year in YEARS:
            for month in MONTHS:
                issue_date = datetime(year, month, 1, 12)
                fname_opts = [
                    f"{year}{month:02d}0112_{site}F_hefs_csv_stats.csv",
                    f"{year}{month:02d}0112_{site}_hefs_csv_stats.csv",
                ]
                csv_path = None
                for fname in fname_opts:
                    test_path = os.path.join(BASE_DIR, site, fname)
                    if os.path.exists(test_path):
                        csv_path = test_path
                        break
                if not csv_path:
                    continue

                df_raw = pd.read_csv(csv_path, header=None, index_col=0)
                var_codes = df_raw.iloc[1].tolist()  # row 1 holds variable codes, not row 0
                df = df_raw.iloc[2:].copy()
                df.columns = var_codes
                df.index = pd.to_datetime(df.index)

                this_row = df.loc[df.index == issue_date]
                if this_row.empty:
                    continue
                this_row = this_row.iloc[0]

                try:
                    val_90 = round(float(this_row.get("QCSFH1", np.nan)), 3)
                    val_75 = round(float(this_row.get("QCSFHG", np.nan)), 3)
                    val_50 = round(float(this_row.get("QCSFH5", np.nan)), 3)
                    val_25 = round(float(this_row.get("QCSFHH", np.nan)), 3)
                    val_10 = round(float(this_row.get("QCSFH9", np.nan)), 3)
                except Exception:
                    continue

                vals = np.array([val_10, val_25, val_50, val_75, val_90])
                if np.any((vals == -999) | np.isnan(vals)):
                    continue

                # 30%/70% in standard-normal quantile space between the median and 25%/75%
                val_30 = round(val_50 + Z_25_TO_30 * (val_25 - val_50), 3)
                val_70 = round(val_50 + Z_25_TO_30 * (val_75 - val_50), 3)

                out_rows.append({
                    "site": site,
                    "publicationDate": issue_date.strftime("%Y-%m-%d"),
                    "issueDate": issue_date.strftime("%Y-%m-%d"),
                    "forecastPeriodStart": f"{year}-04-01",
                    "forecastPeriodEnd": f"{year}-07-31",
                    "forecast_90": val_90, "forecast_70": val_70, "forecast_50": val_50,
                    "forecast_30": val_30, "forecast_10": val_10,
                    "source": "CNRFC_hcst",
                })

    out_df = pd.DataFrame(out_rows).sort_values(["site", "issueDate"])
    out_df.to_csv(OUT_CSV, index=False)
    print("Done! Output shape:", out_df.shape)
    return out_df


if __name__ == "__main__":
    parse()
