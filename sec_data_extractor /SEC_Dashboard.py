"""
SEC Extractor Pro Dashboard
===========================

Run with:
    streamlit run sec_dashboard_pro.py

Requirements:
    pip install -r requirements.txt
"""

import streamlit as st
import pandas as pd
import sys
import os
import time
from datetime import datetime, timedelta
import io
import difflib

# ─────────────────────────────────────────────────────────
# PAGE CONFIG (MUST BE THE VERY FIRST STREAMLIT COMMAND)
# ─────────────────────────────────────────────────────────
st.set_page_config(
    page_title="SEC Extractor Pro",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ─────────────────────────────────────────────────────────
# PATH CONFIGURATION
# Set EXTRACTOR_DIR to the folder containing rest_datapoints.py
# ─────────────────────────────────────────────────────────
EXTRACTOR_DIR = os.path.dirname(os.path.abspath(__file__))

if EXTRACTOR_DIR not in sys.path:
    sys.path.insert(0, EXTRACTOR_DIR)

# ─────────────────────────────────────────────────────────
# CUSTOM CSS
# ─────────────────────────────────────────────────────────
st.markdown("""
<style>
    .block-container { padding-top: 1.5rem !important; }
    [data-testid="stSidebar"] { background: #0f172a !important; }
    [data-testid="stSidebar"] * { color: #e2e8f0 !important; }
    [data-testid="stSidebar"] .stButton button {
        background: #1e40af !important; color: white !important;
        border-radius: 8px; border: none; width: 100%;
    }
    [data-testid="stSidebar"] .stButton button:hover { background: #1d4ed8 !important; }

    .compact-header {
        display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px;
        border-bottom: 1px solid rgba(128,128,128,0.2); padding-bottom: 8px; margin-bottom: 15px;
    }
    .compact-title { font-size: 1.4rem; font-weight: 600; margin: 0; line-height: 1.2; }
    .compact-subtitle { font-weight: 400; opacity: 0.6; font-size: 1.1rem; }
    .compact-stats { font-size: 0.85rem; opacity: 0.8; line-height: 1.2; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────
# FUZZY MATCH UTILITY
# ─────────────────────────────────────────────────────────

def get_similarity(a, b):
    """Returns a fuzzy match percentage between two strings (0 to 100)."""
    a_str = str(a).strip().lower() if pd.notna(a) else ""
    b_str = str(b).strip().lower() if pd.notna(b) else ""

    if a_str == b_str:
        return 100.0
    if not a_str or not b_str:
        return 0.0

    return difflib.SequenceMatcher(None, a_str, b_str).ratio() * 100.0

# ─────────────────────────────────────────────────────────
# SESSION STATE
# ─────────────────────────────────────────────────────────
if "df_results" not in st.session_state:    st.session_state["df_results"] = None
if "run_ts" not in st.session_state:        st.session_state["run_ts"] = None
if "last_lookback" not in st.session_state: st.session_state["last_lookback"] = None

# ─────────────────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 📋 SEC Extractor Pro")
    st.caption("On-The-Fly Memory Extraction")
    st.divider()

    st.markdown("#### 📅 Filing Lookback Window")
    lookback_days = st.number_input("Last N days", min_value=1, max_value=365, value=10, step=1)

    today = datetime.today().date()
    from_date = today - timedelta(days=int(lookback_days))
    st.caption(f"📆 Pulling filings from **{from_date}** → **{today}**")
    st.divider()

    run_btn   = st.button("▶  Run Extractor", use_container_width=True)
    clear_btn = st.button("🗑  Clear Results", use_container_width=True)

if clear_btn:
    st.session_state["df_results"] = None
    st.session_state["run_ts"] = None
    st.session_state["last_lookback"] = None
    st.rerun()

# ─────────────────────────────────────────────────────────
# RUN EXTRACTOR ENGINE
# ─────────────────────────────────────────────────────────
if run_btn:
    try:
        import rest_datapoints
    except ImportError as e:
        st.error(f"❌ Could not import `rest_datapoints.py`.\nError: `{e}`")
    else:
        st.markdown("### ▶ Extractor Running…")
        prog_bar = st.progress(0, text="Fetching data from SQL...")
        m1, m2, m3, m4 = st.columns(4)
        lbl_done, lbl_pending, lbl_pct, lbl_elapsed = m1.empty(), m2.empty(), m3.empty(), m4.empty()

        start_ts = time.time()

        def progress_callback(done, total):
            pct = int(done / total * 100) if total else 0
            elapsed = round(time.time() - start_ts, 1)
            prog_bar.progress(min(pct, 100) / 100.0, text=f"Scraping SEC EDGAR: {done:,} / {total:,} ({pct}%)")
            lbl_done.metric("Done", f"{done:,} / {total:,}")
            lbl_pending.metric("Pending", f"{total - done:,}")
            lbl_pct.metric("Progress", f"{pct}%")
            lbl_elapsed.metric("Elapsed", f"{elapsed}s")

        old_stdout = sys.stdout
        sys.stdout = io.StringIO()

        try:
            df = rest_datapoints.run_and_return(
                progress_callback=progress_callback,
                lookback_days=int(lookback_days)
            )
            elapsed_total = round(time.time() - start_ts, 1)
            prog_bar.progress(1.0, text=f"✅ Done in {elapsed_total}s — {len(df):,} rows extracted")

            st.session_state["df_results"] = df
            st.session_state["run_ts"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            st.session_state["last_lookback"] = int(lookback_days)
            st.rerun()

        except Exception as e:
            st.error(f"❌ Extractor failed: `{e}`")
        finally:
            sys.stdout = old_stdout

# ─────────────────────────────────────────────────────────
# DASHBOARD UI
# ─────────────────────────────────────────────────────────
df = st.session_state.get("df_results")

if df is None:
    st.markdown("## SEC Extractor Pro")
    st.info("👈 Set your **lookback window** and click **▶ Run Extractor** in the sidebar to fetch SEC filing data.")
else:
    st.markdown(
        f"""
        <div class="compact-header">
            <div class="compact-title">SEC Extractor Pro <span class="compact-subtitle">Results</span></div>
            <div class="compact-stats">
                🕐 {st.session_state['run_ts']} &nbsp;|&nbsp;
                📋 {len(df):,} rows &nbsp;|&nbsp;
                🧩 {len(df.columns)} cols &nbsp;|&nbsp;
                📅 {st.session_state['last_lookback']}d lookback
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    tab_filings, tab_export = st.tabs(["📄 Filings Data", "💾 Export Result"])

    with tab_filings:
        @st.cache_data(ttl=3600)
        def get_dropdown_data():
            try:
                import rest_datapoints
                countries = getattr(rest_datapoints, "fetch_country_mapping", lambda: {})()
                users = getattr(rest_datapoints, "fetch_user_mapping", lambda: [])()
                return countries, users
            except:
                return {}, []

        country_map, user_list = get_dropdown_data()
        country_name_to_id = {v: k for k, v in country_map.items()}

        f1, f2, f3, f4 = st.columns([1.5, 1, 1, 1])
        with f1: search_q    = st.text_input("🔍 Global Search", placeholder="Search all columns…")
        with f2: sel_country = st.selectbox("🌐 Domicile Country", ["All"] + sorted(list(country_name_to_id.keys())))
        with f3: sel_shell   = st.selectbox("🐚 Shell Company", ["All", "Yes", "No"])
        with f4: sel_name    = st.selectbox("👤 Account Name", ["All"] + sorted(user_list))

        st.markdown("##### 🔀 Fuzzy Column Comparison Tool")

        db_cols  = sorted([c for c in df.columns if str(c).upper().startswith("DB ")])
        sec_cols = sorted([c for c in df.columns if str(c).upper().startswith("SEC ")])

        cc1, cc2, cc3, cc4 = st.columns([1.25, 1.25, 1.5, 1])
        with cc1: col_a       = st.selectbox("DB Column (A)", ["— select —"] + db_cols)
        with cc2: col_b       = st.selectbox("SEC Column (B)", ["— select —"] + sec_cols)
        with cc3: match_rule  = st.radio("Show rows where…", ["All rows", "Matches ✅", "Differences ❌"], horizontal=True)
        with cc4:
            fuzzy_threshold = st.number_input(
                "Similarity Threshold %", min_value=1, max_value=100, value=100, step=1,
                help="100% requires an exact text match. 85% allows minor typos or abbreviations."
            )

        temp = df.copy()

        # Apply dropdown filters
        if sel_country != "All":
            temp = temp[temp["DB DomicileCountry"] == country_name_to_id[sel_country]]

        if sel_shell != "All":
            temp = temp[temp["DB IsShell"] == ("Y" if sel_shell == "Yes" else "N")]

        if sel_name != "All" and "Name" in temp.columns:
            temp = temp[temp["Name"] == sel_name]

        # Apply comparison filter
        comparison_on = col_a != "— select —" and col_b != "— select —"

        if comparison_on:
            similarities = temp.apply(lambda row: get_similarity(row[col_a], row[col_b]), axis=1)

            if match_rule == "Matches ✅":
                temp = temp[similarities >= fuzzy_threshold]
            elif match_rule == "Differences ❌":
                temp = temp[similarities < fuzzy_threshold]

            temp.insert(0, f'Match % ({col_a} vs {col_b})', similarities.loc[temp.index].round(1))

            n_match = (similarities >= fuzzy_threshold).sum()
            n_diff  = len(similarities) - n_match

            sm1, sm2, sm3 = st.columns(3)
            sm1.metric("Total Rows Compared", f"{len(similarities):,}")
            sm2.metric(f"Matches (≥{fuzzy_threshold}%) ✅", f"{n_match:,}")
            sm3.metric(f"Differences (<{fuzzy_threshold}%) ❌", f"{n_diff:,}")

        # Apply global search
        if search_q.strip():
            mask = temp.astype(str).apply(lambda s: s.str.contains(search_q.strip(), case=False, na=False)).any(axis=1)
            temp = temp[mask]

        cols_to_hide = ["ShellEvidence", "ShellSource", "rn"]
        display_df = temp.drop(columns=[c for c in cols_to_hide if c in temp.columns])

        st.caption(f"Showing **{len(temp):,}** rows (Filters applied)")
        st.dataframe(display_df.reset_index(drop=True), use_container_width=True, height=580)

    with tab_export:
        st.markdown("### 💾 Export Extracted Data")
        e1, e2 = st.columns(2)

        with e1:
            st.markdown("**Download as CSV**")
            st.download_button(
                label="⬇ Download Full CSV",
                data=df.to_csv(index=False).encode("utf-8"),
                file_name=f"SEC_Data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
                use_container_width=True,
            )

        with e2:
            st.markdown("**Download as Excel (.xlsx)**")
            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine="openpyxl") as writer:
                df.to_excel(writer, index=False, sheet_name="Results")
            buf.seek(0)

            st.download_button(
                label="⬇ Download Excel File",
                data=buf.read(),
                file_name=f"SEC_Data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
