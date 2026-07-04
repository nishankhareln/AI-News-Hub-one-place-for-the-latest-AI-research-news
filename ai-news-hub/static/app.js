// AI News Hub - frontend. Fetches papers + news from the backend and renders cards.

const state = { papers: null, news: null, active: "papers", query: "" };

// One conversation id per page load, so the Ask agent remembers follow-ups.
const ASK_THREAD =
  window.crypto && crypto.randomUUID ? crypto.randomUUID() : "t" + Date.now();

function timeAgo(dateStr) {
  if (!dateStr) return "";
  const then = new Date(dateStr);
  if (isNaN(then)) return "";
  const diff = (Date.now() - then.getTime()) / 1000;
  if (diff < 3600) return Math.max(1, Math.floor(diff / 60)) + "m ago";
  if (diff < 86400) return Math.floor(diff / 3600) + "h ago";
  return Math.floor(diff / 86400) + "d ago";
}

function esc(str) {
  const d = document.createElement("div");
  d.textContent = str || "";
  return d.innerHTML;
}

// ---- source filters: show/hide cards by source (e.g. only Hugging Face) ----
const filters = { papers: "all", news: "all" };

function applyFilter(kind) {
  const listId = kind === "papers" ? "papers-list" : "news-list";
  const sel = filters[kind];
  document.querySelectorAll(`#${listId} .card`).forEach((c) => {
    c.style.display = sel === "all" || c.dataset.source === sel ? "" : "none";
  });
}

function buildFilterBar(kind) {
  const bar = document.getElementById(kind === "papers" ? "papers-filter" : "news-filter");
  const listId = kind === "papers" ? "papers-list" : "news-list";
  const sources = [
    ...new Set(
      [...document.querySelectorAll(`#${listId} .card`)]
        .map((c) => c.dataset.source)
        .filter(Boolean)
    ),
  ];
  if (sources.length < 2) {
    bar.innerHTML = "";
    return;
  }
  if (filters[kind] !== "all" && !sources.includes(filters[kind])) filters[kind] = "all";
  bar.innerHTML = ["all", ...sources]
    .map(
      (s) =>
        `<button class="filter-chip${filters[kind] === s ? " active" : ""}" data-src="${esc(s)}">${s === "all" ? "All" : esc(s)}</button>`
    )
    .join("");
  bar.querySelectorAll(".filter-chip").forEach((btn) =>
    btn.addEventListener("click", () => {
      filters[kind] = btn.dataset.src;
      buildFilterBar(kind);
    })
  );
  applyFilter(kind);
}

function emptyMessage(kind, data) {
  if (state.query) return `No ${kind} found for “${esc(state.query)}”. Try another word.`;
  if (data.error) return `Couldn’t load ${kind}: ${esc(data.error)}`;
  return `No ${kind} found right now.`;
}

function renderPapers(data) {
  const el = document.getElementById("papers-list");
  if (!data.items || !data.items.length) {
    el.innerHTML = `<div class="placeholder">${emptyMessage("papers", data)}</div>`;
    document.getElementById("papers-filter").innerHTML = "";
    return;
  }
  el.innerHTML = data.items
    .map((p) => {
      const authors =
        p.authors.length > 3
          ? p.authors.slice(0, 3).join(", ") + " +" + (p.authors.length - 3)
          : p.authors.join(", ");
      const cats = (p.categories || [])
        .slice(0, 3)
        .map((c) => `<span class="chip">${esc(c)}</span>`)
        .join("");
      const src = (p.link || "").includes("huggingface") ? "Hugging Face" : "arXiv";
      return `
        <article class="card" data-source="${esc(src)}">
          <h3><a href="${esc(p.link)}" target="_blank" rel="noopener">${esc(p.title)}</a></h3>
          <div class="meta">
            ${cats}
            <span>${esc(authors)}</span>
            <span>${timeAgo(p.published)}</span>
          </div>
          <p class="summary">${esc(p.summary)}</p>
        </article>`;
    })
    .join("");
  buildFilterBar("papers");
}

function renderNews(data) {
  const el = document.getElementById("news-list");
  if (!data.items || !data.items.length) {
    el.innerHTML = `<div class="placeholder">${emptyMessage("news", data)}</div>`;
    document.getElementById("news-filter").innerHTML = "";
    return;
  }
  el.innerHTML = data.items
    .map((n) => {
      const points = n.points != null ? `<span>▲ ${n.points}</span>` : "";
      return `
        <article class="card" data-source="${esc(n.source)}">
          <h3><a href="${esc(n.link)}" target="_blank" rel="noopener">${esc(n.title)}</a></h3>
          <div class="meta">
            <span class="source-tag">${esc(n.source)}</span>
            <span>${timeAgo(n.published)}</span>
            ${points}
          </div>
        </article>`;
    })
    .join("");
  buildFilterBar("news");
}

async function load(kind, force) {
  const status = document.getElementById("status");
  const listId = kind === "papers" ? "papers-list" : "news-list";
  if (!state[kind] || force) {
    document.getElementById(listId).innerHTML =
      `<div class="placeholder">Loading ${kind}…</div>`;
    status.textContent = "Loading…";
    const params = new URLSearchParams();
    if (state.query) params.set("q", state.query);
    if (force) params.set("t", Date.now()); // cache-bust on manual refresh/search
    const qs = params.toString();
    try {
      const resp = await fetch(`/api/${kind}` + (qs ? `?${qs}` : ""));
      state[kind] = await resp.json();
    } catch (e) {
      state[kind] = { items: [], error: "Network error" };
    }
    status.textContent = "Updated " + new Date().toLocaleTimeString();
  }
  if (kind === "papers") renderPapers(state.papers);
  else renderNews(state.news);
}

function switchTab(tab) {
  state.active = tab;
  document.querySelectorAll(".tab").forEach((b) =>
    b.classList.toggle("active", b.dataset.tab === tab)
  );
  document.querySelectorAll(".panel").forEach((p) =>
    p.classList.toggle("active", p.id === tab)
  );
  // The top search bar + refresh only apply to the papers/news feeds.
  const feedTab = tab === "papers" || tab === "news";
  document.getElementById("search-form").style.display = feedTab ? "" : "none";
  document.getElementById("search-info").style.display = feedTab ? "" : "none";
  document.getElementById("refresh").style.display = feedTab ? "" : "none";
  document.getElementById("status").style.display = feedTab ? "" : "none";
  if (feedTab) load(tab);
}

function updateSearchInfo() {
  const info = document.getElementById("search-info");
  if (state.query) {
    info.hidden = false;
    info.innerHTML =
      `Showing results for <strong>“${esc(state.query)}”</strong>` +
      ` <button id="clear-search" class="clear-search">✕ clear</button>`;
    document.getElementById("clear-search").addEventListener("click", clearSearch);
  } else {
    info.hidden = true;
    info.innerHTML = "";
  }
}

// Run a new search across both tabs. Passing "" resets to the default feeds.
function runSearch(term) {
  state.query = term.trim();
  state.papers = null;
  state.news = null;
  updateSearchInfo();
  const other = state.active === "papers" ? "news" : "papers";
  load(state.active, true);
  load(other, true);
}

function clearSearch() {
  document.getElementById("search-input").value = "";
  runSearch("");
}

document.querySelectorAll(".tab").forEach((btn) =>
  btn.addEventListener("click", () => switchTab(btn.dataset.tab))
);

document.getElementById("refresh").addEventListener("click", () => {
  load(state.active, true);
});

document.getElementById("search-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const term = document.getElementById("search-input").value.trim();
  if (term === state.query) return; // nothing changed
  runSearch(term);
});

// ---- Ask AI agent ----
async function runAsk(message) {
  const ansEl = document.getElementById("ask-answer");
  const linksEl = document.getElementById("ask-links");
  ansEl.innerHTML = `<div class="placeholder">Thinking… pulling links for you…</div>`;
  linksEl.innerHTML = "";
  try {
    const resp = await fetch("/api/agent", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, thread_id: ASK_THREAD }),
    });
    const data = await resp.json();
    if (data.error) {
      ansEl.innerHTML = `<div class="error">${esc(data.error)}</div>`;
      return;
    }
    ansEl.innerHTML = data.answer
      ? `<p class="ask-text">${esc(data.answer).replace(/\n/g, "<br>")}</p>`
      : "";
    const links = data.links || [];
    if (!links.length) {
      linksEl.innerHTML = `<div class="placeholder">No links found — try rephrasing.</div>`;
      return;
    }
    linksEl.innerHTML = links
      .map(
        (l) => `
        <article class="card">
          <h3><a href="${esc(l.url)}" target="_blank" rel="noopener">${esc(l.title || l.url)}</a></h3>
          <div class="meta">
            <span class="source-tag">${esc(l.source || "Link")}</span>
            <span class="link-url">${esc(l.url)}</span>
          </div>
        </article>`
      )
      .join("");
  } catch (e) {
    ansEl.innerHTML = `<div class="error">Network error. Is the server running?</div>`;
  }
}

document.getElementById("ask-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const m = document.getElementById("ask-input").value.trim();
  if (m) runAsk(m);
});

// Initial load
load("papers");
// Prefetch news quietly so the tab is instant.
load("news");
