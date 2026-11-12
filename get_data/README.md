# get_data — run order per source

Each source is independent of the others; run in the order listed to produce
the file `assemble_archive/concat_wsf.all_methods.py` reads. See
`../ARCHIVE_BUILD.md` for the full pipeline and provenance.

| Source | Run order | Final output |
|---|---|---|
| Naturalized flow obs (the archive obs record) | `obs/proc_obs.py` | `source_data/obs/all_seasonal_naturalized_flow.csv` |
| NRCS official (forecasts + NRCS's own verification obs) | `nrcs/get_wsf_nrcs.sh` → `nrcs/parse_nrcs_fcsts.py` → `nrcs/get_obs_nrcs.sh` → `nrcs/parse_nrcs_obs_concat.py` | `source_data/nrcs/nrcs_fcst_obs.all_sites_yrs.wsf_rodeo.csv` |
| RFC official + hindcast | per-RFC scripts in `rfc/` (listed in `../ARCHIVE_BUILD.md`, "RFC sources"), then `rfc/concat_rfc_wsf.py` | `source_data/rfc/all_rfc_wsf.csv` |
| CA DWR Bulletin 120 | none — CSV provided directly by CA DWR | `source_data/cadwr_b120/cadwr_b120_wsf.csv` |
| WSF Rodeo top-5 hindcasts | `usbr_wsfr/parse_wsfr_solutions.py` | `source_data/rodeo_winners/wsf_rodeo_solutions.amjj_wsf.csv` |
