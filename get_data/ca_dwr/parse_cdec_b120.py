"""Parse CA DWR Bulletin 120 April-July forecasts from the CDEC internal query
export into the archive's cadwr_b120_wsf.csv.

Reconstructs the raw->archive step for CA DWR, which previously had no surviving
script. See README.md alongside the raw file for the source and its sensor mapping.

WHY THE day == 1 FILTER IS LOAD-BEARING
---------------------------------------
The CDEC export contains the official first-of-month B120 forecast AND the
~weekly mid-month updates that follow it (2517 day-1 rows vs ~4956 mid-month).
The previous, unscripted version of this step collapsed every row onto
publicationDate = YYYY-MM-01 without deduplicating, so the last row in file
order won -- always the LATEST update of the month. In WY2004-2023 that made
119 of 120 archived "first-of-month" CA DWR forecasts actually mid-month
issues, mean issue day 23.8, giving CA DWR ~3 weeks of extra snowpack
information over every method it is benchmarked against. April RMSE was 37.5%
better than the true April 1 product. CA DWR is the primary benchmark at both
California sites, so that inflation propagated into every CA DWR skill number
and every head-to-head comparison against it.

Verified: a day-1 row exists for 100% of site-months in the 2004-2023 window,
and (STATION_ID, DATE_TIME, SENSOR_NUM) is unique among day-1 rows, so this
filter loses no data and needs no tie-break.

B120 is issued Feb/Mar/Apr/May (a handful of June). There is no January
forecast -- CA DWR's absence from January statistics is real, not missing data.
"""

import os
from pathlib import Path

import pandas as pd

ARCHIVE_ROOT = Path(os.environ.get("WSF_ARCHIVE_ROOT", Path.home() / "wsf_archive_v1.0"))
SRC_DIR = ARCHIVE_ROOT / "source_data" / "cadwr_b120"
RAW_FILE = SRC_DIR / "cdec_raw_b120.rodeo.csv"
OUT_FILE = SRC_DIR / "cadwr_b120_wsf.csv"

# Sensor -> exceedance quantile, per README.md: "AJ 10%: 260, AJ 50%: 261,
# AJ 90%: 262". These are EXCEEDANCE probabilities already (AJ 10% is the wet/
# high value), matching the archive convention, so no reversal is applied here.
SENSOR_TO_COL = {"260": "forecast_10", "261": "forecast_50", "262": "forecast_90"}

# MRC (Merced at Merced Falls) is deliberately excluded. CA DWR has no primary
# forecast point at Merced/Pohono Bridge (11266500); MRC is further downstream
# and the provider states the two "are not comparable" (README.md).
STATION_META = {
    "AMF": {"site": "FOLC1", "usgs_id": "11446220"},
    "SBF": {"site": "FRAC1", "usgs_id": "11251000"},
}

AF_TO_KAF = 1000.0


def parse():
    raw = pd.read_csv(RAW_FILE, dtype=str)
    raw["dt"] = pd.to_datetime(raw["DATE_TIME"], errors="coerce")
    raw["value_kaf"] = pd.to_numeric(raw["VALUE"], errors="coerce") / AF_TO_KAF
    raw = raw.dropna(subset=["dt", "value_kaf"])

    official = raw[(raw["dt"].dt.day == 1) & raw["SENSOR_NUM"].isin(SENSOR_TO_COL)].copy()
    official = official[official["STATION_ID"].isin(STATION_META)]

    dupes = official.duplicated(["STATION_ID", "dt", "SENSOR_NUM"]).sum()
    if dupes:
        raise SystemExit(
            f"{dupes} duplicate (station, date, sensor) rows among first-of-month "
            "records; a tie-break rule is needed before this can be written."
        )

    official["col"] = official["SENSOR_NUM"].map(SENSOR_TO_COL)
    wide = (
        official.pivot_table(index=["STATION_ID", "dt"], columns="col",
                             values="value_kaf", aggfunc="first")
        .reset_index()
    )

    for col in ["forecast_90", "forecast_70", "forecast_50", "forecast_30", "forecast_10"]:
        if col not in wide:
            wide[col] = pd.NA  # f30/f70 are not published by CA DWR; left empty, never interpolated

    wide["site"] = wide["STATION_ID"].map(lambda s: STATION_META[s]["site"])
    wide["usgs_id"] = wide["STATION_ID"].map(lambda s: STATION_META[s]["usgs_id"])
    wide["publicationDate"] = wide["dt"].dt.strftime("%Y-%m-%d")
    wide["issueDate"] = wide["publicationDate"]
    wide["forecastPeriodStart"] = wide["dt"].dt.year.map(lambda y: f"{y}-04-01")
    wide["forecastPeriodEnd"] = wide["dt"].dt.year.map(lambda y: f"{y}-07-31")
    wide["source"] = "CADWR_official"
    wide["RFC Site ID"] = wide["site"]
    wide["NRCS Site ID (Triplet)"] = wide["usgs_id"] + ":CA:USGS"

    out_cols = ["site", "publicationDate", "issueDate", "forecastPeriodStart",
                "forecastPeriodEnd", "forecast_90", "forecast_70", "forecast_50",
                "forecast_30", "forecast_10", "source", "RFC Site ID", "usgs_id",
                "NRCS Site ID (Triplet)"]
    out = wide[out_cols].sort_values(["site", "publicationDate"]).reset_index(drop=True)
    out.to_csv(OUT_FILE, index=False)
    print(f"Saved: {OUT_FILE}  ({len(out)} rows, first-of-month B120 only)")
    return out


if __name__ == "__main__":
    parse()
