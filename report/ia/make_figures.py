"""Pastel, TikZ-style flow diagrams for the IA-format report -> report/ia/figures/. Needs Graphviz `dot`."""
import subprocess
from pathlib import Path

OUT = Path(__file__).resolve().parent / "figures"
BLUE, ORANGE, PURPLE, GREEN, RED, GREY = ("#E8F0FB", "#7A9CC6"), ("#FFF1DC", "#D9A55B"), ("#F2E8F8", "#A98BC2"), \
    ("#E8F5EA", "#7FB38A"), ("#FBEAEC", "#D48A93"), ("#F4F4F4", "#9E9E9E")
BASE = ('graph [fontname="Times New Roman," bgcolor="white" pad=0.15]; '
        'node [shape=box style="rounded,filled" fontname="Times New Roman," fontsize=13 penwidth=1.1 margin="0.2,0.07"]; '
        'edge [color="#333333" arrowsize=0.7 penwidth=1.0 fontname="Times New Roman," fontsize=11];')


def n(name, label, col, bold_first=True, **kw):
    lines = label.replace("&", "&amp;").split("\n")
    head = f"<B>{lines[0]}</B>" if bold_first else lines[0]
    rest = "".join(f'<BR/><FONT POINT-SIZE="11">{l}</FONT>' for l in lines[1:])
    extra = " ".join(f'{k}="{v}"' for k, v in kw.items())
    return f'{name} [label=<{head}{rest}> fillcolor="{col[0]}" color="{col[1]}" {extra}];'


def dot(name, body):
    OUT.mkdir(parents=True, exist_ok=True)
    src = f"digraph G {{ {BASE} {body} }}"
    subprocess.run(["dot", "-Tpng", "-Gdpi=250", "-o", str(OUT / f"{name}.png")], input=src.encode(), check=True)


dot("fig1_architecture", "rankdir=TB; nodesep=0.3; ranksep=0.32; " + " ".join([
    n("sched", "Daily Scheduler\n(Cloud Scheduler / cron: POST /run/daily)", BLUE),
    n("ing", "Ingestion Service\n(transcripts, 10-K/10-Q MD&A, news; dedupe + chunk)", ORANGE),
    n("absa", "ABSA Service\n(aspect extraction + sentiment model ladder)", PURPLE),
    n("reg", "Model Registry\n(MLflow: serving model)", GREY),
    n("db", "Storage Layer\n(documents, chunks, aspect scores, briefs, traces)", GREY, shape="cylinder"),
    n("ext", "Extractor Agent\n(top-k evidence per aspect)", GREEN),
    n("bull", "Bull Agent\n(supportive claims)", GREEN), n("bear", "Bear Agent\n(concerning claims)", RED),
    n("skp", "Skeptic Agent\n(grounding gate)", ORANGE), n("jdg", "Judge Agent\n(brief + confidence)", PURPLE),
    n("out", "Delivery Layer\n(dashboard, daily digest, drift monitor)", BLUE),
    "{ rank=same; absa; reg; } { rank=same; bull; bear; }",
    "sched -> ing -> absa -> db -> ext; reg -> absa [style=dashed]; ext -> bull; ext -> bear; bull -> skp; bear -> skp;",
    "skp -> jdg -> out;",
]))

dot("fig2_workflow", "rankdir=TB; nodesep=0.35; ranksep=0.3; " + " ".join([
    n("a", "Scheduled daily run", BLUE, bold_first=False),
    n("b", "Fetch documents for the watchlist", BLUE, bold_first=False),
    n("c", "Already ingested?\n(content hash)", ORANGE, shape="diamond", style="filled"),
    n("skip", "Skip (idempotent)", GREY, bold_first=False),
    n("d", "Split speakers, prepared vs Q&A, sentences", BLUE, bold_first=False),
    n("e", "Extract aspects + score with serving model", BLUE, bold_first=False),
    n("f", "Inputs changed\nsince last brief?", ORANGE, shape="diamond", style="filled"),
    n("cache", "Reuse cached brief", GREY, bold_first=False),
    n("g", "Run agents: extract, argue, verify, judge", GREEN, bold_first=False),
    n("h", "Drift check + daily digest + dashboard", PURPLE, bold_first=False),
    "{ rank=same; c; skip; } { rank=same; f; cache; }",
    'a -> b -> c; c -> skip [label=" yes"]; c -> d [label=" no"]; d -> e -> f; f -> cache [label=" no"];',
    'f -> g [label=" yes"]; g -> h; cache -> h;',
]))

dot("fig3_grounding", "rankdir=TB; nodesep=0.45; ranksep=0.28; " + " ".join([
    n("cl", "Bull / Bear claim\n+ cited sentence IDs", GREEN),
    n("c1", "1. Citation exists?", ORANGE, bold_first=False),
    n("c2", "2. Numbers appear in source?", ORANGE, bold_first=False),
    n("c3", "3. Similar and overlapping?", ORANGE, bold_first=False),
    n("c4", "4. NLI entailment?", ORANGE, bold_first=False),
    n("sup", "Supported\n(enters the brief)", GREEN), n("unv", "Unverified\n(shown, flagged)", BLUE),
    n("rej", "Rejected\n(dropped, kept in audit trail)", RED),
    "{ rank=same; c3; unv; } { rank=same; c4; rej; }",
    'cl -> c1 -> c2 -> c3 -> c4; c4 -> sup [label=" passes"]; c3 -> unv [label=" weak"];',
    'c4 -> rej [label=" contradicted"]; c1 -> rej [label=" no" constraint=false]; c2 -> rej [label=" no" constraint=false];',
]))
print(sorted(p.name for p in OUT.glob("fig*.png")))
