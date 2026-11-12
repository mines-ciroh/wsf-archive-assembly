# metadata/

Reference files used by `get_data/`/`assemble_archive/` and by
`wsf-protocol-paper`'s `fig_scripts/`: site registry and basin/RFC GIS files.
Not a copy of the benchmark archive.

Broader USBR/WSF Rodeo competition data (obs labels, metadata, supplementary
NRCS data, winning-team materials) is mirrored for reproducibility in
[HydrometBench](https://github.com/mines-ciroh/HydrometBench/tree/main/water_supply_fcst/wsf_rodeo_data),
not duplicated here.

## metadata/raw_external/

Externally-provided source files, unmodified.

- `wsf_rodeo_metadata.usbr_raw.csv` — 2024 USBR WSF Rodeo site metadata,
  byte-for-byte as published in
  [HydrometBench](https://github.com/mines-ciroh/HydrometBench/blob/main/water_supply_fcst/wsf_rodeo_data/hindcast_stage/metadata.csv).
- `gis/wsf_rodeo_forecast_with_ha.gpkg` — basin delineation polygons,
  USBR Rodeo-provided.
- `gis/rfc_us.{shp,dbf,shx,prj}` — NWS RFC boundary polygons, public NOAA data.

## WSF_Rodeo_ForecastLocations.csv

Site registry for the 26 study basins (USGS ID/name/lat-lon, NRCS ID/name,
RFC ID/name/region), read directly by `get_data/rfc/concat_rfc_wsf.py`
(`LOOKUP_FILE`) and by `wsf-protocol-paper/fig_scripts/`.

**Provenance:** `site_id`/`usgs_id`/lat-lon/`rfc_*` columns match
`raw_external/wsf_rodeo_metadata.usbr_raw.csv`. Additional columns (NRCS
triplet IDs, per-agency elevation/lat/lon, source URLs, comments) are
manually curated.

Corrections applied relative to the upstream file (diff against
`raw_external/wsf_rodeo_metadata.usbr_raw.csv`):

- Colville R at Kettle Falls (12409000): RFC Name = "Colville River at
  Kettle Falls", RFC Site ID = KTFW1, RFC = NWRFC (see also the manual
  override in `concat_rfc_wsf.py`).
- Pueblo Reservoir Inflow (07099400): RFC value `ARBRFC` corrected to `ABRFC`.
- Sweetwater River near Alcova (06639000): RFC Site ID = SWEW4,
  RFC = MBRFC. No RFC forecast data for this site is in the archive.

Scripts read this copy. The editable original lives on the CIROH HPC at
`/beegfs/sets/aw-ciroh/common/datasets/wsf_rodeo_data/WSF_Rodeo_ForecastLocations.csv`;
re-sync this copy if that file changes.

## CA DWR Bulletin 120 raw data

CA DWR's raw forecast history (provided by CA DWR) and its
provenance note live in the archive at `source_data/cadwr_b120/`, not in
this repo — same as every other source's raw data.

B120 covers Folsom (American R) and Friant (San Joaquin) but not Merced at
Pohono Bridge (11266500): per CA DWR, Merced/Pohono is
only a secondary forecast point for them (less rigorous methodology, not
digitized), unlike Folsom/Friant's primary-reservoir status. NRCS forecasts
Merced instead (f50 only, no uncertainty quantiles there).

## Observation data

`source_data/obs/` in the archive traces to the
[DrivenData WSF Hindcast competition](https://www.drivendata.org/competitions/257/reclamation-water-supply-forecast-hindcast/data/).
Not copied here; already public and citable by URL.

CA DWR also separately provided their own observed Apr-Jul flow for the American River below Folsom (AMF/11446220) and San
Joaquin below Friant (SBF/11251000). This and its provenance note live in
the archive at `source_data/obs/cadwr_raw/`, not in this repo.
