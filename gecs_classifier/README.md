# 🔬 GECS Industry Classifier

An AI-powered industry classification engine using **Hybrid Search (BM25 + Semantic Embeddings)** combined with a **local LLM via Ollama**. Built with Streamlit.

---

## 🚀 How It Works

1. **Hybrid Retrieval** — Combines BM25 (keyword) and BGE semantic embeddings using Reciprocal Rank Fusion (RRF) to retrieve the most relevant industry candidates.
2. **LLM Classification** — A local Qwen model (via Ollama) picks the best industry from the top candidates using structured reasoning.
3. **Hallucination Correction** — A 3-tier fallback (exact match → fuzzy match → top retrieval) prevents invalid outputs.

---

## 🛠️ Setup

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Install Ollama & pull a model
```bash
# Install Ollama from https://ollama.com
ollama pull qwen2.5:14b
```

### 3. Set environment variables
```bash
# Windows
set DB_PASSWORD=your_database_password

# Linux/Mac
export DB_PASSWORD=your_database_password
```

> ⚠️ Never hardcode credentials. Always use environment variables.

### 4. Configure database connection
In `chatbox.py`, update the `CONN_STR` with your SQL Server details:
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

### 5. Run the app
```bash
streamlit run streamlitGECS.py
```

---

## ⚙️ Configuration

| Parameter | Default | Description |
|---|---|---|
| `ALPHA` | `0.25` | BM25 vs Semantic weight (0 = full semantic, 1 = full BM25) |
| `RETRIEVAL_MULTIPLIER` | `5` | How many extra candidates to retrieve internally |
| `EMBEDDING_MODEL` | `BAAI/bge-large-en-v1.5` | Sentence transformer model |

---

## 📁 Project Structure

```
gecs_classifier/
├── chatbox.py          # Backend: retrieval, embeddings, LLM classification
├── streamlitGECS.py    # Frontend: Streamlit UI
├── requirements.txt    # Python dependencies
└── README.md
```

---

## 🧠 Tech Stack

- **Streamlit** — UI
- **BM25 (rank_bm25)** — Keyword retrieval
- **BGE Embeddings (sentence-transformers)** — Semantic retrieval
- **Ollama (Qwen)** — Local LLM inference
- **pyodbc** — SQL Server connection
