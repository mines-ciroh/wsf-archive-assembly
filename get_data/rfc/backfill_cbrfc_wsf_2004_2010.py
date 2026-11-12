"""Backfill CBRFC Water Supply Outlook forecasts for WY2004-2010, Jan/Feb/Mar/Apr
issues, for 7 sites not otherwise covered by the ESP-text-based cbrfc_wsf.csv
pipeline (download_cbrfc.py) before ~2009.

Two source eras, stitched into one output CSV:

1. 2004-2007: static PDF bulletins at a stable URL pattern
   https://www.cbrfc.noaa.gov/wsup/water/{basin}/{year}/{basin}_{mon}.pdf
   (basin in uc|gb|lc, mon in ja|fe|ma|ap). Parsed with pdfplumber from the
   "Specific Site Forecasts" tables (columns: Stream, Station, Most Probable,
   Percent Avg/Med, Reas. Max, Reas. Min).

2. 2008-2010: the PDF pattern 404s (site redesign). The successor page
   https://www.cbrfc.noaa.gov/wsup/pub2/outlook.php?region=..&month=..&year=..
   still resolves live but the site's backend database has since dropped the
   historical numeric "Specific Site Forecasts" tables for these old
   month/year combos (narrative text only, tables empty) -- confirmed by
   direct request as of 2026-09-28. The numbers survive only in Wayback
   Machine snapshots crawled while the backend still had them (crawls from
   2013 onward reliably do; some regions/months have no earlier capture).
   This script queries the CDX API for the earliest 200-status snapshot of
   each (region, year, month) combo and parses the archived HTML, which
   explicitly labels columns "Forecast Period / 50% Exceedance / Percent
   Average / 10% Exceedance / 90% Exceedance" -- i.e. this later web format
   states the exceedance convention outright, confirming f10=wet/high,
   f90=dry/low, consistent with the PDF-era "Reas. Max"/"Reas. Min" columns.

Sites covered (RFC id, USGS id, basin/region code per era):
    DIRC2 09050700  BLUE / DILLON RES          uc-pdf, uc-outlook
    DRGC2 09361500  ANIMAS - DURANGO           uc-pdf, sj-outlook
    TPIC2 09109000  TAYLOR / TAYLOR PARK RES   uc-pdf, uc-outlook
    RURC2 09080190  FRYING PAN / RUEDI RES     uc-pdf, uc-outlook
    MBLC2 09251000  YAMPA / MAYBELL, NR        uc-pdf, gn-outlook
    OAWU1 10128500  WEBER / OAKLEY, NR         gb-pdf, sl-outlook
    VIRU1 09406000  VIRGIN / VIRGIN            lc-pdf, vg-outlook

GBRW4 (09211150, Green R - Fontenelle Res inflow) was investigated and
EXCLUDED: it never appears in a "Specific Site Forecasts" table with
max/min quantiles in the PDF era. It only appears (a) in the "Flood Control
Forecasts" map as a most-probable-only percent-of-average inflow figure, and
(b) in the "End of Month Reservoir Contents" table, which is *usable
capacity / EOM contents / percent usable capacity* -- static reservoir
storage, not a forecast at all. Fabricating f10/f90 for it would violate the
no-fabricated-quantiles rule, so it is dropped, never relabeled.

Output: $ARCHIVE_ROOT/source_data/rfc/cbrfc_wsf.outlook_pdf_2004_2010.csv
Raw PDFs cached under: $ARCHIVE_ROOT/source_data/rfc/cbrfc_outlook_pdf/
Raw wayback HTML cached under: $ARCHIVE_ROOT/source_data/rfc/cbrfc_outlook_wayback_html/
"""

import os
import re
import time
import json
import glob
import html
from datetime import datetime

import pandas as pd

ARCHIVE_ROOT = os.environ.get("WSF_ARCHIVE_ROOT", os.path.expanduser("~/wsf_archive_v1.0"))
RFC_DIR = f"{ARCHIVE_ROOT}/source_data/rfc"
PDF_DIR = f"{RFC_DIR}/cbrfc_outlook_pdf"
WAYBACK_DIR = f"{RFC_DIR}/cbrfc_outlook_wayback_html"
OUT_CSV = f"{RFC_DIR}/cbrfc_wsf.outlook_pdf_2004_2010.csv"

MON_CODE = {1: "ja", 2: "fe", 3: "ma", 4: "ap"}
PDF_YEARS = [2004, 2005, 2006, 2007]          # direct PDF pattern only works these years
WAYBACK_YEARS = [2008, 2009, 2010]            # PDF pattern 404s; use wayback outlook.php
MONTHS = [1, 2, 3, 4]

# site: (usgs_id, pdf_basin, wayback_region, match substrings for the row)
SITES = {
    "DIRC2": dict(usgs_id="09050700", pdf_basin="uc", wb_region="uc",
                  stream="BLUE", station="DILLON RES"),
    "DRGC2": dict(usgs_id="09361500", pdf_basin="uc", wb_region="sj",
                  stream="ANIMAS", station="DURANGO"),
    "TPIC2": dict(usgs_id="09109000", pdf_basin="uc", wb_region="uc",
                  stream="TAYLOR", station="TAYLOR PARK RES"),
    "RURC2": dict(usgs_id="09080190", pdf_basin="uc", wb_region="uc",
                  stream="FRYING PAN", station="RUEDI RES, BASALT, NR"),
    "MBLC2": dict(usgs_id="09251000", pdf_basin="uc", wb_region="gn",
                  stream="YAMPA", station="MAYBELL, NR"),
    "OAWU1": dict(usgs_id="10128500", pdf_basin="gb", wb_region="sl",
                  stream="WEBER", station="OAKLEY, NR"),
    "VIRU1": dict(usgs_id="09406000", pdf_basin="lc", wb_region="vg",
                  stream="VIRGIN", station="VIRGIN"),
}
# GBRW4 / 09211150 deliberately excluded -- see module docstring.


# --------------------------------------------------------------------------
# Era 1: 2004-2007 static PDFs
# --------------------------------------------------------------------------

def download_pdfs():
    import requests

    os.makedirs(PDF_DIR, exist_ok=True)
    basins = sorted({s["pdf_basin"] for s in SITES.values()})
    for year in PDF_YEARS:
        for basin in basins:
            for m, mon in MON_CODE.items():
                fn = os.path.join(PDF_DIR, f"{basin}_{mon}_{year}.pdf")
                if os.path.exists(fn) and os.path.getsize(fn) > 0:
                    continue
                url = f"https://www.cbrfc.noaa.gov/wsup/water/{basin}/{year}/{basin}_{mon}.pdf"
                print(f"GET {url}")
                r = requests.get(url, timeout=20)
                if r.status_code == 200 and r.headers.get("content-type", "").startswith("application/pdf"):
                    with open(fn, "wb") as f:
                        f.write(r.content)
                else:
                    print(f"  FAILED status={r.status_code}")
                time.sleep(1)


def _row_regexes(stream, station):
    # Row layout: "<STREAM> <STATION> v1 v2 v3 v4" where v1=MostProbable(f50),
    # v2=%avg/med, v3=Reas.Max(f10, wet), v4=Reas.Min(f90, dry). A leading
    # footnote glyph "(cid:NN)" may be glued directly onto the station text
    # in 2004-2005 PDFs (pdfplumber renders footnote symbols as literal
    # "(cid:NN)" tokens). Station-only rows (stream printed once on an
    # earlier row, then omitted on subsequent rows for the same stream --
    # confirmed for MAYBELL, NR under YAMPA in every 2004-2007 uc_ap/ja/fe/ma
    # PDF checked: the stream token "YAMPA" never repeats on the MAYBELL
    # line) must also be tried even when a stream name is configured, since
    # a site can appear either way depending on table layout. We try the
    # full "<STREAM> <STATION> ..." pattern first (more specific / avoids
    # false positives when the same station name is reused across streams)
    # and fall back to the station-only pattern if that fails.
    num = r"([\d,]+\.?\d*)"
    patterns = []
    if stream:
        patterns.append(
            rf"^{re.escape(stream)}\s+(?:\(cid:\d+\))?{re.escape(station)}\s+{num}\s+{num}\s+{num}\s+{num}\s*$"
        )
    patterns.append(
        rf"^(?:\(cid:\d+\))?{re.escape(station)}\s+{num}\s+{num}\s+{num}\s+{num}\s*$"
    )
    return [re.compile(p) for p in patterns]


def parse_pdfs():
    import pdfplumber

    rows = []
    diagnostics = []
    for year in PDF_YEARS:
        for m, mon in MON_CODE.items():
            for rfc_id, s in SITES.items():
                basin = s["pdf_basin"]
                fn = os.path.join(PDF_DIR, f"{basin}_{mon}_{year}.pdf")
                if not os.path.exists(fn):
                    diagnostics.append((rfc_id, year, m, "missing_pdf"))
                    continue
                rxs = _row_regexes(s["stream"], s["station"])
                found = None
                with pdfplumber.open(fn) as pdf:
                    for page in pdf.pages:
                        text = page.extract_text() or ""
                        if "SPECIFIC" not in text.upper() and s["station"].split(",")[0] not in text.upper():
                            continue
                        lines = [ln.strip() for ln in text.split("\n")]
                        for ln in lines:
                            for rx in rxs:
                                mobj = rx.match(ln)
                                if mobj:
                                    found = mobj.groups()
                                    break
                            if found:
                                break
                        if found:
                            break
                if not found:
                    diagnostics.append((rfc_id, year, m, "row_not_found"))
                    continue
                f50, pct, f10, f90 = [float(v.replace(",", "")) for v in found]
                # Period check for VIRU1: confirmed directly from the LC PDF's
                # own narrative text for EVERY (basin, year, month) combo in
                # 2004-2007 -- the "VIRGIN RIVER" section always states
                # "April-July stream flow forecasts for the Virgin River are
                # as follows" immediately before the numbers, even in months
                # (e.g. Jan/Feb 2004) where the Specific Site Forecasts table
                # itself carries no footnote glyph on the VIRGIN row and the
                # table's generic caption says "January/February through May
                # volume forecasts (except where noted)". The glyph
                # ("(cid:77)"/"(cid:190)", glued to the row or standing alone
                # on the preceding line) appears inconsistently across
                # years/PDF-generator versions and cannot be relied on as a
                # gate -- it under-selects true April-July rows (confirmed:
                # 2004-01 and 2004-02 VIRU1 have no glyph at all but are
                # April-July per the narrative). So VIRU1 rows are always
                # accepted as April-July; no separate gate is applied here.
                rows.append({
                    "site": rfc_id,
                    "usgs_id": s["usgs_id"],
                    "publicationDate": f"{year}-{m:02d}-01",
                    "issueDate": f"{year}-{m:02d}-01",
                    "bulletin_date": f"{year}-{m:02d}-01",
                    "forecastPeriodStart": f"{year}-04-01",
                    "forecastPeriodEnd": f"{year}-07-31",
                    "forecast_90": f90,
                    "forecast_70": None,
                    "forecast_50": f50,
                    "forecast_30": None,
                    "forecast_10": f10,
                    "source": "CBRFC_official",
                    "coordinated": True,
                    "raw_source": "pdf",
                })
    return pd.DataFrame(rows), diagnostics


# --------------------------------------------------------------------------
# Era 2: 2008-2010 via Wayback Machine snapshots of pub2/outlook.php
# --------------------------------------------------------------------------

def _requests_get_retry(url, tries=3, timeout=20, **kw):
    # web.archive.org is flaky from this host: connections are refused
    # intermittently (confirmed via repeated curl/requests probes on
    # 2026-09-28 -- CDX and page fetches alike sometimes connect
    # immediately and sometimes hard-refuse for a few seconds), not
    # rate-limited in the usual HTTP-429 sense. Retry with a short capped
    # backoff rather than treating a single failure as "no snapshot" --
    # but keep tries/backoff small, since with up to a few candidate
    # snapshots per (region, year, month) combo x up to 60 combos, an
    # aggressive retry budget here turns into a multi-hour run whenever the
    # flakiness streak is long (observed directly during development: a
    # single combo took >5 min under a 6-try/20s-cap policy).
    import requests

    last_exc = None
    for attempt in range(tries):
        try:
            r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=timeout, **kw)
            return r
        except requests.exceptions.RequestException as e:
            last_exc = e
            time.sleep(min(2 ** attempt, 5))
    raise last_exc


def _cdx_captures(region, year, month, limit=5):
    url = (
        "https://web.archive.org/cdx/search/cdx"
        f"?url=cbrfc.noaa.gov/wsup/pub2/outlook.php?month={month}%26region={region}%26year={year}"
        f"&output=json&filter=statuscode:200&limit={limit}"
    )
    r = _requests_get_retry(url)
    r.raise_for_status()
    data = r.json()
    if len(data) < 2:
        return []
    return [row[1] for row in data[1:]]  # timestamps, earliest first


def download_wayback():
    os.makedirs(WAYBACK_DIR, exist_ok=True)
    regions = sorted({s["wb_region"] for s in SITES.values()})
    for region in regions:
        for year in WAYBACK_YEARS:
            for month in MONTHS:
                fn = os.path.join(WAYBACK_DIR, f"{region}_{month}_{year}.html")
                if os.path.exists(fn) and os.path.getsize(fn) > 0:
                    continue
                if os.path.exists(fn + ".missing"):
                    continue
                try:
                    timestamps = _cdx_captures(region, year, month)
                except Exception as e:
                    print(f"CDX lookup failed {region} {year}-{month}: {e}")
                    time.sleep(1)
                    continue
                time.sleep(1)
                if not timestamps:
                    print(f"No wayback capture for region={region} year={year} month={month}")
                    open(fn + ".missing", "w").close()
                    continue
                # Try snapshots earliest-first; some early captures can be
                # error pages or otherwise missing the site-forecast table
                # (e.g. mid-crawl redesign), so fall back to the next one.
                saved = False
                for ts in timestamps:
                    wb_url = (
                        f"https://web.archive.org/web/{ts}/"
                        f"http://www.cbrfc.noaa.gov/wsup/pub2/outlook.php?region={region}&month={month}&year={year}"
                    )
                    try:
                        r = _requests_get_retry(wb_url)
                    except Exception as e:
                        print(f"FAILED (after retries) {wb_url}: {e}")
                        time.sleep(1)
                        continue
                    if r.status_code == 200 and re.search(r'id=[A-Z0-9]{5}&', r.text):
                        with open(fn, "w") as f:
                            f.write(r.text)
                        print(f"Saved {fn} (ts={ts})")
                        saved = True
                        break
                    else:
                        print(f"  snapshot ts={ts} has no site table, trying next")
                    time.sleep(1)
                if not saved:
                    print(f"No usable wayback capture (table missing in all snapshots) for region={region} year={year} month={month}")
                    open(fn + ".missing", "w").close()


# Row layout confirmed directly from the raw archived HTML (2013 crawl of
# outlook.php?region=uc&month=4&year=2008, see REVISION_NOTE/backfill report):
#   <a href="...id={SITE}&...">{name}</a><td class="wsup...">{Period}
#   <td class="wsup...">{90% Exceedance}<td class="wsup..."><i><b>{50% Exceedance}</b></i>
#   <td class="wsup..."><b>{Percent Average}</b><td class="wsup...">{10% Exceedance}</tr>
# i.e. column order is 90%, 50%, %avg, 10% (NOT 50%/%avg/10%/90% as in the
# 2004-2007 PDF-era table) -- confirmed against the page's own header row
# ("90% Exceedance Volume" / "50% Exceedance Volume" / "Percent Average" /
# "10% Exceedance Volume") and against the exceedance-convention definitions
# section further down the same page (10% exceedance = old "Reasonable
# Maximum", 90% exceedance = old "Reasonable Minimum" -- same convention as
# the PDF era, just relabeled).
_WAYBACK_ROW_RE = re.compile(
    r'id=([A-Z0-9]{5})&[^>]*>\s*[^<]*</a>'
    r'<td class="wsup\w*">([A-Za-z\-]+)'
    r'<td class="wsup\w*">([\d,]+\.?\d*)'
    r'<td class="wsup\w*"><i><b>([\d,]+\.?\d*)</b></i>'
    r'<td class="wsup\w*"><b>([\d,]+\.?\d*)</b>'
    r'<td class="wsup\w*">([\d,]+\.?\d*)</tr>'
)

# RFC site id (as it appears in the outlook.php href) -> our rfc_id key.
# Confirmed by direct inspection of the archived HTML that these are the
# same 5-character site codes as the PDF era (DIRC2, TPIC2, etc.) -- the
# outlook.php id= parameter is literally the RFC site code.
_WAYBACK_SITE_ID = {s_id: s_id for s_id in SITES}


def parse_wayback():
    rows = []
    diagnostics = []
    for year in WAYBACK_YEARS:
        for month in MONTHS:
            for rfc_id, s in SITES.items():
                region = s["wb_region"]
                fn = os.path.join(WAYBACK_DIR, f"{region}_{month}_{year}.html")
                if not os.path.exists(fn):
                    diagnostics.append((rfc_id, year, month, "missing_wayback_html"))
                    continue
                raw = open(fn).read()
                found = None
                for m in _WAYBACK_ROW_RE.finditer(raw):
                    site_id, period, f90, f50, pct, f10 = m.groups()
                    if site_id != rfc_id:
                        continue
                    if period != "April-July":
                        # A site can appear with more than one period row
                        # (e.g. a March-June residual alongside the
                        # April-July full-period row); only the latter is
                        # our predictand.
                        continue
                    found = (f90, f50, pct, f10)
                    break
                if not found:
                    diagnostics.append((rfc_id, year, month, "row_not_found"))
                    continue
                f90, f50, pct, f10 = [float(v.replace(",", "")) for v in found]
                rows.append({
                    "site": rfc_id,
                    "usgs_id": s["usgs_id"],
                    "publicationDate": f"{year}-{month:02d}-01",
                    "issueDate": f"{year}-{month:02d}-01",
                    "bulletin_date": f"{year}-{month:02d}-01",
                    "forecastPeriodStart": f"{year}-04-01",
                    "forecastPeriodEnd": f"{year}-07-31",
                    "forecast_90": f90,
                    "forecast_70": None,
                    "forecast_50": f50,
                    "forecast_30": None,
                    "forecast_10": f10,
                    "source": "CBRFC_official",
                    "coordinated": True,
                    "raw_source": "wayback_outlook_php",
                })
    return pd.DataFrame(rows), diagnostics


# --------------------------------------------------------------------------

OUT_COLS = ["site", "publicationDate", "issueDate", "forecastPeriodStart",
            "forecastPeriodEnd", "forecast_90", "forecast_70", "forecast_50",
            "forecast_30", "forecast_10", "source", "bulletin_date", "coordinated"]


def main(parse_only=False):
    if not parse_only:
        download_pdfs()
        download_wayback()
    df_pdf, diag_pdf = parse_pdfs()
    df_wb, diag_wb = parse_wayback()
    print(f"PDF era rows: {len(df_pdf)}; diagnostics: {len(diag_pdf)}")
    for d in diag_pdf:
        print("  PDF diag:", d)
    print(f"Wayback era rows: {len(df_wb)}; diagnostics: {len(diag_wb)}")
    for d in diag_wb:
        print("  WB diag:", d)

    df_all = pd.concat([df_pdf, df_wb], ignore_index=True)
    df_all = df_all.sort_values(["site", "publicationDate"]).reset_index(drop=True)
    # ordering sanity: f10 >= f50 >= f90
    bad = df_all[~((df_all["forecast_10"] >= df_all["forecast_50"]) &
                   (df_all["forecast_50"] >= df_all["forecast_90"]))]
    if len(bad):
        print(f"WARNING: {len(bad)} rows fail f10>=f50>=f90 ordering:")
        print(bad)

    df_out = df_all[OUT_COLS]
    df_out.to_csv(OUT_CSV, index=False)
    print(f"Saved {len(df_out)} rows to {OUT_CSV}")
    return df_all


if __name__ == "__main__":
    import sys
    main(parse_only="--parse-only" in sys.argv)
