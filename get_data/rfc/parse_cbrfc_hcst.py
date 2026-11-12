"""Parse CBRFC ESP reforecasts (hindcasts) into Apr-Jul volume quantiles by site/init.

Raw input: first-of-month unregulated reforecasts provided directly by CBRFC (John Lhotak,
Nov 1980 - Sep 2020; GBRW4/MBLC2 through Sep 2021), one tarball per site:
    $WSF_RAW_RFC_HCST_ROOT/cbrfc_wsf/<SITE>.tar.gz
      -> <YYYY>/<MM>/01/UnReg/<SITE>[L]_{F,H}.SIM24.SQME.24.CS.csv.gz   (daily traces, CFS-days)
These are CBRFC's data and are not redistributed with the archive; only the derived
Apr-Jul volume quantiles (OUT_CSV) are. Files are read straight from the tarballs.
"""

import os
import re
import tarfile
import gzip
from io import StringIO
from datetime import datetime

import numpy as np
import pandas as pd

ARCHIVE_ROOT = os.environ.get("WSF_ARCHIVE_ROOT", os.path.expanduser("~/wsf_archive_v1.0"))
RAW_ROOT = os.environ.get("WSF_RAW_RFC_HCST_ROOT",
                          os.path.expanduser("~/aw-ciroh/common/datasets/rfc_wsf"))
BASE_DIR = f"{RAW_ROOT}/cbrfc_wsf"
OUT_CSV = f"{ARCHIVE_ROOT}/source_data/rfc/cbrfc_wsf.hcst_1981_2021.csv"

SITES = ["RURC2", "GBRW4", "DRGC2", "DIRC2", "MBLC2", "TPIC2", "VIRU1", "OAWU1"]  # ALEC2 excluded: not a WSF Rodeo site
YEARS = range(1981, 2022)  # every WY whose Jan-Apr inits exist (WY2020 all sites, WY2021 GBRW4/MBLC2)
MONTHS = [1, 2, 3, 4]
CFSD_TO_AF = 1.98347  # 1 CFS-day = 1.98347 acre-feet
MEMBER_PATH = re.compile(r"^(\d{4})/(\d{2})/01/UnReg/.+\.SQME\.24\.CS\.csv\.gz$")


def parse():
    out_rows = []
    for site in SITES:
        print(f"Processing site: {site}")
        tar = tarfile.open(f"{BASE_DIR}/{site}.tar.gz")
        members = {}
        for m in tar.getmembers():
            mm = MEMBER_PATH.match(m.name)
            if mm:
                members[(int(mm.group(1)), int(mm.group(2)))] = m
        for year in YEARS:
            for month in MONTHS:
                if (year, month) not in members:
                    continue
                with gzip.open(tar.extractfile(members[(year, month)]), "rt") as f:
                    lines = [line for line in f if not line.startswith("#")]
                df = pd.read_csv(StringIO("".join(lines)), index_col=0)

                period_start, period_end = f"{year}-04-01", f"{year}-07-31"
                period_idx = (df.index >= period_start) & (df.index <= period_end)
                df_period = df.loc[period_idx].apply(pd.to_numeric, errors="coerce")

                member_sums = df_period.sum(axis=0)
                member_kaf = (member_sums * CFSD_TO_AF / 1000.0).dropna()
                if len(member_kaf) < 5:
                    continue

                issue_date = datetime(year, month, 1, 12)
                out_rows.append({
                    "site": site,
                    "publicationDate": issue_date.strftime("%Y-%m-%d"),
                    "issueDate": issue_date.strftime("%Y-%m-%d"),
                    "forecastPeriodStart": period_start,
                    "forecastPeriodEnd": period_end,
                    "forecast_90": round(np.percentile(member_kaf, 90), 3),
                    "forecast_70": round(np.percentile(member_kaf, 70), 3),
                    "forecast_50": round(np.percentile(member_kaf, 50), 3),
                    "forecast_30": round(np.percentile(member_kaf, 30), 3),
                    "forecast_10": round(np.percentile(member_kaf, 10), 3),
                    "source": "CBRFC_hcst",
                })

    out_df = pd.DataFrame(out_rows).sort_values(["site", "issueDate"])
    out_df.to_csv(OUT_CSV, index=False)
    print("Done! Output shape:", out_df.shape)
    return out_df


if __name__ == "__main__":
    parse()
