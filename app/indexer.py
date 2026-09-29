"""
WikiLens Indexer
Extracts fields from data/enwiki_namespace_0_00009.parquet
and builds a high-performance SQLite FTS5 full-text index in data/wikilens.db.
Original dataset is strictly read-only and never modified.
"""

import os
import sys
import json
import time
import sqlite3
import pyarrow.parquet as pq

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
PARQUET_FILE = os.path.join(DATA_DIR, "enwiki_namespace_0_00009.parquet")
DB_FILE = os.path.join(DATA_DIR, "wikilens.db")

def extract_sections_text(sections_json_str):
    """Extracts raw text paragraphs and headings from sections JSON string."""
    if not sections_json_str:
        return ""
    try:
        data = json.loads(sections_json_str)
        texts = []
        def walk(obj):
            if isinstance(obj, dict):
                val = obj.get("value")
                if isinstance(val, str) and obj.get("type") in ("paragraph", "heading", "sentence"):
                    texts.append(val)
                for part in obj.get("has_parts", []):
                    walk(part)
            elif isinstance(obj, list):
                for item in obj:
                    walk(item)
        walk(data)
        return " ".join(texts)
    except Exception:
        return ""

def extract_infobox_facts(infobox_json_str):
    """Extracts key-value facts dictionary from infoboxes JSON string."""
    if not infobox_json_str:
        return ""
    try:
        data = json.loads(infobox_json_str)
        facts = {}
        def walk(obj):
            if isinstance(obj, dict):
                if obj.get("type") == "field" and obj.get("name") and obj.get("value"):
                    # keep clean string facts
                    if len(facts) < 12 and isinstance(obj["value"], str):
                        facts[obj["name"]] = obj["value"]
                for part in obj.get("has_parts", []):
                    walk(part)
            elif isinstance(obj, list):
                for item in obj:
                    walk(item)
        walk(data)
        return json.dumps(facts, ensure_ascii=False) if facts else ""
    except Exception:
        return ""

def build_index():
    print(f"Opening dataset: {PARQUET_FILE}")
    if not os.path.exists(PARQUET_FILE):
        raise FileNotFoundError(f"Dataset not found at {PARQUET_FILE}")

    parquet_file = pq.ParquetFile(PARQUET_FILE)
    total_rows = parquet_file.metadata.num_rows
    print(f"Total rows to index: {total_rows}")

    if os.path.exists(DB_FILE):
        print(f"Removing previous index database at {DB_FILE}...")
        os.remove(DB_FILE)

    con = sqlite3.connect(DB_FILE)
    cur = con.cursor()

    cur.execute("PRAGMA synchronous = OFF;")
    cur.execute("PRAGMA journal_mode = MEMORY;")
    cur.execute("PRAGMA cache_size = 100000;")

    # 1. Main article metadata table
    cur.execute("""
    CREATE TABLE articles (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        url TEXT NOT NULL,
        description TEXT,
        abstract TEXT,
        image_url TEXT,
        infobox_facts TEXT,
        date_modified TEXT,
        char_count INTEGER
    );
    """)

    # 2. FTS5 Virtual Table for BM25 search
    # Fields: name (title), description (context), abstract (lead), sections_text (deep body)
    cur.execute("""
    CREATE VIRTUAL TABLE articles_fts USING fts5(
        name,
        description,
        abstract,
        sections_text,
        tokenize = 'porter unicode61'
    );
    """)

    # 3. Trigram table for fast fuzzy title search and typo tolerance
    cur.execute("""
    CREATE VIRTUAL TABLE name_trigram USING fts5(
        name,
        tokenize = 'trigram'
    );
    """)

    start_time = time.time()
    batch_size = 2500
    num_row_groups = parquet_file.num_row_groups

    indexed_count = 0
    batch_articles = []
    batch_fts = []
    batch_trigram = []

    for rg in range(num_row_groups):
        table = parquet_file.read_row_group(rg)
        pydict = table.to_pydict()
        rg_rows = table.num_rows

        for i in range(rg_rows):
            aid = pydict['identifier'][i]
            name = pydict['name'][i] or ""
            url = pydict['url'][i] or ""
            desc = pydict['description'][i] or ""
            abstract = pydict['abstract'][i] or ""
            
            img_dict = pydict['image'][i]
            image_url = img_dict.get('content_url', "") if isinstance(img_dict, dict) and img_dict.get('content_url') else ""
            
            infobox_raw = pydict['infoboxes'][i]
            infobox_facts = extract_infobox_facts(infobox_raw)
            
            dm = str(pydict['date_modified'][i]) if pydict['date_modified'][i] else ""
            
            ver = pydict['version'][i]
            char_count = ver.get('number_of_characters', 0) if isinstance(ver, dict) else 0

            sections_raw = pydict['sections'][i]
            sections_text = extract_sections_text(sections_raw)

            batch_articles.append((aid, name, url, desc, abstract, image_url, infobox_facts, dm, char_count))
            batch_fts.append((aid, name, desc, abstract, sections_text))
            batch_trigram.append((aid, name))
            indexed_count += 1

            if len(batch_articles) >= batch_size:
                cur.executemany("INSERT INTO articles VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", batch_articles)
                cur.executemany("INSERT INTO articles_fts (rowid, name, description, abstract, sections_text) VALUES (?, ?, ?, ?, ?)", batch_fts)
                cur.executemany("INSERT INTO name_trigram (rowid, name) VALUES (?, ?)", batch_trigram)
                con.commit()
                batch_articles.clear()
                batch_fts.clear()
                batch_trigram.clear()
                elapsed = time.time() - start_time
                print(f"Indexed {indexed_count}/{total_rows} articles ({indexed_count/total_rows*100:.1f}%) in {elapsed:.1f}s...")

    if batch_articles:
        cur.executemany("INSERT INTO articles VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", batch_articles)
        cur.executemany("INSERT INTO articles_fts (rowid, name, description, abstract, sections_text) VALUES (?, ?, ?, ?, ?)", batch_fts)
        cur.executemany("INSERT INTO name_trigram (rowid, name) VALUES (?, ?)", batch_trigram)
        con.commit()

    # Create helper index on article name for autocomplete prefix lookup
    cur.execute("CREATE INDEX IF NOT EXISTS idx_articles_name ON articles(name COLLATE NOCASE);")
    con.commit()

    total_time = time.time() - start_time
    db_size = os.path.getsize(DB_FILE) / (1024 * 1024)
    print(f"\nIndexing Complete!")
    print(f"Total articles indexed: {indexed_count}")
    print(f"Database file: {DB_FILE} ({db_size:.2f} MB)")
    print(f"Time taken: {total_time:.2f} seconds ({indexed_count/total_time:.0f} docs/sec)")

    con.close()

if __name__ == "__main__":
    build_index()
