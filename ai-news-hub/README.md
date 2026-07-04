# AI News Hub

A simple webpage for the latest AI **research papers** and **news**, all in one place.
Built because AI moves so fast it's hard to keep up — this page just shows you what's new.

## What it does

- **Research Papers** — newest papers from arXiv (AI / Machine Learning / NLP / Computer Vision)
- **AI News** — headlines from Hacker News, VentureBeat, and MIT Tech Review
- **Search** — type a topic; papers come straight from an arXiv search, news is filtered
- **Ask AI** — tell the agent what you want ("latest papers on diffusion models", "what's new with OpenAI") and it pulls the real links from arXiv, the news feeds, or the wider web
- **Auto-fetches** live from free sources, cached for 15 minutes

The papers and news work with **no keys**. The Ask agent needs two free keys (below).

## Tech

- Backend: FastAPI (Python)
- Frontend: plain HTML / CSS / JS (served by the backend)
- Sources: arXiv API, Hacker News (Algolia) API, RSS feeds
- Agent: LangGraph + Google Gemini, with Tavily for web search

## Run it locally

```powershell
# 1. (first time) create a virtual environment
python -m venv venv

# 2. activate it
venv\Scripts\Activate.ps1

# 3. install dependencies
pip install -r requirements.txt

# 4. start the server
uvicorn main:app --reload
```

Then open http://127.0.0.1:8000 in your browser.

## Enabling the "Ask AI" agent

The papers and news tabs work as-is. To turn on the Ask tab:

1. Copy `.env.example` to `.env`.
2. Add a **Gemini** key (free): https://aistudio.google.com/app/apikey
3. Add a **Tavily** key for web search (free): https://app.tavily.com
4. Restart the server.

```
GOOGLE_API_KEY=your_gemini_key
TAVILY_API_KEY=your_tavily_key
GEMINI_MODEL=gemini-2.0-flash
```

Without a Gemini key the Ask tab just shows a short note telling you to add one; nothing else breaks.

## Project structure

```
ai-news-hub/
├── main.py            # FastAPI backend: fetches & caches papers + news
├── requirements.txt
├── static/
│   ├── index.html     # the page
│   ├── style.css      # styling
│   └── app.js         # fetches from the API and renders cards
└── README.md
```

## Ideas for later

- Save / bookmark papers
- Daily email digest
- More sources (Hugging Face Papers, Papers with Code, Reddit)
- Let the agent remember the conversation (multi-turn chat)
- A "Go" button that opens the agent's top result for you
