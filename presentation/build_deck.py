"""Build presentation/Sentari_Presentation.pptx on the RAIT / D Y Patil template.

    1. base deck: the template with its content slide (slide3.xml) duplicated 9x, made with the pptx skill:
         unzip template.pptx -> work/;  add_slide.py work/ slide3.xml  (x9);  zip work/ -> base.pptx
    2. python presentation/make_diagrams.py            (architecture + agent diagrams)
    3. python presentation/capture_pilot_screens.py    (needs the API + dashboard running on the pilot DB)
    4. python presentation/build_deck.py base.pptx

All numbers are taken from results/ and the pilot runs; see the notes on each slide.
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

from lxml import etree
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION, XL_LEGEND_POSITION
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Inches, Pt

HERE = Path(__file__).resolve().parent
ASSETS = HERE / "assets"
OUT = HERE / "Sentari_Presentation.pptx"

MAROON, ROSE, INK, GREY, LIGHT = "9F1C33", "F6E4E7", "262626", "595959", "F2F2F2"
GREEN, AMBER, WHITE = "2E7D4F", "B7791F", "FFFFFF"
SERIF, SANS = "Times New Roman", "Calibri"
FOOTER = "Sentari — Sentiment Analysis (231CAUEC51)"


def rgb(h: str) -> RGBColor:
    return RGBColor.from_string(h)


# ------------------------------------------------------------------ low-level helpers
def shape(slide, name):
    return next(s for s in slide.shapes if s.name == name)


def remove(sh):
    sh._element.getparent().remove(sh._element)


def set_runs(tf, lines: list[str]):
    """Replace text keeping the first run's formatting (one paragraph per line)."""
    paras = tf.paragraphs
    proto_p = copy.deepcopy(paras[0]._p)
    for p in paras[1:]:
        p._p.getparent().remove(p._p)
    first = tf.paragraphs[0]
    for r in first.runs[1:]:
        r._r.getparent().remove(r._r)
    first.runs[0].text = lines[0]
    for line in lines[1:]:
        new = copy.deepcopy(proto_p)
        tf._txBody.append(new)
        p = tf.paragraphs[-1]
        for r in p.runs[1:]:
            r._r.getparent().remove(r._r)
        p.runs[0].text = line


def text(slide, x, y, w, h, paras, size=16, font=SERIF, color=INK, bold=False, align=PP_ALIGN.LEFT,
         anchor=MSO_ANCHOR.TOP, space_after=4, line_spacing=None):
    """paras: list of str | dict(t=..., b=bool, c=hex, s=size, bullet=bool, i=italic, runs=[(t, {opts})])."""
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = Inches(0.04)
    tf.margin_top = tf.margin_bottom = Inches(0.02)
    tf.vertical_anchor = anchor
    for i, para in enumerate(paras):
        para = {"t": para} if isinstance(para, str) else para
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = para.get("align", align)
        p.space_after = Pt(para.get("space_after", space_after))
        if line_spacing:
            p.line_spacing = line_spacing
        runs = para.get("runs") or [(para.get("t", ""), {})]
        for t, opts in runs:
            r = p.add_run()
            r.text = t
            f = r.font
            f.name = opts.get("font", para.get("font", font))
            f.size = Pt(opts.get("s", para.get("s", size)))
            f.bold = opts.get("b", para.get("b", bold))
            f.italic = opts.get("i", para.get("i", False))
            f.color.rgb = rgb(opts.get("c", para.get("c", color)))
        if para.get("bullet"):
            bullet(p, para.get("level", 0), para.get("bc", MAROON))
    return tb


def bullet(p, level=0, color=MAROON):
    pPr = p._p.get_or_add_pPr()
    indent = 0.22 + 0.25 * level
    pPr.set("marL", str(int(Inches(indent))))
    pPr.set("indent", str(int(-Inches(0.2))))
    for tag in ("a:buClr", "a:buFont", "a:buChar", "a:buNone"):
        for el in pPr.findall(qn(tag)):
            pPr.remove(el)
    buClr = etree.SubElement(pPr, qn("a:buClr"))
    etree.SubElement(buClr, qn("a:srgbClr")).set("val", color)
    etree.SubElement(pPr, qn("a:buFont")).set("typeface", "Arial")
    etree.SubElement(pPr, qn("a:buChar")).set("char", "•")


def box(slide, x, y, w, h, fill=LIGHT, line=None, shape_type=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.08):
    s = slide.shapes.add_shape(shape_type, Inches(x), Inches(y), Inches(w), Inches(h))
    s.fill.solid()
    s.fill.fore_color.rgb = rgb(fill)
    if line:
        s.line.color.rgb = rgb(line)
        s.line.width = Pt(1)
    else:
        s.line.fill.background()
    s.shadow.inherit = False
    if shape_type == MSO_SHAPE.ROUNDED_RECTANGLE:
        s.adjustments[0] = radius
    s.text_frame.text = ""
    return s


def box_text(s, paras, size=14, color=INK, bold=False, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE, font=SERIF):
    tf = s.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = Inches(0.08)
    tf.margin_top = tf.margin_bottom = Inches(0.04)
    for i, para in enumerate(paras):
        para = {"t": para} if isinstance(para, str) else para
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = para.get("align", align)
        r = p.add_run()
        r.text = para["t"]
        r.font.name = para.get("font", font)
        r.font.size = Pt(para.get("s", size))
        r.font.bold = para.get("b", bold)
        r.font.color.rgb = rgb(para.get("c", color))
    return s


def picture(slide, path, x, y, w=None, h=None, border=True):
    pic = slide.shapes.add_picture(str(path), Inches(x), Inches(y),
                                   Inches(w) if w else None, Inches(h) if h else None)
    if border:
        pic.line.color.rgb = rgb("BFBFBF")
        pic.line.width = Pt(0.75)
    return pic


def table(slide, x, y, w, col_w, rows, header_fill=MAROON, size=12, row_h=0.32, bold_first_col=False, zebra=True):
    t = slide.shapes.add_table(len(rows), len(rows[0]), Inches(x), Inches(y), Inches(w), Inches(row_h * len(rows))).table
    total = sum(col_w)
    for i, cw in enumerate(col_w):
        t.columns[i].width = Emu(int(Inches(w) * cw / total))
    for r, row in enumerate(rows):
        t.rows[r].height = Inches(row_h)
        for c, val in enumerate(row):
            cell = t.cell(r, c)
            cell.margin_left = cell.margin_right = Inches(0.06)
            cell.margin_top = cell.margin_bottom = Inches(0.02)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            cell.fill.solid()
            cell.fill.fore_color.rgb = rgb(header_fill if r == 0 else (LIGHT if zebra and r % 2 == 0 else WHITE))
            val = val if isinstance(val, dict) else {"t": str(val)}
            tf = cell.text_frame
            tf.word_wrap = True
            p = tf.paragraphs[0]
            p.alignment = val.get("align", PP_ALIGN.LEFT if c == 0 else PP_ALIGN.CENTER)
            run = p.add_run()
            run.text = val["t"]
            run.font.name = SERIF
            run.font.size = Pt(val.get("s", size))
            run.font.bold = r == 0 or val.get("b", False) or (bold_first_col and c == 0)
            run.font.color.rgb = rgb(WHITE if r == 0 else val.get("c", INK))
    tbl = t._tbl
    tblPr = tbl.tblPr
    tblPr.set("firstRow", "1")
    tblPr.set("bandRow", "0")
    return t


def notes(slide, s):
    slide.notes_slide.notes_text_frame.text = s


def header(slide, n, title):
    set_runs(shape(slide, "object 6").text_frame, [title.upper()])
    num = shape(slide, "object 8")
    set_runs(num.text_frame, [str(n)])
    num.left, num.width = Inches(0.62), Inches(0.36)   # template box only fits one digit
    num.text_frame.word_wrap = False
    num.text_frame.paragraphs[0].alignment = PP_ALIGN.RIGHT
    set_runs(shape(slide, "object 9").text_frame, [FOOTER])
    remove(shape(slide, "object 5"))   # template body text


# ------------------------------------------------------------------ slides
def title_slide(s):
    set_runs(shape(s, "object 4").text_frame, ["Sentiment Analysis — Final Year Project"])
    tf = shape(s, "object 5").text_frame
    paras = tf.paragraphs
    paras[1].runs[0].text = "“Sentari: An Earnings-Call & Filings Intelligence"
    for r in paras[1].runs[1:]:
        r._r.getparent().remove(r._r)
    # second title line, same formatting as the first
    new = copy.deepcopy(paras[1]._p)
    paras[1]._p.addnext(new)
    tf.paragraphs[2].runs[0].text = "Platform for Retail Investors”"
    last = tf.paragraphs[-1]
    last.runs[0].text = "Roll No.\tName of Student"
    for r in last.runs[1:]:
        r._r.getparent().remove(r._r)
    for name, val in (("object 8", "Nishant Narudkar"), ("object 9", "23AM1031")):
        sh = shape(s, name)
        set_runs(sh.text_frame, [val])
        sh.top = Inches(4.32)   # the two-line project title pushes the header row down
    notes(s, "Sentari: aspect-level sentiment on earnings calls and filings, with grounded multi-agent briefs. "
             "Research and decision-support only - not investment advice.")


def outline(s):
    header(s, 2, "Outline")
    items = ["Problem & Objectives", "System Architecture", "Aspect-Based Sentiment Pipeline",
             "Model Ladder & Lexicon Failure", "Grounded Multi-Agent Briefs", "Dashboard on Real Data",
             "Real-Data Pilot & Signal Study", "Conclusion & Future Work", "References"]
    for i, item in enumerate(items):
        col, row = divmod(i, 5)
        x, y = 0.75 + col * 4.55, 1.62 + row * 0.86
        c = box(s, x, y, 0.56, 0.56, fill=MAROON, shape_type=MSO_SHAPE.OVAL)
        box_text(c, [f"{i + 1:02d}"], size=15, color=WHITE, bold=True, font=SANS)
        text(s, x + 0.72, y + 0.02, 3.6, 0.54, [item], size=18, anchor=MSO_ANCHOR.MIDDLE)
    tag = box(s, 5.3, 5.02, 4.0, 0.95, fill=ROSE)
    box_text(tag, [{"t": "Sentari", "b": True, "c": MAROON, "s": 20},
                   {"t": "sentiment × aspects × grounded agents", "s": 14, "c": GREY}], font=SERIF)
    notes(s, "Nine sections; the last content slide summarises limitations honestly.")


def problem(s):
    header(s, 3, "Problem & Objectives")
    text(s, 0.5, 1.4, 4.45, 0.4, [{"t": "The problem", "b": True, "c": MAROON, "s": 20}])
    text(s, 0.5, 1.85, 4.45, 2.6, [
        {"t": "A retail investor following 15–20 stocks cannot read every earnings call (10,000+ words each) and 10-K/10-Q filing.", "bullet": True},
        {"t": "Document-level “positive / negative” scores miss what matters: softer guidance, margin pressure, hedging in the Q&A.", "bullet": True},
        {"t": "General sentiment lexicons misread finance: “costs fell” is good news; “liabilities decreased” is not negative.", "bullet": True},
    ], size=15, space_after=8)
    q = box(s, 0.5, 4.6, 4.45, 1.35, fill=ROSE)
    box_text(q, [{"t": "Core question", "b": True, "c": MAROON, "s": 15},
                 {"t": "Can we measure what management says about each financial aspect — and trace every claim to its source sentence?", "s": 14}],
             align=PP_ALIGN.LEFT)
    text(s, 5.3, 1.4, 4.2, 0.4, [{"t": "Objectives", "b": True, "c": MAROON, "s": 20}])
    goals = [("G1", "Aspect-level sentiment on 6 aspects: guidance, margins, demand, litigation, management tone, liquidity"),
             ("G2", "Show empirically where general lexicons fail on financial language"),
             ("G3", "Bull / bear / skeptic / judge agents whose every claim is grounded and cited"),
             ("G4", "A working service: ingestion, storage, dashboard, digest, drift monitoring"),
             ("G5", "An honest evaluation — including null results")]
    for i, (g, desc) in enumerate(goals):
        y = 1.88 + i * 0.83
        chip = box(s, 5.3, y + 0.08, 0.62, 0.42, fill=MAROON)
        box_text(chip, [g], size=13, color=WHITE, bold=True, font=SANS)
        text(s, 6.05, y, 3.5, 0.78, [desc], size=13, anchor=MSO_ANCHOR.MIDDLE)
    notes(s, "Scope: US and NSE/BSE listed companies, daily batch pipeline. Out of scope: real-time trading, trade "
             "execution, any guarantee of predictive accuracy.")


def architecture(s):
    header(s, 4, "System Architecture")
    picture(s, ASSETS / "arch.png", 0.45, 1.42, w=9.1, border=False)
    text(s, 0.5, 3.78, 4, 0.35, [{"t": "Technology stack", "b": True, "c": MAROON, "s": 16}])
    stack = ["Python 3.13", "FastAPI", "spaCy", "scikit-learn", "PyTorch", "Hugging Face (FinBERT)", "LangGraph",
             "SQLAlchemy · SQLite / PostgreSQL", "MLflow · DagsHub", "DuckDB", "Next.js 16", "Docker · Cloud Run"]
    x, y = 0.5, 4.2
    for item in stack:
        w = 0.28 + 0.085 * len(item)
        if x + w > 9.5:
            x, y = 0.5, y + 0.47
        chip = box(s, x, y, w, 0.36, fill=LIGHT, line="D9D9D9")
        box_text(chip, [item], size=11, font=SANS)
        x += w + 0.12
    facts = [("Idempotent daily run", "re-runs never duplicate data"), ("Every claim traceable", "brief → cited sentence → model"),
             ("80 automated tests", "fully offline, ~30 s")]
    for i, (a, b) in enumerate(facts):
        f = box(s, 0.5 + i * 3.05, 5.28, 2.9, 0.72, fill=ROSE)
        box_text(f, [{"t": a, "b": True, "c": MAROON, "s": 13}, {"t": b, "s": 11, "c": GREY}])
    notes(s, "Daily pipeline: ingest -> score -> briefs -> drift -> digest (POST /run/daily). The registry decides "
             "which sentiment model serves. Docker/Cloud Run files are written but not yet deployed.")


def pipeline(s):
    header(s, 5, "Aspect-Based Sentiment Pipeline")
    steps = ["Clean &\ndeduplicate", "Split speakers &\nprepared vs Q&A", "Find aspects\n(rules + spaCy)",
             "Negation &\nhedge handling", "Score each\naspect (−1…+1)"]
    for i, st in enumerate(steps):
        c = box(s, 0.45 + i * 1.8, 1.45, 1.85, 0.95, fill=MAROON if i % 2 == 0 else "B8475A", shape_type=MSO_SHAPE.CHEVRON)
        c.adjustments[0] = 0.28
        box_text(c, [{"t": ln, "s": 11} for ln in st.split("\n")], color=WHITE, bold=True, font=SANS)
    aspects = [("Guidance", "outlook, forecasts, targets"), ("Margins", "profitability, costs, pricing"),
               ("Demand", "orders, volumes, backlog"), ("Litigation", "lawsuits, regulation"),
               ("Management tone", "confidence vs caution"), ("Liquidity", "cash, debt, covenants")]
    for i, (a, d) in enumerate(aspects):
        col, row = i % 3, i // 3
        b = box(s, 0.5 + col * 3.05, 2.58 + row * 0.6, 2.9, 0.52, fill=ROSE)
        box_text(b, [{"t": a, "b": True, "c": MAROON, "s": 13}, {"t": d, "s": 10.5, "c": GREY}])
    text(s, 0.5, 3.82, 9, 0.35, [{"t": "Worked example — the same sentences scored by two models", "b": True, "c": MAROON, "s": 15}])
    rows = [["Sentence", "Aspect", "Rules (LM)", "FinBERT"],
            ["Gross margin expanded 180 basis points on favorable mix.", "margins", "+0.90", "+0.99"],
            ["Demand held up in automation, but aerospace orders declined.", "demand", "0.00", "0.00"],
            ["We are lowering our full-year guidance.", "guidance", "−0.50", "−1.00"],
            ["We repaid 200 million dollars of debt and our leverage ratio improved.", "liquidity", "+0.40", "+0.99"],
            ["We are unable to quantify the litigation exposure.", "litigation", "−0.50", "−1.00"]]
    for r in rows[1:]:
        for j in (2, 3):
            v = r[j]
            r[j] = {"t": v, "c": GREEN if v.startswith("+") else MAROON if v.startswith("−") else GREY, "b": True}
    table(s, 0.5, 4.2, 9.0, [5.6, 1.2, 1.1, 1.1], rows, size=11, row_h=0.29)
    notes(s, "Mixed sentence: one positive and one negative demand clause average to neutral - a known simplification. "
             "Scores from `python -m absa_service.cli analyze` with lm_directional (official Loughran-McDonald "
             "dictionary) and fine-tuned FinBERT.")


def models(s):
    header(s, 6, "Model Ladder & Lexicon Failure")
    ladder = [("SentiWordNet", 0.490), ("Decision Tree", 0.519), ("Loughran-McDonald", 0.599), ("FinBERT zero-shot", 0.601),
              ("BiLSTM", 0.607), ("VADER", 0.647), ("CNN", 0.739), ("Naive Bayes", 0.743),
              ("LM + directional rules", 0.805), ("FinBERT fine-tuned", 0.938)]
    cd = CategoryChartData()
    cd.categories = [n for n, _ in ladder]
    cd.add_series("Macro-F1", [v for _, v in ladder])
    gf = s.shapes.add_chart(XL_CHART_TYPE.BAR_CLUSTERED, Inches(0.4), Inches(1.4), Inches(5.35), Inches(4.35), cd)
    ch = gf.chart
    ch.has_legend = False
    ch.has_title = True
    ch.chart_title.text_frame.text = "Macro-F1 on 94 test sentences"
    tr = ch.chart_title.text_frame.paragraphs[0].runs[0]
    tr.font.size, tr.font.bold, tr.font.name, tr.font.color.rgb = Pt(13), True, SANS, rgb(INK)
    ch.font.name, ch.font.size = SANS, Pt(10.5)
    plot = ch.plots[0]
    plot.gap_width = 45
    plot.has_data_labels = True
    dl = plot.data_labels
    dl.number_format, dl.number_format_is_linked = "0.000", False
    dl.position = XL_LABEL_POSITION.OUTSIDE_END
    dl.font.size = Pt(10)
    ser = plot.series[0]
    for i, (n, _) in enumerate(ladder):
        pt = ser.points[i]
        pt.format.fill.solid()
        pt.format.fill.fore_color.rgb = rgb(MAROON if n == "FinBERT fine-tuned" else "B8475A" if "LM +" in n else "BFBFBF")
    va = ch.value_axis
    va.minimum_scale, va.maximum_scale = 0, 1.0
    va.has_major_gridlines = False
    va.visible = False
    ch.category_axis.tick_labels.font.size = Pt(10.5)
    ch.category_axis.format.line.color.rgb = rgb("BFBFBF")

    text(s, 6.0, 1.4, 3.55, 0.4, [{"t": "Error on “trap” sentences", "b": True, "c": MAROON, "s": 16}])
    text(s, 6.0, 1.78, 3.55, 0.5, ["26 sentences where finance inverts everyday polarity"], size=12, color=GREY)
    stats = [("61.5%", "VADER (general lexicon)"), ("61.5%", "Loughran-McDonald word counts"), ("11.5%", "FinBERT fine-tuned")]
    for i, (v, lab) in enumerate(stats):
        y = 2.35 + i * 0.88
        text(s, 6.0, y, 1.55, 0.7, [{"t": v, "b": True, "s": 30, "c": MAROON if i < 2 else GREEN, "font": SANS}], anchor=MSO_ANCHOR.MIDDLE)
        text(s, 7.6, y, 1.95, 0.7, [lab], size=12.5, anchor=MSO_ANCHOR.MIDDLE)
    ex = box(s, 6.0, 5.0, 3.55, 0.78, fill=ROSE)
    box_text(ex, [{"t": "“Customer churn decreased to its lowest level in three years.”", "s": 11, "i": True},
                  {"t": "VADER: negative   ·   truth: positive", "s": 11, "b": True, "c": MAROON}], align=PP_ALIGN.LEFT)
    text(s, 0.45, 5.8, 9.1, 0.32, [{"t": "Test set is small and self-written; trained models learn from template labels, so these scores are optimistic. "
                                        "A 300-sentence human-labelled set from real calls is in progress.", "s": 10.5, "c": GREY, "i": True}])
    notes(s, "Lexicon rows use the official Loughran-McDonald dictionary (1993-2025). lm_directional's rules were written "
             "with sight of the test set, so 0.805 is optimistic. Source: results/model_ladder.json and the official-"
             "dictionary re-evaluation.")


def agents(s):
    header(s, 7, "Grounded Multi-Agent Briefs")
    picture(s, ASSETS / "agents.png", 0.5, 1.42, w=9.0, border=False)
    cd = CategoryChartData()
    cd.categories = ["Number changed", "Citation removed", "Wrong source", "Fabricated", "Polarity flipped"]
    cd.add_series("Heuristic skeptic", (100, 100, 100, 100, 22.7))
    cd.add_series("Skeptic + NLI model", (100, 100, 100, 100, 100))
    gf = s.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(0.4), Inches(2.95), Inches(5.6), Inches(3.05), cd)
    ch = gf.chart
    ch.font.name, ch.font.size = SANS, Pt(10)
    ch.has_title = True
    ch.chart_title.text_frame.text = "Corrupted claims caught (%)"
    tr = ch.chart_title.text_frame.paragraphs[0].runs[0]
    tr.font.size, tr.font.bold, tr.font.color.rgb = Pt(12), True, rgb(INK)
    ch.has_legend = True
    ch.legend.position = XL_LEGEND_POSITION.BOTTOM
    ch.legend.include_in_layout = False
    ch.legend.font.size = Pt(10)
    plot = ch.plots[0]
    plot.gap_width, plot.overlap = 60, -10
    plot.has_data_labels = True
    plot.data_labels.number_format, plot.data_labels.number_format_is_linked = "0", False
    plot.data_labels.position = XL_LABEL_POSITION.OUTSIDE_END
    plot.data_labels.font.size = Pt(9)
    for ser, col in zip(plot.series, ("BFBFBF", MAROON)):
        ser.format.fill.solid()
        ser.format.fill.fore_color.rgb = rgb(col)
    ch.value_axis.maximum_scale, ch.value_axis.minimum_scale = 115, 0
    ch.value_axis.visible = False
    ch.value_axis.has_major_gridlines = False
    ch.category_axis.tick_labels.font.size = Pt(9.5)
    text(s, 6.2, 3.0, 3.35, 3.0, [
        {"t": "Only claims the Skeptic marks supported reach the brief.", "bullet": True},
        {"t": "Every brief sentence cites its source sentence; the full audit trail is stored.", "bullet": True},
        {"t": "Faithful claims wrongly rejected: 0 of 43.", "bullet": True},
        {"t": "The NLI model is needed: word checks miss flipped polarity.", "bullet": True},
        {"t": "LLM optional (Claude API); runs offline by default.", "bullet": True},
    ], size=13, space_after=7)
    notes(s, "Adversarial audit: 43 faithful claims corrupted five ways. 'Caught' = rejected or flagged unverified. "
             "Synthetic corruptions of verbatim claims are the easy case; a human audit of LLM-written claims is not yet done.")


def dashboard(s):
    header(s, 8, "Dashboard on Real Data")
    for i, (img, cap) in enumerate([("pilot_ba_trajectories_crop.png", "Six aspect trajectories for Boeing, 2015–2025 (prepared vs Q&A lines)"),
                                    ("pilot_ba_brief_crop.png", "Boeing brief (Oct 2024 – Apr 2025): every claim links to its source")]):
        x = 0.45 + i * 4.62
        picture(s, ASSETS / img, x, 1.42, w=4.45)
        text(s, x, 3.85, 4.45, 0.45, [cap], size=11, color=GREY, align=PP_ALIGN.CENTER)
    feats = [("Watchlist & top moves", "latest call per company, largest aspect changes"),
             ("Drill-down", "chart point → sentences → source in context → model verdict"),
             ("Monitoring", "quarterly drift (PSI), model registry, daily digest")]
    for i, (a, b) in enumerate(feats):
        f = box(s, 0.45 + i * 3.07, 4.55, 2.95, 1.1, fill=ROSE)
        box_text(f, [{"t": a, "b": True, "c": MAROON, "s": 13}, {"t": b, "s": 11, "c": GREY}])
    notes(s, "Screenshots from the real 10-company pilot (not the synthetic demo data). Next.js 16 dashboard over the "
             "FastAPI read API; dark mode and phone widths supported.")


def pilot(s):
    header(s, 9, "Real-Data Pilot & Signal Study")
    stats = [("10", "companies, 10 sectors"), ("414", "earnings calls, 2015–2025"), ("206k", "sentences parsed"),
             ("45.7k", "aspect scores")]
    for i, (v, lab) in enumerate(stats):
        b = box(s, 0.45 + i * 2.3, 1.42, 2.15, 1.0, fill=ROSE)
        box_text(b, [{"t": v, "b": True, "c": MAROON, "s": 26, "font": SANS}, {"t": lab, "s": 11, "c": GREY}])
    text(s, 0.5, 2.6, 4.3, 0.38, [{"t": "What real calls showed", "b": True, "c": MAROON, "s": 16}])
    text(s, 0.5, 3.0, 4.3, 2.9, [
        {"t": "The two best models agree on only 65% of real aspect mentions (7.7% opposite polarity).", "bullet": True},
        {"t": "“Management sounds weaker in Q&A”: 64% of calls with the rule model, 49% with FinBERT — not robust.", "bullet": True},
        {"t": "Both agree only that demand and liquidity are discussed slightly more negatively in Q&A.", "bullet": True},
    ], size=13, space_after=8)
    src = box(s, 0.5, 5.0, 4.3, 0.98, fill=LIGHT)
    box_text(src, [{"t": "Data: kurry/sp500_earnings_transcripts (Hugging Face, pinned) · prices: Alpaca market data", "s": 10.5, "c": GREY},
                   {"t": "Preliminary: a 300-sentence human-labelled set will decide which model to trust.", "s": 10.5, "b": True, "c": MAROON}],
             align=PP_ALIGN.LEFT)
    text(s, 5.05, 2.6, 4.5, 0.38, [{"t": "Does sentiment move with returns?", "b": True, "c": MAROON, "s": 16}])
    rows = [["Predictor (374 calls)", "Days 0–4 ρ", "p"],
            ["Q&A − prepared gap (FinBERT)", "−0.03", "0.58"],
            ["Q&A − prepared gap (rules)", "−0.07", "0.19"],
            [{"t": "Whole-call sentiment (FinBERT)", "b": True}, {"t": "+0.17", "b": True, "c": GREEN}, {"t": "0.001", "b": True}],
            ["Whole-call sentiment (rules)", {"t": "+0.15", "c": GREEN}, "0.004"],
            ["Drift, days 2–11 (both)", "≈ 0", "n.s."]]
    table(s, 5.05, 3.0, 4.5, [2.7, 1.0, 0.8], rows, size=11, row_h=0.36)
    text(s, 5.05, 5.25, 4.5, 0.75, [{"t": "Returns are market-adjusted (Alpaca prices), with company fixed effects and analyst-EPS controls. "
                                          "The Q&A gap is a null result; whole-call sentiment co-moves with the reaction but does not predict later drift.",
                                     "s": 10.5, "c": GREY, "i": True}])
    notes(s, "Pilot data: kurry/sp500_earnings_transcripts (Hugging Face, pinned revision). Scores: lm_directional and "
             "finbert_ft. Study is PRELIMINARY until the human-labelled real gold set picks the model. Bonferroni over 6 "
             "tests: no Q&A-gap coefficient survives. Source: results/pilot/signal_validity_preliminary.json")


def conclusion(s):
    header(s, 10, "Conclusion & Future Work")
    cols = [("Conclusion", [
                "Aspect-level sentiment and grounded, cited briefs work end-to-end on 414 real earnings calls.",
                "General lexicons fail on finance (61.5% error on trap sentences); domain models fix most of it.",
                "The Skeptic stops fabricated numbers and citations; NLI is needed for flipped polarity.",
                "The Q&A-gap signal is a null result — reported honestly."]),
            ("Limitations", [
                "Test set small and self-written; models trained on template labels.",
                "Models disagree on 35% of real sentences — no model yet validated on real text.",
                "Rule-based aspect detection can mis-file sentences.",
                "Not yet deployed; no LLM-written briefs audited by humans."]),
            ("Future work", [
                "Finish the 300-sentence human-labelled set; pick the model on evidence.",
                "Re-run the signal study with the validated model.",
                "Learned aspect tagger and calibrated confidence.",
                "Deploy on Cloud Run; add NSE/BSE transcripts."])]
    for i, (h, items) in enumerate(cols):
        x = 0.45 + i * 3.07
        head = box(s, x, 1.42, 2.95, 0.5, fill=MAROON)
        box_text(head, [h], size=15, color=WHITE, bold=True)
        box(s, x, 1.97, 2.95, 4.0, fill=ROSE if i == 0 else LIGHT)
        text(s, x + 0.08, 2.08, 2.8, 3.85, [{"t": t, "bullet": True} for t in items], size=14, space_after=10)
    notes(s, "Research and decision-support only; nothing here is investment advice or a trading signal.")


def references(s):
    header(s, 11, "References")
    refs = [
        "T. Loughran and B. McDonald, “When is a liability not a liability? Textual analysis, dictionaries, and 10-Ks,” J. Finance, 66(1), 2011.",
        "C. J. Hutto and E. Gilbert, “VADER: A parsimonious rule-based model for sentiment analysis of social media text,” ICWSM, 2014.",
        "S. Baccianella, A. Esuli and F. Sebastiani, “SentiWordNet 3.0,” LREC, 2010.",
        "D. Araci, “FinBERT: Financial sentiment analysis with pre-trained language models,” arXiv:1908.10063, 2019.",
        "J. Devlin et al., “BERT: Pre-training of deep bidirectional transformers for language understanding,” NAACL, 2019.",
        "C. Sun, L. Huang and X. Qiu, “Utilizing BERT for aspect-based sentiment analysis via constructing auxiliary sentence,” NAACL, 2019.",
        "M. Pontiki et al., “SemEval-2014 Task 4: Aspect based sentiment analysis,” SemEval, 2014.",
        "Y. Kim, “Convolutional neural networks for sentence classification,” EMNLP, 2014.",
        "S. Hochreiter and J. Schmidhuber, “Long short-term memory,” Neural Computation, 9(8), 1997.",
        "Z. Ji et al., “Survey of hallucination in natural language generation,” ACM Computing Surveys, 55(12), 2023.",
        "N. Reimers and I. Gurevych, “Sentence-BERT: Sentence embeddings using Siamese BERT-networks,” EMNLP, 2019.",
        "kurry, “sp500_earnings_transcripts” dataset, Hugging Face, 2025 (MIT licence; research use).",
        "Loughran-McDonald Master Dictionary (1993–2025), Notre Dame Software Repository for Accounting and Finance.",
        "Alpaca Market Data API; LangGraph, FastAPI, spaCy and MLflow documentation.",
    ]
    half = 7
    for c in range(2):
        chunk = refs[c * half:(c + 1) * half]
        text(s, 0.45 + c * 4.6, 1.42, 4.45, 4.6,
             [{"runs": [(f"[{c * half + i + 1}] ", {"b": True, "c": MAROON}), (r, {})]} for i, r in enumerate(chunk)],
             size=12, space_after=9)
    notes(s, "Full citations and tool versions are in the project repository README and requirements.")


def crop_screens():
    from PIL import Image
    for src, box_px in (("pilot_ba_trajectories.png", (205, 100, 1835, 955)), ("pilot_ba_brief.png", (205, 100, 1835, 955))):
        Image.open(ASSETS / src).crop(box_px).save(ASSETS / src.replace(".png", "_crop.png"))


def main(base: str):
    crop_screens()
    prs = Presentation(base)
    slides = list(prs.slides)
    by_file = {sl.part.partname.split("/")[-1]: sl for sl in slides}
    title, thanks = by_file["slide1.xml"], by_file["slide15.xml"]
    content = [by_file["slide3.xml"]] + [by_file[f"slide{n}.xml"] for n in range(16, 25)]
    assert len(content) == 10, len(content)

    # order: title, 10 content slides, thank-you; drop the rest
    keep = [title] + content + [thanks]
    sldIdLst = prs.slides._sldIdLst
    el_for_part = {prs.part.related_part(el.rId): el for el in sldIdLst}
    for el in list(sldIdLst):
        sldIdLst.remove(el)
    for sl in keep:
        sldIdLst.append(el_for_part[sl.part])
    for sl in slides:
        if sl not in keep:
            prs.part.drop_rel(el_for_part[sl.part].rId)

    title_slide(title)
    for fn, sl in zip((outline, problem, architecture, pipeline, models, agents, dashboard, pilot, conclusion, references), content):
        fn(sl)
    notes(thanks, "Questions.")
    prs.save(OUT)
    add_default_content_type(OUT, "jpg", "image/jpeg")
    print("wrote", OUT)


def add_default_content_type(path: Path, ext: str, ctype: str) -> None:
    """python-pptx declares the template's .jpg media per part; restore the extension-level Default the template had."""
    import zipfile
    with zipfile.ZipFile(path) as zin:
        items = [(i, zin.read(i.filename)) for i in zin.infolist()]
    tmp = path.with_suffix(".tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for info, data in items:
            if info.filename == "[Content_Types].xml" and f'Extension="{ext}"' not in data.decode("utf-8"):
                data = data.decode("utf-8").replace("<Default ", f'<Default Extension="{ext}" ContentType="{ctype}"/><Default ', 1).encode("utf-8")
            zout.writestr(info, data)
    tmp.replace(path)


if __name__ == "__main__":
    main(sys.argv[1])
