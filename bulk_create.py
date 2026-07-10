#!/usr/bin/env python3
"""
Bulk create Mailcow mailboxes from one or more CSV files via the Mailcow REST API.

CSV columns: local_part,domain,name,password,quota
Config (API URL, key, delay) is read from a .env file in the same directory.

Usage:
    python3 bulk_create.py -f list1.csv
    python3 bulk_create.py -f list1.csv list2.csv list3.csv list4.csv
    python3 bulk_create.py -f list1.csv -l 100        # first 100 rows of list1
    LIMIT=5 python3 bulk_create.py -f list1.csv         # env override still works

Outputs:
    created.log    - one line per successful creation
    failed.log     - one line per failure (local_part@domain -> status: message)
"""

import argparse
import csv
import os
import sys
import time
import json

try:
    import requests
except ImportError:
    sys.exit("Missing dependency: pip install requests python-dotenv")

try:
    from dotenv import load_dotenv
except ImportError:
    sys.exit("Missing dependency: pip install requests python-dotenv")

# Load .env from the script's own directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

# CLI args: -f/--file is required (no .env fallback)
parser = argparse.ArgumentParser(description="Bulk create Mailcow mailboxes from CSV.")
parser.add_argument(
    "-f", "--file", nargs="+",
    help="One or more CSV files to process (required)",
)
parser.add_argument(
    "-l", "--limit", type=int, default=None,
    help="Max total rows to process across all files (0 = all)",
)
args = parser.parse_args()

API_URL = os.getenv("MAILCOW_API_URL", "").rstrip("/")
API_KEY = os.getenv("MAILCOW_API_KEY", "")
REQUEST_DELAY = float(os.getenv("REQUEST_DELAY", "0.1"))
LIMIT = int(os.getenv("LIMIT", "0") or 0)

# Precedence: -l/--limit > LIMIT env > default 0
if args.limit is not None:
    LIMIT = args.limit
elif "LIMIT" in os.environ:
    try:
        LIMIT = int(os.environ["LIMIT"])
    except ValueError:
        pass

if not API_URL or not API_KEY or API_KEY == "***CHANGE-ME***":
    sys.exit("Configure MAILCOW_API_URL and MAILCOW_API_KEY in .env first")

# Determine file list — -f is REQUIRED, no .env fallback
if args.file:
    FILES = [fp if os.path.isabs(fp) else os.path.join(BASE_DIR, fp) for fp in args.file]
else:
    sys.exit("No input file. Usage: python3 bulk_create.py -f file.csv [file2.csv ...]")

HEADERS = {
    "X-API-Key": API_KEY,
    "Content-Type": "application/json",
}

created_log = os.path.join(BASE_DIR, "created.log")
failed_log = os.path.join(BASE_DIR, "failed.log")


def create_mailbox(row):
    payload = {
        "local_part": row["local_part"].strip(),
        "domain": row["domain"].strip(),
        "name": row.get("name", "").strip() or row["local_part"].strip(),
        "authsource": "mailcow",
        "password": row["password"],
        "password2": row["password"],
        "quota": int(row.get("quota", 1024) or 1024),
        "active": "1",
        "force_pw_update": "0",
    }
    resp = requests.post(
        f"{API_URL}/api/v1/add/mailbox",
        headers=HEADERS,
        json=payload,
        timeout=30,
    )
    return resp.text


def _parse_json(text):
    if text is None:
        return None
    try:
        return json.loads(text, strict=False)
    except Exception:
        try:
            return json.loads(text.strip().replace("\n", "").replace("\r", ""), strict=False)
        except Exception:
            return None


def main():
    created = 0
    failed = 0
    skipped = 0
    skipped_exists = 0
    processed = 0

    with open(created_log, "w") as lc, open(failed_log, "w") as lf:
        for csv_path in FILES:
            if not os.path.exists(csv_path):
                sys.exit(f"CSV not found: {csv_path}")
            print(f"\n--- Processing: {os.path.basename(csv_path)} ---")
            with open(csv_path, newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    processed += 1
                    if LIMIT and processed > LIMIT:
                        skipped += 1
                        continue

                    addr = f"{row['local_part'].strip()}@{row['domain'].strip()}"
                    try:
                        text = create_mailbox(row)
                    except Exception as e:
                        failed += 1
                        lf.write(f"{addr} -> EXCEPTION: {e}\n")
                        print(f"ERR  {addr} -> {e}")
                        time.sleep(REQUEST_DELAY)
                        continue

                    # Parse Mailcow API response correctly.
                    # A 200 can still mean failure (type:danger).
                    ok = False
                    reason = ""
                    code = "?"
                    try:
                        resp_json = _parse_json(text)
                        if isinstance(resp_json, list) and resp_json:
                            first = resp_json[0]
                            if first.get("type") == "success":
                                ok = True
                            else:
                                raw_msg = first.get("msg") or first.get("type") or "unknown"
                                if isinstance(raw_msg, list):
                                    raw_msg = " ".join(str(x) for x in raw_msg)
                                reason = str(raw_msg)
                        elif isinstance(resp_json, dict):
                            reason = str(resp_json)
                        else:
                            reason = text[:120]
                    except Exception as e:
                        reason = f"parse-error:{e}"

                    if ok:
                        created += 1
                        lc.write(f"{addr}\n")
                        print(f"OK   {addr}")
                    elif reason and "exists" in reason.lower():
                        skipped_exists += 1
                        print(f"SKIP {addr} -> already exists")
                    else:
                        failed += 1
                        msg = (reason or text)[:200].replace("\n", " ")
                        lf.write(f"{addr} -> {code}: {msg}\n")
                        print(f"FAIL {addr} -> {code}: {msg}")
                        if os.getenv("DEBUG"):
                            print(f"   [debug] raw reason={reason!r}")

                    time.sleep(REQUEST_DELAY)

    print(f"\n{'=' * 40}")
    print(f"Created : {created}")
    print(f"Failed  : {failed}")
    print(f"Exists  : {skipped_exists}")
    print(f"Skipped : {skipped}")
    print(f"Logs    : {created_log}")
    print(f"         : {failed_log}")


if __name__ == "__main__":
    main()
