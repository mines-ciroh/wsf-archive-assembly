"""Combine test/train (Rodeo competition) observation labels into one seasonal-flow CSV."""

import os
import pandas as pd

RODEO_DATA = os.environ.get("WSF_RODEO_DATA", "/beegfs/sets/aw-ciroh/common/datasets/wsf_rodeo_data")  # DrivenData WSF Rodeo competition data
ARCHIVE_ROOT = os.environ.get("WSF_ARCHIVE_ROOT", os.path.expanduser("~/wsf_archive_v1.0"))
FILES = [
    f"{ARCHIVE_ROOT}/source_data/obs/cross_validation_labels.csv",
    f"{ARCHIVE_ROOT}/source_data/obs/prior_historical_labels.csv",
]
META_FILE = os.path.join(RODEO_DATA, "competition_data/metadata.csv")
OUT_FILE = f"{ARCHIVE_ROOT}/source_data/obs/all_seasonal_naturalized_flow.csv"


def combine():
    dfs = [pd.read_csv(f) for f in FILES]
    combined = pd.concat(dfs, ignore_index=True)

    meta = pd.read_csv(META_FILE)
    meta["site_id"] = meta["site_id"].astype(str).str.strip().str.lower()
    meta["usgs_id"] = meta["usgs_id"].apply(lambda x: str(int(float(x))).zfill(8) if pd.notnull(x) else "")

    combined["site_id"] = combined["site_id"].astype(str).str.strip().str.lower()
    combined = combined.merge(meta[["site_id", "usgs_id"]], on="site_id", how="left")

    combined = combined.sort_values(["site_id", "year", "volume"])
    combined.to_csv(OUT_FILE, index=False)
    print(f"Combined shape: {combined.shape}")
    return combined


if __name__ == "__main__":
    combine()
