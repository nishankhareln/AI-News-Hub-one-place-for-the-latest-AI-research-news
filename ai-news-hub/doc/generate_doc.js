// Generates the AI News Hub project document as a .docx file.
// Run with: NODE_PATH=<global node_modules> node generate_doc.js

const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  AlignmentType, LevelFormat, HeadingLevel, BorderStyle, WidthType,
  ShadingType,
} = require("docx");

const BLUE = "1F7FC2";
const SLATE = "26333F";
const GRID = "CCD8E4";

// ---- small helpers -------------------------------------------------------
const body = (text, opts = {}) =>
  new Paragraph({
    spacing: { after: 140, line: 276 },
    children: [new TextRun({ text, ...opts })],
  });

const runs = (children, after = 140) =>
  new Paragraph({ spacing: { after, line: 276 }, children });

const bullet = (text) =>
  new Paragraph({
    numbering: { reference: "bullets", level: 0 },
    spacing: { after: 80, line: 268 },
    children: [new TextRun(text)],
  });

const step = (text) =>
  new Paragraph({
    numbering: { reference: "steps", level: 0 },
    spacing: { after: 90, line: 268 },
    children: [new TextRun(text)],
  });

const code = (text) =>
  new Paragraph({
    spacing: { after: 60 },
    shading: { type: ShadingType.CLEAR, fill: "F1F5FA" },
    indent: { left: 220 },
    children: [new TextRun({ text, font: "Consolas", size: 20 })],
  });

const h1 = (text) =>
  new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun(text)] });

// table cell
const cell = (children, width, fill) =>
  new TableCell({
    width: { size: width, type: WidthType.DXA },
    margins: { top: 80, bottom: 80, left: 120, right: 120 },
    shading: fill ? { type: ShadingType.CLEAR, fill } : undefined,
    borders: {
      top: { style: BorderStyle.SINGLE, size: 1, color: GRID },
      bottom: { style: BorderStyle.SINGLE, size: 1, color: GRID },
      left: { style: BorderStyle.SINGLE, size: 1, color: GRID },
      right: { style: BorderStyle.SINGLE, size: 1, color: GRID },
    },
    children,
  });

const cellText = (text, bold = false) =>
  new Paragraph({ children: [new TextRun({ text, bold })] });

const cellCode = (text) =>
  new Paragraph({ children: [new TextRun({ text, font: "Consolas", size: 20 })] });

function twoColTable(headerA, headerB, rowsData, wA, wB) {
  const rows = [
    new TableRow({
      tableHeader: true,
      children: [
        cell([cellText(headerA, true)], wA, "D5E8F5"),
        cell([cellText(headerB, true)], wB, "D5E8F5"),
      ],
    }),
  ];
  for (const [a, b, mono] of rowsData) {
    rows.push(
      new TableRow({
        children: [
          cell([mono ? cellCode(a) : cellText(a)], wA),
          cell([cellText(b)], wB),
        ],
      })
    );
  }
  return new Table({
    width: { size: 9360, type: WidthType.DXA },
    columnWidths: [wA, wB],
    rows,
  });
}

const spacer = () => new Paragraph({ spacing: { after: 60 }, children: [] });

// ---- the document --------------------------------------------------------
const doc = new Document({
  styles: {
    default: { document: { run: { font: "Arial", size: 22 } } },
    paragraphStyles: [
      {
        id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 28, bold: true, font: "Arial", color: BLUE },
        paragraph: { spacing: { before: 320, after: 140 }, outlineLevel: 0 },
      },
    ],
  },
  numbering: {
    config: [
      {
        reference: "bullets",
        levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 560, hanging: 280 } } } }],
      },
      {
        reference: "steps",
        levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 560, hanging: 280 } } } }],
      },
    ],
  },
  sections: [
    {
      properties: {
        page: {
          size: { width: 12240, height: 15840 },
          margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 },
        },
      },
      children: [
        // Title block
        new Paragraph({
          spacing: { after: 40 },
          children: [new TextRun({ text: "AI News Hub", bold: true, size: 44, color: SLATE })],
        }),
        new Paragraph({
          spacing: { after: 60 },
          border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: BLUE, space: 6 } },
          children: [new TextRun({ text: "How the site works, in plain language", size: 24, color: "5A6B7C" })],
        }),
        new Paragraph({
          spacing: { after: 220 },
          children: [new TextRun({ text: "Project notes  ·  D:/my_research/ai-news-hub", size: 18, color: "7A8794" })],
        }),

        // Why this exists
        h1("Why this exists"),
        body("AI moves fast enough that keeping up feels like a second job. New papers land on arXiv every day, and the chatter around them moves quicker than that. I wanted one quiet page that just shows what came out: the newest research and the headlines, without the clutter most sites pile on. Open it, glance at what's new, click through if something grabs you. That's the whole idea."),

        // Short version
        h1("The short version"),
        body("There are two parts. A small Python program on the back end goes out and collects papers and news from public sources. A plain web page shows them in two tabs, Papers and News. Nothing is typed in by hand."),
        body("When you open the page, it asks the back end for the latest. The back end either hands over a batch it pulled a few minutes ago, or goes and fetches a fresh one. No database, no login, and no API keys. Every source the site reads is open to anyone."),

        // Tech stack
        h1("What it is built with"),
        body("Each piece does one job:"),
        twoColTable("Tool", "What it does", [
          ["Python 3.11", "The language the back end is written in."],
          ["FastAPI", "The web framework. It answers the browser and serves the page."],
          ["Uvicorn", "The server that runs FastAPI."],
          ["httpx", "Fetches data from the outside sources. It runs asynchronously, so the site can pull from several places at the same time instead of waiting on each one in turn."],
          ["feedparser", "Reads feeds. arXiv and the news sites publish in Atom and RSS formats, and feedparser turns that into data Python can use."],
          ["HTML, CSS, JS", "The front end. No framework and no build step. One page, one stylesheet, one script."],
        ], 2400, 6960),

        // Sources
        h1("Where the papers and news come from"),
        body("Papers come from arXiv, the open archive most AI research is posted to. The site asks for the newest submissions across four areas: artificial intelligence (cs.AI), machine learning (cs.LG), language and NLP (cs.CL), and computer vision (cs.CV). It takes the 30 most recent and keeps them in newest-first order."),
        body("News is pulled from three places at once:"),
        bullet("Hacker News, filtered to stories about AI. This is the liveliest of the three and usually carries the freshest links."),
        bullet("VentureBeat's AI section."),
        bullet("MIT Technology Review's AI coverage."),
        body("The back end reads all three, folds them into a single list, and sorts everything by time so the newest item sits on top no matter which site it came from."),

        // Freshness
        h1("How fresh is it, really?"),
        body("Short answer: as fresh as the moment you open the page, with one small catch worth being clear about."),
        body("When the page loads, or when you press Refresh, it asks the back end for the latest. If nobody has asked in the last 15 minutes, the back end goes out to arXiv and the news sites right then and brings back what is current. If someone did ask in that window, it reuses that batch instead of fetching again. Holding a copy for 15 minutes is called caching, and the site keeps it in memory."),
        body("People often picture this kind of site as a live feed that updates every second. This one does not do that. It does not hold an open stream; it fetches when asked and keeps the result for 15 minutes. There are two reasons. Reusing a recent batch makes the page load instantly. It also keeps the site polite to free services. Asking arXiv for data every second would get the site blocked, and fairly so. If you wanted it closer to live, the 15-minute figure is one number in the code, and the page could also be set to refresh itself on a timer."),

        // Step by step
        h1("Step by step: what happens when you open it"),
        step("Your browser asks the back end for the page, and FastAPI sends back the HTML file."),
        step("The browser then loads the stylesheet and the script."),
        step("The script asks the back end two things straight away: give me the papers, and give me the news. It requests both up front so switching tabs feels instant."),
        step("The back end checks its memory. If it fetched recently, it answers at once. If not, it goes out to the sources."),
        step("For papers, it calls arXiv, waits for the reply, and pulls out each paper's title, authors, summary, link, date, and subject tags."),
        step("For news, it calls Hacker News and the two blogs at the same time, waits for all of them, then merges and sorts the results by date."),
        step("The back end saves both batches in memory with a timestamp, so the next visitor inside 15 minutes gets them with no wait."),
        step("The results travel back to the browser as plain data, and the script turns each item into a card on the page."),
        step("The Refresh button runs the whole trip again and forces a brand-new fetch, skipping the saved copy."),

        // Endpoints
        h1("The endpoints"),
        body("The back end answers at a handful of addresses. The ones starting with /api return data; the rest return the page and its files."),
        twoColTable("Request", "What it returns", [
          ["GET /", "The web page itself (the HTML)."],
          ["GET /api/papers", "The list of papers, as data."],
          ["GET /api/news", "The merged list of news, as data."],
          ["GET /api/health", "A quick \"ok\" so you can confirm the server is up."],
          ["GET /style.css, /app.js", "The page's styling and script, served as static files."],
        ], 3200, 6160),
        body("Both /api answers come back in the same shape: a list of items plus an error field that stays empty when all goes well. If a source is down, that field says what happened and the page still shows whatever did arrive."),

        // API keys
        h1("A note on API keys"),
        body("None are needed, and none are stored. arXiv's API is open. Hacker News is read through a free public search service. The two blogs publish open feeds anyone can read. Because there are no keys, there is nothing secret to guard and nothing that expires."),
        body("If the site later added a source that did require a key, as some news APIs do, the right home for it would be an environment variable kept out of the code and out of version control. There is none of that today."),

        // Resilience
        h1("If a source has a bad day"),
        body("Each fetch is wrapped so that one failing source cannot take down the page. If VentureBeat's feed times out, the news list still comes back with the Hacker News and MIT results. If arXiv is briefly unreachable, the Papers tab shows a short message instead of a blank screen. The site keeps working on whatever is available at the time."),

        // Files
        h1("The files in the project"),
        twoColTable("File", "What's in it", [
          ["main.py", "The back end: fetching, caching, sorting, and the endpoints.", true],
          ["static/index.html", "The page layout and the two tabs.", true],
          ["static/style.css", "The look, including the light sky-blue theme.", true],
          ["static/app.js", "Fetches from the back end and draws the cards.", true],
          ["requirements.txt", "The Python libraries to install.", true],
          ["README.md", "Quick-start notes.", true],
        ], 3200, 6160),

        // Running
        h1("Running it"),
        body("From the project folder, set up once and then start the server:"),
        code("python -m venv venv"),
        code("venv\\Scripts\\Activate.ps1"),
        code("pip install -r requirements.txt"),
        code("uvicorn main:app --reload"),
        body("Then open the address it prints in a browser. By default that is http://127.0.0.1:8000."),

        // Next
        h1("What could come next"),
        body("A few things are on the list but not built yet. A search box to filter by topic. A way to save papers worth returning to. A couple more sources, like Hugging Face Papers. A short morning email with the top items. None of these change how the core works; they sit on top of what is already here."),
      ],
    },
  ],
});

const outPath = path.join(__dirname, "AI News Hub - How It Works.docx");
Packer.toBuffer(doc).then((buf) => {
  fs.writeFileSync(outPath, buf);
  console.log("Wrote " + outPath);
});
