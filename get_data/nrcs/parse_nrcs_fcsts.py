"""Parse raw NRCS forecast JSON (per-state) into a single master CSV.

NOTE: raw input JSON directory (./tmp/{state}/*.json, relative to this
script's original working directory) was not located under the current
archive tree during the 2026-07 audit -- only the already-computed output
(nrcs_fcst.all_sites_yrs.csv) survives. Cannot be rerun as-is; kept for reference.
"""

import json
import csv
import glob
import os

STATES = ["AZ", "CA", "CO", "ID", "MT", "NV", "NM", "OR", "UT", "WA", "WY"]

HEADERS = [
    "stationTriplet", "forecastPointName", "issueDate", "publicationDate",
    "forecastPeriodStart", "forecastPeriodEnd", "elementCode", "forecastStatus",
    "unitCode", "periodNormal", "forecast_90", "forecast_70", "forecast_50",
    "forecast_30", "forecast_10",
]

OUTPUT_DIR = "./fcst_data/parsed_csvs"


def interpolate_percentiles(forecast_values):
    """Interpolate 10%/90% exceedance from 5/30 and 70/95 where NRCS publishes 5/30/50/70/95."""
    def to_float(val):
        if val is None or val == "NaN" or val == "":
            return None
        try:
            return float(val)
        except (ValueError, TypeError):
            return None

    p5 = to_float(forecast_values.get("5"))
    p10 = to_float(forecast_values.get("10"))
    p30 = to_float(forecast_values.get("30"))
    p50 = to_float(forecast_values.get("50"))
    p70 = to_float(forecast_values.get("70"))
    p90 = to_float(forecast_values.get("90"))
    p95 = to_float(forecast_values.get("95"))

    # standard-normal quantile space, as for the archive's other derived quantiles
    # (see harmonize_nrcs_5_95.py): W = (z(.95) - z(.90)) / (z(.95) - z(.70))
    w = (1.6448536 - 1.2815516) / (1.6448536 - 0.5244005)
    if p10 is None and p5 is not None and p30 is not None:
        p10 = p5 + w * (p30 - p5)
    if p90 is None and p70 is not None and p95 is not None:
        p90 = p95 + w * (p70 - p95)

    return {
        "90": str(p90) if p90 is not None else "NaN",
        "70": str(p70) if p70 is not None else "NaN",
        "50": str(p50) if p50 is not None else "NaN",
        "30": str(p30) if p30 is not None else "NaN",
        "10": str(p10) if p10 is not None else "NaN",
    }


def parse():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    csv_files = []

    for state in STATES:
        print(f"Processing state: {state}")
        json_files = sorted(glob.glob(f"./tmp/{state}/nrcs.{state}.WY*.json"))
        state_csv_file = os.path.join(OUTPUT_DIR, f"nrcs_fcst.{state}.all_yrs.csv")
        csv_files.append(state_csv_file)

        with open(state_csv_file, "w", newline="") as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(HEADERS)

            for input_file in json_files:
                if not os.path.isfile(input_file):
                    print(f"Skipping: {input_file} (File does not exist)")
                    continue
                try:
                    with open(input_file, "r") as f:
                        data = json.load(f)
                except (json.JSONDecodeError, UnicodeDecodeError) as e:
                    print(f"Skipping: {input_file} (Invalid JSON format: {e})")
                    continue
                if not isinstance(data, list):
                    print(f"Skipping: {input_file} (Unexpected JSON structure)")
                    continue

                for station in data:
                    station_triplet = station.get("stationTriplet", "NaN")
                    forecast_point = station.get("forecastPointName", "NaN")

                    for forecast in station.get("data", []):
                        issue_date = forecast.get("issueDate", "NaN")
                        publication_date = forecast.get("publicationDate", "NaN")
                        forecast_period = forecast.get("forecastPeriod", ["NaN", "NaN"])
                        forecast_period_start = forecast_period[0] if len(forecast_period) > 0 else "NaN"
                        forecast_period_end = forecast_period[1] if len(forecast_period) > 1 else "NaN"
                        element_code = forecast.get("elementCode", "NaN")
                        forecast_status = forecast.get("forecastStatus", "NaN")
                        unit_code = forecast.get("unitCode", "NaN")
                        period_normal = forecast.get("periodNormal", "NaN")

                        interpolated = interpolate_percentiles(forecast.get("forecastValues", {}))

                        writer.writerow([
                            station_triplet, forecast_point, issue_date, publication_date,
                            forecast_period_start, forecast_period_end, element_code,
                            forecast_status, unit_code, period_normal,
                            interpolated["90"], interpolated["70"], interpolated["50"],
                            interpolated["30"], interpolated["10"],
                        ])

        print(f"CSV saved: {state_csv_file}")

    master_csv_file = os.path.join(OUTPUT_DIR, "nrcs_fcst.all_sites_yrs.csv")
    print("\nCombining all state CSVs into a single master file...")
    with open(master_csv_file, "w", newline="") as master_file:
        writer = csv.writer(master_file)
        writer.writerow(HEADERS)
        for state_csv in csv_files:
            if not os.path.isfile(state_csv):
                print(f"Skipping {state_csv} (File missing)")
                continue
            with open(state_csv, "r") as f:
                reader = csv.reader(f)
                next(reader)
                for row in reader:
                    writer.writerow(row)

    print(f"Master CSV file saved: {master_csv_file}")


if __name__ == "__main__":
    parse()
