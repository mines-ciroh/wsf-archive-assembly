"""Scrape CA DWR Bulletin 120 forecasts from CDEC (2014-2026 only).

Leftover from before CA DWR provided a longer historical record directly
(older archives on CDEC are in harder-to-parse formats). The archive uses
that CA DWR-provided CSV instead (source_data/cadwr_b120/cdec_raw_b120.rodeo.csv),
which is more complete (1932-2025).
"""

import os
import re
import requests
from bs4 import BeautifulSoup
import pandas as pd

ARCHIVE_ROOT = os.environ.get("WSF_ARCHIVE_ROOT", os.path.expanduser("~/wsf_archive_v1.0"))
LOOKUP_FILE = os.path.join(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."), "metadata", "WSF_Rodeo_ForecastLocations.csv")
OUT_FILE = f"{ARCHIVE_ROOT}/source_data/cadwr_b120/cadwr_b120_wsf.cdec_scrape.csv"

SITE_VARIANTS = {
    "FOLC1": ["folsom"],
    "FRAC1": ["friant", "millerton"],
}


def safe_float(val):
    try:
        return float(str(val).replace(",", "").strip())
    except Exception:
        return None


def scrape():
    years = range(2014, 2026)
    months = range(1, 6)
    rows = []

    for year in years:
        for month in months:
            mm = f"{month:02d}"
            url = f"https://cdec.water.ca.gov/reportapp/javareports?name=B120.{year}{mm}"
            print(f"Scraping {url}...")
            try:
                resp = requests.get(url, timeout=10)
                resp.raise_for_status()
            except Exception as e:
                print(f"Failed {url}: {e}")
                continue

            soup = BeautifulSoup(resp.text, "html.parser")
            lines = soup.get_text(separator="\n").splitlines()

            for site_code, variants in SITE_VARIANTS.items():
                found = False
                for i, line in enumerate(lines):
                    if any(variant in line.lower() for variant in variants):
                        num_lines = []
                        for j in range(1, 5):
                            if i + j < len(lines):
                                s = lines[i + j].strip().replace(",", "")
                                if re.fullmatch(r"[-+]?\d*\.\d+|\d+", s):
                                    num_lines.append(s)
                                else:
                                    break
                        if len(num_lines) >= 1:
                            forecast_50 = safe_float(num_lines[0])
                            forecast_90 = safe_float(num_lines[2]) if len(num_lines) > 2 else None
                            forecast_10 = safe_float(num_lines[3]) if len(num_lines) > 3 else None
                        else:
                            nums = re.findall(r"[-+]?\d*\.\d+|\d+", line)
                            forecast_50 = safe_float(nums[0]) if len(nums) >= 1 else None
                            forecast_90 = safe_float(nums[2]) if len(nums) >= 3 else None
                            forecast_10 = safe_float(nums[3]) if len(nums) >= 4 else None

                        forecast_70 = (forecast_90 + forecast_50) / 2 if forecast_90 is not None and forecast_50 is not None else None
                        forecast_30 = (forecast_10 + forecast_50) / 2 if forecast_10 is not None and forecast_50 is not None else None

                        def show(x):
                            return "" if x is None else f"{x:.1f}"

                        pubdate = f"{year}-{mm}-01"
                        rows.append(dict(
                            site=site_code, publicationDate=pubdate, issueDate=pubdate,
                            forecastPeriodStart=f"{year}-04-01", forecastPeriodEnd=f"{year}-07-31",
                            forecast_90=show(forecast_90), forecast_70=show(forecast_70),
                            forecast_50=show(forecast_50), forecast_30=show(forecast_30),
                            forecast_10=show(forecast_10), source="CADWR_official",
                        ))
                        found = True
                        break

                if not found:
                    pubdate = f"{year}-{mm}-01"
                    rows.append(dict(
                        site=site_code, publicationDate=pubdate, issueDate=pubdate,
                        forecastPeriodStart=f"{year}-04-01", forecastPeriodEnd=f"{year}-07-31",
                        forecast_90="", forecast_70="", forecast_50="", forecast_30="", forecast_10="",
                        source="CADWR_official",
                    ))

    df = pd.DataFrame(rows)[[
        "site", "publicationDate", "issueDate", "forecastPeriodStart", "forecastPeriodEnd",
        "forecast_90", "forecast_70", "forecast_50", "forecast_30", "forecast_10", "source",
    ]]
    df.sort_values(by=["site", "issueDate"], inplace=True)

    site_lookup = pd.read_csv(LOOKUP_FILE)
    site_lookup["RFC Site ID"] = site_lookup["RFC Site ID"].astype(str).str.strip().str.upper()
    site_lookup = site_lookup[["RFC Site ID", "USGS ID", "NRCS Site ID (Triplet)"]]

    df["site"] = df["site"].astype(str).str.strip().str.upper()
    merged = df.merge(site_lookup, how="left", left_on="site", right_on="RFC Site ID", suffixes=("", "_lookup"))
    merged.rename(columns={"USGS ID": "usgs_id"}, inplace=True)
    merged["usgs_id"] = merged["usgs_id"].astype(str).str.zfill(8)
    merged.sort_values(by=["site", "issueDate"], inplace=True)
    return merged


if __name__ == "__main__":
    merged = scrape()
    print(f"Scraped {len(merged)} rows (2014-2026 only, superseded subset -- not written to {OUT_FILE})")
