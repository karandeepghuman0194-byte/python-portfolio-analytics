"""
rest_datapoints.py
==============================================================
ENTERPRISE GRADE SEC EXTRACTOR
- Extracts Auditor, EFYE, State, Zip, 52/53 Week Policy
- MERGED: Extracts Shell Company Status (XBRL + Text Fallbacks)
==============================================================
"""

import asyncio
import aiohttp
import pandas as pd
import pyodbc
import re
import ssl
import time
import logging
import os
import json
import warnings
import html
from datetime import datetime

warnings.filterwarnings("ignore")

# ─────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────

# Set BASE_FOLDER to the directory where you want output files saved.
BASE_FOLDER = os.path.dirname(os.path.abspath(__file__))
RUN_TS = datetime.now().strftime("%Y%m%d_%H%M%S")

OUTPUT_FILE     = os.path.join(BASE_FOLDER, f"SEC_Extractor_Merged_{RUN_TS}.xlsx")
LOG_FILE        = os.path.join(BASE_FOLDER, f"sec_extractor_log_{RUN_TS}.txt")
CHECKPOINT_FILE = os.path.join(BASE_FOLDER, f"sec_extractor_checkpoint.json")

CHECKPOINT_EVERY = 100

# Set DB_PASSWORD as an environment variable before running.
# Example (Windows): set DB_PASSWORD=your_password
# Example (Linux/Mac): export DB_PASSWORD=your_password
_db_pwd = os.environ.get("DB_PASSWORD", "")

CONN_STR = (
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=****;"       # Replace with your SQL Server address
    "DATABASE=****;"     # Replace with your database name
    "UID=****;"          # Replace with your database username
    f"PWD={_db_pwd};"
    "TrustServerCertificate=yes;"
)

ZSCALER_CERT_PATH  = ""
MAX_SEC_CONCURRENT = 3
SEC_DELAY          = 0.12
REQ_PER_SEC        = 5.0

HEADERS = {
    "User-Agent":      "YourName your.email@yourorganization.com",  # Replace with your details
    "Accept-Encoding": "gzip, deflate",
    "Accept":          "*/*",
}

# ─────────────────────────────────────────────────────────
# RATE LIMITER
# ─────────────────────────────────────────────────────────

class RateLimiter:
    def __init__(self, rps):
        self.delay = 1.0 / rps
        self.lock  = asyncio.Lock()
        self.last  = 0.0

    async def wait(self):
        async with self.lock:
            now = time.monotonic()
            gap = self.delay - (now - self.last)
            if gap > 0:
                await asyncio.sleep(gap)
            self.last = time.monotonic()

_rate_limiter = None

os.makedirs(BASE_FOLDER, exist_ok=True)
logging.basicConfig(
    filename=LOG_FILE, level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

def log(msg, level="info"):
    print(msg)
    getattr(logging, level)(msg)

def build_ssl_context():
    if ZSCALER_CERT_PATH and os.path.exists(ZSCALER_CERT_PATH):
        return ssl.create_default_context(cafile=ZSCALER_CERT_PATH)
    return ssl.create_default_context()

# ─────────────────────────────────────────────────────────
# SQL QUERY TEMPLATE  ({lookback_days} injected at runtime)
# ─────────────────────────────────────────────────────────

SQL_QUERY_TEMPLATE = """
WITH Ranked AS (
    SELECT
        G.CompanyId,
        W.DocumentId,
        W.EffectiveDate,
        G.CIK,
        W.AccessionNumber,
        G.DomicileCountry,
        O.PlaceOfIncorporation,
        O.FiscalYearEnd,
        O.IsShell,
        A.LegalName,
        CA.AsOfDate,
        AA.PostalCode,
        W.ReviewedDate,
        ACC.Name,
        ROW_NUMBER() OVER (
            PARTITION BY G.CompanyId
            ORDER BY W.ReviewedDate DESC
        ) AS rn
    FROM GlobalReference G
    INNER JOIN WorkQ W
        ON G.CompanyId = W.CompanyId
    INNER JOIN CompanyOperation O
        ON G.CompanyId = O.CompanyId
    INNER JOIN Account ACC
        ON W.AssignedDAId = ACC.UserId
    INNER JOIN CompanyAddress AA
        ON G.CompanyId = AA.CompanyId
       AND AA.AddressType  = '1'
       AND AA.LanguageCode = 'ENG'
    LEFT JOIN CompanyAdvisor CA
        ON G.CompanyId = CA.CompanyId
       AND CA.CessationInformedDate IS NULL
       AND CA.IsDelete = '0'
    LEFT JOIN AdvisorInfo A
        ON CA.AdvisorId  = A.AdvisorId
       AND A.AdvisorType = 'Auditor'
    WHERE W.EventType    = '1'
      AND W.EventStatus  = '2'
      AND W.DocumentType = '202'
      AND G.TypeStatus   = 'true'
      AND W.FormType IN ('10-K', '10-K/A')
      AND W.ReviewedDate >= DATEADD(DAY, -{lookback_days}, GETDATE())
)
SELECT * FROM Ranked WHERE rn = 1
"""

def fetch_sql(lookback_days: int = 10):
    log(f"Connecting to SQL Server... (lookback: {lookback_days} days)")
    query = SQL_QUERY_TEMPLATE.format(lookback_days=int(lookback_days))
    conn  = pyodbc.connect(CONN_STR, timeout=30)
    df    = pd.read_sql(query, conn)
    conn.close()
    log(f"Rows loaded: {len(df):,}")
    return df.to_dict("records")

def fetch_country_mapping():
    """Fetches dictionary mapping CountryId -> CountryName"""
    query = "SELECT CountryId, CountryName FROM Country"
    conn = pyodbc.connect(CONN_STR, timeout=30)
    df = pd.read_sql(query, conn)
    conn.close()
    return dict(zip(df['CountryId'], df['CountryName']))

def fetch_user_mapping():
    """Fetches dictionary mapping UserId -> Name"""
    query = "SELECT UserId, Name FROM Account"
    conn = pyodbc.connect(CONN_STR, timeout=30)
    df = pd.read_sql(query, conn)
    conn.close()
    return df['Name'].dropna().unique().tolist()

# ─────────────────────────────────────────────────────────
# CHECKPOINT UTILS
# ─────────────────────────────────────────────────────────

def load_checkpoint():
    if os.path.exists(CHECKPOINT_FILE):
        try:
            with open(CHECKPOINT_FILE, "r") as f:
                data = json.load(f)
            return {k: v for k, v in data.items() if not v.get("Error")}
        except Exception:
            pass
    return {}

def save_checkpoint(done: dict):
    try:
        with open(CHECKPOINT_FILE, "w") as f:
            json.dump(done, f)
    except Exception:
        pass

# ─────────────────────────────────────────────────────────
# NETWORK / FILING HELPERS
# ─────────────────────────────────────────────────────────

def _is_null(val):
    if val is None:
        return True
    try:
        if pd.isna(val):
            return True
    except Exception:
        pass
    return str(val).strip().lower() in ("", "none", "nan", "null", "nat")

def clean_accession(acc):
    acc    = str(acc).strip()
    digits = re.sub(r"\D", "", acc)
    if len(digits) == 18:
        return f"{digits[:10]}-{digits[10:12]}-{digits[12:]}"
    return acc

def filing_base(cik, acc):
    cik_int = int(float(str(cik).strip()))
    return f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc.replace('-', '')}/"

def index_url(cik, acc):
    return filing_base(cik, acc) + f"{acc}-index.htm"

def make_absolute(base, href):
    if href.startswith("http"):
        return href
    if href.startswith("/"):
        return "https://www.sec.gov" + href
    return base + href

_TIMEOUT = aiohttp.ClientTimeout(total=30)

async def fetch(session, url, ssl_ctx=None, _retry=True, _backoff=5):
    if _rate_limiter:
        await _rate_limiter.wait()
    try:
        kwargs = {"headers": HEADERS, "timeout": _TIMEOUT}
        if ssl_ctx:
            kwargs["ssl"] = ssl_ctx
        async with session.get(url, **kwargs) as r:
            if r.status == 200:
                return await r.text(errors="ignore")
            if r.status == 429 and _retry:
                await asyncio.sleep(_backoff)
                return await fetch(session, url, ssl_ctx, _retry=True, _backoff=min(_backoff * 2, 60))
    except Exception:
        pass
    return None

def extract_doc_url(idx_html, cik, acc):
    base = filing_base(cik, acc)
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', idx_html, re.I | re.S)
    for row in rows:
        cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.I | re.S)
        if len(cells) < 4:
            continue
        typ = re.sub(r'<[^>]+>', '', cells[3]).strip().upper()
        if typ in ('10-K', '10-K/A'):
            m = re.search(r'href="([^"]+)"', cells[2], re.I)
            if m:
                href = m.group(1).split("/ix?doc=")[-1]
                return make_absolute(base, href)
    return None

def clean_html(text):
    t = html.unescape(text)
    t = re.sub(r'<[^>]+>', ' ', t)
    return re.sub(r'\s+', ' ', t).strip()

def get_first_val(fact_list):
    for f in fact_list:
        if f.get("value"):
            return f["value"]
    return ""

# ─────────────────────────────────────────────────────────
# STATE MAPPING
# ─────────────────────────────────────────────────────────

STATE_MAPPING = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
    "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
    "vermont": "VT", "virginia": "VA", "washington": "WA", "west virginia": "WV",
    "wisconsin": "WI", "wyoming": "WY", "district of columbia": "DC",
    "puerto rico": "PR", "bermuda": "BMU", "cayman islands": "CYM",
}

def normalize_state(val):
    if not val:
        return ""
    clean_val = val.strip().lower()
    return STATE_MAPPING.get(clean_val, val.upper() if len(clean_val) == 2 else val)

# ─────────────────────────────────────────────────────────
# ENGINE 1: SEC FACT EXTRACTION
# ─────────────────────────────────────────────────────────

_IX_TAG_RE = re.compile(
    r'<ix:(?:nonnumeric|numeric)([^>]+)>(.*?)</ix:(?:nonnumeric|numeric)>',
    re.I | re.S,
)

def extract_sec_facts(html_text):
    contexts    = {}
    ctx_pattern = re.compile(
        r'<[a-zA-Z0-9_]*:?context\b([^>]*)>(.*?)</[a-zA-Z0-9_]*:?context>',
        re.I | re.S,
    )
    for m in ctx_pattern.finditer(html_text):
        attrs, body = m.group(1), m.group(2)
        id_m = re.search(r'id=["\']([^"\']+)["\']', attrs, re.I)
        if id_m:
            ctx_id = id_m.group(1)
            date_m = re.search(
                r'<[a-zA-Z0-9_]*:?(?:endDate|instant)>\s*([^<]+)\s*</[a-zA-Z0-9_]*:?(?:endDate|instant)>',
                body, re.I,
            )
            if date_m:
                contexts[ctx_id] = date_m.group(1).strip()

    facts = {}
    for m in _IX_TAG_RE.finditer(html_text):
        attrs, inner_html = m.group(1), m.group(2)
        name_m = re.search(r'name=["\']([^"\']+)["\']', attrs, re.I)
        if not name_m:
            continue
        name   = name_m.group(1).lower()
        ctx_m  = re.search(r'contextRef=["\']([^"\']+)["\']', attrs, re.I)
        ctx_id = ctx_m.group(1) if ctx_m else None
        if name not in facts:
            facts[name] = []
        facts[name].append({"value": clean_html(inner_html), "context_date": contexts.get(ctx_id)})

    return facts

# ─────────────────────────────────────────────────────────
# ENGINE 2: SHELL DETECTION
# ─────────────────────────────────────────────────────────

_SHELL_XBRL_TAG_RE = re.compile(
    r'<ix:[a-z]+[^>]*name=["\']dei:EntityShellCompany["\'][^>]*>(.*?)</ix:[a-z]+>',
    re.I | re.S,
)
_SHELL_XBRL_DEI_RE = re.compile(
    r'<dei:EntityShellCompany[^>]*>(.*?)</dei:EntityShellCompany>',
    re.I | re.S,
)

def detect_shell_xbrl(raw_html):
    for m in _SHELL_XBRL_TAG_RE.finditer(raw_html):
        full_tag_open = raw_html[m.start():m.start() + 500]
        text_val      = m.group(1).strip().lower()

        fmt = re.search(r'format=["\']ixt:fixed-(true|false)["\']', full_tag_open, re.I)
        if fmt:
            val = fmt.group(1).lower()
            return ("N" if val == "false" else "Y", "HIGH", f"XBRL format=ixt:fixed-{val}")

        bool_fmt = re.search(r'format=["\']ixt:boolean(true|false)["\']', full_tag_open, re.I)
        if bool_fmt:
            val = bool_fmt.group(1).lower()
            return ("N" if val == "false" else "Y", "HIGH", f"XBRL format=ixt:boolean{val}")

        if "boolballotbox" in full_tag_open.lower():
            clean_text = html.unescape(text_val)
            if any(c in clean_text for c in ["☒", "☑", "þ", "ý", "x", "[x]"]):
                return ("Y", "HIGH", "XBRL boolballotbox=checked")
            if any(c in clean_text for c in ["☐", "¨", "[]"]):
                return ("N", "HIGH", "XBRL boolballotbox=unchecked")

        if text_val in ("false", "no", "0"):  return ("N", "HIGH", f"XBRL text={text_val}")
        if text_val in ("true",  "yes", "1"): return ("Y", "HIGH", f"XBRL text={text_val}")

    for m in _SHELL_XBRL_DEI_RE.finditer(raw_html):
        text_val = m.group(1).strip().lower()
        if text_val in ("false", "no", "0"):  return ("N", "HIGH", f"XBRL dei={text_val}")
        if text_val in ("true",  "yes", "1"): return ("Y", "HIGH", f"XBRL dei={text_val}")

    return None

def detect_shell_text(raw_html):
    t = re.sub(r'[ \t\r\n]+', ' ', re.sub(r'<[^>]+>', ' ', html.unescape(raw_html))).lower()
    if "shell company" not in t:
        return None

    chk   = r'(?:☒|☑|þ|ý|\[\s*x\s*\]|\(\s*x\s*\))'
    unchk = r'(?:☐|¨|\[\s*\]|\(\s*\))'

    if re.search(rf'shell company.{{0,400}}yes\s*{unchk}.{{0,80}}no\s*{chk}',   t): return ("N", "HIGH",   "Checkbox: Yes ☐ No ☒")
    if re.search(rf'shell company.{{0,400}}yes\s*{chk}.{{0,80}}no\s*{unchk}',   t): return ("Y", "HIGH",   "Checkbox: Yes ☒ No ☐")
    if re.search(rf'shell company.{{0,400}}{unchk}\s*yes.{{0,80}}{chk}\s*no',   t): return ("N", "HIGH",   "Checkbox: ☐ Yes ☒ No")
    if re.search(rf'shell company.{{0,400}}{chk}\s*yes.{{0,80}}{unchk}\s*no',   t): return ("Y", "HIGH",   "Checkbox: ☒ Yes ☐ No")
    if re.search(r'shell company.{0,400}\byes\b\s*\bo\b.{0,80}\bno\b\s*\bx\b',  t): return ("N", "HIGH",   "Checkbox: Yes o No x")
    if re.search(r'shell company.{0,400}\byes\b\s*\bx\b.{0,80}\bno\b\s*\bo\b',  t): return ("Y", "HIGH",   "Checkbox: Yes x No o")

    if re.search(r'(?:registrant|company|it)\s+is\s+not\s+a\s+shell\s+company', t): return ("N", "MEDIUM", "Text: is not a shell company")

    for m in re.finditer(r'is\s+a\s+shell\s+company', t):
        start   = max(0, m.start() - 40)
        context = t[start:m.start()]
        if "whether" not in context and "if " not in context and "not " not in context:
            return ("Y", "MEDIUM", "Text: is a shell company")

    if re.search(r'shell company.{0,150}[:\-]\s*no\b',  t): return ("N", "MEDIUM", "Text: shell company: no")
    if re.search(r'shell company.{0,150}[:\-]\s*yes\b', t): return ("Y", "MEDIUM", "Text: shell company: yes")

    return None

# ─────────────────────────────────────────────────────────
# ROW PROCESSING
# ─────────────────────────────────────────────────────────

async def process_row(session, sem, ssl_ctx, row):
    result = row.copy()
    for k in ["Error", "AuditorName", "AuditorAsOfDate", "DocumentEFYE",
              "EntityIncorporationStateCountryCode", "State", "ZipCode",
              "Has52_53WeekPolicy", "MissingFacts",
              "ShellStatus", "ShellConfidence", "ShellEvidence", "ShellSource"]:
        result[k] = ""
    result["ShellStatus"]     = "UNKNOWN"
    result["ShellConfidence"] = "LOW"

    cik, acc = row.get("CIK"), row.get("AccessionNumber")
    if _is_null(cik) or _is_null(acc):
        result["Error"] = "NullCIK/Acc"
        return result

    acc = clean_accession(acc)
    async with sem:
        await asyncio.sleep(SEC_DELAY)

        idx_html = await fetch(session, index_url(cik, acc), ssl_ctx)
        if not idx_html:
            result["Error"] = "IndexFail"
            return result

        xbrl_idx = detect_shell_xbrl(idx_html)
        if xbrl_idx:
            result["ShellStatus"], result["ShellConfidence"], result["ShellEvidence"] = xbrl_idx
            result["ShellSource"] = "XBRL_INDEX"

        doc_url = extract_doc_url(idx_html, cik, acc)
        if not doc_url:
            result["Error"] = "DocURLFail"
            return result

        await asyncio.sleep(SEC_DELAY)
        filing_html = await fetch(session, doc_url, ssl_ctx)
        if not filing_html:
            result["Error"] = "DocFetchFail"
            return result

        facts = extract_sec_facts(filing_html)
        result["AuditorName"] = get_first_val(facts.get("dei:auditorname", []))

        raw_end_dates = facts.get("dei:documentperiodenddate", [])
        as_of_date, efye_date = "", ""
        for f in raw_end_dates:
            if f.get("context_date"):
                try:
                    dt = pd.to_datetime(f["context_date"])
                    if dt.year > 1900:
                        as_of_date = dt.strftime("%Y-%m-%d")
                        efye_date  = (dt + pd.DateOffset(years=1)).strftime("%Y-%m-%d")
                        break
                except Exception:
                    pass

        if not as_of_date:
            for f in raw_end_dates:
                v = f.get("value", "")
                if v:
                    try:
                        dt = pd.to_datetime(v)
                        if re.search(r'\b(?:19|20)\d{2}\b', v) and dt.year > 1900:
                            as_of_date = dt.strftime("%Y-%m-%d")
                            efye_date  = (dt + pd.DateOffset(years=1)).strftime("%Y-%m-%d")
                            break
                    except Exception:
                        pass

        if not as_of_date and raw_end_dates:
            as_of_date = raw_end_dates[0].get("value", "")

        result["AuditorAsOfDate"] = as_of_date
        result["DocumentEFYE"]    = efye_date

        result["EntityIncorporationStateCountryCode"] = normalize_state(
            get_first_val(facts.get("dei:entityincorporationstatecountrycode", []))
        )
        result["State"]   = normalize_state(
            get_first_val(facts.get("dei:entityaddressstateorprovince", []))
        )
        result["ZipCode"] = get_first_val(facts.get("dei:entityaddresspostalzipcode", []))

        fiscal_texts = []
        for tag in [
            "us-gaap:fiscalperiod",
            "us-gaap:fiscalperiodpolicytextblock",
            "us-gaap:businessdescriptionandbasisofpresentationtextblock",
            "us-gaap:businessdescriptionandaccountingpoliciestextblock",
            "us-gaap:basisofpresentationandsignificantaccountingpoliciestextblock",
            "us-gaap:significantaccountingpoliciestextblock",
        ]:
            for f in facts.get(tag, []):
                if f.get("value"):
                    fiscal_texts.append(f["value"])

        combined_fiscal_text = " ".join(fiscal_texts).lower()
        if combined_fiscal_text:
            result["Has52_53WeekPolicy"] = (
                "Yes"
                if re.search(
                    r'\b(?:52|53|fifty[- ]?two|fifty[- ]?three)\b[-\s/]*'
                    r'(?:or|and|to)?[-\s/]*(?:52|53|fifty[- ]?two|fifty[- ]?three)?'
                    r'[-\s]*weeks?\b',
                    combined_fiscal_text,
                )
                else "No"
            )

        missing = [
            k for k in ["AuditorName", "AuditorAsOfDate", "DocumentEFYE",
                         "EntityIncorporationStateCountryCode", "State", "ZipCode"]
            if not result[k]
        ]
        result["MissingFacts"] = ", ".join(missing)

        if result["ShellStatus"] == "UNKNOWN":
            xbrl_doc = detect_shell_xbrl(filing_html)
            if xbrl_doc:
                result["ShellStatus"], result["ShellConfidence"], result["ShellEvidence"] = xbrl_doc
                result["ShellSource"] = "XBRL_DOC"
            else:
                text_res = detect_shell_text(filing_html)
                if text_res:
                    result["ShellStatus"], result["ShellConfidence"], result["ShellEvidence"] = text_res
                    result["ShellSource"] = "TEXT"

    return result

# ─────────────────────────────────────────────────────────
# ORCHESTRATOR
# ─────────────────────────────────────────────────────────

async def run_all(rows, progress_callback=None):
    global _rate_limiter
    _rate_limiter = RateLimiter(REQ_PER_SEC)
    ssl_ctx       = build_ssl_context()
    done          = load_checkpoint()
    pending       = [r for r in rows if str(r["DocumentId"]) not in done]

    if not pending:
        return list(done.values())

    sem       = asyncio.Semaphore(MAX_SEC_CONCURRENT)
    connector = aiohttp.TCPConnector(limit=40, ssl=ssl_ctx)
    completed = 0
    total     = len(pending)

    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [process_row(session, sem, ssl_ctx, row) for row in pending]
        for coro in asyncio.as_completed(tasks):
            try:
                res = await coro
                done[str(res["DocumentId"])] = res
                completed += 1
                if completed % CHECKPOINT_EVERY == 0:
                    save_checkpoint(done)
                if progress_callback:
                    progress_callback(completed, total)
            except Exception as e:
                log(f"Unhandled row exception: {e}", "error")

    save_checkpoint(done)
    return list(done.values())

# ─────────────────────────────────────────────────────────
# COLUMN DEFINITIONS
# ─────────────────────────────────────────────────────────

RENAME_MAP = {
    "DomicileCountry":                     "DB DomicileCountry",
    "PlaceOfIncorporation":                "DB PlaceOfIncorporation",
    "FiscalYearEnd":                       "DB FiscalYearEnd",
    "LegalName":                           "DB AuditorLegalName",
    "AsOfDate":                            "DB AuditorAsOfDate",
    "IsShell":                             "DB IsShell",
    "PostalCode":                          "DB PostalCode",
    "AuditorName":                         "SEC AuditorName",
    "AuditorAsOfDate":                     "SEC AuditorAsOfDate",
    "DocumentEFYE":                        "SEC FiscalYearEnd",
    "EntityIncorporationStateCountryCode": "SEC PlaceOfIncorporation",
    "State":                               "SEC State",
    "ZipCode":                             "SEC PostalCode",
    "ShellStatus":                         "SEC IsShell",
    "ShellConfidence":                     "SEC ShellConfidence",
}

EXCEL_COL_ORDER = [
    "CompanyId", "DocumentId", "EffectiveDate", "CIK", "AccessionNumber", "ReviewedDate",
    "DB DomicileCountry",
    "DB PlaceOfIncorporation",
    "DB FiscalYearEnd",
    "DB AuditorLegalName",
    "DB AuditorAsOfDate",
    "DB IsShell",
    "DB PostalCode",
    "SEC AuditorName",
    "SEC AuditorAsOfDate",
    "SEC FiscalYearEnd",
    "SEC PlaceOfIncorporation",
    "SEC State",
    "SEC PostalCode",
    "SEC IsShell",
    "SEC ShellConfidence",
    "Has52_53WeekPolicy",
    "MissingFacts",
    "Error",
    "Name",
    "ShellEvidence",
    "ShellSource",
    "rn",
]

STREAMLIT_HIDDEN_COLS = {"ShellEvidence", "ShellSource", "rn"}

# ─────────────────────────────────────────────────────────
# DATAFRAME FORMATTER
# ─────────────────────────────────────────────────────────

def _format_dataframe(results):
    """Rename and order all columns. Returns the FULL dataframe (including hidden cols)."""
    df = pd.DataFrame(results)
    if df.empty:
        return df

    df = df.rename(columns=RENAME_MAP)

    if "DB AuditorAsOfDate" in df.columns:
        df["DB AuditorAsOfDate"] = pd.to_datetime(df["DB AuditorAsOfDate"], errors='coerce').dt.strftime('%Y-%m-%d')
        df["DB AuditorAsOfDate"] = df["DB AuditorAsOfDate"].fillna("")

    ordered  = [c for c in EXCEL_COL_ORDER if c in df.columns]
    leftover = [c for c in df.columns if c not in ordered]
    return df[ordered + leftover]

# ─────────────────────────────────────────────────────────
# STREAMLIT ENTRY POINT
# ─────────────────────────────────────────────────────────

def run_and_return(progress_callback=None, lookback_days: int = 10):
    """
    Executes extraction and returns a DataFrame for Streamlit display.
    Hidden columns (ShellEvidence, ShellSource, rn) are dropped from the
    returned DataFrame so they never appear in the UI.
    The full data (including hidden cols) is still written to Excel via save_excel().
    """
    rows    = fetch_sql(lookback_days=lookback_days)
    results = asyncio.run(run_all(rows, progress_callback=progress_callback))
    df      = _format_dataframe(results)

    if os.path.exists(CHECKPOINT_FILE):
        os.remove(CHECKPOINT_FILE)

    cols_to_drop = [c for c in STREAMLIT_HIDDEN_COLS if c in df.columns]
    return df.drop(columns=cols_to_drop)

# ─────────────────────────────────────────────────────────
# CLI ENTRY POINT
# ─────────────────────────────────────────────────────────

def save_excel(results):
    if not results:
        return
    df = _format_dataframe(results)
    df.to_excel(OUTPUT_FILE, index=False, sheet_name="Results")
    log(f"Saved: {OUTPUT_FILE}")

def main():
    rows    = fetch_sql()
    results = asyncio.run(run_all(rows))
    save_excel(results)

if __name__ == "__main__":
    main()
