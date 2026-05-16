import truststore

truststore.inject_into_ssl()

import pandas as pd
import pyodbc
import ollama
import os
import re
import warnings
import numpy as np
import streamlit as st
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer
from difflib import get_close_matches

# ==========================================
# CONFIG
# ==========================================

# Set DB_PASSWORD as an environment variable before running.
# Example (Windows): set DB_PASSWORD=your_password
# Example (Linux/Mac): export DB_PASSWORD=your_password
_db_pwd = os.environ.get("DB_PASSWORD", "")

CONN_STR = (
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=****;"           # Replace with your SQL Server address
    "DATABASE=****;"         # Replace with your database name
    "UID=****;"              # Replace with your database username
    f"PWD={_db_pwd};"
    "TrustServerCertificate=yes;"
)

TAXONOMY_QUERY = """
SELECT
    I.IndustryName,
    I.Description AS IndustryDesc,
    A.ActivityName,
    A.ActivityDescription
FROM MorningstarGlobalIndustry I
LEFT JOIN ActivityDetails A
    ON I.IndustryCode = A.IndustryID
"""

EMBEDDING_MODEL = "BAAI/bge-large-en-v1.5"

# Lower = more semantic weight.
# 0.25 means 25% BM25 + 75% semantic.
ALPHA = 0.25

# Retrieve wider internally, but only send top_k candidates to LLM.
RETRIEVAL_MULTIPLIER = 5

# ==========================================
# TEXT UTILITIES
# ==========================================

def tokenize(text):
    """
    Better tokenizer for BM25 than simple .split().
    Handles punctuation, hyphenated words, slashes, etc.
    """
    return re.findall(r"[a-zA-Z0-9]+", str(text).lower())


def clean_text(value):
    """
    Safely clean database text values.
    """
    if pd.isna(value):
        return ""
    return str(value).strip()


# ==========================================
# CACHED TAXONOMY + HYBRID INDEX
# ==========================================

@st.cache_resource(show_spinner="Loading Taxonomy and building search index...")
def load_taxonomy_and_index():
    conn = pyodbc.connect(CONN_STR)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        df_tax = pd.read_sql(TAXONOMY_QUERY, conn)

    conn.close()

    industry_docs = []
    industry_names = []
    industry_texts = {}

    for industry, group in df_tax.groupby("IndustryName"):
        industry = clean_text(industry)

        ind_desc = clean_text(group["IndustryDesc"].iloc[0])
        if not ind_desc:
            ind_desc = "No description available"

        activity_rows = []
        act_names = []

        for _, row in group.iterrows():
            activity_name = clean_text(row.get("ActivityName", ""))
            activity_desc = clean_text(row.get("ActivityDescription", ""))

            if activity_name:
                act_names.append(activity_name)

            if activity_name or activity_desc:
                activity_rows.append(
                    f"Activity Name: {activity_name}. Activity Description: {activity_desc}"
                )

        activities_text = "\n".join(activity_rows)

        # Weighted/structured industry document.
        # Repeating Industry Name gives stronger signal to BM25 and embeddings.
        doc_text = f"""
Industry Name: {industry}
Industry Name: {industry}
Industry Name: {industry}

Industry Description:
{ind_desc}

Activities:
{activities_text}
"""

        industry_names.append(industry)
        industry_docs.append(doc_text)

        rules = f"""
INDUSTRY: {industry}
Industry Description: {ind_desc}
Activities: {", ".join(act_names)}
"""
        industry_texts[industry] = rules

    print("Building BM25 index...")

    tokenized_corpus = [tokenize(doc) for doc in industry_docs]
    bm25 = BM25Okapi(tokenized_corpus)

    print(f"Building semantic embeddings with {EMBEDDING_MODEL}...")

    embedder = SentenceTransformer(EMBEDDING_MODEL)

    # BGE works better with passage prefix for documents
    corpus_embeddings = embedder.encode(
        [f"passage: {doc}" for doc in industry_docs],
        normalize_embeddings=True,
        show_progress_bar=False,
        batch_size=32
    )

    print("Hybrid index ready.")

    return bm25, embedder, corpus_embeddings, industry_names, industry_texts


# ==========================================
# HYBRID RETRIEVAL
# ==========================================

def _hybrid_retrieve(
    query: str,
    bm25,
    embedder,
    corpus_embeddings,
    industry_names,
    top_k: int
):
    n = len(industry_names)

    if n == 0:
        return []

    # BM25 scores
    query_tokens = tokenize(query)
    bm25_scores = np.array(bm25.get_scores(query_tokens))

    bm25_min = bm25_scores.min()
    bm25_max = bm25_scores.max()

    if bm25_max - bm25_min > 0:
        bm25_norm = (bm25_scores - bm25_min) / (bm25_max - bm25_min)
    else:
        bm25_norm = np.zeros(n)

    # Semantic scores
    # BGE works better with query prefix for query text
    query_embedding = embedder.encode(
        f"query: {query}",
        normalize_embeddings=True
    )

    sem_scores = corpus_embeddings @ query_embedding
    sem_scores = np.clip(sem_scores, 0, 1)

    # Reciprocal Rank Fusion
    rrf_k = 60

    bm25_ranks = np.argsort(-bm25_norm)
    sem_ranks = np.argsort(-sem_scores)

    rrf_scores = np.zeros(n)

    for rank, idx in enumerate(bm25_ranks):
        rrf_scores[idx] += ALPHA * (1.0 / (rrf_k + rank + 1))

    for rank, idx in enumerate(sem_ranks):
        rrf_scores[idx] += (1.0 - ALPHA) * (1.0 / (rrf_k + rank + 1))

    top_indices = np.argsort(-rrf_scores)[:top_k]

    if top_indices.size == 0:
        return []

    rrf_max = rrf_scores[top_indices[0]]
    if rrf_max == 0:
        rrf_max = 1.0

    results = [
        (int(idx), round(float(rrf_scores[idx] / rrf_max) * 100, 1))
        for idx in top_indices
    ]

    return results


# ==========================================
# MODEL WARM-UP
# ==========================================

@st.cache_resource(show_spinner="Warming up model...")
def warm_up_model(model_name: str):
    try:
        ollama.chat(
            model=model_name,
            messages=[{"role": "user", "content": "hi"}],
            options={"num_predict": 10}
        )
        print(f"Model '{model_name}' warmed up.")
    except Exception as e:
        print(f"Warm-up skipped: {e}")

    return True


# ==========================================
# CLASSIFICATION
# ==========================================

@st.cache_data(max_entries=200, show_spinner=False)
def classify_company(
    business_description: str,
    model_name: str = "qwen2.5:14b",
    top_k: int = 5
):
    bm25, embedder, corpus_embeddings, industry_names, industry_texts = load_taxonomy_and_index()

    valid_industry_set = set(industry_names)

    retrieval_top_k = max(top_k * RETRIEVAL_MULTIPLIER, 15)

    all_results = _hybrid_retrieve(
        business_description,
        bm25,
        embedder,
        corpus_embeddings,
        industry_names,
        retrieval_top_k
    )

    retrieval_results = all_results[:top_k]

    if not retrieval_results:
        return {
            "industry": "Error",
            "activity": "Omitted for speed",
            "confidence": 0.0,
            "retrieval_gap": 0.0,
            "reasoning": "No retrieval results found.",
            "candidates": [],
            "hallucination_corrected": False,
        }

    candidate_rules = "TAXONOMY CANDIDATES:\n"

    for idx, score in retrieval_results:
        industry = industry_names[idx]
        candidate_rules += f"\nCandidate Retrieval Score: {score}\n"
        candidate_rules += industry_texts[industry]

    top_candidates = [
        {
            "industry": industry_names[idx],
            "score": score
        }
        for idx, score in retrieval_results
    ]

    confidence = top_candidates[0]["score"] if top_candidates else 0.0

    if len(top_candidates) >= 2:
        retrieval_gap = round(
            top_candidates[0]["score"] - top_candidates[1]["score"],
            1
        )
    else:
        retrieval_gap = 100.0

    valid_names_list = "\n".join(
        f"  - {candidate['industry']}"
        for candidate in top_candidates
    )

    prompt = f"""You are an elite Industry Taxonomist. Classify the company into the single most accurate Industry from the candidates below.

CANDIDATE INDUSTRIES & RULES:
{candidate_rules}

BUSINESS DESCRIPTION:
"{business_description}"

VALID INDUSTRY NAMES:
Choose ONLY from this exact list:
{valid_names_list}

=== THE 4 GOLDEN RULES ===
1. REVENUE IS KING: Base decision on majority of revenue.
2. DOMAIN OVER MEDIUM: If tech/software/data is built specifically for one sector, classify under that domain, not generic IT.
3. IGNORE CORPORATE STRUCTURE: Ignore investment holding company wording. Focus on subsidiary operations.
4. MAKER VS. MOVER: Distinguish manufacturers from distributors/retailers.

=== MANDATORY OUTPUT FORMAT ===
CRITICAL: DO NOT use <think> tags.
Output your response immediately.
You must output exactly two blocks using SQUARE BRACKETS.
Keep reasoning to a MAXIMUM OF 1 SHORT SENTENCE.

[REASONING] One short sentence explaining primary revenue and matching rule.
[INDUSTRY] Exact Industry Name from the valid list.

=== EXAMPLE ===
[REASONING] DaaS is designed exclusively for the healthcare industry, so the Healthcare domain overrides generic IT.
[INDUSTRY] Health Information Services

Now process the provided BUSINESS DESCRIPTION and output your [REASONING] and [INDUSTRY].
"""

    messages = [
        {
            "role": "system",
            "content": "You are a fast, precise classification system. You do not use <think> tags."
        },
        {
            "role": "user",
            "content": prompt
        }
    ]

    ai_industry = "Error"
    ai_reasoning = "No reasoning provided."
    hallucination_corrected = False

    try:
        num_predict = 500 if ("14b" in model_name or "8b" in model_name) else 250

        opts = {
            "temperature": 0.0,
            "num_predict": num_predict
        }

        response = ollama.chat(
            model=model_name,
            messages=messages,
            options=opts
        )

        raw_output = response["message"]["content"].strip()

        # Remove any accidental think blocks
        raw_output = re.sub(
            r"<think>.*?(</think>|$)",
            "",
            raw_output,
            flags=re.DOTALL | re.IGNORECASE
        ).strip()

        print(f"RAW LLM OUTPUT:\n{raw_output}\n")

        # Parse reasoning
        reasoning_match = re.search(
            r"\[REASONING\](.*?)(\[INDUSTR[A-Z]{1,3}\]|$)",
            raw_output,
            re.IGNORECASE | re.DOTALL
        )

        if reasoning_match:
            ai_reasoning = reasoning_match.group(1).strip()
            ai_reasoning = re.sub(
                r"\[INDUSTR[A-Z]{1,3}\]",
                "",
                ai_reasoning,
                flags=re.IGNORECASE
            ).strip()
        else:
            ai_reasoning = "Reasoning omitted or cut off."

        # Parse industry
        industry_match = re.search(
            r"\[INDUSTR[A-Z]{1,3}\](.*)",
            raw_output,
            re.IGNORECASE | re.DOTALL
        )

        if industry_match:
            ai_industry = industry_match.group(1).strip().splitlines()[0].strip()
        else:
            ai_industry = "Parse Failed"

            candidate_industry_names = [candidate["industry"] for candidate in top_candidates]

            for line in raw_output.splitlines():
                cleaned = line.replace("]", "").replace("[", "").strip()

                if cleaned in candidate_industry_names:
                    ai_industry = cleaned
                    break

    except Exception as e:
        ai_industry = "Error"
        ai_reasoning = f"LLM Error: {e}"
        print(f"LLM Error: {e}")

    # ==========================================
    # SAFER FALLBACK CHAIN
    #
    # Tier 1: Exact match in full taxonomy
    # Tier 2: Fuzzy match only within retrieved top candidates
    # Tier 3: Top retrieval match
    # ==========================================

    if ai_industry not in valid_industry_set:
        llm_raw_answer = ai_industry

        candidate_industry_names = [
            candidate["industry"]
            for candidate in top_candidates
        ]

        # Tier 2: fuzzy match only within current retrieved candidates
        close_matches = get_close_matches(
            llm_raw_answer,
            candidate_industry_names,
            n=1,
            cutoff=0.6
        )

        if close_matches:
            ai_industry = close_matches[0]
            hallucination_corrected = True

            print(f"[FuzzyMatchWithinCandidates] '{llm_raw_answer}' → '{ai_industry}'")

            ai_reasoning += (
                f" [Fuzzy-matched within retrieved candidates from "
                f"'{llm_raw_answer}' to '{ai_industry}']"
            )

        else:
            # Tier 3: fall back to top retrieval candidate
            ai_industry = industry_names[retrieval_results[0][0]]
            hallucination_corrected = True

            print(
                f"[FallbackRetrieval] No candidate fuzzy match for "
                f"'{llm_raw_answer}' → using top retrieval: '{ai_industry}'"
            )

            ai_reasoning += (
                f" [Auto-corrected: '{llm_raw_answer}' was invalid; "
                f"top retrieval match used instead.]"
            )

    return {
        "industry": ai_industry,
        "activity": "Omitted for speed",
        "confidence": confidence,
        "retrieval_gap": retrieval_gap,
        "reasoning": ai_reasoning,
        "candidates": top_candidates,
        "hallucination_corrected": hallucination_corrected,
    }
