# Mailcow Bulk User Creator

Bulk-create mailboxes in Mailcow via the REST API from a CSV file.

## Requirements

- Python 3.8+
- `requests`, `python-dotenv` (installed in a local venv, see below)
- A Mailcow API key with **read/write** permission (not read-only)
- The target domain must already exist in Mailcow
- Mailbox password policy must allow the passwords in your CSV

## Setup

```bash
cd /home/zecter/.agent/projects/mailcow/bulkuser

# 1. Create & activate venv (uv is preferred; pip works too)
uv venv .venv && source .venv/bin/activate
uv pip install -r requirements.txt
# or: python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt

# 2. Configure .env (copy from example, fill in real values)
cp .env.example .env
nano .env
```

### `.env` fields

| Key | Description |
|-----|-------------|
| `MAILCOW_API_URL` | Base URL without trailing slash, e.g. `https://webmail.tel.my.id` |
| `MAILCOW_API_KEY` | API key from **Mailcow UI → Configuration → API** (must have write access) |
| `REQUEST_DELAY` | Seconds between requests (default `0.1`) |
| `LIMIT` | Max rows to process (`0` = all). Used for test runs. |

### CSV format

Header row required. Columns: `local_part,domain,name,password,quota`

```csv
local_part,domain,name,password,quota
user0001,tel.my.id,User 0001,Abcd1234!xZ,1024
user0002,tel.my.id,User 0002,Pqrs5678@Wy,1024
```

- `quota` is in **MB** (e.g. `1024` = 1 GB)
- Passwords must satisfy the Mailcow password policy
- **Use Unix line endings (LF)** — CSVs with CRLF (`\r\n`) cause silent failures
- See `mailcow_bulk_users.example.csv` for a template

## Usage

```bash
source .venv/bin/activate

# Process a specific CSV file (REQUIRED: -f must be given)
python3 bulk_create.py -f users.csv

# Process multiple files in one run
python3 bulk_create.py -f users_part1.csv users_part2.csv

# Process only the first N rows (handy for a quick smoke test)
python3 bulk_create.py -f users.csv -l 10

# Environment variable override also works
LIMIT=5 python3 bulk_create.py -f users.csv
```

The `-f` / `--file` argument is **required** — the script does not read a
filename from `.env`. If you run it without `-f`, it prints a usage error.

### Arguments

| Flag | Description |
|------|-------------|
| `-f`, `--file` | One or more CSV files (space-separated). **Required** — no `.env` fallback. |
| `-l`, `--limit` | Max total rows to process across all files (`0` = all). Takes precedence over the `LIMIT` env var. |

Files are processed in the order given. `created.log` and `failed.log` are
overwritten on each run (not appended).

You can split your user list into as many CSV files as you like and process
them however fits your workflow — one at a time, several per run, or all at
once. The script does not care how the files are divided.

### Output

- `created.log` — one line per successfully created mailbox
- `failed.log` — one line per failure (`addr -> reason`)
- Terminal summary: `Created / Failed / Exists / Skipped`

### Exit behavior

- `type:success` → counted as **Created**
- `object_exists` / `mailbox_exists` → counted as **Exists** (skipped, not failed)
- Any other `type:danger` (e.g. `password_complexity`, `mailbox_quota_left_exceeded`) → counted as **Failed** and logged

## Common failures & fixes

| Error | Cause | Fix |
|-------|-------|-----|
| `password_complexity` | Password fails policy, or API key is read-only | Use compliant password; ensure API key has write access |
| `mailbox_quota_left_exceeded` | Total requested quota exceeds domain/disk limit | Raise domain quota template, or lower `quota` in CSV |
| `object_exists` | Mailbox already created in a previous run | Safe to ignore — counted as `Exists` |
| `access_denied` (on delete) | API key lacks delete permission | Delete via UI, or use a key with delete access |
| Empty/odd results, CSV has CRLF | Windows line endings corrupt `local_part` | Run `sed -i 's/\r$//' file.csv` |

## Notes

- The script sends `authsource: "mailcow"` and `password2` (mirror of `password`) —
  both are required by the Mailcow `add/mailbox` endpoint.
- A `200` HTTP status does **not** mean success; the script parses the JSON
  `type` field to determine the real outcome.
- Never commit `.env` or `mailcow_bulk_users.csv` — they contain secrets.
