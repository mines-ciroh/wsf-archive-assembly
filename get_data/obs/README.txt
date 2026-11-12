Data from: https://www.drivendata.org/competitions/257/reclamation-water-supply-forecast-hindcast/data/

These USBR/Rodeo competition volumes are the archive's observation record
(see `../README.md`). For the 22 sites NRCS also covers, this matches NRCS's
own reported adjusted volume almost everywhere; for the 2 sites CA DWR
separately provided obs for, agreement is also strong (see `qc_checks/`).

2 of the 26 archive sites have no independent obs to cross-check against
either source: Merced R at Pohono Bridge (11266500, NRCS issues forecasts
here but doesn't report an actual volume for it) and Ross Reservoir
(12175000, outside the Rodeo competition's site set, no NRCS/CA DWR
benchmark at all).

proc_obs.py's raw inputs (cross_validation_labels.csv,
prior_historical_labels.csv) and its own output
(all_seasonal_naturalized_flow.csv) are gitignored here -- they duplicate the
archive's own source_data/obs/, and the raw inputs are also mirrored
publicly in HydrometBench. Needed locally to run proc_obs.py; not committed.