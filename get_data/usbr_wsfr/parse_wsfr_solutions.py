"""Parse the top-5 WSF Rodeo winning solutions' cross-validated predictions into one CSV."""

import glob
import os

import numpy as np
import pandas as pd

ARCHIVE_ROOT = os.environ.get("WSF_ARCHIVE_ROOT", os.path.expanduser("~/wsf_archive_v1.0"))
LOOKUP_FILE = os.path.join(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."), "metadata", "WSF_Rodeo_ForecastLocations.csv")
SOLUTIONS_DIR = f"{ARCHIVE_ROOT}/source_data/rodeo_winners/water-supply-winners-cv-predictions"
OUT_FILE = f"{ARCHIVE_ROOT}/source_data/rodeo_winners/wsf_rodeo_solutions.amjj_wsf.csv"


def parse():
    solution_files = glob.glob(os.path.join(SOLUTIONS_DIR, "*.csv"))

    site_lookup = pd.read_csv(LOOKUP_FILE)
    site_lookup["site_id"] = site_lookup["site_id"].astype(str).str.strip().str.lower()
    # NaN-safe zero-pad: plain .astype(str).str.zfill(8) mis-pads every row (not just
    # NaN ones) if any USGS ID is missing, since NaN promotes the whole column to
    # float64 on read ("09050700" -> 9050700.0 -> zfill(8) is then a no-op). Currently
    # harmless (USGS ID has no NaNs in WSF_Rodeo_ForecastLocations.csv today) but this
    # matches the same bug class found and fixed elsewhere in the RFC chain.
    site_lookup["usgs_id"] = site_lookup["USGS ID"].apply(lambda x: str(int(x)).zfill(8) if pd.notnull(x) else "")

    all_dfs = []
    for sol_file in solution_files:
        df = pd.read_csv(sol_file)
        df["site_id"] = df["site_id"].astype(str).str.strip().str.lower()
        df["source"] = os.path.splitext(os.path.basename(sol_file))[0]
        all_dfs.append(df)

    combined = pd.concat(all_dfs, ignore_index=True)
    merged = combined.merge(site_lookup[["site_id", "usgs_id"]], on="site_id", how="left")

    merged["issue_date"] = pd.to_datetime(merged["issue_date"])
    keep_months = [1, 2, 3, 4]
    merged = merged[merged["issue_date"].dt.day == 1]
    merged = merged[merged["issue_date"].dt.month.isin(keep_months)]

    merged["issue_date"] = merged["issue_date"].dt.strftime("%Y-%m-%d")
    merged["forecast_90"] = merged["volume_90"].round(3)
    merged["forecast_70"] = np.nan  # not available
    merged["forecast_50"] = merged["volume_50"].round(3)
    merged["forecast_30"] = np.nan  # not available
    merged["forecast_10"] = merged["volume_10"].round(3)

    out_cols = ["site_id", "issue_date", "forecast_90", "forecast_70", "forecast_50",
                "forecast_30", "forecast_10", "source", "usgs_id"]
    output = merged[out_cols].rename(columns={"site_id": "site"})
    output = output.sort_values(["site", "issue_date", "source"])

    output.to_csv(OUT_FILE, index=False)
    print(f"Saved! Shape: {output.shape}")
    return output


if __name__ == "__main__":
    parse()
