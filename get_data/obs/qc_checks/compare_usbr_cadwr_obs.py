"""Compare the archive's USBR/Rodeo obs record against CA DWR's own reported
Apr-Jul observed flow, for the two sites CA DWR provided directly (American
River below Folsom, San Joaquin below Friant).

Usage: python compare_usbr_cadwr_obs.py
"""

import os

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

ARCHIVE_ROOT = os.path.expanduser(os.environ.get("WSF_ARCHIVE_ROOT", "~/wsf_archive_v1.0"))
OBS_FILE = f"{ARCHIVE_ROOT}/source_data/obs/all_seasonal_naturalized_flow.csv"
CADWR_FILE = f"{ARCHIVE_ROOT}/source_data/obs/cadwr_raw/fnf_obs_aj.ca_dwr.csv"

SITE_MAP = {
    "AMF": "11446220",  # American River below Folsom
    "SBF": "11251000",  # San Joaquin River below Friant
}

# obs = archive's definitive naturalized-flow record (USBR/Rodeo competition labels)
obs = pd.read_csv(OBS_FILE)
obs["site"] = obs["usgs_id"].apply(lambda x: str(int(x)).zfill(8) if pd.notnull(x) else "")

cadwr = pd.read_csv(CADWR_FILE)
cadwr["site"] = cadwr["BSN_STR"].map(SITE_MAP).apply(lambda x: str(x).zfill(8))
cadwr = cadwr.rename(columns={"WY": "year", "OBS_AJ": "cadwr_actual"})[["site", "year", "cadwr_actual"]]

merged = obs.merge(cadwr, on=["site", "year"], how="outer", indicator=True)
merged = merged[merged["site"].isin(SITE_MAP.values())]
merged["diff"] = merged["volume"] - merged["cadwr_actual"]
merged["pct_diff"] = 100 * merged["diff"] / merged["cadwr_actual"]
merged["match"] = np.isclose(merged["volume"], merged["cadwr_actual"], rtol=0.01, atol=1.0)

print(f"Total site-years (2 sites): {len(merged)}")
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

obs_only = merged[merged["_merge"] == "left_only"]
cadwr_only = merged[merged["_merge"] == "right_only"]
print(f"\nSite-years in USBR obs only (no CA DWR value to compare): {len(obs_only)}")
print(f"Site-years in CA DWR only (no USBR obs to compare): {len(cadwr_only)}")

# --- plot: parity scatter, one point per site-year, colored by site ---
fig, ax = plt.subplots(figsize=(8, 6))
sites = sorted(both["site"].unique())
cmap = plt.get_cmap("tab10", max(len(sites), 2))
for i, s in enumerate(sites):
    sub = both[both["site"] == s]
    ax.scatter(sub["cadwr_actual"], sub["volume"], s=14, color=cmap(i), alpha=0.7, label=s)

lims = [0, max(both["cadwr_actual"].max(), both["volume"].max()) * 1.05]
ax.plot(lims, lims, color="0.5", lw=1, ls="--", zorder=0)
ax.set_xlim(lims)
ax.set_ylim(lims)
ax.set_xlabel("CA DWR reported Apr-Jul volume (KAF)")
ax.set_ylabel("Archive obs (USBR/Rodeo) volume (KAF)")
ax.set_title("Archive obs vs CA DWR-reported Apr-Jul volume, by site-year")
ax.legend(fontsize=9, loc="upper left", bbox_to_anchor=(1.02, 1))

r2 = np.corrcoef(both["cadwr_actual"], both["volume"])[0, 1] ** 2
rmse = np.sqrt(np.mean((both["volume"] - both["cadwr_actual"]) ** 2))
ax.text(
    0.03, 0.97, f"R² = {r2:.4f}\nRMSE = {rmse:.1f} KAF\nn = {len(both)}",
    transform=ax.transAxes, va="top", ha="left", fontsize=9,
)
fig.tight_layout()
out_png = os.path.join(os.path.dirname(__file__), "usbr_vs_cadwr_obs_parity.png")
fig.savefig(out_png, dpi=150)
print(f"\nSaved plot: {out_png}")
