# Quire Projects — Automated Status Report Pipeline

A Python pipeline that fetches task and time-tracking data from **Quire** via OAuth2, processes it through a configurable assignee-resolution engine, and delivers a formatted **HTML email report** with plain-text attachments — triggered on demand or on schedule via **GitHub Actions**.

---

## Architecture

```
Quire API (OAuth2)
      |
      | GET /api/project/list
      | GET /api/task/search/{oid}
      v
  quire_api.py
  (QuireAPI class)
  - Token management with expiry cache
  - File-based response cache (30 min TTL)
  - Rate limiter (2 req/s)
  - Retry + exponential backoff
      |
      v
  data_processor.py
  (get_processed_dataframe)
  - DataValidator: type checks, range caps
  - AssigneeProcessor: 4-level resolution logic
  - Exclusion filter
  - Tag normalization
      |
      v
  report_generator.py
  - HTML email (Gmail-safe inline styles)
  - TXT activity breakdowns (week + 30 days)
      |
      v
  main.py
  - Assembles pipeline
  - Sends via Gmail SMTP
  - Attaches TXT files
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Data source | Quire REST API v1 (OAuth2 refresh token) |
| HTTP client | requests + retry/backoff decorator |
| Data processing | pandas, numpy |
| Email delivery | smtplib (Gmail SMTP, TLS) |
| Scheduler | GitHub Actions (`workflow_dispatch` + optional cron) |
| Runtime | Python 3.11 |

---

## Assignee Resolution Logic

The `AssigneeProcessor` applies a 4-level priority chain to determine the responsible person for each task:

| Level | Rule | Description |
|---|---|---|
| 0 | Special override | A specific name found in tags always takes priority |
| 1 | Direct assignment | Explicit assignee from Quire |
| 2 | Name in tags | Tag field contains a valid team member name |
| 3 | Rule mapping | Fallback by tag/specialty type (e.g. `Wiring` → `Alice`) |

All names, rules, and overrides are configured via environment variables — no hard-coded names in the source code.

---

## Setup

### 1. Clone and install

```bash
git clone https://github.com/your-username/your-repo.git
cd your-repo
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure environment variables

```bash
cp .env.example .env
# Edit .env with your values
```

Load them before running:

```bash
# Linux/macOS
export $(grep -v '^#' .env | xargs)

# Or use python-dotenv in a wrapper script
```

### 3. Get Quire OAuth2 credentials

1. Go to **quire.io > Account Settings > Apps**
2. Create an OAuth2 application
3. Use the client credentials flow to obtain a `refresh_token`
4. Set `QUIRE_CLIENT_ID`, `QUIRE_CLIENT_SECRET`, and `QUIRE_REFRESH_TOKEN`

### 4. Configure Gmail App Password

1. Enable 2-Step Verification on your Google account
2. Go to **myaccount.google.com > Security > App passwords**
3. Generate a password for "Mail" and set it as `EMAIL_PASSWORD`

### 5. Find Quire project OIDs

```bash
# After setting credentials, run:
python -c "import quire_api; api = quire_api.QuireAPI(); [print(p['oid'], p['name']) for p in api.fetch_projects()]"
```

Use the printed OIDs to build the `PROYECTOS_OBJETIVO` JSON.

### 6. Run locally

```bash
python main.py
```

---

## Environment Variables Reference

### Quire API

| Variable | Description |
|---|---|
| `QUIRE_CLIENT_ID` | OAuth2 client ID |
| `QUIRE_CLIENT_SECRET` | OAuth2 client secret |
| `QUIRE_REFRESH_TOKEN` | Long-lived refresh token |
| `QUIRE_CONNECT_TIMEOUT` | TCP connect timeout in seconds (default: `10`) |
| `QUIRE_READ_TIMEOUT` | Read timeout in seconds (default: `90`) |

### Email

| Variable | Description |
|---|---|
| `EMAIL_SENDER` | Gmail address used to send |
| `EMAIL_PASSWORD` | Gmail App Password |
| `EMAIL_RECIPIENTS` | Comma-separated recipient addresses |
| `REPORT_LABEL` | Footer label shown in the HTML report |

### Team & Projects

| Variable | Format | Description |
|---|---|---|
| `SPECIAL_STAFF` | `"Alice,Bob,Carol"` | Members featured in the Staff Performance section |
| `ASSIGNEE_NAMES` | `"Alice,Bob,Carol"` | All valid assignee names |
| `TARGET_WEEKLY` | `"40.0"` | Weekly hour target (default 40) |
| `TARGET_MONTHLY` | `"171.4"` | Monthly hour target |
| `PROYECTOS_OBJETIVO` | JSON `{"oid":"Name"}` | Projects tracked in the progress table |
| `RULE_MAPPING` | JSON `{"Tag":"Name"}` | Tag-to-assignee fallback rules |
| `NAME_NORMALIZATION` | JSON `{"Alias":"Name"}` | Nickname-to-canonical name map |

---

## GitHub Actions Deployment

Add all variables from the table above as **repository secrets** (`Settings > Secrets and variables > Actions`).

The workflow runs on manual dispatch by default. To enable scheduled runs, uncomment the `schedule` block in `.github/workflows/project_report.yml`.

---

## Project Structure

```
.
├── main.py               # Pipeline orchestrator + email sender
├── quire_api.py          # Quire API client (auth, pagination, cache, retry)
├── data_processor.py     # Data validation and assignee resolution
├── report_generator.py   # HTML + TXT report builders
├── config.py             # Runtime config loaded from env vars
├── requirements.txt
├── .env.example          # Environment variable reference
├── .gitignore
└── .github/
    └── workflows/
        └── project_report.yml   # GitHub Actions workflow
```

---

## Key Design Decisions

- **No hard-coded IDs or names** — all project OIDs, team member names, and routing rules are injected at runtime via environment variables. This makes the codebase fully portable across Quire organizations.
- **File-based API cache** — avoids redundant Quire API calls when running locally. Cache TTL is configurable; GitHub Actions always starts with a clean state.
- **Rate limiter** — enforces a 2 req/s ceiling to stay within Quire's API limits without explicit sleep calls scattered throughout the code.
- **4-level assignee resolution** — deterministic priority chain handles the common real-world case where tasks may be unassigned in the PM tool but inferable from tags.
- **Gmail-safe HTML** — all report styles use inline CSS; no external stylesheets or classes that email clients would strip.
