"""
WikiLens FastAPI Application
Serves the search REST API and static frontend UI.
"""

import os
from fastapi import FastAPI, Query, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from app.search_engine import WikiLensSearchEngine

app = FastAPI(
    title="WikiLens",
    description="Smart Wikipedia Search Engine powered by FTS5, BM25, and Trigram Fuzzy Matching",
    version="1.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

search_engine = WikiLensSearchEngine()

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

@app.get("/api/search")
async def search_articles(
    q: str = Query(..., description="Search query string"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(10, ge=1, le=50, description="Results per page"),
    fuzzy: bool = Query(True, description="Enable fuzzy typo matching"),
    sort_by: str = Query("relevance", description="Sort order: relevance, recent, length"),
    has_image: bool = Query(False, description="Filter: only articles with thumbnail images"),
    has_infobox: bool = Query(False, description="Filter: only articles with structured infoboxes"),
    depth: str = Query("all", description="Filter by depth: all, stub, medium, comprehensive")
):
    """
    Search Wikipedia articles with BM25 relevance ranking, faceted filtering,
    multi-criteria sorting, and typo fallback.
    """
    return search_engine.search(
        query=q,
        page=page,
        page_size=limit,
        enable_fuzzy=fuzzy,
        sort_by=sort_by,
        has_image=has_image,
        has_infobox=has_infobox,
        depth=depth
    )

@app.get("/api/autocomplete")
async def autocomplete_articles(
    q: str = Query(..., description="Query prefix"),
    limit: int = Query(6, ge=1, le=12, description="Max suggestions")
):
    """
    Fast prefix autocomplete suggestions as you type.
    """
    return search_engine.autocomplete(prefix=q, limit=limit)

@app.get("/api/article/{article_id}")
async def get_article_detail(article_id: int):
    """
    Fetch full article details including extracted infobox facts.
    """
    article = search_engine.get_article(article_id)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    return article

@app.get("/api/stats")
async def get_corpus_stats():
    """
    Corpus and indexing statistics.
    """
    return search_engine.get_stats()

# Mount static frontend
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/")
async def serve_index():
    index_file = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"message": "WikiLens backend running. Frontend static files not found."}
