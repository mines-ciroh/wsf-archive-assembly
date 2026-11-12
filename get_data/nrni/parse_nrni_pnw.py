"""Extract per-site NRNI (no regulation, no irrigation) daily flow series from the
PNW unimpaired flows workbook export and write one CSV per site to
source_data/obs/processed_nrni_csvs/, matching the existing {site_code}.csv format.

Source: PNW_unimpaired_Flows_1929-2018_07-2021.csv (multi-row header: name/code/
type/units rows, data starts at row 8). Column selection is by site name (row 0);
only FLOW-NRNI-type columns should be used for sites requiring the NRNI series.

Validated against the prior 1950-2008 HGH5N.csv (built from a shorter, older NRNI
extract): 21,458/21,458 overlapping days match exactly (0.0 abs diff).
"""

import os
import csv

import pandas as pd

SOURCE_CSV = os.environ.get("WSF_NRNI_CSV", "/beegfs/sets/aw-ciroh/common/stn_obs/non_usgs_flow/nrni/PNW_unimpaired_Flows_1929-2018_07-2021.csv")
ARCHIVE_ROOT = os.environ.get("WSF_ARCHIVE_ROOT", os.path.expanduser("~/wsf_archive_v1.0"))
OUT_DIR = f"{ARCHIVE_ROOT}/source_data/obs/processed_nrni_csvs"

DATA_START_ROW = 7  # rows 0-6 are header (name/code/type/E/F/units/type)

# Site name (as it appears in the header row) -> output filename
SITES = {
    "HUNGRY HORSE": "HGH5N",
}


def parse_site(rows, name_row, col_idx):
    records = []
    for row in rows[DATA_START_ROW:]:
        if len(row) <= col_idx:
            continue
        date_str, val = row[1], row[col_idx]
        if not date_str or val in ("", None):
            continue
        try:
            dt = pd.to_datetime(date_str, format="%d%b%Y")
            v = float(val)
        except ValueError:
            continue
        records.append((dt, v))
    return pd.DataFrame(records, columns=["datetime", "streamflow_cfs"]).set_index("datetime").sort_index()


def main():
    with open(SOURCE_CSV, newline="") as f:
        rows = list(csv.reader(f))

    name_row, code_row, type_row = rows[0], rows[1], rows[2]

    for site_name, out_name in SITES.items():
        matches = [i for i, v in enumerate(name_row) if v.strip().upper() == site_name]
        if not matches:
            print(f"Site not found: {site_name}")
            continue
        col_idx = matches[0]
        if type_row[col_idx] != "FLOW-NRNI":
            print(f"WARNING: {site_name} column type is {type_row[col_idx]!r}, not FLOW-NRNI")

        df = parse_site(rows, name_row, col_idx)
        out_path = f"{OUT_DIR}/{out_name}.csv"
        df.to_csv(out_path)
        print(f"{site_name} ({code_row[col_idx]}) -> {out_path}: {df.index.min().date()} to {df.index.max().date()}, n={len(df)}")


if __name__ == "__main__":
    main()
