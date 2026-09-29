// Builds report/ia/Sentari_Report.docx in the department's IA report format (LaTeX-article look: Times, header rule,
// booktabs tables, pastel flow diagrams). Then run export_pdf.ps1 to refresh the lists and export the PDF.
//   node report/ia/build.js
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, ImageRun, Table, TableRow, TableCell, AlignmentType, HeadingLevel,
  LevelFormat, BorderStyle, WidthType, PageBreak, Header, Footer, PageNumber, NumberFormat, TableOfContents,
  StyleLevel, TabStopType, TabStopPosition, VerticalAlign,
} = require(path.join(__dirname, "..", "tools", "node_modules", "docx"));

const ROOT = path.resolve(__dirname, "..", "..");
const FIG = path.join(__dirname, "figures");
const SHOT = path.join(ROOT, "presentation", "assets");
const OUT = path.join(__dirname, "Sentari_Report.docx");

const FONT = "Times New Roman";
const TW = 9026; // text width, A4 with 1" margins (DXA)
const HEADER_LEFT = "Sentari: Earnings-Call Intelligence";
const HEADER_RIGHT = "Sentiment Analysis Report";

// ------------------------------------------------------------------ inline markup: **bold**, *italic*, `code`
function runs(text, base = {}) {
  const out = [];
  const re = /(\*\*[^*]+\*\*|`[^`]+`|\*[^*]+\*)/g;
  let last = 0, m;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(new TextRun({ text: text.slice(last, m.index), ...base }));
    const t = m[0];
    if (t.startsWith("**")) out.push(new TextRun({ text: t.slice(2, -2), ...base, bold: true }));
    else if (t.startsWith("`")) out.push(new TextRun({ text: t.slice(1, -1), ...base, font: "Courier New", size: 21 }));
    else out.push(new TextRun({ text: t.slice(1, -1), ...base, italics: true }));
    last = m.index + t.length;
  }
  if (last < text.length) out.push(new TextRun({ text: text.slice(last), ...base }));
  return out;
}

// paragraphs: LaTeX style - first paragraph after a heading unindented, later ones indented
let indentNext = false;
const P = (text) => {
  const p = new Paragraph({ children: runs(text), alignment: AlignmentType.JUSTIFIED,
    indent: indentNext ? { firstLine: 360 } : undefined });
  indentNext = true;
  return p;
};
let secN = 0, subN = 0;
const H1 = (t, { newPage = true } = {}) => {
  secN += 1; subN = 0; indentNext = false;
  return new Paragraph({ heading: HeadingLevel.HEADING_1, pageBreakBefore: newPage,
    children: [new TextRun(`${secN}`), new TextRun({ text: `\t${t}` })],
    tabStops: [{ type: TabStopType.LEFT, position: 560 }] });
};
const H2 = (t) => {
  subN += 1; indentNext = false;
  return new Paragraph({ heading: HeadingLevel.HEADING_2,
    children: [new TextRun(`${secN}.${subN}`), new TextRun({ text: `\t${t}` })],
    tabStops: [{ type: TabStopType.LEFT, position: 720 }] });
};
const HU = (t) => { indentNext = false; return new Paragraph({ style: "Unnumbered", children: [new TextRun(t)] }); };
const bullets = (items) => { indentNext = true; return items.map((t) => new Paragraph({
  numbering: { reference: "bullets", level: 0 }, children: runs(t), alignment: AlignmentType.JUSTIFIED, spacing: { after: 60 } })); };
let numRef = 0;
const numbered = (items) => { indentNext = true; const ref = `num${numRef++}`; return items.map((t) => new Paragraph({
  numbering: { reference: ref, level: 0 }, children: runs(t), alignment: AlignmentType.JUSTIFIED, spacing: { after: 60 } })); };
let eqN = 0;
const eq = (parts) => { eqN += 1; indentNext = true; return new Paragraph({
  tabStops: [{ type: TabStopType.CENTER, position: TW / 2 }, { type: TabStopType.RIGHT, position: TW }],
  spacing: { before: 120, after: 120 },
  children: [new TextRun("\t"), ...parts.map((p) => typeof p === "string" ? new TextRun({ text: p, italics: true, font: "Cambria Math" }) : p),
    new TextRun(`\t(${eqN})`)] }); };
const quote = (t) => { indentNext = false; return new Paragraph({ indent: { left: 720, right: 720 }, spacing: { before: 80, after: 120 },
  alignment: AlignmentType.JUSTIFIED, children: runs(t, { italics: true }) }); };

// ------------------------------------------------------------------ figures and booktabs tables
let figN = 0, tabN = 0;
function png(file) { const b = fs.readFileSync(file); return { w: b.readUInt32BE(16), h: b.readUInt32BE(20), data: b }; }
function figure(file, caption, { width = 5.6, maxHeight = 7 } = {}) {
  const { w, h, data } = png(file);
  let wi = width, hi = (width * h) / w;
  if (hi > maxHeight) { hi = maxHeight; wi = (maxHeight * w) / h; }
  figN += 1; indentNext = true;
  return [
    new Paragraph({ alignment: AlignmentType.CENTER, keepNext: true, spacing: { before: 120, after: 60 },
      children: [new ImageRun({ type: "png", data, transformation: { width: Math.round(wi * 96), height: Math.round(hi * 96) },
        altText: { title: `Figure ${figN}`, description: caption, name: `Figure ${figN}` } })] }),
    new Paragraph({ style: "FigCaption", children: [new TextRun(`Figure ${figN}: `), ...runs(caption)] }),
  ];
}
const RULE_H = { style: BorderStyle.SINGLE, size: 12, color: "000000" };
const RULE_M = { style: BorderStyle.SINGLE, size: 6, color: "000000" };
const NONE = { style: BorderStyle.NONE, size: 0, color: "FFFFFF" };
function table(caption, headers, rows, widths, { size = 20, boldFirst = true } = {}) {
  const total = widths.reduce((a, b) => a + b, 0);
  const cw = widths.map((x) => Math.round((x * TW) / total));
  cw[cw.length - 1] += TW - cw.reduce((a, b) => a + b, 0);
  const n = rows.length;
  const cell = (text, i, r) => new TableCell({
    width: { size: cw[i], type: WidthType.DXA }, verticalAlign: VerticalAlign.TOP,
    margins: { top: 40, bottom: 40, left: 80, right: 80 },
    borders: { left: NONE, right: NONE, top: r === -1 ? RULE_H : NONE,
               bottom: r === -1 ? RULE_M : r === n - 1 ? RULE_H : NONE },
    children: String(text).split("\n").map((line) => new Paragraph({ spacing: { after: 0, line: 240 }, keepNext: r < n - 1,
      children: runs(line, { size, bold: r === -1 || (boldFirst && i === 0) ? true : undefined }) })),
  });
  tabN += 1; indentNext = true;
  return [
    new Table({ width: { size: TW, type: WidthType.DXA }, columnWidths: cw,
      borders: { top: NONE, bottom: NONE, left: NONE, right: NONE, insideHorizontal: NONE, insideVertical: NONE },
      rows: [new TableRow({ tableHeader: true, children: headers.map((h, i) => cell(h, i, -1)) }),
        ...rows.map((row, r) => new TableRow({ cantSplit: true, children: row.map((c, i) => cell(c, i, r)) }))] }),
    new Paragraph({ style: "TabCaption", children: [new TextRun(`Table ${tabN}: `), ...runs(caption)] }),
  ];
}

// ------------------------------------------------------------------ title page
const C = (text, size, bold = true, after = 60, extra = {}) => new Paragraph({ alignment: AlignmentType.CENTER,
  spacing: { after }, children: [new TextRun({ text, size, bold, ...extra })] });
const members = [["Nishant Narudkar", "23AM1031"], ["Aamir Sarang", "23AM1036"], ["Yash Singh", "23AM1064"], ["Peeyush Hota", "23AM1141"]];
const memberTable = new Table({
  width: { size: 4600, type: WidthType.DXA }, columnWidths: [2700, 1900], alignment: AlignmentType.CENTER,
  borders: { top: NONE, bottom: NONE, left: NONE, right: NONE, insideHorizontal: NONE, insideVertical: NONE },
  rows: members.map(([nm, roll]) => new TableRow({ children: [nm, roll].map((t, i) => new TableCell({
    width: { size: [2700, 1900][i], type: WidthType.DXA }, borders: { top: NONE, bottom: NONE, left: NONE, right: NONE },
    children: [new Paragraph({ alignment: i === 0 ? AlignmentType.RIGHT : AlignmentType.LEFT, spacing: { after: 40 },
      indent: i === 1 ? { left: 360 } : undefined, children: [new TextRun({ text: t, size: 24 })] })] })) })),
});
const logo = png(path.join(FIG, "rait_logo.png"));
const titlePage = [
  new Paragraph({ spacing: { before: 700 }, children: [] }),
  C("B.Tech.", 29), C("Computer Science & Engineering (AIML)", 29), C("Sentiment Analysis (231CAUEC51) Project Report", 29, true, 480),
  C("Sentari: An Earnings-Call & Filings", 41, true, 0), C("Intelligence Platform for Retail Investors", 41, true, 480),
  C("by", 29, true, 200), memberTable,
  new Paragraph({ spacing: { before: 360, after: 60 }, alignment: AlignmentType.CENTER, children: [new TextRun({ text: "Supervisor", size: 29, bold: true })] }),
  C("Ms. Rajashree Shedge", 29, false, 900),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 160 }, children: [new ImageRun({ type: "png", data: logo.data,
    transformation: { width: Math.round(3.1 * 96), height: Math.round((3.1 * logo.h / logo.w) * 96) },
    altText: { title: "RAIT logo", description: "D Y Patil University, Ramrao Adik Institute of Technology", name: "logo" } })] }),
  C("Ramrao Adik Institute of Technology", 29, true, 40), C("(Under the ambit of D. Y. Patil Deemed to be University)", 24, false, 40),
  C("Dr. D. Y. Patil Vidyanagar, Sector 7, Nerul, Navi Mumbai 400 706.", 22, false, 160), C("Academic Year 2026–2027", 29),
];

// ------------------------------------------------------------------ front matter
const FRONT = (t, toc = true) => { indentNext = false; return new Paragraph({ style: toc ? "FrontHeading" : "FrontHeadingNoToc", pageBreakBefore: true, children: [new TextRun(t)] }); };
const abstract = [
  FRONT("Abstract"),
  P("Retail investors who follow fifteen to twenty companies cannot read every earnings-call transcript and 10-K/10-Q filing each quarter, so signals that matter — softer guidance language, hedging in the question-and-answer session, a new litigation risk — are routinely missed. Conventional sentiment tools make this worse: they reduce a whole document to one positive or negative score, and their general-purpose vocabularies misread finance, where *costs fell* is good news and *liabilities decreased* is not negative."),
  P("This report presents **Sentari**, an earnings-call and filings intelligence platform that measures sentiment for six financial aspects — guidance, margins, demand, litigation, management tone and liquidity — rather than for whole documents, tracks each aspect from quarter to quarter, and writes a brief in which every claim is traceable to the sentence that supports it. Sentari combines an idempotent ingestion pipeline with transcript-aware parsing (speakers, prepared remarks versus Q&A), aspect extraction using rules and spaCy dependency parsing, and a ladder of ten sentiment models from VADER and Loughran-McDonald to fine-tuned FinBERT. A LangGraph pipeline of Extractor, Bull, Bear, Skeptic and Judge agents turns scored evidence into a brief; the Skeptic is a grounding gate that checks citations, numbers, semantic similarity and natural-language entailment before any claim reaches the reader."),
  P("On a 94-sentence test set, fine-tuned FinBERT reached a macro-F1 of 0.938, against 0.647 for VADER and 0.599 for the official Loughran-McDonald dictionary; on sentences where financial meaning inverts everyday polarity, VADER erred on 61.5% and FinBERT on 11.5%. The grounding gate caught every fabricated number, missing citation and invented claim in an adversarial audit. A pilot on 414 real earnings calls of ten S&P 500 companies (2015–2025) shows that the prepared-versus-Q&A sentiment gap does not predict stock returns — reported here as a null result — while whole-call sentiment moves with the market's reaction to the call. Limitations, notably a small self-written test set and disagreement between models on real text, are stated throughout."),
  new Paragraph({ spacing: { before: 160 }, alignment: AlignmentType.JUSTIFIED, children: [new TextRun({ text: "Keywords: ", bold: true }),
    new TextRun("Aspect-Based Sentiment Analysis, Financial NLP, Earnings Calls, Loughran-McDonald, FinBERT, Multi-Agent Systems, Grounding, LangGraph.")] }),
];
const contents = [FRONT("Contents", false), new TableOfContents("Contents", { hyperlink: true, headingStyleRange: "1-2" })];
const lists = [
  FRONT("List of Figures", false),
  new TableOfContents("List of Figures", { hyperlink: true, stylesWithLevels: [new StyleLevel("Fig Caption", 1)] }),
  new Paragraph({ style: "FrontHeadingNoToc", spacing: { before: 600 }, children: [new TextRun("List of Tables")] }),
  new TableOfContents("List of Tables", { hyperlink: true, stylesWithLevels: [new StyleLevel("Tab Caption", 1)] }),
];

// ------------------------------------------------------------------ body
const B = [];
const add = (...xs) => xs.flat().forEach((x) => B.push(x));

add(H1("Introduction", { newPage: false }));
add(P("Listed companies publish a steady stream of text: quarterly earnings-call transcripts, annual and quarterly reports (10-K and 10-Q in the United States, results filed with NSE and BSE in India) and a larger volume of news. Much of what changes a company's prospects appears in this text before it appears in the numbers — a guidance range narrowed toward its low end, a chief financial officer who turns evasive about margins in the Q&A, a lawsuit described in a risk-factor footnote. Institutional desks pay analysts and data vendors to monitor this; a retail investor following fifteen to twenty stocks usually cannot, since a single call runs to ten thousand words or more."));
add(P("General-purpose sentiment analysis does not close the gap. It scores a whole document, although one call routinely reports strong demand, weaker margins and a cautious outlook at the same time, and its lexicons were built for reviews and social media, where *decrease*, *cost* and *liability* carry the opposite implications to the ones they carry in finance. Sentari therefore represents a document as a set of aspect-level opinions rather than one score:"));
add(eq(["Sentiment(d) = { (a, s", new TextRun({ text: "a", italics: true, subScript: true, font: "Cambria Math" }), ", evidence", new TextRun({ text: "a", italics: true, subScript: true, font: "Cambria Math" }), ") : a ∈ A },   s ∈ [−1, +1]"]));
add(P("where *A* is the set of six financial aspects, *s* a signed polarity and each score is tied to the sentences that produced it. A multi-agent layer then argues from this evidence, and a verification step ensures that every sentence of the final brief is supported by its cited source."));
add(HU("Problem Statement"));
add(P("Investors cannot rely on document-level, general-purpose sentiment or on ungrounded LLM summaries of financial disclosures. The problem addressed in this report is:"));
add(quote("How can an aspect-based sentiment system measure what management says about each financial aspect of a company, track it over time, and produce a readable brief in which every claim is verifiably grounded in the source text — while being honest, by measurement, about where the approach works and where it does not?"));
add(HU("Objectives and Scope"));
add(P("The objectives are: (G1) aspect-level sentiment on six financial aspects; (G2) an empirical study of where general lexicons fail on financial language; (G3) bull, bear, skeptic and judge agents whose claims are grounded and cited; (G4) a working service with ingestion, storage, a dashboard, a digest and drift monitoring; and (G5) an honest evaluation that reports null results. The scope is daily batch analysis of US and NSE/BSE disclosures. Real-time trading, trade execution and any guarantee of predictive accuracy are out of scope: Sentari is a research and decision-support tool, not investment advice."));

add(H1("Aspect-Based Sentiment Analysis for Financial Text"));
add(P("Sentiment can be analysed at document, sentence or aspect level. Aspect-based sentiment analysis (ABSA) identifies what is being evaluated and the polarity expressed toward each target [7]. Table 1 contrasts the approaches relevant to financial disclosures."));
add(table("Comparison of Sentiment Approaches for Financial Disclosures",
  ["Aspect", "Lexicon (general)", "Machine / Deep Learning", "Sentari (ABSA + agents)"],
  [["Unit of analysis", "Whole document", "Sentence or document", "Aspect clause within a sentence"],
   ["Mechanism", "Word lists (VADER, SentiWordNet)", "Learned from labelled text", "Aspect detection, then per-aspect polarity model"],
   ["Finance awareness", "None: “costs fell” scored negative", "Only if trained on finance", "Financial lexicon, directional rules, FinBERT"],
   ["Output", "One score", "One label", "Six aspect scores over time + cited brief"],
   ["Traceability", "None", "None", "Every claim linked to its sentence"]],
  [1.3, 1.9, 1.9, 2.4], { size: 20 }));
add(H2("The Six Financial Aspects"));
add(P("Each aspect is detected through trigger terms refined by dependency parsing, then scored in the range −1 to +1:"));
add(numbered([
  "**Guidance:** the company's outlook, forecasts and targets (raising or cutting guidance).",
  "**Margins:** profitability, costs and pricing; falling costs are good news for this aspect.",
  "**Demand:** orders, volumes, backlog, customer retention and churn.",
  "**Litigation:** lawsuits, regulatory investigations and legal exposure.",
  "**Management tone:** confidence versus caution, hedging and evasiveness.",
  "**Liquidity:** cash, debt, credit facilities and covenants.",
]));
add(P("The prepared-remarks-versus-Q&A difference of these scores is the platform's signature signal: it tests whether management sounds weaker when answering analysts than when reading its script."));

add(H1("Architecture of Sentari"));
add(P("Sentari is organised as a pipeline of services around a single relational store. A scheduler triggers the daily run; the ingestion service fetches and chunks documents; the ABSA service scores them with the model the registry marks as serving; the agent layer writes briefs; and the delivery layer serves a dashboard, a digest and a drift monitor."));
add(H2("Architecture Diagram"));
add(P("Figure 1 illustrates the conceptual architecture of Sentari."));
add(figure(path.join(FIG, "fig1_architecture.png"), "Conceptual Architecture of Sentari", { width: 4.6, maxHeight: 5.9 }));
add(H2("Architecture Components"));
add(P("The platform partitions the work across specialised modules:"));
add(bullets([
  "**Ingestion Service:** fetches earnings-call transcripts (a pinned public Hugging Face dataset [13]), SEC EDGAR 10-K/10-Q MD&A sections and news; deduplicates by content hash so re-runs never duplicate data; splits transcripts by speaker and into prepared remarks and Q&A.",
  "**ABSA Service (FastAPI):** extracts aspect mentions with rules and spaCy dependency parsing, handles negation scope and hedging, and scores each clause with the serving model.",
  "**Model Registry (MLflow):** records every model version and its test metrics and decides which model serves.",
  "**Agent Layer (LangGraph):** Extractor, Bull, Bear, Skeptic and Judge agents turn evidence into a grounded brief.",
  "**Delivery Layer:** a Next.js dashboard with drill-down from brief to source sentence, a daily digest by e-mail or Slack, and a drift monitor.",
]));
add(table("Agent Roles and Context Sources",
  ["Agent", "Operational Function", "Source Data / Context"],
  [["Extractor", "Selects the strongest evidence per aspect and polarity", "Aspect scores, sentence embeddings"],
   ["Bull", "Builds the supportive case; cites a sentence for every claim", "Positive evidence sentences"],
   ["Bear", "Builds the concerning case; cites a sentence for every claim", "Negative evidence sentences"],
   ["Skeptic", "Verifies each claim against its cited sentence", "Claims + cited source text, NLI model"],
   ["Judge", "Writes the brief from verified claims; computes confidence", "Supported claims, aspect summary"]],
  [1.1, 3.1, 2.6]));

add(H1("Workflow and System Design"));
add(H2("Daily Pipeline Workflow"));
add(P("The daily run is designed to be safe to repeat. Documents already seen are skipped, and a brief is regenerated only when its inputs change, so the agents — and any LLM cost — run only when new calls arrive (Figure 2)."));
add(figure(path.join(FIG, "fig2_workflow.png"), "Daily Workflow of the Sentari Pipeline", { width: 5.0, maxHeight: 4.3 }));
add(H2("Sentiment Model Ladder"));
add(P("All ten models implement one interface — an aspect clause in, a label and a signed score out — so they are interchangeable in production and directly comparable in evaluation: lexicons (VADER [2], SentiWordNet [3], Loughran-McDonald [1] and a rule model adding financial directionality), classical machine learning (Naive Bayes and Decision Tree on TF-IDF), deep learning (a CNN [8] and a BiLSTM [9]) and transformers (FinBERT [4] zero-shot and fine-tuned on the aspect sentence-pair formulation [6])."));
add(H2("Grounding Design"));
add(P("Every claim from the Bull and Bear agents passes the Skeptic's four checks (Figure 3). Only supported claims reach the brief; weak claims are shown as unverified and contradicted ones are dropped but kept in the audit trail."));
add(figure(path.join(FIG, "fig3_grounding.png"), "Skeptic Grounding Gate for Agent Claims", { width: 4.3, maxHeight: 3.7 }));
add(P("The Judge then reports a transparent, uncalibrated confidence:"));
add(eq(["confidence = 0.5 · survival + 0.3 · evidence confidence + 0.2 · aspect coverage"]));

add(H1("Agent Execution Trajectory"));
add(P("An agent execution trajectory τ is the ordered sequence of states, actions and observations produced while generating a brief:"));
add(eq(["τ = { (s", new TextRun({ text: "0", subScript: true, font: "Cambria Math", italics: true }), ", a",
  new TextRun({ text: "0", subScript: true, font: "Cambria Math", italics: true }), ", o",
  new TextRun({ text: "1", subScript: true, font: "Cambria Math", italics: true }), "), …, (s",
  new TextRun({ text: "n", subScript: true, font: "Cambria Math", italics: true }), ", a",
  new TextRun({ text: "n", subScript: true, font: "Cambria Math", italics: true }), ", o",
  new TextRun({ text: "n+1", subScript: true, font: "Cambria Math", italics: true }), ") }"]));
add(P("Table 3 shows the recorded trajectory for the Boeing brief generated on the real-data pilot (Section 7), covering the calls of 28 January and 23 April 2025. Every step is stored in the audit trail."));
add(table("Execution Trajectory for the Boeing Brief (Oct 2024 – Apr 2025)",
  ["Step", "Agent Action (aₜ)", "Observation (oₜ₊₁)", "Next Decision"],
  [["1", "Extractor ranks scored sentences in the window", "230 aspect mentions in 2 calls; 41 evidence sentences kept", "Send positive evidence to Bull, negative to Bear"],
   ["2", "Bull agent builds supportive case", "5 claims (tone, demand, liquidity, guidance, margins)", "Pass claims with citations to Skeptic"],
   ["3", "Bear agent builds concerning case", "6 claims, e.g. $14.3 billion cash usage; 777X costs and tariffs", "Pass claims with citations to Skeptic"],
   ["4", "Skeptic verifies 11 claims", "11 supported, 0 unverified, 0 rejected; NLI entailment 0.77–0.99", "Forward supported claims to Judge"],
   ["5", "Judge writes brief", "Stance mixed (net −0.035); confidence 0.965", "Persist brief and cite sources"],
   ["6", "Store brief and trace", "5 agent steps logged; 0.64 s latency", "Reuse until new calls arrive"]],
  [0.5, 2.1, 2.6, 2.0], { size: 19 }));

add(H1("Evaluation"));
add(P("All models were scored on the same held-out test set of 94 hand-written, aspect-labelled sentences, 26 of which are *trap* sentences where financial meaning inverts everyday polarity. Trainable models learned from 3,400 template-generated weak labels (Table 4)."));
add(table("Model Ladder on the 94-Sentence Test Set",
  ["Model", "Type", "Accuracy", "Macro-F1", "Trap Acc."],
  [["VADER", "Lexicon", "0.649", "0.647", "0.38"], ["SentiWordNet", "Lexicon", "0.489", "0.490", "0.27"],
   ["Loughran-McDonald", "Lexicon", "0.596", "0.599", "0.38"], ["LM + directional rules", "Lexicon + rules", "0.809", "0.805", "0.88"],
   ["Naive Bayes (TF-IDF)", "Classical ML", "0.745", "0.743", "0.69"], ["Decision Tree (TF-IDF)", "Classical ML", "0.532", "0.519", "0.58"],
   ["CNN", "Deep learning", "0.745", "0.739", "0.92"], ["BiLSTM", "Deep learning", "0.638", "0.607", "0.81"],
   ["FinBERT, zero-shot", "Transformer", "0.606", "0.601", "0.35"], ["**FinBERT, fine-tuned**", "Transformer", "**0.936**", "**0.938**", "**0.88**"]],
  [2.2, 1.7, 1.0, 1.0, 1.0], { size: 20 }));
add(P("Fine-tuned FinBERT is the strongest model. General lexicons fail on trap sentences — VADER is wrong on 61.5% of them and SentiWordNet on 73.1% — and plain Loughran-McDonald word counting does not fix this (61.5%), because a word list cannot tell whether *decreased* is good news without knowing what decreased. Directional rules and FinBERT both reduce the error to 11.5%. For example, VADER scores “Customer churn decreased to its lowest level in three years” as negative."));
add(table("Adversarial Grounding Audit: Corrupted Claims Caught by the Skeptic",
  ["Corruption Type", "Claims", "Heuristic Skeptic", "Skeptic + NLI"],
  [["Number changed", "13", "100%", "100%"], ["Citation removed", "43", "100%", "100%"], ["Wrong sentence cited", "43", "100%", "100%"],
   ["Fabricated claim", "43", "100%", "100%"], ["**Polarity flipped**", "22", "**22.7%**", "**100%**"],
   ["Faithful claims wrongly rejected", "43", "0", "0"]],
  [2.6, 1.0, 1.6, 1.6]));
add(P("Structural errors are always caught, but word-level checks miss flipped polarity (“margin *contracted*” citing a sentence that says it *expanded*); the NLI entailment check [12] is therefore essential. These scores are optimistic: the test set is small and self-written, and the corruptions are synthetic."));

add(H1("Case Study: Real Earnings Calls"));
add(P("To evaluate Sentari beyond its test set, the full pipeline was run on real earnings-call transcripts from a public dataset [13] pinned to a fixed revision."));
add(HU("Pilot Profile"));
add(bullets([
  "**Companies:** ten S&P 500 firms across ten sectors — Apple, Microsoft, JPMorgan Chase, Walmart, Johnson & Johnson, ExxonMobil, Boeing, Coca-Cola, Disney and NextEra Energy.",
  "**Data:** 414 earnings calls from 2015 to May 2025; 206,211 sentences parsed; 45,739 aspect mentions scored by each model.",
  "**Market data:** daily prices from the Alpaca market-data API, adjusted against the S&P 500 index (SPY).",
]));
add(figure(path.join(SHOT, "pilot_ba_trajectories_crop.png"), "Sentari Dashboard: Boeing's Six Aspect Trajectories, 2015–2025", { width: 5.9, maxHeight: 4.0 }));
add(HU("Findings"));
add(P("The pipeline produced the Boeing brief traced in Table 3, citing the January 2025 cash burn and the April 2025 remarks on 777X costs and tariffs. Across the pilot, however, the two strongest models agreed on only 65.4% of real aspect mentions and gave opposite polarities to 7.7%, so the question of whether management sounds weaker in Q&A depends on the model: the rule model says so for 64% of calls, FinBERT for 49%. Table 6 tests whether sentiment relates to subsequent market-adjusted returns over 374 calls, using Spearman correlation (ρ)."));
add(table("Signal Validity: Sentiment versus Market-Adjusted Returns (374 Calls)",
  ["Predictor", "Days 0–1 ρ (p)", "Days 0–4 ρ (p)", "Days 2–11 ρ (p)"],
  [["Q&A − prepared gap (rules)", "−0.07 (0.16)", "−0.07 (0.19)", "−0.01 (0.88)"],
   ["Q&A − prepared gap (FinBERT)", "−0.03 (0.52)", "−0.03 (0.58)", "−0.01 (0.90)"],
   ["Whole-call sentiment (rules)", "0.13 (0.013)", "0.15 (0.004)", "−0.09 (0.08)"],
   ["**Whole-call sentiment (FinBERT)**", "**0.13 (0.015)**", "**0.17 (0.001)**", "−0.01 (0.79)"]],
  [2.6, 1.4, 1.4, 1.4], { size: 20 }));
add(P("The prepared-versus-Q&A gap shows no relationship with returns, which is reported as a null result. Whole-call sentiment moves with the stock's reaction around the call, also after controlling for analyst earnings-forecast revisions, but does not predict later drift — it is not a trading signal. These results are preliminary until a human-labelled set of real sentences establishes which model to trust."));
add(figure(path.join(SHOT, "pilot_ba_brief_crop.png"), "Grounded Brief for Boeing: Every Claim Links to its Source Sentence", { width: 5.9, maxHeight: 3.9 }));

add(H1("Benefits, Limitations, and Future Work"));
add(HU("Benefits"));
add(bullets([
  "**Aspect-level insight:** separates guidance, margins, demand, litigation, tone and liquidity instead of one document score.",
  "**Finance-aware scoring:** corrects the systematic errors of general lexicons on financial language.",
  "**Grounded briefs:** every sentence is traceable to its source, with a full audit trail of every agent step.",
  "**Efficient operation:** idempotent ingestion and cached briefs mean work — and LLM cost — only when new documents arrive.",
]));
add(HU("Limitations"));
add(bullets([
  "**Evaluation data:** the 94-sentence test set is small and self-written, and trainable models learned from template labels, so test scores are optimistic.",
  "**Model disagreement:** the two best models disagree on 35% of real sentences; no model is yet validated on real text.",
  "**Aspect detection:** rule-based triggers can file a sentence under the wrong aspect.",
  "**Deployment:** Docker and Cloud Run configuration is written but not yet deployed, and LLM-written briefs have not been audited by humans.",
]));
add(HU("Future Work"));
add(bullets([
  "Complete a 300-sentence human-labelled set from real calls and select the serving model on that evidence.",
  "Re-run the signal-validity study with the validated model; add a learned aspect tagger and calibrated confidence.",
  "Deploy on Google Cloud Run and extend coverage to NSE/BSE transcripts.",
]));

add(H1("Conclusion"));
add(P("Sentari shows that aspect-level sentiment analysis of financial disclosures can be delivered as a complete, working service: from raw earnings calls, through six-aspect scores produced by a comparable ladder of ten models, to a written brief in which every claim is tied to its source sentence and verified by an explicit grounding gate. The evaluation supports both central premises of the project — general-purpose lexicons fail on financial language in a specific, predictable way, and a grounding gate stops the structural errors generative agents make — while showing that an entailment model is required to catch polarity errors."));
add(P("The real-data pilot on 414 earnings calls adds an honest caveat: the prepared-versus-Q&A signal does not predict returns, and the leading models disagree on real text often enough that human-labelled real data is the next essential step. Sentari is therefore best understood as a transparent decision-support tool that helps investors read more, faster, and verify what they read — not as a source of trading signals."));

// references
indentNext = false;
add(new Paragraph({ style: "RefHeading", pageBreakBefore: true, children: [new TextRun("References")] }));
const refs = [
  "T. Loughran and B. McDonald, “When is a liability not a liability? Textual analysis, dictionaries, and 10-Ks,” *The Journal of Finance*, vol. 66, no. 1, pp. 35–65, 2011. https://doi.org/10.1111/j.1540-6261.2010.01625.x",
  "C. J. Hutto and E. Gilbert, “VADER: A parsimonious rule-based model for sentiment analysis of social media text,” *Proc. ICWSM*, 2014.",
  "S. Baccianella, A. Esuli, and F. Sebastiani, “SentiWordNet 3.0: An enhanced lexical resource for sentiment analysis and opinion mining,” *Proc. LREC*, 2010.",
  "D. Araci, “FinBERT: Financial sentiment analysis with pre-trained language models,” arXiv:1908.10063, 2019. https://arxiv.org/abs/1908.10063",
  "J. Devlin, M.-W. Chang, K. Lee, and K. Toutanova, “BERT: Pre-training of deep bidirectional transformers for language understanding,” *Proc. NAACL-HLT*, 2019. https://arxiv.org/abs/1810.04805",
  "C. Sun, L. Huang, and X. Qiu, “Utilizing BERT for aspect-based sentiment analysis via constructing auxiliary sentence,” *Proc. NAACL-HLT*, 2019. https://arxiv.org/abs/1903.09588",
  "M. Pontiki et al., “SemEval-2014 Task 4: Aspect based sentiment analysis,” *Proc. SemEval*, 2014.",
  "Y. Kim, “Convolutional neural networks for sentence classification,” *Proc. EMNLP*, 2014. https://arxiv.org/abs/1408.5882",
  "S. Hochreiter and J. Schmidhuber, “Long short-term memory,” *Neural Computation*, vol. 9, no. 8, pp. 1735–1780, 1997.",
  "Z. Ji et al., “Survey of hallucination in natural language generation,” *ACM Computing Surveys*, vol. 55, no. 12, 2023. https://arxiv.org/abs/2202.03629",
  "S. Yao et al., “ReAct: Synergizing reasoning and acting in language models,” *Proc. ICLR*, 2023. https://arxiv.org/abs/2210.03629",
  "N. Reimers and I. Gurevych, “Sentence-BERT: Sentence embeddings using Siamese BERT-networks,” *Proc. EMNLP-IJCNLP*, 2019. https://arxiv.org/abs/1908.10084",
  "kurry, “S&P 500 earnings call transcripts” dataset, Hugging Face, 2025. https://huggingface.co/datasets/kurry/sp500_earnings_transcripts",
  "Software Repository for Accounting and Finance, “Loughran-McDonald Master Dictionary (1993–2025),” University of Notre Dame. https://sraf.nd.edu/loughranmcdonald-master-dictionary/",
  "N. Narudkar, A. Sarang, Y. Singh, and P. Hota, “Sentari: An Earnings-Call & Filings Intelligence Platform,” GitHub Repository, 2026. https://github.com/nishnarudkar/Sentari",
];
refs.forEach((r, i) => add(new Paragraph({ indent: { left: 540, hanging: 540 }, spacing: { after: 100 }, alignment: AlignmentType.LEFT,
  children: [new TextRun({ text: `[${i + 1}]\t`, size: 22 }), ...runs(r, { size: 22 })], tabStops: [{ type: TabStopType.LEFT, position: 540 }] })));

// ------------------------------------------------------------------ document
const header = () => new Header({ children: [new Paragraph({
  tabStops: [{ type: TabStopType.RIGHT, position: TabStopPosition.MAX }],
  border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: "000000", space: 2 } },
  children: [new TextRun({ text: HEADER_LEFT, size: 21 }), new TextRun({ text: `\t${HEADER_RIGHT}`, size: 21 })] })] });
const footer = () => new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER,
  children: [new TextRun({ children: [PageNumber.CURRENT], size: 22 })] })] });
const page = { size: { width: 11906, height: 16838 }, margin: { top: 1440, right: 1440, bottom: 1300, left: 1440, header: 720, footer: 650 } };

const numbering = [{ reference: "bullets", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
  style: { paragraph: { indent: { left: 540, hanging: 280 } } } }] }];
for (let i = 0; i < 6; i++) numbering.push({ reference: `num${i}`, levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.",
  alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 540, hanging: 360 } } } }] });

const doc = new Document({
  creator: "Nishant Narudkar, Aamir Sarang, Yash Singh, Peeyush Hota", title: "Sentari — Sentiment Analysis Project Report",
  styles: {
    default: { document: { run: { font: FONT, size: 24 }, paragraph: { spacing: { after: 80, line: 276 } } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { font: FONT, size: 34, bold: true }, paragraph: { spacing: { before: 0, after: 200 }, outlineLevel: 0, keepNext: true } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { font: FONT, size: 28, bold: true }, paragraph: { spacing: { before: 240, after: 120 }, outlineLevel: 1, keepNext: true } },
      { id: "Unnumbered", name: "Unnumbered Heading", basedOn: "Normal", next: "Normal",
        run: { font: FONT, size: 28, bold: true }, paragraph: { spacing: { before: 240, after: 120 }, keepNext: true } },
      { id: "FrontHeading", name: "Front Heading", basedOn: "Normal", next: "Normal",
        run: { font: FONT, size: 34, bold: true }, paragraph: { spacing: { after: 240 }, outlineLevel: 0 } },
      { id: "FrontHeadingNoToc", name: "Front Heading Plain", basedOn: "Normal", next: "Normal",
        run: { font: FONT, size: 34, bold: true }, paragraph: { spacing: { after: 240 } } },
      { id: "RefHeading", name: "References Heading", basedOn: "Normal", next: "Normal",
        run: { font: FONT, size: 34, bold: true }, paragraph: { spacing: { after: 240 } } },
      { id: "TOC1", name: "toc 1", basedOn: "Normal", next: "Normal", run: { bold: true }, paragraph: { spacing: { before: 100, after: 40 } } },
      { id: "TOC2", name: "toc 2", basedOn: "Normal", next: "Normal", paragraph: { indent: { left: 360 }, spacing: { after: 40 } } },
      { id: "FigCaption", name: "Fig Caption", basedOn: "Normal", next: "Normal",
        run: { font: FONT, size: 22 }, paragraph: { alignment: AlignmentType.CENTER, spacing: { before: 40, after: 240 } } },
      { id: "TabCaption", name: "Tab Caption", basedOn: "Normal", next: "Normal",
        run: { font: FONT, size: 22 }, paragraph: { alignment: AlignmentType.CENTER, spacing: { before: 100, after: 240 } } },
    ],
  },
  numbering: { config: numbering },
  sections: [
    { properties: { page }, children: titlePage },
    { properties: { page: { ...page, pageNumbers: { start: 1, formatType: NumberFormat.LOWER_ROMAN } } },
      headers: { default: header() }, footers: { default: footer() }, children: [...abstract, ...contents, ...lists] },
    { properties: { page: { ...page, pageNumbers: { start: 1, formatType: NumberFormat.DECIMAL } } },
      headers: { default: header() }, footers: { default: footer() }, children: B },
  ],
});
Packer.toBuffer(doc).then((buf) => { fs.writeFileSync(OUT, buf); console.log("wrote", OUT, (buf.length / 1e6).toFixed(1), "MB"); });
