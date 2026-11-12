"""Aggregate NRCS observed flows and merge with parsed forecasts (AMJJ/AMJJAS)."""

import json
import glob
import os

import pandas as pd

ARCHIVE_ROOT = os.environ.get("WSF_ARCHIVE_ROOT", os.path.expanduser("~/wsf_archive_v1.0"))
OBS_DIR = f"{ARCHIVE_ROOT}/source_data/nrcs/obs_data"
FCST_FILE = f"{ARCHIVE_ROOT}/source_data/nrcs/nrcs_fcst.all_sites_yrs.csv"
OUT_FILE = f"{ARCHIVE_ROOT}/source_data/nrcs/nrcs_fcst_obs.all_sites_yrs.csv"
RAW_OBS_FLAT_FILE = f"{ARCHIVE_ROOT}/source_data/nrcs/nrcs.adj_flows.csv"


def dump_raw_monthly_obs():
    """Flatten raw NRCS obs JSON to one row per station/year/month (element SRVO)."""
    import csv

    with open(RAW_OBS_FLAT_FILE, "w", newline="") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["stationTriplet", "year", "month", "value", "unitCode", "elementCode"])
        for input_file in sorted(glob.glob(os.path.join(OBS_DIR, "*.json"))):
            try:
                with open(input_file, "r") as f:
                    data = json.load(f)
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                print(f"Skipping: {input_file} (Invalid JSON format: {e})")
                continue
            if not isinstance(data, list):
                continue
            for station in data:
                station_triplet = station.get("stationTriplet", "NaN")
                for obs in station.get("data", []):
                    unit_code = obs.get("stationElement", {}).get("storedUnitCode", "NaN")
                    for value_entry in obs.get("values", []):
                        writer.writerow([
                            station_triplet, value_entry.get("year", "NaN"),
                            value_entry.get("month", "NaN"), value_entry.get("value", "NaN"),
                            unit_code, "SRVO",
                        ])
    print(f"Saved {RAW_OBS_FLAT_FILE}")


def concat_and_merge():
    df_fcst = pd.read_csv(FCST_FILE)

    df_fcst["publicationDate"] = pd.to_datetime(df_fcst["publicationDate"], errors="coerce")
    df_fcst = df_fcst[(df_fcst["publicationDate"].dt.month >= 1) & (df_fcst["publicationDate"].dt.month <= 7)]
    df_fcst = df_fcst.dropna(subset=["forecastPeriodStart", "forecastPeriodEnd"])

    df_fcst["forecast_year"] = df_fcst["publicationDate"].dt.year
    df_fcst["forecastPeriodStart"] = pd.to_datetime(
        df_fcst["forecast_year"].astype(str) + "-" + df_fcst["forecastPeriodStart"], errors="coerce")
    df_fcst["forecastPeriodEnd"] = pd.to_datetime(
        df_fcst["forecast_year"].astype(str) + "-" + df_fcst["forecastPeriodEnd"], errors="coerce")
    df_fcst = df_fcst.dropna(subset=["forecastPeriodStart", "forecastPeriodEnd"])

    df_fcst["forecastPeriodStart_str"] = df_fcst["forecastPeriodStart"].dt.strftime("%Y-%m-%d")
    df_fcst["forecastPeriodEnd_str"] = df_fcst["forecastPeriodEnd"].dt.strftime("%Y-%m-%d")

    obs_data = {}
    for obs_file in glob.glob(os.path.join(OBS_DIR, "*.json")):
        with open(obs_file, "r") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                print(f"Skipping invalid JSON file: {obs_file}")
                continue
        if not isinstance(data, list):
            print(f"Skipping file due to error response: {obs_file}")
            continue
        for station in data:
            if "stationTriplet" not in station or "data" not in station:
                print(f"Skipping invalid station entry in {obs_file}")
                continue
            station_triplet = station["stationTriplet"]
            for obs in station["data"]:
                if "values" not in obs:
                    continue
                for value_entry in obs["values"]:
                    year = int(value_entry.get("year"))
                    month = int(value_entry.get("month"))
                    value_af = value_entry.get("value", None)
                    if value_af is not None:
                        obs_data[(station_triplet, year, month)] = value_af

    obs_aggregated = []
    for _, row in df_fcst.iterrows():
        station = row["stationTriplet"]
        start_date, end_date = row["forecastPeriodStart"], row["forecastPeriodEnd"]
        try:
            period_months = pd.date_range(start=start_date, end=end_date, freq="MS")
        except Exception as e:
            print(f"Error generating date range for {station} period {start_date} to {end_date}: {e}")
            continue

        total_obs_af, months_found = 0, []
        for dt in period_months:
            key = (station, int(dt.year), int(dt.month))
            if key in obs_data:
                total_obs_af += obs_data[key]
                months_found.append(dt.month)

        obs_period_complete = len(months_found) == len(period_months)
        total_obs_kaf = total_obs_af / 1000 if obs_period_complete else None

        if not obs_period_complete and len(months_found) > 0:
            print(f"WARNING: Incomplete observed data for {station} {start_date.strftime('%Y-%m-%d')} "
                  f"to {end_date.strftime('%Y-%m-%d')}: Only months found: {months_found}")

        obs_aggregated.append([station, start_date, end_date, total_obs_kaf, obs_period_complete])

    df_obs_agg = pd.DataFrame(
        obs_aggregated,
        columns=["stationTriplet", "forecastPeriodStart", "forecastPeriodEnd", "forecast_period_actual_kaf", "obs_period_complete"])
    df_obs_agg["forecastPeriodStart_str"] = df_obs_agg["forecastPeriodStart"].dt.strftime("%Y-%m-%d")
    df_obs_agg["forecastPeriodEnd_str"] = df_obs_agg["forecastPeriodEnd"].dt.strftime("%Y-%m-%d")

    df_merged = df_fcst.merge(
        df_obs_agg[["stationTriplet", "forecastPeriodStart_str", "forecastPeriodEnd_str",
                     "forecast_period_actual_kaf", "obs_period_complete"]],
        on=["stationTriplet", "forecastPeriodStart_str", "forecastPeriodEnd_str"], how="left", suffixes=("", "_obs"))
    df_merged.drop(columns=["forecastPeriodStart_obs", "forecastPeriodEnd_obs"], errors="ignore", inplace=True)

    df_merged.to_csv(OUT_FILE, index=False)
    print(f"Merged forecast and observed flows saved as {OUT_FILE}")
    return df_merged


if __name__ == "__main__":
    dump_raw_monthly_obs()
    concat_and_merge()
