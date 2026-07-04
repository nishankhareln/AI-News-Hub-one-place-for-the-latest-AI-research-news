"""
LangGraph agent for AI News Hub.

A custom multi-node graph behind the "Ask" tab:

    route ──► search ──► self_check ──► (retry weak results) ──► END
          ├─► brief_gather ──► brief_write ──► END
          └─► fetch_page ──► summarize ──► END

Features the user picked:
  - Briefing pipeline (gather arXiv + news + web, rank, write a short briefing)
  - Memory / follow-ups (a checkpointer keeps the conversation per thread)
  - Self-check node (grades relevance, re-searches once if weak)
  - Summarize-a-link node (reads a URL and summarizes it)

Source-fetching (fetch_papers / fetch_news) lives in main.py and is imported
lazily inside the nodes to avoid a circular import.
"""

import asyncio
import json
import os
import re
from typing import Annotated, TypedDict

import httpx
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import create_react_agent

HEADERS = {"User-Agent": "AI-News-Hub/1.0 (+https://github.com)"}

# Words that mean "give me an overview", which route to the briefing pipeline.
BRIEF_WORDS = (
    "briefing", "brief me", "overview", "what's new", "whats new", "what is new",
    "this week", "lately", "digest", "round up", "roundup", "catch me up",
    "summary of the latest", "what happened",
)
URL_RE = re.compile(r"https?://\S+")


# ---------------------------------------------------------------------------
# Tools (used by the "search" path's ReAct agent)
# ---------------------------------------------------------------------------
@tool
async def search_arxiv(query: str) -> str:
    """Find the latest AI/ML research papers on a topic, from arXiv plus
    Hugging Face trending papers. Input: a short topic, e.g. 'diffusion models'."""
    from main import fetch_papers

    data = await fetch_papers(query)
    results = [
        {"title": p["title"], "url": p["link"], "source": "arXiv/HF"}
        for p in data["items"][:8]
    ]
    return json.dumps({"results": results})


@tool
async def search_news(query: str) -> str:
    """Find recent AI news headlines on a topic from Hacker News, VentureBeat,
    MIT Tech Review, Hugging Face, and IBM."""
    from main import fetch_news

    data = await fetch_news(query)
    results = [
        {"title": n["title"], "url": n["link"], "source": n["source"]}
        for n in data["items"][:8]
    ]
    return json.dumps({"results": results})


@tool
async def web_search(query: str) -> str:
    """Search the whole web for anything (announcements, blog posts, general or
    very recent info) and return the top links."""
    results = await _web_search(query)
    return json.dumps({"results": results, "note": "" if results else "web search off: no TAVILY_API_KEY"})


async def _web_search(query: str, n: int = 6):
    if not os.environ.get("TAVILY_API_KEY"):
        return []
    try:
        from tavily import TavilyClient

        client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])
        resp = await asyncio.to_thread(lambda: client.search(query, max_results=n))
        return [
            {"title": r.get("title", ""), "url": r.get("url", ""), "source": "Web"}
            for r in resp.get("results", [])
        ]
    except Exception:
        return []


def _strip_html(html: str) -> str:
    html = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text).strip()


def _collect_links(messages):
    """Pull tool-returned links out of a ReAct run, de-duplicated, in order."""
    links, seen = [], set()
    for m in messages:
        if isinstance(m, ToolMessage):
            try:
                for r in json.loads(m.content).get("results", []):
                    u = r.get("url")
                    if u and u not in seen:
                        seen.add(u)
                        links.append(r)
            except Exception:
                pass
    return links


def _last_ai_text(messages) -> str:
    for m in reversed(messages):
        if isinstance(m, AIMessage) and isinstance(m.content, str) and m.content.strip():
            return m.content
    return ""


# ---------------------------------------------------------------------------
# Graph state
# ---------------------------------------------------------------------------
class State(TypedDict):
    messages: Annotated[list, add_messages]
    mode: str
    query: str
    url: str
    links: list
    attempts: int
    retry: bool
    page_text: str


SEARCH_SYS = (
    "You are AI News Hub's assistant. Use the tools to pull real links for the "
    "user's request: search_arxiv for papers, search_news for news, web_search "
    "for general or very recent info. You may call several. Base your answer only "
    "on tool results, reply in 2-4 short sentences, then let the links speak."
)


# ---------------------------------------------------------------------------
# Build the graph (once, cached)
# ---------------------------------------------------------------------------
_graph = None


def _get_graph():
    global _graph
    if _graph is not None:
        return _graph

    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    llm = ChatGoogleGenerativeAI(model=model, temperature=0)
    react = create_react_agent(llm, [search_arxiv, search_news, web_search])

    # -- nodes ---------------------------------------------------------------
    async def route(state: State):
        msg = state["messages"][-1].content if state["messages"] else ""
        low = msg.lower()
        base = {"links": [], "attempts": 0, "retry": False, "url": "", "page_text": "", "query": msg}
        url = URL_RE.search(msg)
        if url:
            base["mode"], base["url"] = "summarize", url.group(0)
        elif any(w in low for w in BRIEF_WORDS):
            base["mode"] = "briefing"
        else:
            base["mode"] = "search"
        return base

    async def search_node(state: State):
        sys = SEARCH_SYS
        if state.get("attempts", 0) > 0:
            sys += " The first attempt's results were weak; broaden or rephrase the search."
        history = [m for m in state["messages"][-10:] if not isinstance(m, SystemMessage)]
        result = await react.ainvoke({"messages": [SystemMessage(content=sys)] + history})
        rmsgs = result["messages"]
        return {"messages": [AIMessage(content=_last_ai_text(rmsgs))], "links": _collect_links(rmsgs)}

    async def self_check(state: State):
        if state.get("attempts", 0) >= 1 or not state.get("links"):
            return {"retry": False}
        titles = "; ".join(l.get("title", "") for l in state["links"][:8])
        grade = await llm.ainvoke([
            SystemMessage(content="Reply with only YES or NO."),
            HumanMessage(content=f"Are these results relevant to the request '{state['query']}'? Results: {titles}"),
        ])
        if (grade.content or "").strip().lower().startswith("no"):
            return {"retry": True, "attempts": state.get("attempts", 0) + 1}
        return {"retry": False}

    async def brief_plan(state: State):
        # Pull the core topic out of a sentence like "brief me on AI agents this week".
        msg = await llm.ainvoke([
            SystemMessage(content="Extract the core search topic from the request. Reply with ONLY the topic in 1-5 words, no punctuation."),
            HumanMessage(content=state["query"]),
        ])
        topic = (msg.content or "").strip().strip('."\n')
        return {"query": topic or state["query"]}

    async def brief_gather(state: State):
        from main import fetch_news, fetch_papers

        q = state["query"]
        papers, news = await asyncio.gather(fetch_papers(q), fetch_news(q))
        web = await _web_search(q)
        links, seen = [], set()

        def add(items):
            for r in items:
                u = r.get("url")
                if u and u not in seen:
                    seen.add(u)
                    links.append(r)

        add({"title": p["title"], "url": p["link"],
             "source": "Hugging Face" if "huggingface" in p["link"] else "arXiv"}
            for p in papers["items"][:8])
        add({"title": n["title"], "url": n["link"], "source": n["source"]} for n in news["items"][:8])
        add(web)
        return {"links": links}

    async def brief_write(state: State):
        links = state["links"][:15]
        if not links:
            return {"messages": [AIMessage(content="I couldn't find anything fresh on that topic right now.")]}
        bullet = "\n".join(f"- {l['title']} ({l['source']})" for l in links)
        msg = await llm.ainvoke([
            SystemMessage(content=(
                "Write a short AI briefing. Using ONLY the items, write 3-5 sentences "
                "on the key themes and a few notable items. Do not invent anything.")),
            HumanMessage(content=f"Topic: {state['query']}\nItems:\n{bullet}"),
        ])
        return {"messages": [AIMessage(content=msg.content)]}

    async def fetch_page(state: State):
        text = ""
        try:
            async with httpx.AsyncClient(timeout=20, headers=HEADERS, follow_redirects=True) as client:
                r = await client.get(state["url"])
                r.raise_for_status()
            text = _strip_html(r.text)[:6000]
        except Exception:
            text = ""
        return {"links": [{"title": state["url"], "url": state["url"], "source": "Web"}], "page_text": text}

    async def summarize_node(state: State):
        if not state.get("page_text"):
            return {"messages": [AIMessage(content="I couldn't read that page — it may block bots or need a login.")]}
        msg = await llm.ainvoke([
            SystemMessage(content="Summarize this page in 3-5 sentences, plain English."),
            HumanMessage(content=state["page_text"]),
        ])
        return {"messages": [AIMessage(content=msg.content)]}

    # -- wiring --------------------------------------------------------------
    g = StateGraph(State)
    g.add_node("route", route)
    g.add_node("search", search_node)
    g.add_node("self_check", self_check)
    g.add_node("brief_plan", brief_plan)
    g.add_node("brief_gather", brief_gather)
    g.add_node("brief_write", brief_write)
    g.add_node("fetch_page", fetch_page)
    g.add_node("summarize", summarize_node)

    g.add_edge(START, "route")
    g.add_conditional_edges("route", lambda s: s["mode"], {
        "search": "search", "briefing": "brief_plan", "summarize": "fetch_page",
    })
    g.add_edge("search", "self_check")
    g.add_conditional_edges("self_check", lambda s: "retry" if s.get("retry") else "done", {
        "retry": "search", "done": END,
    })
    g.add_edge("brief_plan", "brief_gather")
    g.add_edge("brief_gather", "brief_write")
    g.add_edge("brief_write", END)
    g.add_edge("fetch_page", "summarize")
    g.add_edge("summarize", END)

    _graph = g.compile(checkpointer=MemorySaver())
    return _graph


async def run_agent(message: str, thread_id: str = "default") -> dict:
    """Entry point used by the FastAPI endpoint."""
    if not os.environ.get("GOOGLE_API_KEY"):
        return {"answer": "", "links": [], "error": (
            "The Ask agent needs a Google Gemini key. Put GOOGLE_API_KEY in a .env "
            "file next to main.py (see .env.example)."
        )}
    try:
        graph = _get_graph()
        result = await graph.ainvoke(
            {"messages": [HumanMessage(content=message)]},
            {"configurable": {"thread_id": thread_id}},
        )
    except Exception as exc:
        return {"answer": "", "links": [], "error": f"Agent error: {exc}"}

    return {
        "answer": _last_ai_text(result.get("messages", [])),
        "links": (result.get("links") or [])[:12],
        "error": None,
    }
