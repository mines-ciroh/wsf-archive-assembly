"""Concatenate all RFC WSF sources into one validated CSV (all_rfc_wsf.csv)."""

import os
from pathlib import Path

import pandas as pd

RODEO_DATA = os.environ.get("WSF_RODEO_DATA", "/beegfs/sets/aw-ciroh/common/datasets/wsf_rodeo_data")  # DrivenData WSF Rodeo competition data
ARCHIVE_ROOT = os.environ.get("WSF_ARCHIVE_ROOT", os.path.expanduser("~/wsf_archive_v1.0"))
LOOKUP_FILE = os.path.join(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."), "metadata", "WSF_Rodeo_ForecastLocations.csv")
METADATA_FILE = os.path.join(RODEO_DATA, "metadata.csv")
OUT_CSV = f"{ARCHIVE_ROOT}/source_data/rfc/all_rfc_wsf.csv"

CSV_FILES = [
    f"{ARCHIVE_ROOT}/source_data/rfc/mbrfc_wsf.csv",
    f"{ARCHIVE_ROOT}/source_data/rfc/cbrfc_wsf.csv",
    f"{ARCHIVE_ROOT}/source_data/rfc/cbrfc_wsf.outlook_pdf_2004_2010.csv",
    f"{ARCHIVE_ROOT}/source_data/rfc/nwrfc_wsf.csv",
    f"{ARCHIVE_ROOT}/source_data/rfc/nwrfc_wsf.wsfcsttext_2005_2013.csv",
    f"{ARCHIVE_ROOT}/source_data/rfc/nwrfc_wsf.esp_agg.csv",
    f"{ARCHIVE_ROOT}/source_data/rfc/cnrfc_wsf.csv",
    f"{ARCHIVE_ROOT}/source_data/rfc/cnrfc_wsf.iem_2004_2012.csv",
    f"{ARCHIVE_ROOT}/source_data/rfc/cnrfc_wsf.hcst_1989_2023.csv",
    f"{ARCHIVE_ROOT}/source_data/rfc/cbrfc_wsf.hcst_1981_2021.csv",
    f"{ARCHIVE_ROOT}/source_data/rfc/wgrfc_wsf_pcon5.csv",
]


def concat():
    site_lookup = pd.read_csv(LOOKUP_FILE)
    # Manual fix: WSF_Rodeo_ForecastLocations.csv has no "RFC Site ID" for Colville R
    # at Kettle Falls (USGS 12409000) even though NWRFC forecasts it as KTFW1 -- without
    # this, its rfc_official rows silently fail to match and the site loses all RFC data.
    site_lookup.loc[site_lookup["USGS ID"] == 12409000, "RFC Site ID"] = "KTFW1"
    site_lookup["RFC Site ID"] = site_lookup["RFC Site ID"].astype(str).str.strip().str.upper()
    site_lookup = site_lookup[["RFC Site ID", "USGS ID", "NRCS Site ID (Triplet)"]]

    metadata = pd.read_csv(METADATA_FILE)
    metadata["site_id"] = metadata["site_id"].astype(str).str.strip()
    metadata["season_start_month"] = metadata["season_start_month"].astype(int)
    metadata["season_end_month"] = metadata["season_end_month"].astype(int)

    rfc_to_season = pd.merge(
        site_lookup,
        metadata[["site_id", "season_start_month", "season_end_month", "rfc_id"]],
        left_on="RFC Site ID", right_on="rfc_id", how="left",
    )

    dfs = []
    for f in CSV_FILES:
        print(f"Reading: {f}")
        df = pd.read_csv(f)
        df["site"] = df["site"].astype(str).str.strip().str.upper()
        df["_src_file"] = Path(f).name
        dfs.append(df)

    concat_df = pd.concat(dfs, ignore_index=True)
    print(f"Combined DataFrame has {len(concat_df)} rows.")

    # Some site-dates are covered by two products under the same *_official source:
    #   NWRFC: the coordinated NWS/NRCS/BC Hydro text bulletin (wsFcstText.cgi,
    #          WY2005-2013) and NWRFC's ESP-based forecast (nwrfc_wsf.csv / esp_agg).
    #   CNRFC: the published Water Supply Outlook bulletin (ESPRSA via IEM, WY2004-2012)
    #          and the daily tabular ESP product (cnrfc_wsf.csv, 2011+), whose quantiles
    #          are unadjusted ESP (its separate "NWS Forecast" column equals the bulletin).
    # "RFC official" = the forecast the RFC published (decision 2026-09-28): published
    # bulletins first, the RFC's ESP product only where no bulletin survives.
    # Left undeduplicated, both reach concat_wsf.all_methods.py, which writes only the
    # quantiles present in each row, splicing one "forecast" out of two products.
    # Lower _pref wins.
    #
    # nwrfc_wsf.regr.csv (a 4-date "regression" extract with no surviving source) is
    # retired: its OWYO3 rows were the "OWYHEE RES OUTFLOW" line (regulated release,
    # 3-32% of observed natural volume), and it carried Apr-Jul rows for HHWM8, LYDM8
    # and pre-2012 STHW1 that the coordinated bulletin never published. Its HEII1 rows
    # are superseded by the full bulletin backfill (identical medians where they overlap).
    _pref = {
        "nwrfc_wsf.wsfcsttext_2005_2013.csv": 0, "nwrfc_wsf.csv": 1, "nwrfc_wsf.esp_agg.csv": 2,
        "cnrfc_wsf.iem_2004_2012.csv": 0, "cnrfc_wsf.csv": 1,
        # CBRFC: esptxt's coordinated columns and the Water Supply Outlook (PDF/Wayback) are the
        # same published product (24/24 identical where both exist, WY2009-2010)
        "cbrfc_wsf.csv": 0, "cbrfc_wsf.outlook_pdf_2004_2010.csv": 1,
    }
    concat_df["_pref"] = concat_df["_src_file"].map(_pref).fillna(0)
    # rows with no forecast values (e.g. CNRFC "Missing" days) must not shadow real ones
    concat_df = concat_df[concat_df["forecast_50"].notna()]
    before = len(concat_df)
    concat_df = (
        concat_df.sort_values("_pref", kind="stable")
        .drop_duplicates(["site", "publicationDate", "source"], keep="first")
        .sort_index()
    )
    dropped = before - len(concat_df)
    if dropped:
        print(f"Deduplicated {dropped} duplicate (site, publicationDate, source) rows "
              "by product preference.")
    concat_df = concat_df.drop(columns=["_pref", "_src_file"])

    # Pecos (PCON5) is a WGRFC forecast point that CBRFC also hosts (2019+). Both reach
    # concat_wsf.all_methods.py as rfc_official, where the row written last would win.
    # Prefer the responsible RFC's own bulletin; keep CBRFC-hosted rows only for dates
    # WGRFC doesn't cover. (WY2019-2020 they agree; WY2021-2023 CBRFC-hosted values
    # equal NRCS's while WGRFC's differ.)
    wg_dates = set(concat_df.loc[(concat_df["site"] == "PCON5")
                                 & (concat_df["source"] == "WGRFC_official"), "publicationDate"])
    shadowed = ((concat_df["site"] == "PCON5") & (concat_df["source"] == "CBRFC_official")
                & concat_df["publicationDate"].isin(wg_dates))
    if shadowed.any():
        print(f"Dropping {shadowed.sum()} CBRFC-hosted PCON5 rows superseded by WGRFC_official.")
        concat_df = concat_df[~shadowed]

    concat_df["site_normalized"] = concat_df["site"].str.rstrip("N")
    rfc_to_season["RFC Site ID Normalized"] = rfc_to_season["RFC Site ID"].str.rstrip("N")

    concat_df = pd.merge(
        concat_df,
        rfc_to_season[["RFC Site ID Normalized", "season_start_month", "season_end_month"]],
        how="left", left_on="site_normalized", right_on="RFC Site ID Normalized",
    )

    concat_df["forecastPeriodStart"] = pd.to_datetime(concat_df["forecastPeriodStart"])
    concat_df["forecastPeriodEnd"] = pd.to_datetime(concat_df["forecastPeriodEnd"])
    concat_df["forecast_start_month"] = concat_df["forecastPeriodStart"].dt.month
    concat_df["forecast_end_month"] = concat_df["forecastPeriodEnd"].dt.month

    has_season_info = concat_df["season_start_month"].notna() & concat_df["season_end_month"].notna()
    valid_mask = (
        ~has_season_info
        | ((concat_df["forecast_start_month"] == concat_df["season_start_month"])
           & (concat_df["forecast_end_month"] == concat_df["season_end_month"]))
    )

    invalid_count = (~valid_mask).sum()
    total_count = len(concat_df)
    if invalid_count > 0:
        print(f"\nWARNING: Found {invalid_count} forecasts with mismatched periods (out of {total_count} total)")
        invalid_df = concat_df[~valid_mask].copy()
        mismatch_summary = invalid_df.groupby("site").agg({
            "forecastPeriodStart": "first", "forecastPeriodEnd": "first",
            "season_start_month": "first", "season_end_month": "first", "site": "count",
        }).rename(columns={"site": "mismatch_count"})
        for site, row in mismatch_summary.iterrows():
            print(f"  {site}: {int(row['mismatch_count'])} forecasts "
                  f"(expected month {row['season_start_month']}-{row['season_end_month']}, "
                  f"found {row['forecastPeriodStart']} to {row['forecastPeriodEnd']})")
        print(f"Removing {invalid_count} forecasts with mismatched periods...")
        concat_df = concat_df[valid_mask].copy()
        print(f"Retained {len(concat_df)} forecasts with matching periods")
    else:
        print(f"All {total_count} forecasts have matching periods!")

    concat_df.drop(columns=["season_start_month", "season_end_month", "forecast_start_month",
                             "forecast_end_month", "RFC Site ID Normalized", "site_normalized"],
                    inplace=True, errors="ignore")

    merged = pd.merge(concat_df, site_lookup, how="left", left_on="site", right_on="RFC Site ID", suffixes=("", "_lookup"))
    merged.rename(columns={"USGS ID": "usgs_id"}, inplace=True)
    # NaN-safe zero-pad: sites with no site_lookup match (e.g. KTFW1, SBDW4N, TOSM8N)
    # promote the whole usgs_id column to float, which .astype(str).zfill(8) mishandles
    # (produces "9050700.0" for everyone, not just the unmatched rows).
    merged["usgs_id"] = merged["usgs_id"].apply(lambda x: str(int(x)).zfill(8) if pd.notnull(x) else "")
    merged.sort_values(by=["site", "issueDate"], inplace=True)

    print(f"\nSaving merged DataFrame with {len(merged)} rows to {OUT_CSV}")
    merged.to_csv(OUT_CSV, index=False)
    return merged


if __name__ == "__main__":
    merged = concat()

    full_list = [
        "PDAC2", "DRGC2", "MBLC2", "TPIC2", "DIRC2", "RURC2", "GBRW4", "OAWU1",
        "VIRU1", "FRAC1", "POHC1", "FOLC1", "TOSM8N", "SBDW4N",
        "HHWM8", "HEII1", "LYDM8", "LUCI1", "HHDW1", "STHW1", "DETO3",
        "RODW1", "OWYO3", "PCON5",
    ]
    merged_sites = merged.site.unique()
    missing = [s for s in full_list if s not in merged_sites]
    print(f"Sites missing from merged df: {missing}")
