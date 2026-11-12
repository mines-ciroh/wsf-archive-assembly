# How the WSF benchmark archive is built

## Pipeline stages

```
external sources  →  get_data/<source>/  →  assemble_archive/  →  wsf_obs_with_all_forecasts.nc
                      (download + parse)     (harmonize + combine)
```

1. `get_data/<source>/` — download/parse scripts per source. Output lands
   in the archive's `source_data/<source>/`, native format/units.
2. `assemble_archive/concat_wsf.all_methods.py` — converts every source to
   common conventions (exceedance probability, KAF, f10/f30/f50/f70/f90,
   WY filtering) and writes `wsf_obs_with_all_forecasts.nc`. It also derives
   the climatological reference forecast from `obs`: `climo` (site, year,
   percentile), `climo_mean` and `climo_n_years` (site, year). For each target
   year in WY1994-2023, the sample is the observations from that period with
   the target year left out.
3. `metadata/` — reference inputs to stages 1-2 (site registry, basin/RFC
   boundaries, CA DWR raw data). See `metadata/README.md`.

## Data sources

| Source | `get_data/` scripts | Output | Provenance |
|---|---|---|---|
| Naturalized flow observations | `obs/proc_obs.py` | `source_data/obs/*.csv` | [DrivenData WSF Hindcast competition](https://www.drivendata.org/competitions/257/reclamation-water-supply-forecast-hindcast/data/) |
| NRCS official forecasts | `nrcs/get_wsf_nrcs.sh`, `parse_nrcs_fcsts.py`, `parse_nrcs_obs_concat.py` | `source_data/nrcs/*.csv` | NRCS public web services |
| RFC official + hindcast | `rfc/*` (see RFC sources below), then `rfc/concat_rfc_wsf.py` | `source_data/rfc/*.csv` | NWS RFC public archives, NWS text products (IEM AFOS archive), and hindcasts provided by CBRFC and CNRFC; site lookup via `metadata/WSF_Rodeo_ForecastLocations.csv` |
| CA DWR Bulletin 120 | none — provided directly | `source_data/cadwr_b120/cadwr_b120_wsf.csv` | Provided by CA DWR; raw data + provenance note live in the archive's `source_data/cadwr_b120/`. `ca_dwr/scrape_cdec_b120_wsf.py` is an earlier CDEC-scrape script, superseded by this more complete record. |
| WSF Rodeo top-5 hindcasts | `usbr_wsfr/parse_wsfr_solutions.py` | `source_data/rodeo_winners/*.csv` | 2024 USBR WSF Rodeo competition results |

## RFC sources

"RFC official" is the forecast the RFC published: published or coordinated
bulletins where they survive, otherwise the RFC's operational ESP product.
Where two products cover the same site and date, `concat_rfc_wsf.py` keeps
one by the preference order below. RFC products are used only for the WSF
Rodeo target season of each site; other seasons are dropped.

| RFC | Product | Years (WY) | Script | Quantiles |
|---|---|---|---|---|
| CBRFC | Official forecasts, coordinated columns of `wsup/graph/esptxt.py` (preferred) | 2009+ | `download_cbrfc.py` | 10/30/50/70/90 or 10/50/90 |
| CBRFC | Water Supply Outlook: PDFs (2004-2007), Wayback snapshots of `wsup/pub2/outlook.php` (2008) | 2004-2008 | `backfill_cbrfc_wsf_2004_2010.py` | 10/50/90 |
| CBRFC | ESP reforecasts, first of month, unregulated (provided by CBRFC) | 1981-2021 | `parse_cbrfc_hcst.py` | from ESP members |
| CNRFC | Water Supply Outlook bulletin, AFOS `ESPRSA` via IEM (preferred) | 2004-2012 | `download_cnrfc_iem_backfill.py` | 10/50/90 |
| CNRFC | Tabular ESP product, `ensembleProductTabular.php` | 2011+ | `download_cnrfc.py` | 10/50/90 published; 30/70 from 25/75 |
| CNRFC | HEFS water supply hindcast volume statistics (provided by CNRFC) | 1990-2023 | `parse_cnrfc_hcst.py` | 10/50/90 published; 30/70 from 25/75 |
| NWRFC | Coordinated water supply bulletin, `ws/wsFcstText.cgi` (preferred) | 2005-2013 | `download_nwrfc_wsfcsttext.py` | Maximum/Minimum = 5%/95% through Mar 2011, scaled to 10/90 under the product's normal error distribution; 10/90 from Dec 2011 |
| NWRFC | ESP water supply forecasts, `water_supply/ws_text.cgi`, `natural/plot/nat_text.cgi` | 2005+ | `download_nwrfc.py` | 10/30/50/70/90; in years published as 10/25/50/75/90, 30/70 from 25/75 |
| NWRFC | ESP aggregates for points without a volumetric product | 2015+ | `parse_nwrfc_esp.py` | 10/30/50/70/90 |
| WGRFC | Water supply bulletins (AFOS `ESPFWR`), Pecos nr Pecos, Mar-Jul (preferred over CBRFC-hosted PCON5) | 2003-2023 | `wgrfc_wsf_parse.py`, `download_wgrfc_iem.py` | 10/50/90 (2018-2020: 10/30/50/70/90); 2021+ published 5/25/50/75/95, f10/f90 and f30/f70 interpolated |
| MBRFC | Water supply bulletins (AFOS `ESPKRF`) | 2017+ | `mbrfc_wsf_parse.py` | Apr-Sep only; not used |

Derived quantiles are interpolated in standard-normal quantile space between the
adjacent published levels (e.g. f30 = f50 + z(0.70)/z(0.75) x (f25 - f50)).

Raw hindcast inputs are read from `$WSF_RAW_RFC_HCST_ROOT` (default
`~/aw-ciroh/common/datasets/rfc_wsf`) and are not redistributed; only the
derived Apr-Jul volume quantiles are.
