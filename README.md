# WikiLens — Smart Wikipedia Search (MVP)

WikiLens is a fast, lightweight, keyword-based Smart Wikipedia Search Engine built over the Wikimedia Wikipedia extract (`data/enwiki_namespace_0_00009.parquet`).

---

## 🔍 How Dataset Fields are Used

| Dataset Field | WikiLens Feature | Implementation |
|---------------|------------------|----------------|
| **`name`** | Title, Search, Autocomplete | Heavily weighted in BM25 (`10.0`), indexed for instantaneous prefix autocomplete and trigram fuzzy matching. |
| **`abstract`** | Search Body & Highlight Snippets | BM25 content matching (`3.0`), highlighted query snippet generation (`<mark>...</mark>`). |
| **`description`** | Context & Relevance Boosting | Boosted in BM25 (`5.0`), displayed as context subtitle tags on search cards. |
| **`sections`** | Deeper Content Matching | Paragraphs extracted and indexed in FTS (`1.0`) so deep article sections match even when not in the lead abstract. |
| **`image.content_url`** | Article Thumbnails | Lead visual previews on search result cards, autocomplete dropdown, and quick-view modal. |
| **`url`** | Wikipedia Source Links | Direct clickable links to live Wikipedia articles. |
| **`infoboxes`** | Structured Article Facts | Parsed into key-value facts pills on result cards and full fact tables in the Quick View modal. |

---

## ⚡ Architecture & Technology Stack

* **Storage & Indexing**: SQLite FTS5 (Full-Text Search 5) with BM25 relevance ranking and Trigram tokenization for typo tolerance.
* **Corpus Size**: 25,000 Wikipedia articles indexed in ~16 seconds (82.8 MB self-contained index).
* **Search Performance**: Sub-millisecond to ~15ms query execution times.
* **Backend**: FastAPI + Uvicorn with asynchronous endpoints for search, autocomplete, and article details.
* **Frontend**: Responsive Single-Page Application (SPA) with dark mode, debounced autocomplete, highlighting, pagination, and Quick View facts drawer.

---

## 🚀 Running the Application

### 1. Build / Rebuild Index (Optional)
```bash
python app/indexer.py
```
*(The index at `data/wikilens.db` is already built and ready.)*

### 2. Launch WikiLens Server
```bash
python run.py
```
* **Web UI**: [http://127.0.0.1:8000](http://127.0.0.1:8000)
* **Interactive API Docs**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

---

## 📡 REST API Endpoints

- `GET /api/search?q={query}&page=1&limit=10&fuzzy=true`: Search articles with BM25 ranking, highlighting, and typo correction.
- `GET /api/autocomplete?q={prefix}&limit=6`: Instant prefix suggestion lookup.
- `GET /api/article/{id}`: Full article details, abstract, and extracted infobox facts.
- `GET /api/stats`: Corpus statistics.
