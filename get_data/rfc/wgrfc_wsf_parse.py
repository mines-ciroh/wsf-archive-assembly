"""Parse WGRFC water supply bulletins (ESPFWR) for Pecos R nr Pecos, NM (PCON5), Mar-Jul.

Sources in wgrfc_esp/<year>/: Kris Lander's WGRFC archive (WY2003-2022), plus products
from the IEM AFOS archive (IEM_ESPFWR_*, download_wgrfc_iem.py) and weather.gov
(AWIPS_ESPFWR_*) that fill WY2019-2023.

The bulletin layout changed several times. Each file is classified by its own column
header, not by year:

  mp_max_min   (<= Feb 2018) MOST PROBABLE / REASONABLE MAXIMUM / REASONABLE MINIMUM,
               each as KAF followed by % of 30-yr average. Reasonable max/min are the
               10%/90% exceedance volumes (labelled so in the 2018 header).
  max30_70min  (Mar 2018 - 2020) 50% / % avg / MAX / 30% / 70% / MIN / 30-yr avg.
               Legend says MAX/MIN = 10%/90% exceedance from 2019; the 2018 legend says
               5%/95%, but the Mar/Apr 2018 values equal NRCS's coordinated 10/30/70/90%
               forecasts exactly, so they are read as 10/90 like the later vintages.
               Mar 2018 prints these four columns as % of average rather than KAF
               (reading them as KAF gives a 70% value above the median); rows like that
               are converted with the row's 30-yr average.
  p5_95        (2021+) 50% / % avg / 95% / 75% / 25% / 5% exceedance / 30-yr avg.
               10% and 90% exceedance are interpolated in standard-normal quantile
               space between the 5%-25% and 75%-95% pairs, and 30%/70% between the median
               and 25%/75% (quantile_method column).

Every row must reproduce its own printed % of average (median, and max/min where
printed) to within rounding, which rejects column-garbled rows (e.g. Jan 2018).
Re-issued products are skipped; where several products are valid for the same date,
the one(s) from the earliest issue day are used, taking the last of those (same-day
corrections supersede).

publicationDate and issueDate are the first of the month the bulletin is valid for
(what concat_wsf.all_methods.py keys on); the actual issue date is in bulletin_date.
"""

import glob
import os
import re
from datetime import datetime

import numpy as np
import pandas as pd
from scipy.stats import norm

ARCHIVE_ROOT = os.environ.get("WSF_ARCHIVE_ROOT", os.path.expanduser("~/wsf_archive_v1.0"))
BASE_DIR = f"{ARCHIVE_ROOT}/source_data/rfc/wgrfc_esp"
OUT_CSV = f"{ARCHIVE_ROOT}/source_data/rfc/wgrfc_wsf_pcon5.csv"

SITE_ROW = re.compile(r"PCON5|PECOS\s+(?:R\s+)?(?:NR|NEAR)[.,]?\s*(?:,\s*NM|PECOS)", re.IGNORECASE)
SKIP_PATTERNS = [r"_SFO\.txt$", r"SpringFloodOutlook", r"FloodOutlook"]
MONTHS = {m: i for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], 1)}

# weight to move from the 5% (95%) exceedance value toward the 25% (75%) value to reach 10% (90%)
Z_WEIGHT = (norm.ppf(0.95) - norm.ppf(0.90)) / (norm.ppf(0.95) - norm.ppf(0.75))
Z_25_TO_30 = (norm.ppf(0.70)) / (norm.ppf(0.75))  # 30%/70% from 25%/75%, normal-quantile space
PCT_TOL = 3.0  # percentage points; printed % of average is rounded to an integer


def month_num(s):
    return MONTHS.get(s[:3].upper())


def header_dates(text):
    """Return (valid_date, issue_date) as YYYY-MM-DD strings, or None."""
    valid = issue = None
    m = re.search(r"ISSUED\s+AS\s+OF\s+([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})", text, re.IGNORECASE)
    if m:
        valid = issue = f"{m.group(3)}-{month_num(m.group(1)):02d}-{int(m.group(2)):02d}"
    m = re.search(r"(?:VALID\s+)?FOR\s+([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})", text, re.IGNORECASE)
    if m and month_num(m.group(1)):
        valid = f"{m.group(3)}-{month_num(m.group(1)):02d}-{int(m.group(2)):02d}"
    m = re.search(r"(?<!-)\bISSUED\s+([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})", text, re.IGNORECASE)
    if m and month_num(m.group(1)):
        issue = f"{m.group(3)}-{month_num(m.group(1)):02d}-{int(m.group(2)):02d}"
    return valid, issue


def detect_format(text):
    if re.search(r"95%\s+75%\s+25%\s+5%", text):
        return "p5_95"
    if re.search(r"MAX\s+30%\s+70%\s+MIN", text):
        return "max30_70min"
    if re.search(r"REASONABLE", text, re.IGNORECASE):
        return "mp_max_min"
    return None


def pct_ok(value, pct, avg):
    return abs(100.0 * value / avg - pct) <= max(PCT_TOL, 0.02 * pct)


def parse_row(line, fmt):
    """Return dict with period and f10/f30/f50/f70/f90, or (None, reason)."""
    m = re.search(r"\b(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP)-(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP)\b", line)
    if m and "MAR-JUL" in line.upper():
        period = ("MAR", "JUL")
        tail = line.upper().split("MAR-JUL", 1)[1]
    elif m:
        period = (m.group(1), m.group(2))
        tail = line[m.end():]
    else:
        pm = re.search(r"\(([12])\)", line)
        if not pm:
            return None, "no period"
        period = ("APR", "SEP") if pm.group(1) == "1" else ("MAR", "JUL")
        tail = line[pm.end():]
    nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", tail)]
    if len(nums) < 7:
        return None, f"only {len(nums)} numbers"
    out = {"period": period, "f30": np.nan, "f70": np.nan, "quantile_method": "native"}

    if fmt == "mp_max_min":
        p50, p50pct, vmax, maxpct, vmin, minpct, avg = nums[:7]
        if not (pct_ok(p50, p50pct, avg) and pct_ok(vmax, maxpct, avg) and pct_ok(vmin, minpct, avg)):
            return None, f"% of avg does not reproduce values {nums[:7]}"
        out.update(f10=vmax, f50=p50, f90=vmin)

    elif fmt == "max30_70min":
        p50, p50pct, vmax, v30, v70, vmin, avg = nums[:7]
        if not pct_ok(p50, p50pct, avg):
            return None, f"median % of avg mismatch {nums[:7]}"
        if not (vmax >= v30 >= p50 >= v70 >= vmin):
            as_kaf = [round(v * avg / 100.0, 1) for v in (vmax, v30, v70, vmin)]
            if as_kaf[0] >= as_kaf[1] >= p50 >= as_kaf[2] >= as_kaf[3]:
                vmax, v30, v70, vmin = as_kaf
                out["quantile_method"] = "native_pct_of_avg"
            else:
                return None, f"non-monotone in both KAF and % readings {nums[:7]}"
        out.update(f10=vmax, f30=v30, f50=p50, f70=v70, f90=vmin)

    elif fmt == "p5_95":
        p50, p50pct, e95, e75, e25, e5, avg = nums[:7]
        if not pct_ok(p50, p50pct, avg):
            return None, f"median % of avg mismatch {nums[:7]}"
        if not (e5 >= e25 >= p50 >= e75 >= e95):
            return None, f"non-monotone {nums[:7]}"
        out.update(f10=e5 + Z_WEIGHT * (e25 - e5), f50=p50, f90=e95 + Z_WEIGHT * (e75 - e95),
                   f30=p50 + Z_25_TO_30 * (e25 - p50), f70=p50 + Z_25_TO_30 * (e75 - p50),
                   quantile_method="z_interp_from_5_25_75_95")
    return out, None


def parse():
    files = sorted(glob.glob(os.path.join(BASE_DIR, "**", "*.txt"), recursive=True))
    print(f"Found {len(files)} files under {BASE_DIR}")
    cands, log = [], []
    for fpath in files:
        fname = os.path.basename(fpath)
        if any(re.search(p, fname, re.IGNORECASE) for p in SKIP_PATTERNS):
            continue
        with open(fpath, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
        if re.search(r"RE.?ISSUED", text, re.IGNORECASE):
            log.append((fname, "re-issued product, skipped"))
            continue
        valid, issue = header_dates(text)
        fmt = detect_format(text)
        if not valid or not fmt:
            log.append((fname, f"no header date/format (valid={valid}, fmt={fmt})"))
            continue
        # IEM filenames carry HHMM; use it to order same-day corrections
        hhmm = re.search(r"_(\d{4})\.txt$", fname) if fname.startswith("IEM_") else None
        rows = [l for l in text.splitlines() if SITE_ROW.search(l)]
        for line in rows:
            rec, why = parse_row(line, fmt)
            if rec is None:
                log.append((fname, why))
                continue
            if rec["period"] != ("MAR", "JUL"):
                continue
            cands.append({
                "valid": valid[:8] + "01", "bulletin_date": issue or valid,
                "order": hhmm.group(1) if hhmm else "0000", "file": fname, "fmt": fmt, **rec})
            break  # first Pecos nr Pecos row in the product

    c = pd.DataFrame(cands)
    # keep the earliest issue day per valid month; within that day the last product
    c = c.sort_values(["valid", "bulletin_date", "order"])
    first_day = c.groupby("valid")["bulletin_date"].transform("min")
    c = c[c["bulletin_date"] == first_day]
    dup = c[c.duplicated("valid", keep=False)]
    for v, g in dup.groupby("valid"):
        vals = g[["f10", "f50", "f90"]].round(2).drop_duplicates()
        if len(vals) > 1:
            print(f"  NOTE {v}: same-day products differ, keeping last:\n{g[['file', 'f10', 'f50', 'f90']]}")
    c = c.groupby("valid").tail(1)

    df = pd.DataFrame({
        "site": "PCON5",
        "publicationDate": c["valid"], "issueDate": c["valid"],
        "forecastPeriodStart": c["valid"].str[:4] + "-03-01",
        "forecastPeriodEnd": c["valid"].str[:4] + "-07-31",
        "forecast_90": c["f90"].round(2), "forecast_70": c["f70"].round(2), "forecast_50": c["f50"],
        "forecast_30": c["f30"].round(2), "forecast_10": c["f10"].round(2),
        "source": "WGRFC_official", "bulletin_date": c["bulletin_date"],
        "quantile_method": c["quantile_method"], "raw_file": c["file"],
    }).sort_values("issueDate")
    df.to_csv(OUT_CSV, index=False)

    print(f"\nRejected/skipped rows ({len(log)}):")
    for f, why in log:
        print(f"  {f}: {why}")
    print(f"\nSaved {len(df)} rows to {OUT_CSV}")
    return df


if __name__ == "__main__":
    parse()
