// Builds report/Sentari_Project_Report.docx from the figures, screenshots and results in the repo.
//   cd report/tools && npm install && node build_report.js
// Then open in Word and update fields (or run export_pdf.ps1, which also refreshes the tables of contents).
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, ImageRun, Table, TableRow, TableCell, AlignmentType, HeadingLevel,
  LevelFormat, BorderStyle, WidthType, ShadingType, PageBreak, Header, Footer, PageNumber, NumberFormat,
  TableOfContents, StyleLevel, PositionalTab, PositionalTabAlignment, PositionalTabRelativeTo, PositionalTabLeader,
  TabStopType,
} = require("docx");

const ROOT = path.resolve(__dirname, "..", "..");
const FIG = path.join(ROOT, "report", "figures");
const SHOT = path.join(ROOT, "report", "screenshots");
const OUT = path.join(ROOT, "report", "Sentari_Project_Report.docx");

const FONT = "Calibri", MONO = "Consolas";
const NAVY = "1F3864", ACCENT = "2F5D8A", MUTED = "595959", RULE = "BFC7D1", HEAD_FILL = "DCE4EE", ZEBRA = "F4F6F9";
const CONTENT_W = 9026; // A4 width 11906 - 2 x 1440 margins (DXA)

// ------------------------------------------------------------------ inline markup: **bold**, *italic*, `code`
function runs(text, base = {}) {
  const out = [];
  const re = /(\*\*[^*]+\*\*|`[^`]+`|\*[^*]+\*)/g;
  let last = 0, m;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(new TextRun({ text: text.slice(last, m.index), ...base }));
    const t = m[0];
    if (t.startsWith("**")) out.push(new TextRun({ text: t.slice(2, -2), bold: true, ...base }));
    else if (t.startsWith("`")) out.push(new TextRun({ text: t.slice(1, -1), font: MONO, size: 19, color: "3A3A3A", ...base }));
    else out.push(new TextRun({ text: t.slice(1, -1), italics: true, ...base }));
    last = m.index + t.length;
  }
  if (last < text.length) out.push(new TextRun({ text: text.slice(last), ...base }));
  return out;
}

const P = (text, opts = {}) => new Paragraph({ children: runs(text), alignment: AlignmentType.JUSTIFIED, ...opts });
const H1 = (text) => new Paragraph({ heading: HeadingLevel.HEADING_1, pageBreakBefore: true, children: [new TextRun(text)] });
const H2 = (text) => new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun(text)] });
const H3 = (text) => new Paragraph({ heading: HeadingLevel.HEADING_3, children: [new TextRun(text)] });
const bullets = (items, ref = "bullets") => items.map((t) => new Paragraph({ numbering: { reference: ref, level: 0 }, children: runs(t), alignment: AlignmentType.LEFT }));
let numberedListId = 0;
const numbered = (items) => { const ref = `num${numberedListId++ % 12}`; return items.map((t) => new Paragraph({ numbering: { reference: ref, level: 0 }, children: runs(t) })); };
const code = (lines) => lines.map((l, i) => new Paragraph({
  style: "Code", children: [new TextRun({ text: l || " ", font: MONO, size: 17 })],
  spacing: { before: i === 0 ? 80 : 0, after: i === lines.length - 1 ? 160 : 0 },
}));
const formula = (text) => new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 100, after: 140 },
  children: [new TextRun({ text, font: "Cambria Math", size: 22, italics: true })] });
const note = (text) => new Paragraph({
  children: runs(text, { size: 20 }), alignment: AlignmentType.LEFT, spacing: { before: 120, after: 160 }, keepLines: true,
  shading: { type: ShadingType.CLEAR, fill: "FFF7E6", color: "auto" },
  border: { left: { style: BorderStyle.SINGLE, size: 18, color: "D9B877", space: 8 } }, indent: { left: 200, right: 120 },
});

// ------------------------------------------------------------------ figures and tables (numbered per chapter)
let chapter = 0, figN = 0, tabN = 0;
const figures = [];
function newChapter(title) { chapter += 1; figN = 0; tabN = 0; return H1(`${chapter}  ${title}`); }

function pngSize(file) {
  const b = fs.readFileSync(file);
  return { w: b.readUInt32BE(16), h: b.readUInt32BE(20), data: b };
}
function figure(file, caption, { width = 6.2, maxHeight = 8.3 } = {}) {
  const { w, h, data } = pngSize(file);
  let wIn = width, hIn = (width * h) / w;
  if (hIn > maxHeight) { hIn = maxHeight; wIn = (maxHeight * w) / h; }
  figN += 1;
  const label = `Figure ${chapter}.${figN}`;
  return [
    new Paragraph({ alignment: AlignmentType.CENTER, keepNext: true, spacing: { before: 160, after: 60 },
      children: [new ImageRun({ type: "png", data, transformation: { width: Math.round(wIn * 96), height: Math.round(hIn * 96) },
        altText: { title: label, description: caption, name: label } })] }),
    new Paragraph({ style: "FigureCaption", children: [new TextRun({ text: `${label}: `, bold: true }), ...runs(caption)] }),
  ];
}
const shot = (name, caption, opts) => figure(path.join(SHOT, name), caption, opts);
const fig = (name, caption, opts) => figure(path.join(FIG, name), caption, opts);

const border = { style: BorderStyle.SINGLE, size: 4, color: RULE };
const borders = { top: border, bottom: border, left: border, right: border };
function table(caption, headers, rows, widths, { fontSize = 19, firstColBold = false } = {}) {
  const total = widths.reduce((a, b) => a + b, 0);
  const scaled = widths.map((x) => Math.round((x * CONTENT_W) / total));
  scaled[scaled.length - 1] += CONTENT_W - scaled.reduce((a, b) => a + b, 0);
  const cell = (text, i, header, zebra) => new TableCell({
    borders, width: { size: scaled[i], type: WidthType.DXA },
    shading: header ? { fill: HEAD_FILL, type: ShadingType.CLEAR, color: "auto" } : zebra ? { fill: ZEBRA, type: ShadingType.CLEAR, color: "auto" } : undefined,
    margins: { top: 60, bottom: 60, left: 100, right: 100 },
    children: String(text).split("\n").map((line) => new Paragraph({ spacing: { before: 0, after: 0, line: 252 },
      children: runs(line, { size: fontSize, bold: header || (firstColBold && i === 0) ? true : undefined }) })),
  });
  tabN += 1;
  const label = `Table ${chapter}.${tabN}`;
  return [
    new Paragraph({ style: "TableCaption", keepNext: true, children: [new TextRun({ text: `${label}: `, bold: true }), ...runs(caption)] }),
    new Table({
      width: { size: CONTENT_W, type: WidthType.DXA }, columnWidths: scaled,
      rows: [new TableRow({ tableHeader: true, children: headers.map((h, i) => cell(h, i, true)) }),
        ...rows.map((r, ri) => new TableRow({ cantSplit: true, children: r.map((c, i) => cell(c, i, false, ri % 2 === 1)) }))],
    }),
    new Paragraph({ spacing: { before: 0, after: 120 }, children: [] }),
  ];
}

// ------------------------------------------------------------------ data from results/
const R = (f) => JSON.parse(fs.readFileSync(path.join(ROOT, "results", f), "utf8"));
const ladder = R("model_ladder.json");
const lexfail = R("lexicon_failures.json");
const gH = R("grounding_adversarial_heuristic.json");
const gN = R("grounding_adversarial_nli.json");
const pct = (x, d = 1) => `${(x * 100).toFixed(d)}%`;
const f3 = (x) => x.toFixed(3);
const PRETTY = { vader: "VADER", sentiwordnet: "SentiWordNet", lm_lexicon: "Loughran-McDonald (seed list)",
  lm_directional: "LM + directional rules", nb_tfidf: "Naive Bayes (TF-IDF)", dt_tfidf: "Decision Tree (TF-IDF)",
  cnn: "CNN (Kim-style)", lstm: "BiLSTM", finbert_zeroshot: "FinBERT, zero-shot", finbert_ft: "FinBERT, fine-tuned" };
const RUNG = { vader: "Lexicon", sentiwordnet: "Lexicon", lm_lexicon: "Lexicon", lm_directional: "Lexicon + rules",
  nb_tfidf: "Classical ML", dt_tfidf: "Classical ML", cnn: "Deep learning", lstm: "Deep learning",
  finbert_zeroshot: "Transformer", finbert_ft: "Transformer" };
const ORDER = ["vader", "sentiwordnet", "lm_lexicon", "lm_directional", "nb_tfidf", "dt_tfidf", "cnn", "lstm", "finbert_zeroshot", "finbert_ft"];
const prf = (g, c) => `${g.per_class[c].precision.toFixed(2)} / ${g.per_class[c].recall.toFixed(2)} / ${g.per_class[c].f1.toFixed(2)}`;

// ------------------------------------------------------------------ front matter
const title = [
  new Paragraph({ spacing: { before: 1800 }, alignment: AlignmentType.CENTER, children: [new TextRun({ text: "SENTARI", bold: true, size: 72, color: NAVY, characterSpacing: 60 })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 120, after: 120 }, children: [new TextRun({ text: "An Earnings-Call & Filings Intelligence Platform for Retail Investors", size: 32, color: ACCENT })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 900 }, children: [new TextRun({ text: "Aspect-based sentiment analysis with grounded multi-agent briefs", italics: true, size: 24, color: MUTED })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, border: { top: { style: BorderStyle.SINGLE, size: 6, color: RULE, space: 12 } }, spacing: { before: 200 }, children: [new TextRun({ text: "Project Report", bold: true, size: 30 })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 120 }, children: [new TextRun({ text: "Final Year Project — Sentiment Analysis (231CAUEC51)", size: 24 })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 700 }, children: [new TextRun({ text: "Submitted by", size: 22, color: MUTED })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 60 }, children: [new TextRun({ text: "Nishant Vikas Narudkar", bold: true, size: 28 })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 700 }, children: [new TextRun({ text: "Ramrao Adik Institute of Technology", size: 24 })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: "D Y Patil University, Navi Mumbai", size: 24 })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 500 }, children: [new TextRun({ text: "September 2026", size: 24, color: MUTED })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 200 }, children: [new TextRun({ text: "Source code: github.com/nishnarudkar/Sentari", size: 20, color: ACCENT })] }),
];

const FM_HEAD = (t) => new Paragraph({ style: "FrontHeading", pageBreakBefore: true, children: [new TextRun(t)] });

const abstract = [
  new Paragraph({ style: "FrontHeading", children: [new TextRun("Abstract")] }),
  P("Retail investors who follow fifteen to twenty companies cannot read every earnings-call transcript, 10-K/10-Q filing and news item each quarter, so subtle but important signals — softer guidance language, hedging in the Q&A, litigation risk in a footnote — are routinely missed. **Sentari** is a daily intelligence service that ingests these disclosures, measures sentiment at the level of six financial *aspects* (guidance, margins, demand, litigation, management tone and liquidity) instead of one document-level score, tracks how each aspect moves from quarter to quarter, and produces a written brief in which every sentence is traceable to the source sentence that supports it."),
  P("The system comprises an idempotent ingestion pipeline with transcript-aware parsing (speakers, prepared remarks versus Q&A), an aspect-extraction stage combining rules with spaCy dependency parsing, and a *model ladder* of ten sentiment models — VADER, SentiWordNet, Loughran-McDonald, a finance-directional rule model, Naive Bayes, Decision Tree, CNN, BiLSTM, and FinBERT both zero-shot and fine-tuned — all evaluated on one held-out gold set and tracked in MLflow. A LangGraph pipeline of Extractor, Bull, Bear, Skeptic and Judge agents writes the brief; the Skeptic acts as a grounding gate that checks citations, numbers, semantic similarity and entailment, and removes unsupported claims before the Judge sees them. Results are served through a FastAPI service and a Next.js dashboard with drill-down from brief to source sentence, together with a drift monitor and a daily digest."),
  P(`On a hand-written gold set of 94 aspect-labelled sentences, fine-tuned FinBERT reached a macro-F1 of ${f3(ladder.finbert_ft.gold.macro_f1)} and the finance-directional rule model ${f3(ladder.lm_directional.gold.macro_f1)}, against ${f3(ladder.vader.gold.macro_f1)} for VADER and ${f3(ladder.sentiwordnet.gold.macro_f1)} for SentiWordNet. On 26 "trap" sentences where financial meaning inverts everyday polarity (falling costs are good news), VADER was wrong ${pct(lexfail.models.vader.error_rate_trap)} of the time and SentiWordNet ${pct(lexfail.models.sentiwordnet.error_rate_trap)}. In an adversarial grounding audit the Skeptic caught every fabricated number, missing or wrong citation and invented claim; the heuristic Skeptic caught only ${pct(gH.polarity_flip.catch_rate)} of polarity-flipped claims, which rose to 100% with a transformer NLI model.`),
  P("These numbers are reported with their limitations: the gold set is small, the training data are template-generated weak labels, and the demonstration corpus is synthetic. The signal-validity study and a human grounding audit are designed and implemented but have not yet been run on real data. The report states throughout which parts are measured, which are built but unverified, and which remain to be done."),
  new Paragraph({ spacing: { before: 200 }, children: [new TextRun({ text: "Keywords: ", bold: true }), new TextRun("aspect-based sentiment analysis, financial NLP, Loughran-McDonald, FinBERT, multi-agent LLM systems, grounding, hallucination detection, earnings calls")] }),
];

const tocs = [
  FM_HEAD("Table of Contents"),
  new TableOfContents("Table of Contents", { hyperlink: true, headingStyleRange: "1-2" }),
  FM_HEAD("List of Figures"),
  new TableOfContents("List of Figures", { hyperlink: true, stylesWithLevels: [new StyleLevel("Figure Caption", 1)] }),
  FM_HEAD("List of Tables"),
  new TableOfContents("List of Tables", { hyperlink: true, stylesWithLevels: [new StyleLevel("Table Caption", 1)] }),
];

// abbreviations table is built without chapter numbering
function plainTable(headers, rows, widths) {
  const t = table("", headers, rows, widths);
  tabN -= 1;
  return [t[1], t[2]];
}
const abbreviations = [
  FM_HEAD("Abbreviations"),
  ...plainTable(["Term", "Meaning"], [
    ["ABSA", "Aspect-Based Sentiment Analysis"], ["API", "Application Programming Interface"],
    ["BiLSTM", "Bidirectional Long Short-Term Memory network"], ["CNN", "Convolutional Neural Network"],
    ["DT", "Decision Tree"], ["DVC", "Data Version Control"], ["EDGAR", "SEC Electronic Data Gathering, Analysis and Retrieval system"],
    ["F1 / macro-F1", "Harmonic mean of precision and recall / unweighted mean of per-class F1"],
    ["FinBERT", "BERT model further trained on financial text (ProsusAI/finbert)"], ["LLM", "Large Language Model"],
    ["LM", "Loughran-McDonald financial sentiment dictionary"], ["MD&A", "Management's Discussion and Analysis section of a 10-K/10-Q"],
    ["NB", "Naive Bayes"], ["NLI", "Natural Language Inference (entailment / neutral / contradiction)"],
    ["NSE / BSE", "National Stock Exchange / Bombay Stock Exchange of India"], ["PSI", "Population Stability Index"],
    ["Q&A", "The unscripted question-and-answer part of an earnings call"], ["SWN", "SentiWordNet"],
    ["TF-IDF", "Term Frequency – Inverse Document Frequency"], ["VADER", "Valence Aware Dictionary and sEntiment Reasoner"],
  ], [1.3, 4]),
];

// ------------------------------------------------------------------ chapters
const body = [];
const add = (...xs) => xs.flat().forEach((x) => body.push(x));

// 1 ---------------------------------------------------------------
add(newChapter("Introduction"));
add(H2("1.1  Background and motivation"));
add(P("Listed companies publish a steady stream of text: quarterly earnings-call transcripts, annual and quarterly reports (10-K and 10-Q in the United States, results and investor presentations filed with NSE and BSE in India), and a larger volume of news. Much of what moves a company's prospects is expressed in this text before it shows up in the numbers — a guidance range narrowed toward its low end, a CFO who becomes evasive about margins in the Q&A, a new lawsuit described in a risk-factor footnote."));
add(P("Institutional investors pay analysts and data vendors to monitor this. A retail investor following fifteen to twenty stocks usually cannot: a single earnings call runs to ten thousand words or more, and each company produces several documents per quarter. General-purpose sentiment tools do not close the gap, because they score a whole document as positive or negative and because their vocabularies were built for reviews and social media, where \"liability\", \"decrease\" or \"cost\" carry the opposite implications to the ones they carry in finance."));
add(H2("1.2  Problem statement"));
add(P("Build a daily intelligence service that watches a user's watchlist, extracts sentiment about specific financial aspects rather than whole documents, tracks how that sentiment moves quarter over quarter, and produces a grounded, human-readable brief in which every claim can be traced back to the exact sentence that generated it — while being honest, by measurement, about where the approach works and where it does not."));
add(H2("1.3  Objectives"));
add(table("Project goals (from the project specification)", ["#", "Goal", "Where it is addressed"], [
  ["G1", "Aspect-level (not document-level) sentiment extraction from unstructured financial text", "Chapter 4.3–4.5"],
  ["G2", "Show empirically where general-purpose lexicons fail on financial language", "Chapter 6.3"],
  ["G3", "Multi-agent reasoning (bull / bear / skeptic / judge) that is grounded — no hallucinated claims", "Chapters 4.7, 6.4"],
  ["G4", "A real deployed service: scheduled ingestion, persistent storage, drift monitoring, a UI", "Chapters 4, 5, 10"],
  ["G5", "An honest evaluation, including where the signal does not predict anything", "Chapters 6, 11"],
], [0.5, 4.2, 1.6], { firstColBold: true }));
add(H2("1.4  Scope"));
add(P("**In scope:** US and NSE/BSE-listed companies with public transcripts and filings; the six aspects guidance, margins, demand, litigation, management tone and liquidity; a daily batch pipeline; a web dashboard and an e-mail/Slack digest."));
add(P("**Out of scope:** real-time or intraday sentiment, trade execution or portfolio management, and any guarantee that a signal predicts returns. Sentari is a research and decision-support tool; every screen, API response and digest carries a not-investment-advice notice."));
add(H2("1.5  Contributions"));
add(bullets([
  "An end-to-end, tested pipeline from raw disclosures to a cited brief, runnable fully offline on a bundled synthetic corpus and configurable for live sources.",
  "A ten-model sentiment ladder scored on one held-out, aspect-labelled gold set, with per-class precision, recall and F1, latency, and MLflow tracking.",
  "A lexicon failure analysis built around *trap* sentences, quantifying how general-purpose lexicons invert financial meaning.",
  "A grounding gate (the Skeptic agent) and an adversarial audit that measures what it catches, showing both its strengths and a specific weakness (polarity flips) and how an NLI model removes it.",
  "A prepared-remarks-versus-Q&A sentiment delta as a per-call signal, and a statistical harness to test whether it predicts post-earnings drift.",
]));
add(H2("1.6  Organisation of this report"));
add(P("Chapter 2 reviews the relevant methods. Chapter 3 presents the system design and Chapter 4 its implementation. Chapter 5 walks through the user interface with screenshots. Chapter 6 reports the evaluation and Chapter 7 the testing. Chapter 8 maps the work to the course syllabus, Chapter 9 covers ethics, Chapter 10 compares progress with the project plan, Chapter 11 discusses limitations and future work, and Chapter 12 concludes. Appendices give run instructions, configuration, the API reference and the repository layout."));

// 2 ---------------------------------------------------------------
add(newChapter("Background and Related Work"));
add(H2("2.1  Levels of sentiment analysis"));
add(P("Sentiment can be analysed at document, sentence or aspect level [10]. Document-level scores are too coarse for earnings calls, where a company commonly reports strong demand, weaker margins and a cautious outlook in the same call. Aspect-based sentiment analysis (ABSA) identifies the targets being evaluated (aspects) and the polarity expressed toward each; it was formalised by the SemEval-2014 shared task [9]. Sentari uses a fixed, domain-defined aspect set and treats aspect detection and polarity scoring as separate stages."));
add(H2("2.2  Lexicon- and knowledge-based methods"));
add(P("**VADER** [2] is a rule-based lexicon tuned for social media, with heuristics for negation, intensifiers and punctuation. **SentiWordNet 3.0** [3] assigns positive and negative scores to WordNet synsets. Both are general-purpose. Loughran and McDonald [1] showed that almost three-quarters of the words that general dictionaries mark as negative are not negative in 10-K filings (for example *tax*, *cost*, *liability*), and built finance-specific word lists — negative, positive, uncertainty and litigious — now standard in financial text analysis. A known limitation of all word-list methods is directionality: in finance the polarity of *decreased* depends on its subject (falling costs are good, falling margins are bad)."));
add(H2("2.3  Machine-learning and deep-learning methods"));
add(P("Supervised classifiers over bag-of-words or TF-IDF features — Naive Bayes and decision trees among them — are strong, cheap baselines [15]. Convolutional networks over word embeddings [5] and recurrent networks such as LSTMs [6] learn local n-gram patterns and longer dependencies respectively, and can capture negation and word order that bag-of-words features miss."));
add(H2("2.4  Transformers and FinBERT"));
add(P("BERT [7] pre-trains a Transformer encoder on large corpora and is fine-tuned for downstream tasks. FinBERT [4] further adapts BERT to financial text and was fine-tuned for sentiment on the Financial PhraseBank [11]. For ABSA, Sun et al. [8] showed that feeding the aspect as an auxiliary second sentence lets one encoder handle all aspects; Sentari's transformer rung uses this sentence-pair formulation."));
add(H2("2.5  LLM agents, hallucination and grounding"));
add(P("Large language models can write fluent summaries but are prone to *hallucination* — statements not supported by their inputs [13]. Common mitigations are retrieval (giving the model the evidence), requiring citations, and verifying claims after generation, for instance with natural language inference (NLI) models that classify whether a premise entails, contradicts or is neutral to a hypothesis. Sentari combines all three: agents argue only from retrieved, scored evidence; each claim must cite chunk IDs; and a separate Skeptic stage verifies claims before they can reach the brief."));
add(H2("2.6  Monitoring deployed models"));
add(P("Deployed NLP models degrade when their input distribution shifts. The Population Stability Index (PSI) [14], widely used in credit scoring, measures the shift between two categorical distributions; Cohen's *d* [17] measures a standardised shift in a mean. Sentari applies PSI to the mix of aspects mentioned and *d* to model confidence, per ticker and week."));

// 3 ---------------------------------------------------------------
add(newChapter("System Design"));
add(H2("3.1  Architecture overview"));
add(P("Sentari is organised as a pipeline of services around a single relational store (Figure 3.1). A scheduler triggers the daily run; the ingestion service fetches, deduplicates and chunks documents; the ABSA service tags aspects and scores them with whichever model the registry marks as serving; the agent layer turns scored evidence into a brief; and the delivery layer exposes everything through an API, a dashboard, a digest and a drift monitor."));
add(fig("fig_architecture.png", "System architecture. Dark arrows follow the processing order; grey arrows are reads and writes to the database; the dashed arrow is the registry selecting the serving model."));
add(H2("3.2  End-to-end data flow"));
add(numbered([
  "**Trigger.** Cloud Scheduler (or cron) calls `POST /run/daily`, optionally authenticated with a shared token.",
  "**Ingest.** Each configured scraper returns raw documents; text is normalised and hashed; documents already seen are skipped, so re-runs never duplicate data.",
  "**Chunk.** Transcripts are split by speaker and section (prepared remarks or Q&A) and then into sentences; filings and news are split into sentences.",
  "**Score.** Every new chunk is embedded for retrieval, its aspect mentions are extracted, and each mention is scored by the serving model. Operator lines and analysts' questions are not scored, because they are not company statements.",
  "**Brief.** For each ticker whose inputs changed, the agent graph runs and writes the brief and a full audit trail. Unchanged inputs reuse the cached brief.",
  "**Monitor and deliver.** Drift reports are computed and the digest of the day's largest aspect moves is rendered and, if configured, sent.",
]));
add(H2("3.3  Database design"));
add(P("All state lives in one SQLAlchemy schema that runs on SQLite for development and tests and on PostgreSQL in production (Figure 3.2, Table 3.1). Aspect scores are denormalised with ticker, date and section so trajectory queries need no joins. Embeddings are stored as JSON arrays so no vector extension is required; the Postgres migration enables pgvector for later ANN search."));
add(fig("fig_schema.png", "Database schema. Solid edges are foreign keys; dashed edges are logical references stored as values."));
add(table("Database tables", ["Table", "Purpose", "Key constraints"], [
  ["documents", "One row per ingested document (transcript, 10-K, 10-Q, news, NSE filing)", "`content_hash` unique — makes ingestion idempotent"],
  ["chunks", "Sentences with section (prepared / qa / mdna / body), speaker and embedding", "(`document_id`, `idx`) unique"],
  ["aspect_scores", "Polarity, signed score and confidence per chunk × aspect × model", "(`chunk_id`, `aspect`, `model_name`) unique"],
  ["briefs", "Final brief as structured JSON, confidence, token counts, latency", "`input_fingerprint` indexed — brief cache"],
  ["agent_traces", "Every agent step of every brief, with cited chunk IDs", "ordered by `step`"],
  ["model_runs", "Every trained/evaluated model version, metrics, MLflow run ID", "`serving` flag selects the live model"],
  ["drift_reports", "Weekly PSI and confidence shift per ticker, with alert flag", "one row per (ticker, window)"],
], [1.2, 3.3, 2.3], { firstColBold: true }));
add(H2("3.4  Agent orchestration"));
add(P("The agent layer is a LangGraph state graph (Figure 3.3). The Bull and Bear agents run in parallel after the Extractor; the Skeptic waits for both; the Judge sees only what the Skeptic lets through. Agent state carries an append-only trace, so every intermediate result is persisted in `agent_traces`."));
add(fig("fig_agents.png", "Agent graph. Rejected claims never reach the Judge but remain in the audit trail."));
add(H2("3.5  Technology stack"));
add(table("Technology stack (planned in the specification vs. used)", ["Layer", "Planned", "Used in this build"], [
  ["Languages", "Python, TypeScript", "Python 3.13 (services), TypeScript (dashboard)"],
  ["NLP", "spaCy, NLTK/VADER, SentiWordNet", "spaCy `en_core_web_sm`, vaderSentiment, NLTK SentiWordNet"],
  ["ML / DL", "scikit-learn, PyTorch", "scikit-learn 1.8, PyTorch 2.13 (CPU), Hugging Face Transformers"],
  ["Agents", "LangGraph, LangChain", "LangGraph; Anthropic SDK (optional LLM backend); LangChain not needed"],
  ["API", "FastAPI", "FastAPI + Uvicorn"],
  ["Tracking / versioning", "MLflow, DVC", "MLflow (file store or server); `dvc.yaml` pipeline written"],
  ["Database / vectors", "PostgreSQL, pgvector or Qdrant", "SQLite (dev/tests), PostgreSQL (Compose); JSON embeddings"],
  ["Scheduling", "Cloud Scheduler / Airflow", "Cloud Scheduler design + `/run/daily` endpoint; Airflow not used"],
  ["Containers / deploy", "Docker, Compose, Cloud Run", "Dockerfiles, Compose and Cloud Run guide written (not yet built or deployed)"],
  ["Frontend", "Next.js", "Next.js 16, React 19, dependency-free SVG charts"],
  ["Notifications", "SMTP / Slack API", "SMTP and Slack incoming webhook"],
], [1.3, 2.1, 3.4], { firstColBold: true }));

// 4 ---------------------------------------------------------------
add(newChapter("Implementation"));
add(P("The implementation is about 4,000 lines of Python across seven packages and 600 lines of TypeScript, with 55 automated tests (Table 4.1). This chapter describes each component in pipeline order."));
add(table("Code base by package (lines including comments and blank lines)", ["Package", "Lines", "Responsibility"], [
  ["ingestion/", "499", "scrapers, normalisation, transcript parsing, idempotent pipeline"],
  ["absa_service/", "2,029", "preprocessing, aspect extraction, ten models, training, scoring, signals, registry, API, CLI"],
  ["agents/", "661", "extractor, bull/bear, skeptic, judge, LangGraph graph, LLM backends"],
  ["storage/", "180", "SQLAlchemy schema, engine/session helpers, migration"],
  ["monitoring/, delivery/", "165", "drift monitor; digest rendering, SMTP and Slack delivery"],
  ["evaluation/", "546", "metrics, lexicon failure, grounding audit, signal validity, latency/cost, report"],
  ["tests/", "551", "55 tests (unit, integration, API)"],
  ["dashboard/", "626", "Next.js pages, chart and drawer components, API client"],
], [1.6, 0.8, 4.4], { firstColBold: true }));

add(H2("4.1  Ingestion service"));
add(P("Each source implements a `Scraper.fetch(ticker, since)` interface and returns raw documents tagged with ticker, document type and date (Table 4.2). Network scrapers share a client that caches every raw response on disk *before* parsing — so a parsing bug never forces a re-download — and retries with exponential back-off on rate limits."));
add(table("Data sources", ["Scraper", "Source", "Status"], [
  ["`sample`", "Bundled synthetic transcripts and a 10-Q for two fictional companies (ACMX, NVLT)", "Used for all tests and the demonstration"],
  ["`sec_edgar`", "SEC EDGAR submissions API; extracts the MD&A section of 10-K/10-Q filings [16]", "Implemented; not yet run against live EDGAR (needs a contact User-Agent)"],
  ["`news_rss`", "Public news RSS search by company name", "Implemented; not verified live"],
  ["`nse`", "NSE corporate announcements; returns nothing rather than circumvent access controls", "Implemented; not verified live"],
], [1.1, 3.6, 2.1], { firstColBold: true }));
add(P("**Normalisation and deduplication.** Text is Unicode-normalised, quotes and dashes unified, and stage directions such as *[Operator Instructions]* removed. A SHA-256 hash of ticker, document type and whitespace-normalised text is the document's identity; a unique constraint makes re-ingestion a no-op."));
add(P("**Transcript parsing.** Lines beginning with a speaker tag (\"Maria Chen -- CEO:\") switch the current speaker; phrases such as \"question-and-answer session\" or the operator opening the line switch the section from prepared remarks to Q&A. Sentences are then split with a regular expression that respects financial abbreviations (*Inc.*, *Q3.*, *U.S.*). Table 4.3 shows the result on the start of a sample call."));
add(table("Transcript parsing output (first sentences of the ACMX Q1 2025 sample call)", ["#", "Section", "Speaker", "Sentence"], [
  ["2", "prepared", "Maria Chen (CEO)", "We delivered a strong first quarter."],
  ["5", "prepared", "Maria Chen (CEO)", "We are raising our full-year guidance and now expect revenue growth of 10% to 12%."],
  ["7", "prepared", "David Osei (CFO)", "Gross margin expanded 180 basis points to 34.2% on favorable mix and productivity gains."],
  ["12", "qa", "Operator", "We will now begin the question-and-answer session."],
  ["17", "qa", "Maria Chen (CEO)", "Well, we believe demand should remain healthy, although visibility beyond the third quarter is limited."],
  ["23", "qa", "David Osei (CFO)", "We cannot comment on the details, but we could face a material charge if the outcome is unfavorable."],
], [0.35, 0.8, 1.5, 4.5]));

add(H2("4.2  Preprocessing"));
add(bullets([
  "**Negation scope.** A negation cue (*not, no, without, cannot, unable, …n't*) marks the following tokens as negated until a clause boundary or four tokens. Negated tokens are prefixed `NEG_` for the learned models and flip polarity for the lexicons.",
  "**Hedging.** Modal and epistemic words (*may, could, believe, expect, visibility, uncertain*) give each clause a hedge score in [0, 1], used by the management-tone aspect.",
  "**Clause splitting.** Sentences are split at contrast conjunctions and semicolons, so \"Demand held up, **but** aerospace orders declined\" yields two separately scored clauses.",
]));
add(H2("4.3  Aspect extraction"));
add(P("Aspect detection combines a trigger lexicon with dependency parsing. Each aspect has a list of trigger terms (for margins: *gross margin, operating margin, input costs, pricing, tariffs, …*). In each clause the earliest matching trigger per aspect is taken. spaCy then parses the clause and, starting from the trigger's syntactic head, collects the *opinion words* that govern it — adjectival modifiers, the head verb, complements and negations — walking up to four ancestors to find negation attached to a governing verb (as in *\"we do **not** expect any material impact from ongoing litigation\"*). Without spaCy the extractor falls back to a six-token window; a test checks that both paths detect the same aspects."));
add(shot("16_terminal_analyze.png", "Command-line analysis of a five-sentence passage (rule-based model): each sentence yields one score per detected aspect, with the matched trigger in brackets.", { width: 6.3 }));
add(P("Figure 4.1 shows the behaviour on a mixed passage. The second sentence contains one positive and one negative demand clause; the two scores are averaged to neutral, which is a deliberate simplification discussed in Chapter 11. The last sentence is tagged both litigation and management tone, because *unable to* is a tone trigger."));

add(H2("4.4  The model ladder"));
add(P("All ten models implement one interface, `predict(items) → predictions`, where an item is an aspect clause plus its aspect and a prediction is a label (negative/neutral/positive), a signed score in [−1, 1] and a confidence. This makes every rung interchangeable in the scoring pipeline and directly comparable in evaluation (Table 4.4)."));
add(table("Models on the ladder", ["Rung", "Model", "How it scores a clause"], [
  ["Lexicon", "VADER", "Compound score of the clause; ±0.05 thresholds"],
  ["Lexicon", "SentiWordNet", "Weighted positive−negative score of the first three synsets per word, sign-flipped under negation"],
  ["Lexicon", "Loughran-McDonald", "Positive minus negative word counts with negation flips (curated seed subset of the LM categories; the official dictionary can be dropped in)"],
  ["Lexicon + rules", "LM + directional", "LM lists plus directionality: *up/down* verbs flip sign for metrics where higher is worse (costs, debt, churn, litigation expense); event phrases (*named as a defendant*, *undrawn*); uncertainty words for tone"],
  ["Classical ML", "Naive Bayes, Decision Tree", "TF-IDF over word 1–2-grams of negation-marked tokens with an aspect token prepended"],
  ["Deep learning", "CNN", "Kim-style CNN [5]: 100-d embeddings, filter widths 2/3/4 × 64, max-pool, dropout 0.4"],
  ["Deep learning", "BiLSTM", "Bidirectional LSTM (96 units per direction) with masked mean pooling; optional GloVe initialisation"],
  ["Transformer", "FinBERT zero-shot", "ProsusAI/finbert applied as-is to the (clause, \"aspect: …\") sentence pair"],
  ["Transformer", "FinBERT fine-tuned", "FinBERT fine-tuned on the sentence pair (2 epochs, AdamW, lr 3e-5, 1,500 examples, CPU)"],
], [1.1, 1.5, 4.2]));
add(P("**Training data.** Hand-labelling at scale was out of reach, so, as the project plan anticipated, the trainable models learn from *weak labels*: 4,000 template-generated sentences whose labels follow from financial directionality (for example \"input costs fell\" → positive, \"gross margin fell\" → negative), negation, valence words and event phrases, balanced across the six aspects. Any template sentence that coincides with a gold sentence is removed, and 15% is held out for validation. The consequences of this choice for the evaluation are discussed in Section 6.2."));
add(H2("4.5  Scoring and the prepared-versus-Q&A signal"));
add(P("For each new chunk the scorer extracts aspect mentions, scores each clause with the serving model, averages clauses of the same aspect, and writes one `aspect_scores` row per aspect with ticker, date and section. It also stores an embedding of the chunk for retrieval (a deterministic 384-dimensional feature-hashing embedder by default; Sentence-Transformers optionally)."));
add(P("The platform's signature signal compares what management says in the scripted part of a call with what it says unscripted. For a transcript and aspect *a*:"));
add(formula("Δ(a) = mean score of a in Q&A − mean score of a in prepared remarks"));
add(P("and the per-call delta is the mean of Δ(a) over aspects present in both sections. A strongly negative delta means management sounded markedly weaker when answering analysts than when reading its script. The naive comparator used in the signal-validity study is the plain document-level mean."));
add(H2("4.6  Model registry and serving"));
add(P("Training (`python -m absa_service.train`) fits every trainable model, evaluates every model on the gold set, logs parameters and metrics to MLflow, records a `model_runs` row, and marks the best model by gold macro-F1 as *serving*. The API resolves which model to use in the order: explicit request → `SENTARI_MODEL` → registry serving flag → the rule-based model. If trained weights are missing the service falls back to the rule-based model rather than failing."));

add(H2("4.7  Agent layer"));
add(H3("Extractor"));
add(P("For a ticker and date range the Extractor loads all aspect scores and ranks each aspect's chunks by:"));
add(formula("rank = |score| × (0.5 + confidence) + 0.3 × cosine(chunk, aspect query)"));
add(P("It keeps the top *k* = 4 positive and top 4 negative chunks per aspect, so both sides of the debate get material, and computes an aspect summary and the per-call Q&A deltas."));
add(H3("Bull and Bear"));
add(P("Each side builds the strongest case from evidence of its polarity and must cite chunk IDs for every claim. With an Anthropic API key the claims are written by Claude, prompted to use only the numbered evidence; without one, a deterministic backend composes claims directly from the strongest chunks. Claim IDs are prefixed `bl` and `br` so the two sides can never collide in the brief or the trace — a bug that the tests caught during development (Section 7.3)."));
add(H3("Skeptic — the grounding gate"));
add(table("Skeptic checks, applied to every claim in order", ["Check", "Test", "On failure"], [
  ["1  Citation", "Every cited ID exists in the retrieved evidence", "rejected"],
  ["2  Numbers", "Every number in the claim appears in the cited text", "rejected"],
  ["3  Similarity", "Embedding cosine ≥ 0.12 and content-word overlap ≥ 45% with the cited text", "unverified"],
  ["4  Entailment", "Heuristic: claim polarity cues must not contradict the chunk's scored polarity. NLI mode: cross-encoder entailment ≥ 0.5; contradiction ≥ 0.6 rejects", "rejected (contradiction) / unverified"],
], [1.2, 4.2, 1.4], { firstColBold: true }));
add(P("Only `supported` claims enter the brief body. `Unverified` claims are shown separately and flagged; `rejected` claims are dropped but kept in the audit trail. Near-verbatim quotes are exempt from the heuristic polarity check, because the cue lists cannot see negation (a faithful quote of *\"we do not expect any material impact from litigation\"* was otherwise rejected — found during development)."));
add(H3("Judge"));
add(P("The Judge assembles the brief from surviving claims: a stance from the net aspect sentiment, bull and bear claims grouped by aspect, the largest negative Q&A delta if below −0.3, and a confidence score. With an LLM the summary is rewritten in prose, and is discarded in favour of the template if it cites any claim that did not survive. Confidence is a transparent heuristic, not a calibrated probability:"));
add(formula("confidence = 0.5 × survival + 0.3 × mean evidence confidence + 0.2 × aspect coverage"));
add(P("where survival = (supported + 0.4 × unverified) / all claims."));
add(H3("Cost control"));
add(P("Each brief is fingerprinted by a hash of its exact inputs (ticker, window, every chunk ID and rounded score, and the LLM name). If a brief with the same fingerprint exists it is returned without running the agents, so the LLM is invoked only when new documents actually arrive for a ticker."));

add(H2("4.8  Drift monitoring"));
add(P("For each ticker and for the watchlist as a whole, the monitor compares the last seven days with the preceding 28:"));
add(formula("PSI = Σₐ (pₐ − qₐ) · ln(pₐ / qₐ)        d = (μ_current − μ_baseline) / σ_pooled"));
add(P("where p and q are the current and baseline aspect-mention shares and d is Cohen's d on model confidence. An alert fires when PSI > 0.25 or |d| > 0.8; windows with fewer than five scores report *insufficient data*. Reports are keyed by (ticker, window) so re-running the daily job replaces rather than duplicates them."));
add(H2("4.9  API and delivery"));
add(P("The FastAPI service exposes analysis endpoints, the dashboard's read API and the daily-run trigger (Figure 4.2; full list in Appendix C). The digest ranks, across the watchlist, the largest changes in a ticker's per-document aspect mean between its two most recent documents, appends drift alerts and the disclaimer, and sends to Slack and/or e-mail when configured."));
add(shot("13_api_swagger.png", "Interactive API documentation generated by FastAPI (`/docs`)."));
add(H2("4.10  Dashboard"));
add(P("The Next.js dashboard has five views — watchlist, ticker, brief, drift monitor and model registry — described with screenshots in Chapter 5. Charts are hand-written SVG with no charting dependency; colour tokens adapt to light and dark mode; and every page repeats the research-use disclaimer."));
add(H2("4.11  Configuration and deployment"));
add(bullets([
  "**Configuration.** A `.env` file (template: `.env.example`) is loaded before any module reads its settings; real environment variables always win and empty values are ignored. A test fails if the code reads a variable that the template does not document.",
  "**Containers.** A CPU-only backend image, a standalone Next.js image, and a Compose file adding PostgreSQL (pgvector) and an MLflow server.",
  "**Cloud.** A Cloud Run guide covers Cloud SQL, both services and a Cloud Scheduler job that calls `/run/daily` with a token; the endpoint is idempotent, so scheduler retries are safe.",
  "**Reproducibility.** `dvc.yaml` defines the train → lexicon-failure → grounding stages; CI runs the Python tests and the dashboard type-check and build on every push.",
]));
add(note("**Status:** the container images have not been built and nothing has been deployed yet (Docker Desktop was not running during development and no cloud project was available). These files are written and reviewed but unverified."));

// 5 ---------------------------------------------------------------
add(newChapter("User Interface Walkthrough"));
add(P("All screenshots in this chapter were captured from the running system using the bundled synthetic corpus — two fictional companies, Acme Industrial (ACMX) and Novalite Software (NVLT), with two earnings calls each and one 10-Q — after one daily run. The serving model was fine-tuned FinBERT (selected by the registry) and the Skeptic used the NLI backend. Company names, people and figures in these screens are invented."));
add(H2("5.1  Watchlist"));
add(P("The landing page shows the day's largest aspect moves and one card per ticker with the latest call's six aspect scores. A ⚠ marks aspects where the Q&A was more than 0.5 below the prepared remarks. The badge shows the latest brief's stance and confidence."));
add(shot("01_watchlist.png", "Watchlist: top aspect moves and per-ticker aspect scores from the latest call."));
add(H2("5.2  Aspect trajectories and drill-down"));
add(P("The ticker page plots each aspect over time: the solid line is the document mean, the green and red dashed lines the prepared-remarks and Q&A means. For ACMX the Q&A line sits below the prepared line for most aspects — the pattern the prepared-versus-Q&A signal is designed to surface."));
add(shot("02_ticker_trajectories.png", "Ticker view for ACMX: six aspect trajectories with prepared-remarks and Q&A lines."));
add(P("Clicking any point lists the scored sentences behind it (Figure 5.3); clicking a sentence opens the source drawer (Figure 5.4), which shows the sentence in context with speakers, the document it came from, and every model verdict stored for it."));
add(shot("03_drilldown_sentences.png", "Drill-down: the management-tone point for the Q2 call opens the sentences, sections, scores and model behind it."));
add(shot("04_source_drawer.png", "Source drawer: the selected sentence highlighted in its surrounding transcript, with the model's verdict."));
add(H2("5.3  Grounded brief"));
add(P("The brief page shows the stance, the confidence with its components, the summary, and the verified bull and bear claims by aspect. Every claim carries *src* chips; each opens the cited source sentence. Unverified claims, if any, are listed separately, and the number of rejected claims is stated."));
add(shot("05_brief_top.png", "Brief for ACMX: stance, confidence breakdown and a summary in which every claim is cited."));
add(shot("06_brief_bull_bear.png", "Verified bull and bear claims grouped by aspect."));
add(note("**Observed weakness (Figure 5.5).** The same sentence is cited under several aspects — \"Demand conditions are uncertain …\" appears as the bear claim for guidance, demand *and* management tone, and \"Our management team is confident in the outlook\" as a guidance claim. The cause is that one sentence can trigger several aspects (*outlook* is a guidance trigger; *uncertain* a tone trigger) and each side picks the strongest sentence per aspect independently. The claims are correctly grounded, but the brief is repetitive and over-counts one sentence. Deduplicating claims by cited chunk is listed as future work."));
add(shot("07_brief_citation_drawer.png", "Following a citation from the brief to its source sentence."));
add(P("The audit trail (Figure 5.8) exposes the output of every agent. For the Skeptic it records, per claim, each check's result, the similarity and overlap values and the NLI probabilities — here 0.976 entailment for a quoted claim."));
add(shot("08_brief_audit_trail.png", "Agent audit trail: the Skeptic's per-claim checks and NLI probabilities."));
add(H2("5.4  Drift monitor and model registry"));
add(shot("09_drift_monitor.png", "Drift monitor: PSI and confidence shift per ticker and for the whole watchlist, with baseline versus current aspect mix."));
add(P("The ACMX alert (PSI 2.33) illustrates a limitation rather than real drift: the current window contains only five scores, all from one 10-Q, whose aspect mix naturally differs from calls. The five-score minimum is too low for a watchlist this small; Chapter 11 discusses it."));
add(shot("10_model_registry.png", "Model registry: every rung with gold-set metrics and the serving flag."));
add(shot("14_mlflow_runs.png", "MLflow experiment `sentari-absa-ladder` with one run per model. (Durations are logging times; training times are in Section 6.2.)"));
add(H2("5.5  Dark mode and small screens"));
add(shot("11_dark_mode_ticker.png", "Ticker view in dark mode (NVLT)."));
add(shot("12_mobile_watchlist.png", "Watchlist at phone width (390 px).", { width: 2.6 }));
add(P("At 390 px the cards reflow correctly, but the navigation bar does not: the disclaimer text wraps into four lines and overflows the right edge (Figure 5.12). This is a known layout defect to fix."));

// 6 ---------------------------------------------------------------
add(newChapter("Evaluation"));
add(P("The project plan asks for five evaluations. Table 6.1 summarises their status; the rest of the chapter reports each one."));
add(table("Evaluation plan status", ["#", "Evaluation", "Status"], [
  ["1", "Model ladder comparison on one held-out set", "Done (Section 6.2)"],
  ["2", "Lexicon failure analysis", "Done (Section 6.3)"],
  ["3", "Grounding audit", "Adversarial audit done; human-annotated audit tooling built, not yet run (Section 6.4)"],
  ["4", "Signal validity (Q&A delta vs. post-earnings drift)", "Harness built and tested; not run — needs real transcripts and prices (Section 6.5)"],
  ["5", "Latency and cost per brief", "Latency measured; LLM cost not measured — no API key used (Section 6.6)"],
], [0.4, 3.4, 3.0]));
add(H2("6.1  Data and protocol"));
add(bullets([
  "**Gold (test) set:** 94 hand-written sentences, each labelled with one aspect and a polarity: every aspect has 5–6 positive, 6 negative and 4 neutral examples. 26 are flagged as *traps* — sentences where financial meaning inverts everyday polarity. The gold set is used only for evaluation.",
  "**Training set:** 3,400 weak-labelled template sentences, with 600 more held out for validation (Section 4.4). FinBERT was fine-tuned on the first 1,500 for CPU time.",
  "**Metrics:** accuracy, macro-F1, per-class precision/recall/F1, accuracy on the trap subset, and inference time per sentence on CPU. One training seed.",
]));
add(H2("6.2  Model ladder"));
add(table("Model ladder on the 94-sentence gold set (P / R / F1 per class)", ["Model", "Acc.", "Macro-F1", "Negative", "Neutral", "Positive", "Trap acc.", "ms/item"],
  ORDER.map((n) => { const g = ladder[n].gold; return [PRETTY[n], f3(g.accuracy), `**${f3(g.macro_f1)}**`, prf(g, "negative"), prf(g, "neutral"), prf(g, "positive"), g.trap_accuracy.toFixed(2), g.latency_ms_per_item.toFixed(2)]; }),
  [2.0, 0.6, 0.8, 1.35, 1.35, 1.35, 0.7, 0.7], { fontSize: 16 }));
add(fig("fig_ladder_f1.png", "Macro-F1 by model, coloured by rung."));
add(P(`Fine-tuned FinBERT is the strongest model (macro-F1 ${f3(ladder.finbert_ft.gold.macro_f1)}), followed by the LM + directional rule model (${f3(ladder.lm_directional.gold.macro_f1)}). Adding finance-specific vocabulary alone moves the lexicon rung from ${f3(ladder.vader.gold.macro_f1)} (VADER) to ${f3(ladder.lm_lexicon.gold.macro_f1)} (Loughran-McDonald); adding directionality moves it to ${f3(ladder.lm_directional.gold.macro_f1)}. Zero-shot FinBERT (${f3(ladder.finbert_zeroshot.gold.macro_f1)}) does worse than plain Loughran-McDonald: it was trained for sentence-level sentiment and does not know which aspect it is being asked about, so fine-tuning on the aspect pair is what makes it useful here.`));
add(fig("fig_confusion.png", "Confusion matrices for the general-purpose lexicon, the best rule model and the best learned model."));
add(P("VADER's errors are spread across all cells, including 14 negative/positive swaps — the direction errors that matter most for an investor. FinBERT's six errors are mostly positive/negative confusions on trap sentences about costs and cash (Section 6.3); the rule model's errors are mostly confusions with neutral."));
add(fig("fig_latency.png", "Accuracy against inference cost per sentence on CPU (log scale)."));
add(P("The rule model scores a sentence in about 0.03 ms; FinBERT takes about 10 ms, three hundred times longer. At watchlist scale both are affordable, which is why the registry serves FinBERT, but the rule model is a strong fallback and remains the default when no trained weights are present."));
add(H3("Why these numbers are optimistic"));
add(bullets([
  `**Weak labels are too easy.** CNN, BiLSTM and FinBERT all reached 100% accuracy on the weak-label validation split within a few epochs, yet ${pct(ladder.cnn.gold.accuracy, 0)}–${pct(ladder.finbert_ft.gold.accuracy, 0)} on gold. The templates are far more regular than real language; validation accuracy on them says nothing about real performance.`,
  "**The gold set is small.** One sentence is about 1.1 accuracy points; differences of a few points between models are within noise, and only one seed was run.",
  "**Gold and templates share phrasing.** Both were written by the same author about the same six aspects, so the trained models' gold scores will overstate performance on real transcripts.",
  "**The rule model was written with sight of the gold set.** Its directional rules reflect patterns the author had read; its score is an optimistic upper bound. (Gold-derived words were removed from the plain LM seed list to keep that baseline fair.)",
  "**The LM lexicon is a curated subset,** not the official ~86,000-word dictionary.",
]));

add(H2("6.3  Lexicon failure analysis"));
add(P("Table 6.3 and Figure 6.4 split each model's error rate between the 26 trap sentences and the other 68."));
add(table("Error rate on trap and non-trap sentences", ["Model", "All (n=94)", "Trap (n=26)", "Non-trap (n=68)"],
  Object.entries(lexfail.models).map(([n, m]) => [PRETTY[n] || n, pct(m.error_rate), `**${pct(m.error_rate_trap)}**`, pct(m.error_rate_nontrap)]),
  [2.6, 1.3, 1.3, 1.5]));
add(fig("fig_lexicon_traps.png", "Error rate on finance-inverted (trap) sentences versus the rest."));
add(P("General-purpose lexicons are wrong on most trap sentences: 61.5% for VADER and 73.1% for SentiWordNet. Plain Loughran-McDonald counting fixes much of the vocabulary problem on ordinary sentences (11.8% error) but not the trap problem (57.7%), because a word list cannot tell whether *decreased* is good or bad without knowing what decreased. Directional rules (15.4%) and the learned models close most of the gap. Table 6.4 lists representative failures."));
add(table("Representative trap sentences mis-scored by VADER", ["Aspect", "Sentence", "Gold", "VADER", "LM+dir.", "FinBERT"], [
  ["demand", "Customer churn decreased to its lowest level in three years.", "pos", "neg", "✓", "✓"],
  ["liquidity", "Total liabilities decreased and our net debt fell to its lowest level in a decade.", "pos", "neg", "✓", "✓"],
  ["litigation", "Legal expenses decreased as the dispute was resolved earlier than planned.", "pos", "neg", "✓", "✓"],
  ["litigation", "Litigation expenses increased this quarter as the patent case moved toward trial.", "neg", "pos", "✓", "✓"],
  ["litigation", "The jury verdict went against us and we recorded a 90 million dollar provision.", "neg", "pos", "✓", "✓"],
  ["demand", "Churn increased in the mid-market as customers consolidated vendors.", "neg", "pos", "✓", "✓"],
  ["margins", "Cost of revenue increased 14% year over year, outpacing sales growth.", "neg", "pos", "✓", "✗ pos"],
  ["liquidity", "Cash declined by 400 million dollars and we fully drew our credit facility.", "neg", "pos", "✓", "✗ pos"],
  ["guidance", "We now expect operating expenses to come in below the low end of our prior guidance.", "pos", "neg", "✓", "✗ neg"],
  ["guidance", "We do not expect to meet our prior guidance for free cash flow this year.", "neg", "pos", "✗", "✓"],
], [0.9, 3.9, 0.55, 0.6, 0.65, 0.75], { fontSize: 17 }));
add(P("The residual FinBERT errors are the same phenomenon in a subtler form: *increased* next to a cost, or *declined* next to cash, pulls the model toward the polarity of the verb rather than the implication for the company. This supports the project's premise that financial directionality must be modelled explicitly or learned from data that contains it."));
add(shot("17_terminal_lexicon_failure.png", "Output of `python -m evaluation.lexicon_failure`.", { width: 5.4 }));

add(H2("6.4  Grounding audit"));
add(P("**Adversarial audit.** Starting from 43 faithful claims (verbatim scored sentences), the audit creates five kinds of corrupted claims that imitate how a generator fails, passes all of them through the Skeptic, and counts a corrupted claim as *caught* if it is rejected or flagged unverified — both keep it out of the brief body."));
const gRow = (k, label) => [label, String(gH[k].n), pct(gH[k].catch_rate, 1), pct(gH[k].hard_reject_rate, 1), pct(gN[k].catch_rate, 1), pct(gN[k].hard_reject_rate, 1)];
add(table("Adversarial grounding audit (caught = rejected or flagged; hard reject = rejected)", ["Corruption", "n", "Heuristic caught", "Heuristic rejected", "NLI caught", "NLI rejected"], [
  gRow("number_swap", "Number changed"), gRow("no_citation", "Citation removed"), gRow("wrong_citation", "Wrong chunk cited"),
  gRow("fabrication", "Fabricated claim"), gRow("polarity_flip", "**Polarity flipped**"),
  ["Faithful claims (false alarms)", "43", "0 flagged", "0 rejected", "0 flagged", "0 rejected"],
], [2.2, 0.5, 1.1, 1.1, 1.0, 1.0], { fontSize: 18 }));
add(fig("fig_grounding.png", "Skeptic catch rate by corruption type, heuristic versus NLI entailment."));
add(P("Structural failures — invented numbers, missing or wrong citations, fabricated claims — are caught in both modes, and no faithful claim was wrongly flagged. The heuristic Skeptic, however, let 17 of 22 polarity-flipped claims through (*\"gross margin **contracted** 180 basis points\"* citing a sentence that says it *expanded*): the claim shares almost every word and number with its source, so similarity checks pass, and the polarity-cue heuristic is too coarse. With the NLI model all 22 were rejected. The NLI backend should therefore be treated as required, not optional, for real use."));
add(P("**Caveats.** The corruptions are synthetic and the faithful claims are verbatim, which is the easy case; paraphrased LLM claims are harder to verify. The audit therefore bounds the Skeptic's catch rate from above. A human audit — `grounding_audit --export N` samples claims from real briefs into a spreadsheet for 1/0 annotation and `--score` computes the supported fraction and the Skeptic's agreement with the annotator — is implemented and tested but has not been run, because no LLM-written briefs have been generated yet."));
add(H2("6.5  Signal validity"));
add(P("The question is whether the prepared-versus-Q&A delta correlates with the subsequent five-day return (market-adjusted) better than document-level sentiment does. The harness builds three predictors per call (delta, document-level mean, prepared-only mean), joins them to forward returns from a CSV or from Yahoo Finance, and reports Spearman ρ with p-value, Pearson r, a 2,000-sample bootstrap 95% confidence interval, and the difference between the delta and document-level correlations, together with an explicit interpretation that defaults to a null result when nothing is significant."));
add(note("**Not run.** The only corpus available is synthetic, so any correlation with real prices would be meaningless, and no returns file is bundled on purpose. Tests exercise the harness on fake returns only to check the plumbing. With a watchlist-sized sample (tens of calls) a null result is the expected outcome; the project plan treats a clearly reasoned null result as a legitimate finding."));
add(H2("6.6  Latency and cost"));
add(table("Measured latency", ["Operation", "Measured", "Notes"], [
  ["Score one sentence", "0.03 ms (rules) – 10.5 ms (FinBERT)", "CPU, gold-set average (Table 6.2)"],
  ["Generate one brief, offline agents", "0.79 s mean, 1.55 s max", "Rule-based model, heuristic Skeptic, 2 briefs"],
  ["Generate one brief, NLI Skeptic", "4.9 s", "Includes loading the NLI model; first brief of the run"],
  ["Full daily run on the sample corpus", "84 s", "Fresh database; 5 documents, 88 chunks, FinBERT scoring, NLI Skeptic, 2 briefs, drift, digest; includes loading both models"],
  ["LLM tokens and cost per brief", "not measured", "Recorded per brief (tokens in/out) once an API key is configured"],
  ["Fine-tuning time", "CNN 10 s · BiLSTM 28 s · FinBERT 238 s", "CPU; FinBERT on 1,500 examples, 2 epochs"],
], [2.2, 2.2, 2.4]));
add(P("Cached briefs cost nothing: a second daily run with no new documents skipped all five documents as duplicates, wrote no new scores or embeddings and returned both cached briefs. It did re-analyse six chunks that contain no aspect mention (they leave no score row to mark them as done) — harmless, but wasted work at scale."));
add(H2("6.7  Qualitative findings from the end-to-end run"));
add(bullets([
  "**Q&A is weaker than the script.** On ACMX's first call the Q&A-minus-prepared delta was −1.15, driven by guidance (−1.99: \"raising our full-year guidance\" in the script, \"visibility beyond the third quarter is limited\" in the Q&A) and margins (−1.98: a 180 bp expansion in the script, input costs \"a headwind\" and tariffs \"difficult to predict\" in the Q&A). The signal behaves as designed on text written to exhibit it; whether it does so on real calls is the open question of Section 6.5.",
  "**Repeated claims** across aspects in the brief (Section 5.3).",
  "**Over-confident transformer.** FinBERT assigned −1.00 with 100% confidence to *\"We are not able to say.\"* — a reasonable negative-tone reading, but the certainty is not warranted; confidence values are uncalibrated.",
  "**Mixed document types.** The top digest move (ACMX demand +0.15 → +0.99) compares a call with a 10-Q filed six days later; trajectories mix document types, which inflates moves.",
  "**Noisy drift alerts** on very small windows (Section 5.4).",
]));

// 7 ---------------------------------------------------------------
add(newChapter("Testing"));
add(H2("7.1  Strategy"));
add(P("Every test runs offline in about 20 seconds with no API keys: the LLM backend is pinned to the deterministic heuristic, the serving model to the rule-based model, and the `.env` loader is disabled, so results never depend on a developer's local files. Tests use in-memory SQLite, the bundled sample corpus and FastAPI's test client."));
add(table("Automated tests by module (55 in total; one test is parametrised six ways)", ["Module", "Tests", "What is covered"], [
  ["test_ingestion.py", "6", "normalisation, abbreviation-aware splitting, speaker/section parsing, hashing, idempotent ingestion"],
  ["test_absa.py", "20", "negation scope, hedging, clause splitting, aspect triggers, spaCy vs. fallback agreement, directional scoring, VADER's failure, gold-set integrity, no gold leakage into training data, trainable model beats chance"],
  ["test_agents.py", "9", "Skeptic accepts faithful claims; rejects fabricated numbers, bad citations and contradictions; full graph produces a cited brief with every agent in the trace; brief caching; rejected claims never reach the brief"],
  ["test_api_and_monitoring.py", "9", "PSI, drift alerting and idempotency, API validation and errors, daily run followed by every dashboard endpoint, cron-token enforcement"],
  ["test_evaluation.py", "6", "lexicon failure analysis, adversarial grounding thresholds, human-audit export/score round trip, signal-validity plumbing and null reporting, latency report"],
  ["test_env_loader.py", "5", "real environment wins over .env, empty values ignored, skip flag, parser edge cases, every variable documented"],
], [1.8, 0.6, 4.4], { firstColBold: true }));
add(shot("15_terminal_tests.png", "Test run: 55 passed.", { width: 5.4 }));
add(H2("7.2  Continuous integration"));
add(P("A GitHub Actions workflow installs CPU-only PyTorch and the NLP models, runs the Python suite, and type-checks and builds the dashboard on every push and pull request. (Its results on GitHub were not inspected during this phase.)"));
add(H2("7.3  Defects found and fixed"));
add(table("Defects found through testing and use", ["Defect", "Found by", "Fix"], [
  ["Bull and bear claim IDs both started with *b*, so a rejected bear claim could hide an accepted bull claim", "Test: rejected claims never reach the brief", "Distinct `bl` / `br` prefixes"],
  ["Skeptic rejected a verbatim quote containing negation as \"contradicted\"", "Inspecting a generated brief", "Near-verbatim quotes exempt from the cue heuristic"],
  ["Offline LLM backend reported its name as *base*, breaking cost reports", "Test: latency/cost report", "Name set in the constructor"],
  ["Dashboard shipped a Next.js release with known security advisories", "`npm audit`", "Upgraded to Next.js 16 / React 19 (0 advisories)"],
  ["Daily CLI crashed printing the digest (▲ ▼ ⚠) on Windows consoles", "Running the pipeline for this report", "stdout reconfigured to UTF-8"],
  ["Each daily run appended duplicate drift reports", "Screenshot of the drift page for this report", "One report per (ticker, window); regression test added"],
], [3.0, 1.9, 1.9]));

// 8 ---------------------------------------------------------------
add(newChapter("Syllabus Mapping"));
add(table("Mapping to the Sentiment Analysis course (231CAUEC51)", ["Module", "Topic", "Where it appears in Sentari"], [
  ["M1", "Levels, challenges, applications", "Aspect-level framing (1.1, 2.1); non-advice ethics (9)"],
  ["M2", "Preprocessing and feature engineering", "Transcript-aware segmentation, negation scope, hedging, clause splitting, TF-IDF, embeddings (4.1, 4.2)"],
  ["M3", "Lexicon- and knowledge-based methods", "VADER, SentiWordNet, Loughran-McDonald, directional rules; lexicon failure analysis (4.4, 6.3)"],
  ["M4", "Machine-learning and deep-learning methods", "Naive Bayes, Decision Tree, CNN, BiLSTM, fine-tuned FinBERT — one ladder, one test set (4.4, 6.2)"],
  ["M5", "Aspect-based sentiment analysis", "Aspect triggers with dependency-parsed opinion targets, aspect-pair transformer, per-aspect trajectories (4.3–4.5)"],
  ["M6", "Applications", "Financial decision support: dashboard, digest, grounded briefs, drift monitoring (4.7–4.10, 5)"],
], [0.6, 2.0, 4.2], { firstColBold: true }));

// 9 ---------------------------------------------------------------
add(newChapter("Ethical and Legal Considerations"));
add(bullets([
  "**Not investment advice.** Sentari describes what companies said; it makes no recommendation and no price prediction. The disclaimer appears in the API description and every response that carries analysis, on every dashboard page, and in every digest and brief.",
  "**Honest uncertainty.** Confidence is labelled a heuristic, unverified claims are visibly flagged, and the evaluation reports negative and missing results alongside positive ones.",
  "**Source terms.** Official APIs are preferred (SEC EDGAR with a contact User-Agent, as the SEC requires). Scrapers respect terms of use; the NSE scraper returns nothing rather than work around access controls. Raw responses are cached to minimise load on sources.",
  "**Data protection.** Only public corporate disclosures and news are processed; no personal data is collected. Speaker names in transcripts are public officers' statements. API keys live in a gitignored `.env` and never in code or logs.",
  "**Synthetic data.** The demonstration corpus is fictional and labelled SYNTHETIC in every document title shown in the UI.",
]));

// 10 --------------------------------------------------------------
add(newChapter("Project Status Against the Plan"));
add(table("Roadmap from the project specification", ["Phase", "Deliverable", "Status"], [
  ["1  Data pipeline", "Ingestion for a 10-ticker pilot watchlist", "Pipeline built and tested on sample data; live pilot pending a transcript source and watchlist"],
  ["2  Preprocessing & lexicons", "Clean corpus; VADER/SWN/LM scored; failure analysis", "Done"],
  ["3  Classical ML + DL", "NB, DT, CNN, LSTM trained and logged in MLflow", "Done"],
  ["4  Aspect extraction", "POS/dependency-based extraction; aspect-level scoring", "Done (rules + dependency parse; supervised aspect tagger not built)"],
  ["5  Transformer", "FinBERT fine-tuned on aspect sentiment", "Done (on weak labels)"],
  ["6  Agent layer", "Bull/bear/skeptic/judge with grounding checks", "Done"],
  ["7  Storage + dashboard", "Schema live; dashboard with drill-down", "Done (SQLite verified; PostgreSQL untested)"],
  ["8  Deployment + monitoring", "Dockerised, on Cloud Run, drift monitor running", "Drift monitor done; Docker/Cloud Run files written, not built or deployed"],
  ["9  Evaluation", "Ladder table, grounding audit, signal validity", "Ladder and adversarial audit done; human audit and signal validity pending real data"],
  ["10  Report + demo", "Final report, recorded demo, GitHub polish", "This report; demo video not recorded"],
], [1.7, 2.4, 2.7], { firstColBold: true }));
add(H2("10.1  Remaining work, in priority order"));
add(numbered([
  "**Real transcripts.** Choose a source (public dataset, NSE/BSE transcript PDFs, company IR pages or a paid API), write the scraper, and ingest the 10-ticker pilot.",
  "**Real gold set.** Annotate a few hundred sentences from real filings and calls, then re-run the ladder and the lexicon analysis against the official Loughran-McDonald dictionary.",
  "**Signal validity** on the pilot with real forward returns; report the result whatever it is.",
  "**LLM agents** with an API key; human grounding audit of about 50 claims; measure tokens and cost per brief.",
  "**Deploy:** build the images, run on Cloud Run with Cloud SQL and the scheduler, then record the demo.",
  "**Fixes found in this report:** deduplicate claims by cited chunk; raise the drift minimum sample; separate trajectories by document type; fix the mobile navigation bar.",
]));

// 11 --------------------------------------------------------------
add(newChapter("Limitations and Future Work"));
add(H2("11.1  Limitations"));
add(bullets([
  "**Evaluation data.** A 94-sentence self-written gold set, weak template labels and a synthetic corpus limit what the numbers can show; Section 6.2 lists the specific biases.",
  "**Aspect handling.** One sentence can trigger several aspects and contribute the same claim to each; mixed clauses of one aspect are averaged, so a strong positive and a strong negative cancel to neutral; aspect detection is rule-based with no learned tagger.",
  "**Grounding.** The heuristic Skeptic cannot detect polarity inversions; even with NLI, verification is only as good as the entailment model, and has not been tested on paraphrased LLM claims.",
  "**Calibration.** Model confidences (notably FinBERT's) and the brief confidence are not calibrated probabilities.",
  "**Monitoring.** Drift alerts on very small windows are noisy; trajectories mix document types.",
  "**Deployment.** Live scrapers, containers, PostgreSQL, cloud deployment and digest sending are implemented but unverified.",
]));
add(H2("11.2  Future work"));
add(bullets([
  "A supervised aspect tagger trained on the real gold set, with claim deduplication across aspects.",
  "Calibrated confidence (temperature scaling on a real validation set) and per-aspect thresholds.",
  "Multiple training seeds and bootstrap confidence intervals for every ladder metric.",
  "pgvector or Qdrant approximate-nearest-neighbour retrieval over sentence-transformer embeddings for larger watchlists.",
  "Speaker-level analysis (CEO versus CFO tone) and question-level Q&A analysis (which analyst question triggered hedging).",
  "Indian-market coverage through exchange-filed transcript PDFs, including PDF text extraction.",
]));

// 12 --------------------------------------------------------------
add(newChapter("Conclusion"));
add(P("Sentari shows that aspect-level analysis of financial disclosures can be delivered as a working, end-to-end service: from raw documents, through six-aspect sentiment scored by a comparable ladder of ten models, to a written brief in which every claim is tied to its source sentence and checked by an explicit grounding gate before a reader sees it."));
add(P("The measurements support the project's two central premises. General-purpose lexicons fail on financial language in a specific, predictable way — they read the direction of a verb rather than its implication for the company — and both finance-specific directionality and fine-tuned transformers largely correct it. And a grounding gate does stop the structural errors that generative models make; the adversarial audit also exposed where a heuristic gate fails and showed that an entailment model closes that gap."));
add(P("Equally, the report is explicit about what is not yet shown. The model numbers come from a small self-written test set and weak labels; the corpus is synthetic; and the platform's signature signal has not been tested against real prices. The next steps are therefore clear and practical: real transcripts, a larger real gold set, the signal-validity study and a deployed service. The pipeline, evaluation harnesses and tests needed for each of them are already in place."));

// References ------------------------------------------------------
const refs = [
  "T. Loughran and B. McDonald, \"When is a liability not a liability? Textual analysis, dictionaries, and 10-Ks,\" *The Journal of Finance*, vol. 66, no. 1, pp. 35–65, 2011.",
  "C. J. Hutto and E. Gilbert, \"VADER: A parsimonious rule-based model for sentiment analysis of social media text,\" in *Proc. 8th Int. AAAI Conf. on Weblogs and Social Media (ICWSM)*, 2014.",
  "S. Baccianella, A. Esuli and F. Sebastiani, \"SentiWordNet 3.0: An enhanced lexical resource for sentiment analysis and opinion mining,\" in *Proc. LREC*, 2010.",
  "D. Araci, \"FinBERT: Financial sentiment analysis with pre-trained language models,\" arXiv:1908.10063, 2019.",
  "Y. Kim, \"Convolutional neural networks for sentence classification,\" in *Proc. EMNLP*, 2014, pp. 1746–1751.",
  "S. Hochreiter and J. Schmidhuber, \"Long short-term memory,\" *Neural Computation*, vol. 9, no. 8, pp. 1735–1780, 1997.",
  "J. Devlin, M.-W. Chang, K. Lee and K. Toutanova, \"BERT: Pre-training of deep bidirectional transformers for language understanding,\" in *Proc. NAACL-HLT*, 2019.",
  "C. Sun, L. Huang and X. Qiu, \"Utilizing BERT for aspect-based sentiment analysis via constructing auxiliary sentence,\" in *Proc. NAACL-HLT*, 2019.",
  "M. Pontiki et al., \"SemEval-2014 Task 4: Aspect based sentiment analysis,\" in *Proc. 8th Int. Workshop on Semantic Evaluation (SemEval)*, 2014.",
  "B. Liu, *Sentiment Analysis and Opinion Mining*. Morgan & Claypool, 2012.",
  "P. Malo, A. Sinha, P. Korhonen, J. Wallenius and P. Takala, \"Good debt or bad debt: Detecting semantic orientations in economic texts,\" *JASIST*, vol. 65, no. 4, pp. 782–796, 2014.",
  "N. Reimers and I. Gurevych, \"Sentence-BERT: Sentence embeddings using Siamese BERT-networks,\" in *Proc. EMNLP-IJCNLP*, 2019. (Cross-encoder NLI model `cross-encoder/nli-deberta-v3-small` from the Sentence-Transformers library.)",
  "Z. Ji et al., \"Survey of hallucination in natural language generation,\" *ACM Computing Surveys*, vol. 55, no. 12, 2023.",
  "N. Siddiqi, *Credit Risk Scorecards: Developing and Implementing Intelligent Credit Scoring*. Wiley, 2006.",
  "F. Pedregosa et al., \"Scikit-learn: Machine learning in Python,\" *JMLR*, vol. 12, pp. 2825–2830, 2011.",
  "U.S. Securities and Exchange Commission, \"EDGAR application programming interfaces,\" sec.gov developer resources.",
  "J. Cohen, *Statistical Power Analysis for the Behavioral Sciences*, 2nd ed. Lawrence Erlbaum, 1988.",
  "A. Paszke et al., \"PyTorch: An imperative style, high-performance deep learning library,\" in *Proc. NeurIPS*, 2019.",
  "T. Wolf et al., \"Transformers: State-of-the-art natural language processing,\" in *Proc. EMNLP: System Demonstrations*, 2020.",
  "M. Zaharia et al., \"Accelerating the machine learning lifecycle with MLflow,\" *IEEE Data Engineering Bulletin*, vol. 41, no. 4, 2018.",
];
add(new Paragraph({ heading: HeadingLevel.HEADING_1, pageBreakBefore: true, children: [new TextRun("References")] }));
refs.forEach((r, i) => add(new Paragraph({ spacing: { after: 100 }, indent: { left: 540, hanging: 540 },
  children: [new TextRun(`[${i + 1}]	`), ...runs(r)] })));

// Appendices ------------------------------------------------------
const appendix = (letter, t) => { chapter = letter; figN = 0; tabN = 0; return new Paragraph({ heading: HeadingLevel.HEADING_1, pageBreakBefore: true, children: [new TextRun(`Appendix ${letter}  ${t}`)] }); };
add(appendix("A", "Running the System"));
add(P("Prerequisites: Python 3.12+, Node.js 20+. All commands run from the repository root."));
add(code([
  "pip install -r requirements.txt",
  "python -m spacy download en_core_web_sm",
  "",
  "# tests (offline) and the daily pipeline",
  "python -m pytest -q",
  "python -m absa_service.cli daily",
  "python -m absa_service.cli analyze \"<any earnings text>\"",
  "",
  "# model ladder and evaluation",
  "python -m absa_service.train --transformer --transformer-zero-shot",
  "python -m evaluation.lexicon_failure",
  "SENTARI_NLI=hf python -m evaluation.grounding_audit --adversarial",
  "python -m evaluation.signal_validity --returns returns.csv",
  "python -m evaluation.report",
  "",
  "# services",
  "uvicorn absa_service.main:app --port 8000      # API; docs at /docs",
  "cd dashboard && npm install && npm run dev     # http://localhost:3000",
  "docker compose up --build                      # full stack (not yet verified)",
]));
add(appendix("B", "Configuration"));
add(P("Copy `.env.example` to `.env` (gitignored). Everything is optional for offline use; `SETUP.md` explains how to obtain each value."));
add(table("Configuration variables", ["Variable", "Purpose"], [
  ["`DATABASE_URL`", "SQLAlchemy URL; default local SQLite"],
  ["`SENTARI_MODEL`", "Force the serving model (else the registry decides)"],
  ["`ANTHROPIC_API_KEY`, `SENTARI_LLM`, `SENTARI_LLM_MODEL`", "LLM agents; `SENTARI_LLM=heuristic` forces offline"],
  ["`SENTARI_NLI=hf`", "Transformer NLI entailment in the Skeptic (recommended)"],
  ["`SENTARI_USER_AGENT`", "Contact User-Agent required by SEC EDGAR"],
  ["`SENTARI_EMBEDDER`, `SENTARI_GLOVE`, `SENTARI_BASE_MODEL`", "Embeddings, GloVe vectors, transformer checkpoint"],
  ["`MLFLOW_TRACKING_URI`", "MLflow server (default local file store)"],
  ["`SLACK_WEBHOOK_URL`, `SMTP_*`, `DIGEST_TO`", "Digest delivery"],
  ["`SENTARI_CRON_TOKEN`, `CORS_ORIGINS`", "Protect `/run/daily`; allowed dashboard origins"],
  ["`SENTARI_ARTIFACTS`, `SENTARI_CACHE_DIR`", "Model weights and raw-response cache locations"],
], [2.8, 4.0]));
add(appendix("C", "API Reference"));
add(table("HTTP endpoints", ["Method", "Path", "Purpose"], [
  ["GET", "/health", "Service status, aspect list, disclaimer"],
  ["POST", "/analyze", "Aspect sentiment for free text"],
  ["POST", "/score", "Raw polarity for (text, aspect) pairs with any model"],
  ["GET", "/models", "Model registry: runs, metrics, serving flag"],
  ["GET", "/watchlist", "Per-ticker latest aspect summary and brief"],
  ["GET", "/tickers/{ticker}/trajectory", "Per-document aspect means over time"],
  ["GET", "/tickers/{ticker}/points", "Scored sentences behind a trajectory point"],
  ["GET", "/chunks/{chunk_id}", "Source sentence with context and all model verdicts"],
  ["GET", "/tickers/{ticker}/briefs", "Recent briefs for a ticker"],
  ["GET", "/briefs/{brief_id}", "Brief with audit trail and resolved sources"],
  ["POST", "/briefs/generate", "Generate or fetch the cached brief"],
  ["GET", "/drift", "Drift reports"],
  ["GET", "/digest", "Current top aspect moves"],
  ["POST", "/run/daily", "Daily pipeline (scheduler target; optional token)"],
], [0.8, 2.5, 3.5]));
add(appendix("D", "Repository Structure"));
add(table("Repository layout", ["Path", "Contents"], [
  ["ingestion/", "scrapers/ (sample, sec_edgar, news, nse), normalize.py, pipeline.py, scheduler_config.yaml"],
  ["absa_service/", "preprocessing/, models/ (lexicon, classical_ml, deep_learning, transformer), aspect_extraction.py, scoring.py, signals.py, train.py, registry.py, serving.py, main.py + api.py (FastAPI), orchestration.py, cli.py"],
  ["agents/", "extractor_agent.py, bull_bear_agents.py, skeptic_agent.py, judge_agent.py, graph.py (LangGraph), llm.py"],
  ["storage/", "models.py (schema), db.py, migrations/"],
  ["monitoring/, delivery/", "drift.py; digest.py"],
  ["dashboard/", "Next.js app: watchlist, ticker, brief, drift and model pages"],
  ["evaluation/", "metrics, lexicon_failure, grounding_audit, signal_validity, latency_cost, report, model_comparison.ipynb"],
  ["data/", "sample/ (synthetic corpus), gold/gold.tsv (evaluation set)"],
  ["results/", "committed evaluation outputs quoted in this report"],
  ["report/", "this report, its figures and screenshots, and the scripts that regenerate them"],
  ["tests/", "55 automated tests"],
  ["root", "Dockerfile, docker-compose.yml, dvc.yaml, .github/workflows/ci.yml, deploy/, .env.example, SETUP.md, CLAUDE.md"],
], [1.5, 5.3], { firstColBold: true }));
add(P("**Development tooling.** Git and GitHub for version control; pytest; Playwright for the screenshots in this report; and Claude Code, an AI coding assistant, used during development (commits it helped write are marked as co-authored in the Git history)."));

// ------------------------------------------------------------------ document
const header = new Header({ children: [new Paragraph({ alignment: AlignmentType.RIGHT, border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: RULE, space: 4 } },
  children: [new TextRun({ text: "Sentari — Project Report", size: 17, color: MUTED })] })] });
const footer = (fmt) => new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ children: [PageNumber.CURRENT], size: 18, color: MUTED })] })] });
const page = { size: { width: 11906, height: 16838 }, margin: { top: 1440, right: 1440, bottom: 1300, left: 1440, header: 700, footer: 600 } };

const numberingConfigs = [{ reference: "bullets", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
  style: { paragraph: { indent: { left: 540, hanging: 300 } } } }] }];
for (let i = 0; i < 12; i++) numberingConfigs.push({ reference: `num${i}`, levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT,
  style: { paragraph: { indent: { left: 540, hanging: 360 } } } }] });

const doc = new Document({
  creator: "Nishant Vikas Narudkar", title: "Sentari — Project Report",
  description: "Final year project report: earnings-call and filings intelligence platform",
  features: { updateFields: true },
  styles: {
    default: { document: { run: { font: FONT, size: 22 }, paragraph: { spacing: { after: 140, line: 288 } } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 34, bold: true, color: NAVY, font: FONT }, paragraph: { spacing: { before: 0, after: 280 }, outlineLevel: 0,
          border: { bottom: { style: BorderStyle.SINGLE, size: 8, color: ACCENT, space: 6 } } } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 27, bold: true, color: NAVY, font: FONT }, paragraph: { spacing: { before: 320, after: 140 }, outlineLevel: 1, keepNext: true } },
      { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 23, bold: true, color: ACCENT, font: FONT }, paragraph: { spacing: { before: 220, after: 100 }, outlineLevel: 2, keepNext: true } },
      { id: "FrontHeading", name: "Front Heading", basedOn: "Normal", next: "Normal",
        run: { size: 34, bold: true, color: NAVY, font: FONT }, paragraph: { spacing: { after: 280 },
          border: { bottom: { style: BorderStyle.SINGLE, size: 8, color: ACCENT, space: 6 } } } },
      { id: "FigureCaption", name: "Figure Caption", basedOn: "Normal", next: "Normal",
        run: { size: 19, color: "404040", font: FONT }, paragraph: { alignment: AlignmentType.CENTER, spacing: { before: 40, after: 240 } } },
      { id: "TableCaption", name: "Table Caption", basedOn: "Normal", next: "Normal",
        run: { size: 19, color: "404040", font: FONT }, paragraph: { spacing: { before: 200, after: 80 }, keepNext: true } },
      { id: "Code", name: "Code", basedOn: "Normal",
        run: { font: MONO, size: 17 }, paragraph: { spacing: { line: 240 }, shading: { type: ShadingType.CLEAR, fill: "F3F4F6", color: "auto" }, indent: { left: 120, right: 120 } } },
    ],
  },
  numbering: { config: numberingConfigs },
  sections: [
    { properties: { page }, children: title },
    { properties: { page: { ...page, pageNumbers: { start: 1, formatType: NumberFormat.LOWER_ROMAN } } },
      headers: { default: header }, footers: { default: footer() }, children: [...abstract, ...tocs, ...abbreviations] },
    { properties: { page: { ...page, pageNumbers: { start: 1, formatType: NumberFormat.DECIMAL } } },
      headers: { default: header }, footers: { default: footer() }, children: body },
  ],
});

Packer.toBuffer(doc).then((buf) => { fs.writeFileSync(OUT, buf); console.log("wrote", OUT, (buf.length / 1e6).toFixed(1), "MB"); });
