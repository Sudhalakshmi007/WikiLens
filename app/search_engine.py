"""
WikiLens Search Engine
Provides fast keyword-based search with BM25 relevance ranking,
prefix autocomplete, fuzzy matching for typo tolerance,
faceted filtering, multi-criteria sorting, and server-side LRU caching.
"""

import os
import re
import json
import sqlite3
import difflib
import threading
from collections import OrderedDict
from typing import List, Dict, Any, Optional, Tuple

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_FILE = os.path.join(DATA_DIR, "wikilens.db")

class LRUCache:
    """Thread-safe in-memory LRU cache."""
    def __init__(self, capacity: int = 512):
        self.capacity = capacity
        self.cache: OrderedDict = OrderedDict()
        self.lock = threading.Lock()

    def get(self, key: Any) -> Optional[Any]:
        with self.lock:
            if key not in self.cache:
                return None
            self.cache.move_to_end(key)
            return self.cache[key]

    def set(self, key: Any, value: Any) -> None:
        with self.lock:
            if key in self.cache:
                self.cache.move_to_end(key)
            self.cache[key] = value
            if len(self.cache) > self.capacity:
                self.cache.popitem(last=False)

    def clear(self) -> None:
        with self.lock:
            self.cache.clear()

class WikiLensSearchEngine:
    def __init__(self, db_path: str = DB_FILE):
        self.db_path = db_path
        if not os.path.exists(self.db_path):
            raise FileNotFoundError(f"Database not found at {self.db_path}. Please run indexer first.")
        self.search_cache = LRUCache(capacity=512)
        self.autocomplete_cache = LRUCache(capacity=256)

    def get_connection(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA query_only = ON;")
        con.execute("PRAGMA cache_size = 50000;")
        return con

    def clean_query_tokens(self, query: str) -> List[str]:
        """Cleans and extracts alphanumeric query tokens."""
        tokens = re.findall(r'\b\w+\b', query.lower())
        return [t for t in tokens if len(t) > 0]

    def build_fts_query(self, query: str) -> str:
        """
        Builds a safe FTS5 query string.
        - Supports exact phrases if quoted
        - Supports prefix matching on last token
        - Weighted across columns
        """
        clean_text = re.sub(r'[*+^~:(){}\[\]]', ' ', query).strip()
        tokens = clean_text.split()
        if not tokens:
            return ""

        # Phrase search if whole query is surrounded by quotes
        if clean_text.startswith('"') and clean_text.endswith('"') and len(tokens) > 1:
            phrase = clean_text.strip('"').strip()
            return f'"{phrase}"'

        # Default: Combine tokens with AND, and make the last token prefix-capable for fast typing
        terms = []
        for i, token in enumerate(tokens):
            if token.lower() in ("and", "or", "not"):
                continue
            if i == len(tokens) - 1 and len(token) >= 3:
                terms.append(f'"{token}"*')
            else:
                terms.append(f'"{token}"')

        return " AND ".join(terms) if terms else f'"{tokens[0]}"'

    def find_fuzzy_candidates(self, con: sqlite3.Connection, query: str, limit: int = 5) -> List[str]:
        """
        Finds fuzzy candidate article names for misspelled queries.
        Uses trigram matching and difflib similarity.
        """
        tokens = self.clean_query_tokens(query)
        if not tokens:
            return []

        search_term = " ".join(tokens)
        candidates = set()

        cur = con.cursor()
        for token in tokens:
            if len(token) >= 3:
                trigrams = [token[i:i+3] for i in range(len(token)-2)]
                if trigrams:
                    trigram_query = ' AND '.join(f'"{tg}"' for tg in trigrams[:4])
                    try:
                        cur.execute("""
                        SELECT name FROM name_trigram
                        WHERE name_trigram MATCH ?
                        LIMIT 20
                        """, (trigram_query,))
                        for row in cur.fetchall():
                            candidates.add(row["name"])
                    except Exception:
                        pass

        if not candidates:
            first_chars = search_term[:2]
            cur.execute("""
            SELECT name FROM articles
            WHERE name LIKE ?
            LIMIT 50
            """, (f"{first_chars}%",))
            for row in cur.fetchall():
                candidates.add(row["name"])

        if not candidates:
            return []

        matches = difflib.get_close_matches(search_term, list(candidates), n=limit, cutoff=0.5)
        return matches

    def search(
        self,
        query: str,
        page: int = 1,
        page_size: int = 10,
        enable_fuzzy: bool = True,
        sort_by: str = "relevance",       # "relevance", "recent", "length"
        has_image: bool = False,
        has_infobox: bool = False,
        depth: str = "all"                # "all", "stub", "medium", "comprehensive"
    ) -> Dict[str, Any]:
        """
        Executes a smart keyword search with BM25 relevance ranking,
        faceted filtering, sorting, typo fallback, and in-memory LRU caching.
        """
        query = query.strip()
        if not query:
            return {
                "query": "",
                "total_results": 0,
                "page": page,
                "page_size": page_size,
                "total_pages": 0,
                "did_you_mean": None,
                "filter_zero_results": False,
                "unfiltered_total": 0,
                "cached": False,
                "results": []
            }

        # Check LRU Cache
        cache_key = (
            query.lower(),
            page,
            page_size,
            enable_fuzzy,
            sort_by.lower(),
            bool(has_image),
            bool(has_infobox),
            depth.lower()
        )
        cached_result = self.search_cache.get(cache_key)
        if cached_result is not None:
            # Return fresh copy with cached flag set
            res = dict(cached_result)
            res["cached"] = True
            return res

        fts_expr = self.build_fts_query(query)
        offset = (page - 1) * page_size
        con = self.get_connection()
        cur = con.cursor()

        results = []
        did_you_mean = None
        filter_zero_results = False
        unfiltered_total = 0

        # Construct WHERE clauses for facets
        where_clauses = ["articles_fts MATCH ?"]
        params = [fts_expr]

        if has_image:
            where_clauses.append("a.image_url != ''")
        if has_infobox:
            where_clauses.append("a.infobox_facts != ''")
        if depth == "stub":
            where_clauses.append("a.char_count < 2000")
        elif depth == "medium":
            where_clauses.append("a.char_count >= 2000 AND a.char_count <= 10000")
        elif depth == "comprehensive":
            where_clauses.append("a.char_count > 10000")

        # Construct ORDER BY
        if sort_by == "recent":
            order_sql = "a.date_modified DESC, score ASC"
        elif sort_by == "length":
            order_sql = "a.char_count DESC, score ASC"
        else:  # default "relevance"
            order_sql = "score ASC"

        where_sql = " AND ".join(where_clauses)

        try:
            sql = f"""
            SELECT
                a.id,
                a.name,
                a.url,
                a.description,
                a.abstract,
                a.image_url,
                a.infobox_facts,
                a.date_modified,
                a.char_count,
                bm25(articles_fts, 10.0, 5.0, 3.0, 1.0) AS score,
                snippet(articles_fts, 0, '<mark>', '</mark>', '...', 10) AS title_snippet,
                snippet(articles_fts, 2, '<mark>', '</mark>', '...', 25) AS abstract_snippet,
                snippet(articles_fts, 3, '<mark>', '</mark>', '...', 25) AS sections_snippet
            FROM articles_fts
            JOIN articles a ON a.id = articles_fts.rowid
            WHERE {where_sql}
            ORDER BY {order_sql}
            LIMIT ? OFFSET ?
            """
            cur.execute(sql, params + [page_size, offset])
            rows = cur.fetchall()

            # Count total matching rows
            count_sql = f"""
            SELECT COUNT(*)
            FROM articles_fts
            JOIN articles a ON a.id = articles_fts.rowid
            WHERE {where_sql}
            """
            cur.execute(count_sql, params)
            total_count = cur.fetchone()[0]

            # Check if 0 results are caused by filters
            is_filtered = has_image or has_infobox or (depth != "all")
            if total_count == 0 and is_filtered:
                cur.execute("SELECT COUNT(*) FROM articles_fts WHERE articles_fts MATCH ?", (fts_expr,))
                raw_matches = cur.fetchone()[0]
                if raw_matches > 0:
                    filter_zero_results = True
                    unfiltered_total = raw_matches

            # If 0 results overall and fuzzy search is enabled, try finding closest matches
            if total_count == 0 and not filter_zero_results and enable_fuzzy:
                fuzzy_names = self.find_fuzzy_candidates(con, query, limit=3)
                if fuzzy_names:
                    best_match = fuzzy_names[0]
                    did_you_mean = best_match
                    fuzzy_fts = self.build_fts_query(best_match)
                    fuzzy_params = [fuzzy_fts] + params[1:]
                    cur.execute(sql, fuzzy_params + [page_size, offset])
                    rows = cur.fetchall()
                    cur.execute(count_sql, fuzzy_params)
                    total_count = cur.fetchone()[0]

            for r in rows:
                raw_abstract = r["abstract"] or ""
                snippet_text = r["abstract_snippet"]
                matched_in = "abstract"

                if not snippet_text or '<mark>' not in snippet_text:
                    if r["sections_snippet"] and '<mark>' in r["sections_snippet"]:
                        snippet_text = r["sections_snippet"]
                        matched_in = "sections"
                    elif raw_abstract:
                        snippet_text = raw_abstract[:220] + ("..." if len(raw_abstract) > 220 else "")
                        matched_in = "abstract"
                    else:
                        snippet_text = r["description"] or "No summary available."
                        matched_in = "description"

                facts = {}
                if r["infobox_facts"]:
                    try:
                        facts = json.loads(r["infobox_facts"])
                    except Exception:
                        facts = {}

                # Calculate estimated read time: ~200 words / min, ~5 chars / word
                chars = r["char_count"] or len(raw_abstract)
                read_time_mins = max(1, round(chars / 1000))

                results.append({
                    "id": r["id"],
                    "name": r["name"],
                    "url": r["url"],
                    "description": r["description"] or "",
                    "snippet": snippet_text,
                    "matched_in": matched_in,
                    "image_url": r["image_url"] or None,
                    "infobox_facts": facts,
                    "date_modified": r["date_modified"] or "",
                    "char_count": r["char_count"] or 0,
                    "read_time_mins": read_time_mins,
                    "bm25_score": round(abs(r["score"]), 3)
                })

        except Exception as e:
            print(f"FTS Query Error on '{query}': {e}")
            total_count = 0
            results = []
        finally:
            con.close()

        result_payload = {
            "query": query,
            "used_query": did_you_mean if did_you_mean else query,
            "did_you_mean": did_you_mean,
            "filter_zero_results": filter_zero_results,
            "unfiltered_total": unfiltered_total,
            "total_results": total_count,
            "page": page,
            "page_size": page_size,
            "total_pages": (total_count + page_size - 1) // page_size if total_count > 0 else 0,
            "sort_by": sort_by,
            "has_image": has_image,
            "has_infobox": has_infobox,
            "depth": depth,
            "cached": False,
            "results": results
        }

        # Cache valid results
        self.search_cache.set(cache_key, result_payload)
        return result_payload

    def autocomplete(self, prefix: str, limit: int = 6) -> List[Dict[str, Any]]:
        """
        Instant autocomplete suggestions by prefix on article name with in-memory LRU caching.
        """
        prefix = prefix.strip()
        if not prefix or len(prefix) < 2:
            return []

        cache_key = (prefix.lower(), limit)
        cached = self.autocomplete_cache.get(cache_key)
        if cached is not None:
            return cached

        con = self.get_connection()
        cur = con.cursor()
        try:
            cur.execute("""
            SELECT id, name, description, image_url, url
            FROM articles
            WHERE name LIKE ?
            ORDER BY
                CASE WHEN LOWER(name) = LOWER(?) THEN 0 ELSE 1 END,
                LENGTH(name) ASC
            LIMIT ?
            """, (f"{prefix}%", prefix, limit))
            rows = cur.fetchall()

            suggestions = []
            for r in rows:
                suggestions.append({
                    "id": r["id"],
                    "name": r["name"],
                    "description": r["description"] or "",
                    "image_url": r["image_url"] or None,
                    "url": r["url"]
                })

            if len(suggestions) < limit:
                cur.execute("""
                SELECT id, name, description, image_url, url
                FROM articles
                WHERE name LIKE ? AND name NOT LIKE ?
                ORDER BY LENGTH(name) ASC
                LIMIT ?
                """, (f"% {prefix}%", f"{prefix}%", limit - len(suggestions)))
                for r in cur.fetchall():
                    suggestions.append({
                        "id": r["id"],
                        "name": r["name"],
                        "description": r["description"] or "",
                        "image_url": r["image_url"] or None,
                        "url": r["url"]
                    })

            self.autocomplete_cache.set(cache_key, suggestions)
            return suggestions
        finally:
            con.close()

    def get_article(self, article_id: int) -> Optional[Dict[str, Any]]:
        """Retrieves full article details by ID."""
        con = self.get_connection()
        cur = con.cursor()
        try:
            cur.execute("""
            SELECT id, name, url, description, abstract, image_url, infobox_facts, date_modified, char_count
            FROM articles
            WHERE id = ?
            """, (article_id,))
            row = cur.fetchone()
            if not row:
                return None

            facts = {}
            if row["infobox_facts"]:
                try:
                    facts = json.loads(row["infobox_facts"])
                except Exception:
                    facts = {}

            return {
                "id": row["id"],
                "name": row["name"],
                "url": row["url"],
                "description": row["description"] or "",
                "abstract": row["abstract"] or "",
                "image_url": row["image_url"] or None,
                "infobox_facts": facts,
                "date_modified": row["date_modified"] or "",
                "char_count": row["char_count"] or 0
            }
        finally:
            con.close()

    def get_stats(self) -> Dict[str, Any]:
        """Returns corpus summary stats."""
        con = self.get_connection()
        cur = con.cursor()
        try:
            cur.execute("SELECT COUNT(*) FROM articles;")
            total_articles = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM articles WHERE image_url != '';")
            articles_with_images = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM articles WHERE infobox_facts != '';")
            articles_with_infobox = cur.fetchone()[0]

            return {
                "total_articles": total_articles,
                "articles_with_images": articles_with_images,
                "articles_with_infobox": articles_with_infobox,
                "engine": "WikiLens Keyword + BM25 + Trigram Fuzzy Search Engine"
            }
        finally:
            con.close()
