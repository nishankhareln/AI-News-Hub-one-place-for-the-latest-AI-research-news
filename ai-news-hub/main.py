"""
AI News Hub - a simple page for the latest AI research papers and news,
plus an "Ask" agent (LangGraph + Gemini) that pulls real links on request.

Backend: FastAPI. It fetches live from free sources, caches the results for
15 minutes so we don't hammer the APIs, and serves a small static frontend.

Sources:
  - Research papers: arXiv API (cs.AI, cs.LG, cs.CL, cs.CV) - free, no key
  - AI news: Hacker News (Algolia API) + VentureBeat AI (RSS) - free, no key
  - Ask agent: Gemini (needs GOOGLE_API_KEY) + Tavily web search (TAVILY_API_KEY)
"""

import asyncio
import calendar
import json
import os
import re
import time
import urllib.parse
from pathlib import Path

import feedparser
import httpx
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Load keys from a local .env file if one exists (optional dependency).
try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).parent / ".env")
except Exception:
    pass

app = FastAPI(title="AI News Hub")

BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR / "static"

# Simple in-memory cache with a time-to-live, so repeated page loads are fast
# and we stay friendly to the free APIs.

CACHE_TTL_SECONDS = 15 * 60
_cache: dict[str, dict] = {}


def cache_get(key: str):
    item = _cache.get(key)
    if item and (time.time() - item["ts"] < CACHE_TTL_SECONDS):
        return item["data"]
    return None


def cache_set(key: str, data):
    _cache[key] = {"data": data, "ts": time.time()}


# A browser-like user agent keeps some feeds/APIs from blocking us.
HEADERS = {"User-Agent": "AI-News-Hub/1.0 (+https://github.com)"}


# ---------------------------------------------------------------------------
# Research papers (arXiv)

# The four AI-related categories we always stay within.
ARXIV_CATS = "cat:cs.AI+OR+cat:cs.LG+OR+cat:cs.CL+OR+cat:cs.CV"


def _arxiv_url(query: str = "") -> str:
    """Build the arXiv query. With no term we get the newest AI papers; with a
    term we search those categories for it, still newest-first."""
    term = query.strip()
    if term:
        # Phrase-search the term across title/abstract/etc, inside the AI cats.
        enc = urllib.parse.quote(f'"{term}"')
        search = f"%28{ARXIV_CATS}%29+AND+all:{enc}"
    else:
        search = ARXIV_CATS
    return (
        "https://export.arxiv.org/api/query"
        f"?search_query={search}"
        "&sortBy=submittedDate&sortOrder=descending&max_results=30"
    )


# Hugging Face daily papers - community-voted "trending" AI research.
HF_PAPERS_URL = "https://huggingface.co/api/daily_papers"


async def fetch_hf_papers():
    """Trending AI papers from Hugging Face, in the same shape as arXiv items."""
    items = []
    try:
        async with httpx.AsyncClient(timeout=20, headers=HEADERS, follow_redirects=True) as client:
            resp = await client.get(HF_PAPERS_URL)
            resp.raise_for_status()
        for entry in resp.json():
            p = entry.get("paper", {})
            pid = p.get("id", "")
            if not pid:
                continue
            items.append(
                {
                    "title": " ".join((p.get("title") or "").split()),
                    "summary": " ".join((p.get("summary") or "").split()),
                    "authors": [a.get("name", "") for a in p.get("authors", [])],
                    "link": f"https://huggingface.co/papers/{pid}",
                    "published": entry.get("publishedAt", p.get("publishedAt", "")),
                    "categories": ["Hugging Face"],
                }
            )
    except Exception:
        pass
    return items


def _paper_id(paper):
    """Pull the arXiv id out of a link so arXiv and HF copies can be de-duped."""
    m = re.search(r"(\d{4}\.\d{4,5})", paper.get("link", ""))
    return m.group(1) if m else paper.get("link", "")


async def fetch_papers(query: str = ""):
    cache_key = f"papers:{query.strip().lower()}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    papers = []
    arxiv_error = None
    try:
        async with httpx.AsyncClient(timeout=20, headers=HEADERS, follow_redirects=True) as client:
            resp = await client.get(_arxiv_url(query))
            resp.raise_for_status()
        feed = feedparser.parse(resp.content)
        for entry in feed.entries:
            authors = [a.get("name", "") for a in entry.get("authors", [])]
            # arXiv summaries have hard line breaks; flatten them.
            summary = " ".join(entry.get("summary", "").split())
            papers.append(
                {
                    "title": " ".join(entry.get("title", "").split()),
                    "summary": summary,
                    "authors": authors,
                    "link": entry.get("link", ""),
                    "published": entry.get("published", ""),
                    "categories": [t.get("term", "") for t in entry.get("tags", [])],
                }
            )
    except Exception as exc:  # keep going even if arXiv is down - HF may still work
        arxiv_error = f"arXiv fetch failed: {exc}"

    # Add Hugging Face trending papers (filtered by the search term if there is one).
    term = query.strip().lower()
    hf = await fetch_hf_papers()
    if term:
        hf = [p for p in hf if term in p["title"].lower() or term in p["summary"].lower()]

    seen = {_paper_id(p) for p in papers}
    for p in hf[:20]:
        pid = _paper_id(p)
        if pid not in seen:
            seen.add(pid)
            papers.append(p)

    if papers:
        error = None
    elif arxiv_error:
        error = arxiv_error
    elif term:
        error = f'No papers found for "{query.strip()}"'
    else:
        error = "No papers found"

    result = {"items": papers, "error": error}
    if papers:
        cache_set(cache_key, result)
    return result


# ---------------------------------------------------------------------------
# AI news (Hacker News + VentureBeat AI RSS), merged and sorted by date
# ---------------------------------------------------------------------------
RSS_FEEDS = [
    ("VentureBeat AI", "https://venturebeat.com/category/ai/feed/"),
    ("MIT Tech Review AI", "https://www.technologyreview.com/topic/artificial-intelligence/feed"),
    ("Hugging Face", "https://huggingface.co/blog/feed.xml"),
    # IBM has no working RSS of its own, so we pull IBM AI coverage via Google News.
    ("IBM AI", "https://news.google.com/rss/search?q=IBM+artificial+intelligence&hl=en-US&gl=US&ceid=US:en"),
]


def _hn_url(query: str = "") -> str:
    # With no search term we browse AI stories; with one, we search for it.
    term = query.strip() or "AI"
    return (
        "https://hn.algolia.com/api/v1/search_by_date"
        f"?tags=story&query={urllib.parse.quote(term)}&hitsPerPage=25"
    )


async def _fetch_hn(client: httpx.AsyncClient, query: str = ""):
    items = []
    try:
        resp = await client.get(_hn_url(query))
        resp.raise_for_status()
        for hit in resp.json().get("hits", []):
            title = hit.get("title")
            if not title:
                continue
            url = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}"
            items.append(
                {
                    "title": title,
                    "link": url,
                    "source": "Hacker News",
                    "published": hit.get("created_at", ""),
                    "ts": hit.get("created_at_i", 0),  # epoch seconds, for sorting
                    "points": hit.get("points", 0),
                }
            )
    except Exception:
        pass
    return items


async def _fetch_rss(client: httpx.AsyncClient, source: str, url: str, term: str = ""):
    items = []
    try:
        resp = await client.get(url)
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
        for entry in feed.entries[:15]:
            title = " ".join(entry.get("title", "").split())
            # When searching, only keep feed items whose title mentions the term.
            if term and term not in title.lower():
                continue
            # feedparser parses dates into a UTC struct_time; timegm -> epoch.
            parsed = entry.get("published_parsed") or entry.get("updated_parsed")
            ts = calendar.timegm(parsed) if parsed else 0
            items.append(
                {
                    "title": title,
                    "link": entry.get("link", ""),
                    "source": source,
                    "published": entry.get("published", entry.get("updated", "")),
                    "ts": ts,
                    "points": None,
                }
            )
    except Exception:
        pass
    return items


async def fetch_news(query: str = ""):
    term = query.strip().lower()
    cache_key = f"news:{term}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    async with httpx.AsyncClient(timeout=20, headers=HEADERS, follow_redirects=True) as client:
        tasks = [_fetch_hn(client, query)]
        tasks += [_fetch_rss(client, name, url, term) for name, url in RSS_FEEDS]
        groups = await asyncio.gather(*tasks)

    items = [item for group in groups for item in group]

    # Each item carries a numeric "ts" (epoch seconds); sort newest first.
    items.sort(key=lambda item: item.get("ts", 0), reverse=True)

    if items:
        error = None
    elif term:
        error = f'No news found for "{query.strip()}"'
    else:
        error = "No news sources responded"

    result = {"items": items, "error": error}
    if items:
        cache_set(cache_key, result)
    return result

# "Ask" agent - implemented as a LangGraph graph in agent.py. Imported lazily
# in the endpoint so the rest of the site keeps working even if the agent
# libraries or API keys are missing.

class AgentQuery(BaseModel):
    message: str = ""
    thread_id: str = "default"


# ---------------------------------------------------------------------------
# API routes

@app.post("/api/agent")
async def api_agent(body: AgentQuery):
    message = body.message.strip()
    if not message:
        return JSONResponse({"answer": "", "links": [], "error": "Type a request first."})
    try:
        from agent import run_agent
    except Exception as exc:
        return JSONResponse({"answer": "", "links": [], "error": f"Agent unavailable: {exc}"})
    return JSONResponse(await run_agent(message, body.thread_id or "default"))


@app.get("/api/papers")
async def api_papers(q: str = ""):
    return JSONResponse(await fetch_papers(q))


@app.get("/api/news")
async def api_news(q: str = ""):
    return JSONResponse(await fetch_news(q))


@app.get("/api/health")
async def health():
    return {"status": "ok"}


# Serve the frontend. Mounted last so it doesn't shadow the API routes.
@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/", StaticFiles(directory=STATIC_DIR), name="static")
