# wsf-archive-assembly

Code and workflows for assembling the Water Supply Forecast benchmark archive.

## Repository Structure

* `get_data/` – Source-specific download and parsing workflows (see `get_data/README.md` for run order)
* `assemble_archive/` – Workflows that combine source datasets into benchmark archives
* `metadata/` – External inputs and site registries these workflows depend on (see `metadata/README.md`)
* `ARCHIVE_BUILD.md` – Pipeline stages and data sources

This repo contains the code that builds the archive, not the archive
itself. The archive (`wsf_archive_v1.0`) is deposited separately (DOI below).

## Paths

Scripts read and write under the archive root and take external inputs from
environment variables:

| Variable | Used for | Default |
|---|---|---|
| `WSF_ARCHIVE_ROOT` | archive root (`source_data/`, `proc_data/`) | `~/wsf_archive_v1.0` |
| `WSF_RODEO_DATA` | DrivenData WSF Rodeo competition data (`metadata.csv`) | CIROH HPC shared copy |
| `WSF_NRNI_CSV` | `PNW_unimpaired_Flows_1929-2018_07-2021.csv` (BPA NRNI) | CIROH HPC shared copy |
| `WSF_RAW_RFC_HCST_ROOT` | raw CBRFC/CNRFC hindcast files | `~/aw-ciroh/common/datasets/rfc_wsf` |

Site lookups use `metadata/WSF_Rodeo_ForecastLocations.csv` in this repo.
The raw CBRFC/CNRFC hindcasts were provided by the agencies and are not
redistributed; the archive holds the derived seasonal-volume quantiles. The
CA DWR Bulletin 120 history is in the archive's `source_data/cadwr_b120/`.

## Funding

This work was supported by a grant to the Colorado School of Mines through the NOAA Cooperative Institute for Research to Operations in Hydrology (CIROH), funded under NOAA Cooperative Agreement NA22NWS4320003 with the University of Alabama, and by U.S. Army Corps of Engineers award W26HM432051757 to the NSF National Center for Atmospheric Research (NCAR).

## License

Code: Apache-2.0 (`LICENSE`). Keep `NOTICE` with any copy or derivative. The archive is licensed separately (see its deposit).

Preprint:

> *A Community Evaluation Protocol for Seasonal Water Supply Forecasting in the Western U.S.*
> Joshua T. Sturtevant, Andrew W. Wood, Chris D. Frans, Ian M. Ferguson, and Thomas C. Pagano
> *Water Resources Research* (in review)
> https://essopenarchive.org/doi/pdf/10.22541/essoar.15005900/v2

## Related Resources

* **WSF Protocol Repository**: https://github.com/mines-ciroh/HydrometBench/tree/main/water_supply_fcst
* **Paper Reproducibility Repository**: https://github.com/mines-ciroh/wsf-protocol-paper
* **Benchmark Archive DOI**: TBD

## Repository Purpose

This repository contains the workflows used to assemble the Water Supply Forecast (WSF) benchmark archive, including source-data acquisition, parsing, quality control, harmonization, and archive generation. The resulting benchmark archive supports protocol development, forecast evaluation, and manuscript reproducibility efforts.
