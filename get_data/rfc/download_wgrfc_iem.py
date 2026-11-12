"""Download WGRFC water supply bulletins (AFOS PIL ESPFWR) from the IEM text archive.

Fills years missing from the locally provided WGRFC archive (wgrfc_esp/<year>/).
Each product is saved unmodified as wgrfc_esp/<year>/IEM_ESPFWR_<YYYYMMDDHHMM>.txt,
where the timestamp is the AWIPS header's transmission time (from the WMO line).
"""

import os
import re
import time

import requests

ARCHIVE_ROOT = os.environ.get("WSF_ARCHIVE_ROOT", os.path.expanduser("~/wsf_archive_v1.0"))
BASE_DIR = f"{ARCHIVE_ROOT}/source_data/rfc/wgrfc_esp"
URL = ("https://mesonet.agron.iastate.edu/cgi-bin/afos/retrieve.py"
       "?pil=ESPFWR&fmt=text&sdate={y}-12-15T00:00Z&edate={y1}-04-20T00:00Z&limit=200&order=asc")
YEARS = range(2004, 2024)  # water years


def download():
    for wy in YEARS:
        resp = requests.get(URL.format(y=wy - 1, y1=wy), timeout=60)
        resp.raise_for_status()
        products = [p.strip("\x01\x03\r\n ") for p in resp.text.split("\x01") if p.strip()]
        out_dir = f"{BASE_DIR}/{wy}"
        os.makedirs(out_dir, exist_ok=True)
        n_saved = 0
        for p in products:
            m = re.search(r"FGUS\d\d\s+KFWR\s+(\d{2})(\d{2})(\d{2})", p)
            # product timestamp: ddhhmm from WMO header; month/year come from the text itself
            d = re.search(r"ISSUED\s+([A-Z]+)\s+(\d{1,2}),?\s+(\d{4})", p, re.IGNORECASE)
            if not (m and d):
                continue
            stamp = f"{d.group(3)}{d.group(1)[:3].upper()}{int(d.group(2)):02d}_{m.group(2)}{m.group(3)}"
            with open(f"{out_dir}/IEM_ESPFWR_{stamp}.txt", "w") as fh:
                fh.write(p + "\n")
            n_saved += 1
        print(f"WY{wy}: {len(products)} products returned, {n_saved} saved")
        time.sleep(1)


if __name__ == "__main__":
    download()
