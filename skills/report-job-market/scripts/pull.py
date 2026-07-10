"""pull.py — MECHANICAL, read-only. Pull triaged rows from the job sheet and emit
deduplicated reason batches for classification.

Usage:  python skills/report-job-market/scripts/pull.py [OUT_DIR]

Reads every tab, keeps rows whose job_status is Suitable / Yes / Not Suitable,
and writes to OUT_DIR (default ./.report_tmp):
  - summary.json     : per-tab status counts + reasoned/total tallies
  - ns_batch1.json   : distinct not-suitable reasons (with counts), first half
  - ns_batch2.json   : distinct not-suitable reasons (with counts), second half
  - su_batch.json    : distinct suitable reasons (with counts)
  - triaged.json      : full triaged rows (for optional deeper analysis)

This script makes NO suitability or category decisions. It only reads and tallies.
Sheet id / service-account come from config_local.py, then env, then defaults.
"""
import json
import os
import re
import sys
from collections import Counter

import gspread
from google.oauth2.service_account import Credentials

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def _cfg(name, default):
    # prefer repo-root config_local.py, then env, then default
    sys.path.insert(0, REPO_ROOT)
    try:
        import config_local  # type: ignore
        val = getattr(config_local, name, None)
        if val:
            return val
    except Exception:
        pass
    return os.getenv(name, default)


SHEET_ID = _cfg("GOOGLE_SHEET_ID", "")
SA_FILE = _cfg("GOOGLE_SERVICE_ACCOUNT_FILE", os.path.join(REPO_ROOT, "service_account.json"))
if not os.path.isabs(SA_FILE):
    SA_FILE = os.path.join(REPO_ROOT, SA_FILE)

OUT_DIR = sys.argv[1] if len(sys.argv) > 1 else os.path.join(REPO_ROOT, ".report_tmp")
os.makedirs(OUT_DIR, exist_ok=True)

TRIAGED = {"suitable", "not suitable", "yes"}
KEEP = ("title", "company", "job_status", "suitability_reason", "job_level",
        "is_remote", "location", "date_posted", "description")


def norm(t):
    return re.sub(r"\s+", " ", str(t).strip())


def distinct(rows):
    reps, cnt = {}, Counter()
    for r in rows:
        key = norm(r["suitability_reason"]).lower()
        cnt[key] += 1
        reps.setdefault(key, norm(r["suitability_reason"]))
    return [{"reason": reps[k], "count": c} for k, c in cnt.most_common()]


def main():
    if not SHEET_ID:
        sys.exit("GOOGLE_SHEET_ID not found in config_local.py or env.")
    scopes = ["https://www.googleapis.com/auth/spreadsheets",
              "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_file(SA_FILE, scopes=scopes)
    sh = gspread.authorize(creds).open_by_key(SHEET_ID)

    summary, rows = {}, []
    for ws in sh.worksheets():
        counts = Counter()
        for r in ws.get_all_records():
            status = norm(r.get("job_status", ""))
            counts[status or "(blank)"] += 1
            if status.lower() in TRIAGED:
                rows.append({"country": ws.title, **{k: norm(r.get(k, "")) for k in KEEP}})
        summary[ws.title] = dict(counts)

    ns = [r for r in rows if r["job_status"].lower() == "not suitable" and r["suitability_reason"]]
    su = [r for r in rows if r["job_status"].lower() in ("suitable", "yes") and r["suitability_reason"]]
    nsd, sud = distinct(ns), distinct(su)
    half = len(nsd) // 2

    def dump(name, obj):
        with open(os.path.join(OUT_DIR, name), "w") as f:
            json.dump(obj, f, ensure_ascii=False, indent=1)

    dump("summary.json", summary)
    dump("ns_batch1.json", nsd[:half])
    dump("ns_batch2.json", nsd[half:])
    dump("su_batch.json", sud)
    dump("triaged.json", rows)

    print(f"OUT_DIR={OUT_DIR}")
    print(f"triaged rows: {len(rows)}  (not-suitable reasoned={len(ns)}, suitable reasoned={len(su)})")
    print(f"distinct: ns={len(nsd)} (batches {half}/{len(nsd)-half}), su={len(sud)}")
    for c, cnt in summary.items():
        print(f"  {c}: {cnt}")


if __name__ == "__main__":
    main()
