"""
GECS Industry Classifier Dashboard
====================================

Run with:
    streamlit run streamlitGECS.py

Requirements:
    pip install -r requirements.txt
"""

import streamlit as st
import time

from chatbox import classify_company, load_taxonomy_and_index, warm_up_model

# =====================================================
# PAGE CONFIG
# =====================================================
st.set_page_config(
    page_title="GECS Classifier",
    page_icon="🔬",
    layout="centered"
)

# =====================================================
# CSS
# =====================================================
st.markdown("""
<style>

.stApp {
    background-color: #0e1117;
    color: white;
}

textarea {
    font-size: 16px !important;
}

.result-box {
    padding: 20px;
    border-radius: 12px;
    background: #1c1f26;
    border: 1px solid #2d313a;
    margin-top: 20px;
}

.metric {
    font-size: 30px;
    font-weight: bold;
    color: #3ecf8e;
}

.label {
    color: #9aa4b2;
    font-size: 13px;
    text-transform: uppercase;
    letter-spacing: 1px;
}

.warn-box {
    padding: 10px 16px;
    border-radius: 8px;
    background: #2a1f0e;
    border: 1px solid #c87941;
    color: #f0a85a;
    margin-top: 12px;
    font-size: 13px;
}

</style>
""", unsafe_allow_html=True)

# =====================================================
# HEADER
# =====================================================
st.title("🔬 GECS Industry Classifier")
st.caption("AI Classification Engine · Hybrid Search (BM25 + Semantic)")

# =====================================================
# SIDEBAR SETTINGS
# =====================================================
with st.sidebar:
    st.header("⚙️ Settings")
    selected_model = st.selectbox(
        "Model Selection",
        ["qwen3:8b-q4_K_M", "qwen2.5:7b-instruct", "qwen2.5:14b"],
        index=0,
        help="Select the local LLM to run. Smaller models are faster."
    )

    selected_top_k = st.selectbox(
        "Top Candidates (Hybrid Search)",
        [3, 5, 7],
        index=0,
        help="Number of candidates retrieved and sent to the LLM. 3 is recommended for best speed."
    )

    st.divider()
    st.caption("Retrieval: BM25 + BGE-large-en-v1.5 · Fusion: RRF (α=0.25)")

# =====================================================
# PRE-LOAD
# =====================================================
load_taxonomy_and_index()
warm_up_model(selected_model)

# =====================================================
# INPUT
# =====================================================
description = st.text_area(
    "Company Description",
    height=220,
    placeholder="Paste company business description..."
)

# =====================================================
# CLASSIFY BUTTON
# =====================================================
if st.button("Classify Industry", use_container_width=True):

    if not description.strip():
        st.warning("Please enter a business description.")

    else:
        start_time = time.time()

        with st.spinner(f"Running classification with {selected_model}..."):
            result = classify_company(description, model_name=selected_model, top_k=selected_top_k)

        end_time = time.time()
        process_time = round(end_time - start_time, 2)

        # Hallucination warning
        if result.get("hallucination_corrected"):
            st.markdown(
                '<div class="warn-box">⚠️ LLM returned an invalid industry name and was auto-corrected to the top retrieval match.</div>',
                unsafe_allow_html=True
            )

        # Final result
        st.markdown(
            f"""
<div class="result-box">

<div class="label">Predicted Industry</div>
<h2>{result['industry']}</h2>

<div class="label">Confidence</div>
<div class="metric">{result['confidence']}%</div>

<br>

<div class="label">Reasoning</div>
<p>{result['reasoning']}</p>

<div class="label" style="margin-top: 15px;">Processing Time</div>
<p style="color: #ccc;">{process_time} seconds</p>

</div>
""",
            unsafe_allow_html=True
        )

        # Top candidates
        st.subheader("Top Candidates")

        for idx, cand in enumerate(result['candidates'], start=1):
            st.progress(cand['score'] / 100)
            st.write(f"{idx}. {cand['industry']} — {cand['score']}%")
