"""Compare the archive's USBR/Rodeo obs record against NRCS's own reported
actual volumes, site by site, to see where they agree vs where the archive
obs record isn't just repeating NRCS's number.

Usage: python compare_usbr_nrcs_obs.py
"""

import os

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

RODEO_DATA = os.environ.get("WSF_RODEO_DATA", "/beegfs/sets/aw-ciroh/common/datasets/wsf_rodeo_data")  # DrivenData WSF Rodeo competition data
ARCHIVE_ROOT = os.path.expanduser(os.environ.get("WSF_ARCHIVE_ROOT", "~/wsf_archive_v1.0"))
OBS_FILE = f"{ARCHIVE_ROOT}/source_data/obs/all_seasonal_naturalized_flow.csv"
NRCS_FILE = f"{ARCHIVE_ROOT}/source_data/nrcs/nrcs_fcst_obs.all_sites_yrs.wsf_rodeo.csv"
META_FILE = os.path.join(RODEO_DATA, "metadata.csv")

# obs = archive's definitive naturalized-flow record (USBR/Rodeo competition labels)
obs = pd.read_csv(OBS_FILE)
obs["site"] = obs["usgs_id"].apply(lambda x: str(int(x)).zfill(8) if pd.notnull(x) else "")

meta = pd.read_csv(META_FILE)
meta["site"] = meta["usgs_id"].apply(lambda x: str(int(x)).zfill(8) if pd.notnull(x) else "")
meta = meta.drop_duplicates("site").set_index("site")

nrcs = pd.read_csv(NRCS_FILE)
nrcs["site"] = nrcs["stationTriplet"].str.split(":").str[0].str.zfill(8)
nrcs.loc[nrcs["site"] == "09109209", "site"] = "09109000"  # same manual fix as concat_wsf.all_methods.py

# keep only rows whose forecast period matches this site's official season
# (same filter concat_wsf.all_methods.py applies), so we're comparing the
# same volume definition, not an arbitrary sub-period.
def matches_season(row):
    if row["site"] not in meta.index:
        return False
    sm = int(meta.loc[row["site"], "season_start_month"])
    em = int(meta.loc[row["site"], "season_end_month"])
    end_day = 31 if em in (1, 3, 5, 7, 8, 10, 12) else 30
    return row["forecastPeriodStart"].endswith(f"{sm:02d}-01") and row["forecastPeriodEnd"].endswith(f"{em:02d}-{end_day}")

nrcs = nrcs[nrcs.apply(matches_season, axis=1)]
nrcs_actual = (
    nrcs.dropna(subset=["forecast_period_actual_kaf"])
    .groupby(["site", "forecast_year"])["forecast_period_actual_kaf"]
    .median()
    .reset_index()
    .rename(columns={"forecast_year": "year", "forecast_period_actual_kaf": "nrcs_actual"})
)

merged = obs.merge(nrcs_actual, on=["site", "year"], how="outer", indicator=True)
merged["diff"] = merged["volume"] - merged["nrcs_actual"]
merged["pct_diff"] = 100 * merged["diff"] / merged["nrcs_actual"]
merged["match"] = np.isclose(merged["volume"], merged["nrcs_actual"], rtol=0.01, atol=1.0)

print(f"Total site-years: {len(merged)}")
print(merged["_merge"].value_counts(), "\n")

print("Per-site summary (of years present in both):")
both = merged[merged["_merge"] == "both"]
summary = both.groupby("site").agg(
    n_years=("match", "size"),
    n_match=("match", "sum"),
    median_pct_diff=("pct_diff", lambda x: x.abs().median()),
).sort_values("median_pct_diff", ascending=False)
summary["frac_match"] = summary["n_match"] / summary["n_years"]
print(summary.to_string())

obs_only = merged[merged["_merge"] == "left_only"]["site"].unique()
nrcs_only = merged[merged["_merge"] == "right_only"]["site"].unique()
print(f"\nSites/years in USBR obs only (no NRCS actual to compare): {len(obs_only)} site(s) touched")
print(f"Sites/years in NRCS actual only (no USBR obs to compare): {len(nrcs_only)} site(s) touched")

# --- plot: parity scatter, one point per site-year, colored by site ---
fig, ax = plt.subplots(figsize=(8, 6))
sites = sorted(both["site"].unique())
cmap = plt.get_cmap("tab20", len(sites))
for i, s in enumerate(sites):
    sub = both[both["site"] == s]
    ax.scatter(sub["nrcs_actual"], sub["volume"], s=14, color=cmap(i), alpha=0.7, label=s)

lims = [0, max(both["nrcs_actual"].max(), both["volume"].max()) * 1.05]
ax.plot(lims, lims, color="0.5", lw=1, ls="--", zorder=0)
ax.set_xlim(lims)
ax.set_ylim(lims)
ax.set_xlabel("NRCS reported adjusted volume (KAF)")
ax.set_ylabel("Archive obs (USBR/Rodeo) volume (KAF)")
ax.set_title("Archive obs vs NRCS-reported adjusted volume, by site-year")
ax.legend(fontsize=6, ncol=2, loc="upper left", bbox_to_anchor=(1.02, 1))

r2 = np.corrcoef(both["nrcs_actual"], both["volume"])[0, 1] ** 2
rmse = np.sqrt(np.mean((both["volume"] - both["nrcs_actual"]) ** 2))
ax.text(
    0.03, 0.97, f"R² = {r2:.4f}\nRMSE = {rmse:.1f} KAF\nn = {len(both)}",
    transform=ax.transAxes, va="top", ha="left", fontsize=9,
)
fig.tight_layout()
out_png = os.path.join(os.path.dirname(__file__), "usbr_vs_nrcs_obs_parity.png")
fig.savefig(out_png, dpi=150)
print(f"\nSaved plot: {out_png}")
