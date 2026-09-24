"""Generate report figures (charts + diagrams) from results/*.json into report/figures/.

    python report/tools/make_figures.py
Diagrams need Graphviz `dot` on PATH.
"""
from __future__ import annotations

import json
import subprocess
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
RES = ROOT / "results"
OUT = ROOT / "report" / "figures"
OUT.mkdir(parents=True, exist_ok=True)

INK, MUTED, GRID = "#1c1c1a", "#6b6b66", "#e3e2dc"
BLUE, GREEN, RED, GREY, AMBER = "#2f5d8a", "#1f8a5b", "#c2413b", "#9a998f", "#b7791f"
RUNG_COLOR = {"Lexicon": "#8fa9c4", "Lexicon + rules": "#5d82a8", "Classical ML": "#b59a6d",
              "Deep learning": "#7a9e7e", "Transformer": BLUE}
RUNG = {"vader": "Lexicon", "sentiwordnet": "Lexicon", "lm_lexicon": "Lexicon", "lm_directional": "Lexicon + rules",
        "nb_tfidf": "Classical ML", "dt_tfidf": "Classical ML", "cnn": "Deep learning", "lstm": "Deep learning",
        "finbert_zeroshot": "Transformer", "finbert_ft": "Transformer"}
PRETTY = {"vader": "VADER", "sentiwordnet": "SentiWordNet", "lm_lexicon": "Loughran-McDonald",
          "lm_directional": "LM + directional rules", "nb_tfidf": "Naive Bayes", "dt_tfidf": "Decision Tree",
          "cnn": "CNN", "lstm": "BiLSTM", "finbert_zeroshot": "FinBERT zero-shot", "finbert_ft": "FinBERT fine-tuned"}
LABELS = ["negative", "neutral", "positive"]

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.edgecolor": GRID, "axes.labelcolor": INK,
                     "xtick.color": MUTED, "ytick.color": MUTED, "axes.spines.top": False,
                     "axes.spines.right": False, "savefig.dpi": 200, "savefig.bbox": "tight"})


def load(name):
    return json.loads((RES / name).read_text(encoding="utf-8"))


def ladder_chart():
    lad = {k: v for k, v in load("model_ladder.json").items() if not k.startswith("_")}
    names = sorted(lad, key=lambda n: lad[n]["gold"]["macro_f1"])
    f1 = [lad[n]["gold"]["macro_f1"] for n in names]
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    bars = ax.barh([PRETTY[n] for n in names], f1, color=[RUNG_COLOR[RUNG[n]] for n in names], height=0.62)
    for b, v in zip(bars, f1):
        ax.text(v + 0.01, b.get_y() + b.get_height() / 2, f"{v:.3f}", va="center", fontsize=9, color=INK)
    ax.set_xlim(0, 1.05)
    ax.set_xlabel("Macro-F1 on the 94-sentence gold set")
    ax.xaxis.grid(True, color=GRID); ax.set_axisbelow(True)
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in RUNG_COLOR.values()]
    ax.legend(handles, RUNG_COLOR.keys(), loc="lower right", frameon=False, fontsize=8.5)
    ax.set_title("Model ladder: macro-F1 by model", loc="left", fontsize=11.5, color=INK)
    fig.savefig(OUT / "fig_ladder_f1.png"); plt.close(fig)


def trap_chart():
    lf = load("lexicon_failures.json")["models"]
    order = ["vader", "sentiwordnet", "lm_lexicon", "lm_directional", "nb_tfidf", "cnn", "finbert_ft"]
    x = np.arange(len(order)); w = 0.38
    trap = [lf[n]["error_rate_trap"] * 100 for n in order]
    non = [lf[n]["error_rate_nontrap"] * 100 for n in order]
    fig, ax = plt.subplots(figsize=(7.2, 3.9))
    b1 = ax.bar(x - w / 2, trap, w, color=RED, label="Trap sentences (n=26)")
    b2 = ax.bar(x + w / 2, non, w, color=GREY, label="Other sentences (n=68)")
    for bars in (b1, b2):
        for b in bars:
            ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 1, f"{b.get_height():.0f}", ha="center",
                    fontsize=8, color=INK)
    short = {"sentiwordnet": "Senti-\nWordNet", "lm_lexicon": "Loughran-\nMcDonald", "lm_directional": "LM +\ndirectional",
             "nb_tfidf": "Naive\nBayes", "finbert_ft": "FinBERT\nfine-tuned"}
    ax.set_xticks(x, [short.get(n, PRETTY[n]) for n in order], fontsize=8.5)
    ax.set_ylabel("Error rate (%)"); ax.set_ylim(0, 85)
    ax.yaxis.grid(True, color=GRID); ax.set_axisbelow(True)
    ax.legend(frameon=False, fontsize=8.5)
    ax.set_title("Lexicon failure: error on finance-inverted (trap) sentences", loc="left", fontsize=11.5, color=INK)
    fig.savefig(OUT / "fig_lexicon_traps.png"); plt.close(fig)


def grounding_chart():
    h, n = load("grounding_adversarial_heuristic.json"), load("grounding_adversarial_nli.json")
    kinds = ["number_swap", "no_citation", "wrong_citation", "fabrication", "polarity_flip"]
    pretty = ["Number\nswapped", "Citation\nremoved", "Wrong chunk\ncited", "Fabricated\nclaim", "Polarity\nflipped"]
    x = np.arange(len(kinds)); w = 0.38
    fig, ax = plt.subplots(figsize=(7.2, 3.7))
    for off, data, col, lab in ((-w / 2, h, GREY, "Heuristic skeptic"), (w / 2, n, BLUE, "Skeptic + NLI model")):
        vals = [data[k]["catch_rate"] * 100 for k in kinds]
        bars = ax.bar(x + off, vals, w, color=col, label=lab)
        for b, k in zip(bars, kinds):
            ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 1.5, f"{b.get_height():.0f}%", ha="center",
                    fontsize=8, color=INK)
    ax.set_xticks(x, pretty, fontsize=8.5)
    ax.set_ylim(0, 112); ax.set_ylabel("Caught (rejected or flagged), %")
    ax.yaxis.grid(True, color=GRID); ax.set_axisbelow(True)
    ax.legend(frameon=False, fontsize=8.5, loc="upper center", bbox_to_anchor=(0.5, -0.17), ncol=2)
    ax.set_title("Grounding audit: skeptic catch rate by corruption type", loc="left", fontsize=11.5, color=INK)
    fig.savefig(OUT / "fig_grounding.png"); plt.close(fig)


def confusion(name, lf, lad):
    """Rebuild the confusion matrix from per-class support + the logged misclassifications."""
    support = {c: lad[name]["gold"]["per_class"][c]["support"] for c in LABELS}
    m = np.zeros((3, 3), dtype=int)
    wrong = Counter((f["gold"], f["predicted"]) for f in lf[name]["failures"])
    for (g, p), k in wrong.items():
        m[LABELS.index(g), LABELS.index(p)] += k
    for i, c in enumerate(LABELS):
        m[i, i] = support[c] - m[i].sum()
    return m


def confusion_chart():
    lf, lad = load("lexicon_failures.json")["models"], load("model_ladder.json")
    names = ["vader", "lm_directional", "finbert_ft"]
    fig, axes = plt.subplots(1, 3, figsize=(8.4, 3.0))
    for ax, name in zip(axes, names):
        m = confusion(name, lf, lad)
        ax.imshow(m, cmap="Blues", vmin=0, vmax=32)
        for i in range(3):
            for j in range(3):
                ax.text(j, i, m[i, j], ha="center", va="center", fontsize=10, color="white" if m[i, j] > 18 else INK)
        ax.set_xticks(range(3), ["neg", "neu", "pos"]); ax.set_yticks(range(3), ["neg", "neu", "pos"])
        ax.set_xlabel("predicted"); ax.set_ylabel("gold" if name == names[0] else "")
        ax.set_title(PRETTY[name], fontsize=10, color=INK)
        for s in ax.spines.values():
            s.set_visible(False)
    fig.suptitle("Confusion matrices on the gold set", x=0.02, ha="left", fontsize=11.5, color=INK)
    fig.tight_layout()
    fig.savefig(OUT / "fig_confusion.png"); plt.close(fig)


def latency_chart():
    lad = {k: v for k, v in load("model_ladder.json").items() if not k.startswith("_")}
    names = list(lad)
    fig, ax = plt.subplots(figsize=(7.2, 3.6))
    for n in names:
        g = lad[n]["gold"]
        ax.scatter(g["latency_ms_per_item"], g["macro_f1"], s=60, color=RUNG_COLOR[RUNG[n]], zorder=3)
        off, ha = {"nb_tfidf": ((-6, -12), "right"), "cnn": ((6, 4), "left")}.get(n, ((6, 3), "left"))
        ax.annotate(PRETTY[n], (g["latency_ms_per_item"], g["macro_f1"]), xytext=off, textcoords="offset points",
                    fontsize=8, color=INK, ha=ha)
    ax.set_xscale("log"); ax.set_xlabel("Inference time per sentence (ms, log scale, CPU)")
    ax.set_ylabel("Macro-F1"); ax.grid(True, color=GRID); ax.set_axisbelow(True)
    ax.set_title("Accuracy vs. cost of inference", loc="left", fontsize=11.5, color=INK)
    fig.savefig(OUT / "fig_latency.png"); plt.close(fig)


def dot(name: str, src: str):
    (OUT / f"{name}.dot").write_text(src, encoding="utf-8")
    subprocess.run(["dot", "-Tpng", "-Gdpi=200", str(OUT / f"{name}.dot"), "-o", str(OUT / f"{name}.png")], check=True)
    (OUT / f"{name}.dot").unlink()


NODE = 'node [shape=box style="rounded,filled" fontname="Helvetica" fontsize=11 color="#9aa7b4" fillcolor="#f4f6f8" penwidth=1.1];'
EDGE = 'edge [color="#6b7a89" arrowsize=0.7 fontname="Helvetica" fontsize=9 fontcolor="#6b6b66"];'


def diagrams():
    dot("fig_architecture", f"""digraph G {{ rankdir=TB; nodesep=0.45; ranksep=0.3; newrank=true; {NODE} {EDGE}
  sched [label="Scheduler (Cloud Scheduler / cron)\nPOST /run/daily" fillcolor="#fff7e6" color="#d9b877"];
  subgraph cluster_ing {{ label="Ingestion service" fontname="Helvetica" fontsize=12 style="rounded" color="#c9ced4";
    src [label="Sources: sample | SEC EDGAR MD&A | news RSS | NSE"];
    norm [label="Normalise + dedupe (content hash)\nspeakers, prepared vs Q&A, sentence chunks"]; src -> norm; }}
  subgraph cluster_absa {{ label="ABSA service (FastAPI)" fontname="Helvetica" fontsize=12 style="rounded" color="#c9ced4";
    asp [label="Aspect extraction\nrules + spaCy dependency parse, negation, hedging"];
    mdl [label="Polarity model (served from registry)\nlexicon | NB / DT | CNN / BiLSTM | FinBERT"]; asp -> mdl; }}
  subgraph cluster_ag {{ label="Agent orchestration (LangGraph)" fontname="Helvetica" fontsize=12 style="rounded" color="#c9ced4";
    ext [label="Extractor"]; bull [label="Bull" fillcolor="#e8f4ee" color="#8cc2a6"]; bear [label="Bear" fillcolor="#f8e9e8" color="#d9a19d"];
    skp [label="Skeptic (grounding gate)" fillcolor="#fff7e6" color="#d9b877"]; jdg [label="Judge: brief + confidence"];
    ext -> bull; ext -> bear; bull -> skp; bear -> skp; skp -> jdg; }}
  subgraph cluster_del {{ label="Delivery & monitoring" fontname="Helvetica" fontsize=12 style="rounded" color="#c9ced4";
    dash [label="Next.js dashboard"]; dig [label="Digest (SMTP / Slack)"]; drift [label="Drift monitor"]; }}
  db [label="SQLite / PostgreSQL\n\ndocuments\nchunks\naspect_scores\nbriefs\nagent_traces\nmodel_runs\ndrift_reports" shape=cylinder fillcolor="#eef3f8" width=1.9];
  reg [label="MLflow + model_runs\n(serving flag)" shape=cylinder fillcolor="#eef3f8"];
  {{ rank=same; mdl; reg; }} {{ rank=same; bull; bear; db; }} {{ rank=same; dash; dig; drift; }}
  sched -> src; norm -> asp [label=" new chunks"]; mdl -> ext [label=" scored evidence"];
  reg -> mdl [style=dashed label=" which model serves"];
  norm -> db [constraint=false color="#9aa7b4"]; mdl -> db [constraint=false color="#9aa7b4" label=" scores"];
  db -> ext [constraint=false color="#9aa7b4" label=" top-k"]; jdg -> db [constraint=false color="#9aa7b4" label=" brief + trace"];
  jdg -> dig [style=invis]; db -> dash [constraint=false color="#9aa7b4"]; db -> dig [constraint=false color="#9aa7b4"]; db -> drift [constraint=false color="#9aa7b4"]; }}""")

    dot("fig_agents", f"""digraph G {{ rankdir=TB; nodesep=0.35; ranksep=0.35; {NODE} {EDGE}
  in [label="ticker + date range" shape=plaintext style="" fontname="Helvetica"];
  ext [label="Extractor\ntop-k chunks per aspect and polarity\n(|score| x confidence + similarity)"];
  bull [label="Bull agent\nclaims + chunk citations" fillcolor="#e8f4ee" color="#8cc2a6"];
  bear [label="Bear agent\nclaims + chunk citations" fillcolor="#f8e9e8" color="#d9a19d"];
  skp [label="Skeptic\n1 citation exists   2 numbers in source\n3 similarity + overlap   4 entailment" fillcolor="#fff7e6" color="#d9b877"];
  jdg [label="Judge\nbrief from verified claims\nconfidence score"];
  drop [label="rejected: dropped\n(kept in audit trail)" style="rounded,dashed" color="#b0b0aa" fontcolor="#6b6b66"];
  out [label="brief (supported claims)\n+ 'unverified' list\n+ full agent_traces" shape=note fillcolor="#eef3f8"];
  {{ rank=same; bull; bear; }} {{ rank=same; jdg; drop; }}
  in -> ext; ext -> bull; ext -> bear; bull -> skp; bear -> skp;
  skp -> jdg [label=" supported /\n unverified"]; skp -> drop [label=" rejected"]; jdg -> out; }}""")

    dot("fig_schema", f"""digraph G {{ rankdir=LR; nodesep=0.25; ranksep=0.5; node [shape=plaintext fontname="Helvetica" fontsize=10]; {EDGE}
  documents [label=<<table border="0" cellborder="1" cellspacing="0" cellpadding="4" color="#9aa7b4"><tr><td bgcolor="#dfe7ef"><b>documents</b></td></tr><tr><td align="left">id, ticker, doc_type, doc_date<br align="left"/>title, source, source_url<br align="left"/>content_hash (unique)<br align="left"/></td></tr></table>>];
  chunks [label=<<table border="0" cellborder="1" cellspacing="0" cellpadding="4" color="#9aa7b4"><tr><td bgcolor="#dfe7ef"><b>chunks</b></td></tr><tr><td align="left">id, document_id, idx<br align="left"/>text, section, speaker<br align="left"/>embedding (JSON)<br align="left"/></td></tr></table>>];
  scores [label=<<table border="0" cellborder="1" cellspacing="0" cellpadding="4" color="#9aa7b4"><tr><td bgcolor="#dfe7ef"><b>aspect_scores</b></td></tr><tr><td align="left">chunk_id, aspect, polarity<br align="left"/>score, confidence<br align="left"/>model_name, model_version<br align="left"/>ticker, doc_date, section<br align="left"/></td></tr></table>>];
  briefs [label=<<table border="0" cellborder="1" cellspacing="0" cellpadding="4" color="#9aa7b4"><tr><td bgcolor="#dfe7ef"><b>briefs</b></td></tr><tr><td align="left">id, ticker, period_start/end<br align="left"/>summary, confidence, body (JSON)<br align="left"/>input_fingerprint<br align="left"/>tokens_in/out, latency_s<br align="left"/></td></tr></table>>];
  traces [label=<<table border="0" cellborder="1" cellspacing="0" cellpadding="4" color="#9aa7b4"><tr><td bgcolor="#dfe7ef"><b>agent_traces</b></td></tr><tr><td align="left">brief_id, step, agent<br align="left"/>payload (JSON)<br align="left"/></td></tr></table>>];
  runs [label=<<table border="0" cellborder="1" cellspacing="0" cellpadding="4" color="#9aa7b4"><tr><td bgcolor="#dfe7ef"><b>model_runs</b></td></tr><tr><td align="left">name, version, mlflow_run_id<br align="left"/>metrics (JSON), serving<br align="left"/></td></tr></table>>];
  drift [label=<<table border="0" cellborder="1" cellspacing="0" cellpadding="4" color="#9aa7b4"><tr><td bgcolor="#dfe7ef"><b>drift_reports</b></td></tr><tr><td align="left">ticker, week_start<br align="left"/>psi_aspect_mix, confidence_shift<br align="left"/>alert, detail (JSON)<br align="left"/></td></tr></table>>];
  documents -> chunks [label="1:n"]; chunks -> scores [label="1:n"]; briefs -> traces [label="1:n"];
  scores -> runs [style=dashed label="model_name"]; briefs -> chunks [style=dashed label="cites chunk ids"]; }}""")


if __name__ == "__main__":
    ladder_chart(); trap_chart(); grounding_chart(); confusion_chart(); latency_chart(); diagrams()
    print("\n".join(sorted(p.name for p in OUT.glob("*.png"))))
