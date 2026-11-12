"""Concatenate all WSF methods (NRCS, CA DWR, RFC, WSF Rodeo winners) into a
single NetCDF file of forecasts + observations.

Note: for 09109209, NRCS site ID was manually fixed to 09109000 (Taylor Park).
All forecast quantiles are stored as EXCEEDANCE probabilities (water resources standard).
"""

import os

import numpy as np
import pandas as pd
import xarray as xr

RODEO_DATA = os.environ.get("WSF_RODEO_DATA", "/beegfs/sets/aw-ciroh/common/datasets/wsf_rodeo_data")  # DrivenData WSF Rodeo competition data
ARCHIVE_ROOT = os.environ.get("WSF_ARCHIVE_ROOT", os.path.expanduser("~/wsf_archive_v1.0"))
OUT_FILE = f"{ARCHIVE_ROOT}/proc_data/wsf_obs_with_all_forecasts.nc"
OBS_FILE = f"{ARCHIVE_ROOT}/source_data/obs/all_seasonal_naturalized_flow.csv"
META_FILE = os.path.join(RODEO_DATA, "metadata.csv")
NRCS_FILE = f"{ARCHIVE_ROOT}/source_data/nrcs/nrcs_fcst_obs.all_sites_yrs.wsf_rodeo.csv"
WSFR_SOL_FILE = f"{ARCHIVE_ROOT}/source_data/rodeo_winners/wsf_rodeo_solutions.amjj_wsf.csv"
CADWR_FILE = f"{ARCHIVE_ROOT}/source_data/cadwr_b120/cadwr_b120_wsf.csv"
RFC_FILE = f"{ARCHIVE_ROOT}/source_data/rfc/all_rfc_wsf.csv"

ALLOWED_INIT_DATES = ["01-01", "02-01", "03-01", "04-01"]  # only first-of-month Jan-Apr
AMJJAS_IDS = {"06054500", "06259000"}  # exclude RFC forecasts from these sites (AMJJAS vs AMJJ mismatch)


def zpad8(series):
    """Zero-pad a USGS ID column to 8 digits, NaN-safe.

    Plain `.astype(str).str.zfill(8)` silently mis-pads if any row is NaN --
    that promotes the whole column to float64 on CSV read, turning
    "09050700" into 9050700.0, which zfill(8) then leaves untouched (already
    9+ chars). Found via a real regression: unmatched RFC site codes
    (KTFW1, SBDW4N, TOSM8N) blanked usgs_id for those rows, silently breaking
    zero-padding for every other site in the same column.
    """
    return series.apply(lambda x: str(int(float(x))).zfill(8) if pd.notnull(x) and str(x).strip() != "" else "")

WSF_RODEO_METHODS = [
    ("oshbocker", "wsf_rodeo_1place"),
    ("ck-ua", "wsf_rodeo_2place"),
    ("rasyidstat", "wsf_rodeo_3place"),
    ("kurisu", "wsf_rodeo_4place"),
    ("progin", "wsf_rodeo_5place"),
]
PERCENTILE_LIST = ["f10", "f30", "f50", "f70", "f90"]


CLIMO_YEARS = np.arange(1994, 2024)  # 30-yr climatology period, WY1994-2023
# Exceedance level -> non-exceedance sample percentile
CLIMO_PCT = {"f10": 90, "f30": 70, "f50": 50, "f70": 30, "f90": 10}


def build_climatology(obs_array, year_list):
    """Leave-one-out 30-yr climatology for each site and target year in CLIMO_YEARS.

    Matches the reference in wsf-protocol-paper/calc_stats/calc_bulk_fcst_stats.py:
    the sample is every observed year in CLIMO_YEARS except the target year itself.
    Returns quantiles (site, year, percentile), mean (site, year), sample size (site, year).
    """
    years = np.asarray(year_list)
    n_site, n_year = obs_array.shape
    q = np.full((n_site, n_year, len(PERCENTILE_LIST)), np.nan)
    mean = np.full((n_site, n_year), np.nan)
    n = np.zeros((n_site, n_year), dtype=np.int64)
    in_period = np.isin(years, CLIMO_YEARS)
    for si in range(n_site):
        for yi in np.where(in_period)[0]:
            keep = in_period & np.isfinite(obs_array[si]) & (years != years[yi])
            sample = obs_array[si, keep]
            n[si, yi] = sample.size
            if sample.size == 0:
                continue
            mean[si, yi] = sample.mean()
            q[si, yi, :] = np.percentile(sample, [CLIMO_PCT[p] for p in PERCENTILE_LIST])
    return q, mean, n


def build():
    # --- 1. Load obs ---
    obs = pd.read_csv(OBS_FILE)
    if "usgs_id" in obs.columns:
        obs["site"] = obs["usgs_id"].apply(lambda x: str(int(float(x))).zfill(8) if pd.notnull(x) else "")
    else:
        obs["site"] = obs["site_id"].astype(str).str.zfill(8)
    obs["year"] = obs["year"].astype(int)
    obs = obs[obs["year"] >= 1900]

    # --- 2. Load metadata ---
    meta = pd.read_csv(META_FILE)
    meta["site"] = meta["usgs_id"].apply(lambda x: str(int(float(x))).zfill(8) if pd.notnull(x) else "")
    meta = meta.drop_duplicates("site").set_index("site")
    meta = meta.reindex(obs["site"].unique())
    # 12175000 (Ross Reservoir) isn't in the Rodeo competition metadata.csv (it was
    # added to this study outside the competition site set); every other site in the
    # archive uses Apr-Jul, which matches this site's season in the prior archive build.
    missing_season = meta["season_start_month"].isna()
    if missing_season.any():
        print(f"WARNING: no metadata season for {list(meta.index[missing_season])}, defaulting to Apr-Jul (4-7)")
        meta.loc[missing_season, "season_start_month"] = 4
        meta.loc[missing_season, "season_end_month"] = 7

    # --- 3. Build obs arrays ---
    site_list = sorted(obs["site"].unique())
    year_list = sorted(obs["year"].unique())
    obs_array = np.full((len(site_list), len(year_list)), np.nan)
    site_idx = {s: i for i, s in enumerate(site_list)}
    year_idx = {y: i for i, y in enumerate(year_list)}
    for _, row in obs.iterrows():
        s, y = row["site"], row["year"]
        if s in site_idx and y in year_idx:
            obs_array[site_idx[s], year_idx[y]] = row["volume"]

    season_start_month = meta.loc[site_list, "season_start_month"].astype(int).values
    season_end_month = meta.loc[site_list, "season_end_month"].astype(int).values

    # --- 4. NRCS forecasts ---
    nrcs = pd.read_csv(NRCS_FILE)
    nrcs["usgs_id"] = nrcs["stationTriplet"].str.split(":").str[0].str.zfill(8)
    nrcs.loc[nrcs["usgs_id"] == "09109209", "usgs_id"] = "09109000"  # manual site ID fix
    nrcs["init_date"] = pd.to_datetime(nrcs["publicationDate"], errors="coerce")
    nrcs["issue_monthday"] = nrcs["init_date"].dt.strftime("%m-%d")
    nrcs["start_md"] = nrcs["forecastPeriodStart"].str[-5:]
    nrcs["end_md"] = nrcs["forecastPeriodEnd"].str[-5:]

    nrcs = nrcs[nrcs["issue_monthday"].isin(ALLOWED_INIT_DATES)]
    nrcs = nrcs[
        (nrcs["elementCode"].str.upper() == "SRVO")
        & (nrcs["forecastStatus"].str.lower().isin(["final", "official"]))
    ].copy()

    period_map = {}
    for s in site_list:
        if s in meta.index:
            sm, em = int(meta.loc[s, "season_start_month"]), int(meta.loc[s, "season_end_month"])
            period_map[s] = (f"{sm:02d}-01", f"{em:02d}-31" if em in [7, 8, 10, 12] else f"{em:02d}-30")

    def match_period(row):
        sm_em = period_map.get(row["usgs_id"])
        if sm_em is None:
            return False
        return row["start_md"] == sm_em[0] and row["end_md"] == sm_em[1]

    nrcs = nrcs[nrcs.apply(match_period, axis=1)]
    print(f"NRCS: {len(nrcs)} forecasts after filtering for {ALLOWED_INIT_DATES}")

    # --- 5. WSFR solution forecasts ---
    sol = pd.read_csv(WSFR_SOL_FILE)
    sol["site"] = zpad8(sol["usgs_id"])
    sol["init_date"] = pd.to_datetime(sol["issue_date"])
    sol["init_date_str"] = sol["init_date"].dt.strftime("%Y-%m-%d")
    sol["issue_monthday"] = sol["init_date"].dt.strftime("%m-%d")
    sol["source"] = sol["source"].str.strip().str.lower()
    sol = sol[sol["issue_monthday"].isin(ALLOWED_INIT_DATES)]

    sol_methods = dict(WSF_RODEO_METHODS)
    sol = sol[sol["source"].isin(sol_methods.keys())]
    print(f"WSF Rodeo: {len(sol)} forecasts after filtering for {ALLOWED_INIT_DATES}")
    print("Converting WSF Rodeo from non-exceedance to exceedance probabilities...")

    tmp = sol[["forecast_10", "forecast_30", "forecast_50", "forecast_70", "forecast_90"]].copy()
    sol["forecast_10"] = tmp["forecast_90"]  # 10% non-exceedance = 90% exceedance
    sol["forecast_30"] = tmp["forecast_70"]
    sol["forecast_50"] = tmp["forecast_50"]
    sol["forecast_70"] = tmp["forecast_30"]
    sol["forecast_90"] = tmp["forecast_10"]

    # --- 6. CA DWR ---
    cadwr = pd.read_csv(CADWR_FILE)
    cadwr["usgs_id"] = zpad8(cadwr["usgs_id"])
    cadwr["init_date"] = pd.to_datetime(cadwr["publicationDate"], errors="coerce")
    cadwr["init_date_str"] = cadwr["init_date"].dt.strftime("%Y-%m-%d")
    cadwr["issue_monthday"] = cadwr["init_date"].dt.strftime("%m-%d")
    cadwr = cadwr[cadwr["issue_monthday"].isin(ALLOWED_INIT_DATES)]
    cadwr = cadwr[cadwr["usgs_id"].isin(site_list)]
    print(f"CA DWR: {len(cadwr)} forecasts after filtering for {ALLOWED_INIT_DATES}")

    # --- 7. RFC ---
    rfc = pd.read_csv(RFC_FILE)
    rfc["usgs_id"] = zpad8(rfc["usgs_id"])
    rfc["init_date"] = pd.to_datetime(rfc["publicationDate"], errors="coerce")
    rfc["init_date_str"] = rfc["init_date"].dt.strftime("%Y-%m-%d")
    rfc["issue_monthday"] = rfc["init_date"].dt.strftime("%m-%d")
    rfc = rfc[rfc["issue_monthday"].isin(ALLOWED_INIT_DATES)]

    print(f"RFC before excluding AMJJAS sites: {len(rfc)} forecasts")
    rfc = rfc[~rfc["usgs_id"].isin(AMJJAS_IDS)]
    print(f"RFC after excluding AMJJAS sites: {len(rfc)} forecasts")
    rfc = rfc[rfc["usgs_id"].isin(site_list)]
    rfc["method"] = np.where(rfc["source"].str.endswith("_official"), "rfc_official",
                              np.where(rfc["source"].str.endswith("_hcst"), "rfc_hcst", None))
    rfc = rfc[rfc["method"].notnull()]
    print(f"RFC: {len(rfc)} forecasts after filtering")

    # --- 8. Arrays ---
    init_dates = sorted(set(nrcs["init_date"].dt.strftime("%Y-%m-%d")).union(
        set(sol["init_date_str"])).union(set(cadwr["init_date_str"])).union(set(rfc["init_date_str"])))
    print(f"\nTotal unique init_dates: {len(init_dates)}")

    fcst_method_list = ["nrcs", "ca_dwr"] + [m[1] for m in WSF_RODEO_METHODS] + ["rfc_official", "rfc_hcst"]
    wsf_array = np.full((len(site_list), len(init_dates), len(PERCENTILE_LIST), len(fcst_method_list)), np.nan)
    date_idx = {d: i for i, d in enumerate(init_dates)}
    pct_idx = {p: i for i, p in enumerate(PERCENTILE_LIST)}
    meth_idx = {m: i for i, m in enumerate(fcst_method_list)}

    # --- 9. Fill NRCS ---
    for _, row in nrcs.iterrows():
        s = row["usgs_id"]
        if s not in site_idx:
            continue
        d = pd.Timestamp(row["init_date"]).strftime("%Y-%m-%d")
        if d not in date_idx:
            continue
        for p in PERCENTILE_LIST:
            col = f"forecast_{p[1:]}"
            if col in row and pd.notnull(row[col]):
                wsf_array[site_idx[s], date_idx[d], pct_idx[p], meth_idx["nrcs"]] = row[col]

    # --- 10. Fill CA DWR ---
    for _, row in cadwr.iterrows():
        s, d = row["usgs_id"], row["init_date_str"]
        if s not in site_idx or d not in date_idx:
            continue
        for p in PERCENTILE_LIST:
            col = f"forecast_{p[1:]}"
            if col in row and pd.notnull(row[col]):
                wsf_array[site_idx[s], date_idx[d], pct_idx[p], meth_idx["ca_dwr"]] = row[col]

    # --- 11. Fill WSFR solutions ---
    for _, row in sol.iterrows():
        s, d, src = row["site"], row["init_date_str"], row["source"]
        if s not in site_idx or d not in date_idx or src not in sol_methods:
            continue
        m_idx = meth_idx[sol_methods[src]]
        for p in PERCENTILE_LIST:
            col = f"forecast_{p[1:]}"
            if col in row and pd.notnull(row[col]):
                wsf_array[site_idx[s], date_idx[d], pct_idx[p], m_idx] = row[col]

    # --- 12. Fill RFC (with per-forecast exceedance-inversion detection) ---
    print("Filling RFC data with per-forecast inversion detection...")
    rfc_inverted_count = {"rfc_official": 0, "rfc_hcst": 0}
    rfc_total_count = {"rfc_official": 0, "rfc_hcst": 0}

    for _, row in rfc.iterrows():
        s, d, m = row["usgs_id"], row["init_date_str"], row["method"]
        if s not in site_idx or d not in date_idx or m not in meth_idx:
            continue
        m_idx = meth_idx[m]

        rfc_quantiles = {}
        for p in PERCENTILE_LIST:
            col = f"forecast_{p[1:]}"
            if col in row and pd.notnull(row[col]):
                rfc_quantiles[p] = row[col]

        if not ("f10" in rfc_quantiles and "f90" in rfc_quantiles):
            # median-only (or partial) forecasts are kept, like NRCS/CA DWR: they still
            # count for deterministic scores; CRPS/Brier skip them for lack of tails
            for p in rfc_quantiles:
                wsf_array[site_idx[s], date_idx[d], pct_idx[p], m_idx] = rfc_quantiles[p]
        else:
            rfc_total_count[m] += 1
            is_inverted = rfc_quantiles["f10"] < rfc_quantiles["f90"]
            if is_inverted:
                rfc_inverted_count[m] += 1
                wsf_array[site_idx[s], date_idx[d], pct_idx["f10"], m_idx] = rfc_quantiles["f90"]
                wsf_array[site_idx[s], date_idx[d], pct_idx["f30"], m_idx] = rfc_quantiles.get("f70", np.nan)
                wsf_array[site_idx[s], date_idx[d], pct_idx["f50"], m_idx] = rfc_quantiles.get("f50", np.nan)
                wsf_array[site_idx[s], date_idx[d], pct_idx["f70"], m_idx] = rfc_quantiles.get("f30", np.nan)
                wsf_array[site_idx[s], date_idx[d], pct_idx["f90"], m_idx] = rfc_quantiles["f10"]
            else:
                for p in PERCENTILE_LIST:
                    if p in rfc_quantiles:
                        wsf_array[site_idx[s], date_idx[d], pct_idx[p], m_idx] = rfc_quantiles[p]

    print(f"RFC Official: {rfc_inverted_count['rfc_official']}/{rfc_total_count['rfc_official']} forecasts inverted and corrected")
    print(f"RFC Hindcast: {rfc_inverted_count['rfc_hcst']}/{rfc_total_count['rfc_hcst']} forecasts inverted and corrected")

    # --- 13. Climatological reference forecast ---
    climo_q, climo_mean, climo_n = build_climatology(obs_array, year_list)

    # --- 14. Build final xarray Dataset ---
    ds = xr.Dataset(
        {
            "obs": (["site", "year"], obs_array),
            "wsf": (["site", "init_date", "percentile", "fcst_method"], wsf_array),
            "climo": (["site", "year", "percentile"], climo_q),
            "climo_mean": (["site", "year"], climo_mean),
            "climo_n_years": (["site", "year"], climo_n),
            "fcst_start_month": (["site"], season_start_month),
            "fcst_end_month": (["site"], season_end_month),
        },
        coords={"site": site_list, "year": year_list, "init_date": init_dates,
                "percentile": PERCENTILE_LIST, "fcst_method": fcst_method_list},
    )

    ds.attrs["title"] = "Western US Seasonal Water Supply Forecasts with Observations"
    ds.attrs["description"] = "Aggregated seasonal water supply forecasts from multiple sources"
    ds.attrs["probability_convention"] = "EXCEEDANCE"
    ds.attrs["probability_interpretation"] = (
        "All forecast quantiles represent EXCEEDANCE probabilities. f10 = 10% exceedance "
        "probability (90% of values will be below this threshold). This follows the water "
        "resources forecasting standard used by NRCS, RFC, and CA DWR.")
    ds.attrs["init_date_filter"] = "Only January 1, February 1, March 1, and April 1 forecasts included"
    ds.attrs["date_created"] = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")

    ds["obs"].attrs["long_name"] = "Observed seasonal naturalized flow volume"
    ds["obs"].attrs["units"] = "thousand acre-feet (KAF)"
    ds["wsf"].attrs["long_name"] = "Water supply forecast quantiles"
    ds["wsf"].attrs["units"] = "thousand acre-feet (KAF)"
    ds["wsf"].attrs["probability_type"] = "exceedance"
    ds["wsf"].attrs["description"] = "Forecast quantiles as exceedance probabilities (e.g., f10 = 10% chance of exceeding this value)"
    ds["percentile"].attrs["description"] = "Exceedance probability levels: f10=10% exceedance, f30=30%, f50=50% (median), f70=70%, f90=90%"
    ds["fcst_method"].attrs["description"] = "Forecast method/source. NRCS, CA DWR, RFC use native exceedance format. WSF Rodeo converted from non-exceedance to exceedance."
    climo_desc = (
        f"Leave-one-out climatology from observed seasonal volumes, WY{CLIMO_YEARS[0]}-{CLIMO_YEARS[-1]}: "
        "for each target year, the sample is the observations in that period with the target "
        "year's own observation removed. Defined for target years in that period only (NaN otherwise). "
        "The same for every initialization date.")
    ds["climo"].attrs["long_name"] = "Climatological reference forecast quantiles"
    ds["climo"].attrs["units"] = "thousand acre-feet (KAF)"
    ds["climo"].attrs["probability_type"] = "exceedance"
    ds["climo"].attrs["description"] = (
        climo_desc + " Quantiles are sample percentiles (linear interpolation), stored as "
        "exceedance probabilities like `wsf` (f10 = 90th percentile of the sample).")
    ds["climo_mean"].attrs["long_name"] = "Climatological reference forecast mean"
    ds["climo_mean"].attrs["units"] = "thousand acre-feet (KAF)"
    ds["climo_mean"].attrs["description"] = climo_desc + " Mean of the sample (deterministic reference)."
    ds["climo_n_years"].attrs["long_name"] = "Number of observed years in the climatology sample"

    if os.path.exists(OUT_FILE):
        os.remove(OUT_FILE)
    ds.to_netcdf(OUT_FILE)
    print(f"\nSaved NetCDF: {OUT_FILE}")
    print(ds)
    return ds


if __name__ == "__main__":
    build()
