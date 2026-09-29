"""Slide-sized Graphviz diagrams in the RAIT template palette -> presentation/assets/. Needs `dot` on PATH."""
import subprocess
from pathlib import Path

OUT = Path(__file__).resolve().parent / "assets"
MAROON, ROSE, GREY, INK = "#9F1C33", "#F6E4E7", "#F2F2F2", "#262626"
NODE = (f'node [shape=box style="rounded,filled" fontname="Calibri" fontsize=15 color="{MAROON}" '
        f'fillcolor="{GREY}" fontcolor="{INK}" penwidth=1.3 margin="0.18,0.08"];')
EDGE = f'edge [color="{MAROON}" arrowsize=0.8 penwidth=1.4 fontname="Calibri" fontsize=12 fontcolor="#595959"];'


def dot(name: str, src: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    subprocess.run(["dot", "-Tpng", "-Gdpi=220", "-o", str(OUT / f"{name}.png")], input=src.encode(), check=True)


dot("arch", f"""digraph G {{ rankdir=TB; nodesep=0.55; ranksep=0.55; newrank=true; bgcolor="transparent"; {NODE} {EDGE}
  src [label="Data sources\nEarnings calls (HF)\nSEC EDGAR 10-K/10-Q\nNews RSS | NSE" fillcolor="white"];
  ing [label="Ingestion\nclean + dedupe\nspeakers, prepared / Q&A\nsentence chunks"];
  absa [label="ABSA service\naspect extraction\n(rules + spaCy)\npolarity model"];
  reg [label="Model registry\nMLflow" shape=cylinder fillcolor="white"];
  db [label="Database\nSQLite / PostgreSQL" shape=cylinder fillcolor="white"];
  ag [label="Agents (LangGraph)\nExtractor -> Bull | Bear\n-> Skeptic -> Judge" fillcolor="{ROSE}"];
  out [label="Delivery\nNext.js dashboard\ndaily digest\ndrift monitor" fillcolor="white"];
  {{ rank=same; src; ing; absa; reg; }} {{ rank=same; out; ag; db; }}
  src -> ing -> absa; absa -> reg [dir=back style=dashed label="serves"];
  out -> ag -> db [style=invis];                       # bottom row order: out | agents | db (flow runs right to left)
  absa -> db [label=" scores"]; db -> ag [label="evidence" constraint=false]; ag -> out [label="briefs" constraint=false];
  src -> out [style=invis]; reg -> db [style=invis]; }}""")

dot("agents", f"""digraph G {{ rankdir=LR; nodesep=0.3; ranksep=0.45; bgcolor="transparent"; {NODE} {EDGE}
  ext [label="Extractor\\ntop-k scored\\nsentences per aspect"];
  bull [label="Bull agent\\nclaims + citations" fillcolor="#E6F2EA" color="#2E7D4F"];
  bear [label="Bear agent\\nclaims + citations" fillcolor="{ROSE}"];
  skp [label="Skeptic (grounding gate)\\n1 citation exists\\l2 numbers in source\\l3 similarity + overlap\\l4 NLI entailment\\l" fillcolor="#FFF4DD" color="#B7791F"];
  jdg [label="Judge\\nbrief + confidence\\n(verified claims only)"];
  ext -> bull; ext -> bear; bull -> skp; bear -> skp; skp -> jdg [label="supported"]; }}""")
print(sorted(p.name for p in OUT.glob("*.png")))
