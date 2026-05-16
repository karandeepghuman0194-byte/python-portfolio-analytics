# 📋 SEC Extractor Pro

An async SEC EDGAR filing extractor with a Streamlit dashboard. Pulls 10-K/10-K/A filings and extracts key data points including Auditor, Fiscal Year End, State, Zip Code, Shell Company status, and 52/53-Week fiscal policy.

---

## 🚀 What It Extracts

| Field | Source |
|---|---|
| Auditor Name & As-Of Date | SEC XBRL (`dei:AuditorName`) |
| Fiscal Year End (EFYE) | SEC XBRL (`dei:DocumentPeriodEndDate`) |
| Place of Incorporation | SEC XBRL (`dei:EntityIncorporationStateCountryCode`) |
| State | SEC XBRL (`dei:EntityAddressStateOrProvince`) |
| Zip Code | SEC XBRL (`dei:EntityAddressPostalZipCode`) |
| Shell Company Status | XBRL tags + text checkbox fallback |
| 52/53-Week Fiscal Policy | Accounting policy text blocks |

---

## 🛠️ Setup

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Set environment variables
```bash
# Windows
set DB_PASSWORD=your_database_password

# Linux/Mac
export DB_PASSWORD=your_database_password
```

> ⚠️ Never hardcode credentials. Always use environment variables.

### 3. Configure database connection
In `rest_datapoints.py`, update the `CONN_STR` with your SQL Server details:
```python
CONN_STR = (
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=your_server;"
    "DATABASE=your_database;"
    "UID=your_username;"
    f"PWD={_db_pwd};"
    "TrustServerCertificate=yes;"
)
```

Also update the `User-Agent` header in `HEADERS`:
```python
HEADERS = {
    "User-Agent": "YourName your.email@yourorganization.com",
    ...
}
```
> SEC EDGAR requires a valid User-Agent with a real email address per their [fair access policy](https://www.sec.gov/os/accessing-edgar-data).

### 4. Run the dashboard
```bash
streamlit run sec_dashboard_pro.py
```

### 5. (Optional) Run as CLI for Excel export
```bash
python rest_datapoints.py
```

---

## ⚙️ Configuration

| Parameter | Default | Description |
|---|---|---|
| `MAX_SEC_CONCURRENT` | `3` | Max concurrent SEC requests |
| `SEC_DELAY` | `0.12s` | Delay between requests |
| `REQ_PER_SEC` | `5.0` | Rate limiter (requests per second) |
| `CHECKPOINT_EVERY` | `100` | Save checkpoint every N rows |

---

## 📁 Project Structure

```
sec_extractor/
├── rest_datapoints.py      # Backend: SQL fetch, async SEC scraping, shell detection
├── sec_dashboard_pro.py    # Frontend: Streamlit dashboard UI
├── requirements.txt        # Python dependencies
└── README.md
```

---

## 🧠 Tech Stack

- **Streamlit** — Dashboard UI
- **aiohttp + asyncio** — Async SEC EDGAR requests
- **pyodbc** — SQL Server connection
- **pandas** — Data processing and Excel export
- **openpyxl** — Excel file generation
