"""Generate a customer-facing PDF explaining ops_pipeline3 and its Spark replacement.

Chapters:
  1. Pipeline ops_pipeline3 explained (steps + diagram)
  2. The replacement notebook code, syntax-highlighted like the Fabric editor
  3. Parallelism and scaling notes

Pure-Python rendering: Pygments (highlighting) + xhtml2pdf (HTML -> PDF).
"""

import html
import json
import os

from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import PythonLexer
from xhtml2pdf import pisa

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOTEBOOK = os.path.join(_ROOT, "notebooks", "replace_ops_pipeline3.ipynb")
OUT_PDF = os.path.join(_ROOT, "reports", "ops_pipeline3_explained.pdf")

# Fabric-like light editor palette.
CODE_BG = "#f3f3f3"
ACCENT = "#0f6cbd"  # Fabric blue

_formatter = HtmlFormatter(noclasses=True, style="friendly", nowrap=False)


def highlight_code(code: str) -> str:
    return highlight(code, PythonLexer(), _formatter)


def load_cells() -> list[dict]:
    nb = json.load(open(NOTEBOOK, encoding="utf-8"))
    cells = []
    for c in nb["cells"]:
        cells.append({"type": c["cell_type"], "src": "".join(c["source"])})
    return cells


def md_inline(text: str) -> str:
    """Very small markdown-ish inline conversion for the notebook markdown cells."""
    text = html.escape(text)
    # `code`
    import re

    text = re.sub(r"`([^`]+)`", r'<font face="Courier" color="#a31515">\1</font>', text)
    # **bold**
    text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)
    return text


def render_markdown_cell(src: str) -> str:
    out = []
    for line in src.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("### "):
            out.append(f'<p class="h3">{md_inline(s[4:])}</p>')
        elif s.startswith("## "):
            out.append(f'<p class="h2">{md_inline(s[3:])}</p>')
        elif s.startswith("# "):
            out.append(f'<p class="h1cell">{md_inline(s[2:])}</p>')
        elif s.startswith("> "):
            out.append(f'<p class="note">{md_inline(s[2:])}</p>')
        elif s[:2] in ("- ", "* ") or (len(s) > 2 and s[0].isdigit() and s[1] == "."):
            out.append(f'<p class="li">{md_inline(s)}</p>')
        else:
            out.append(f"<p>{md_inline(s)}</p>")
    return "\n".join(out)


def render_notebook() -> str:
    parts = []
    for cell in load_cells():
        if cell["type"] == "markdown":
            parts.append(f'<div class="nbmd">{render_markdown_cell(cell["src"])}</div>')
        else:
            parts.append(
                '<table class="codecell" width="100%"><tr>'
                f'<td class="codebar"></td><td class="codebody">{highlight_code(cell["src"])}</td>'
                "</tr></table>"
            )
    return "\n".join(parts)


def box(title: str, body: str = "", bg: str = "#ffffff", border: str = ACCENT) -> str:
    inner = f'<b>{title}</b>' + (f'<br/><font size="7">{body}</font>' if body else "")
    return (
        f'<table width="86%" align="center" cellpadding="6" '
        f'style="margin:3px auto; background-color:{bg}; border:1.2pt solid {border};">'
        f'<tr><td align="center">{inner}</td></tr></table>'
    )


def arrow() -> str:
    return '<p align="center" style="font-size:13pt; color:#555; margin:0;">&#8595;</p>'


def diagram() -> str:
    return (
        box("datacopyjobsetup", "Lakehouse control table (SourceName, WatermarkColumn, LastUpdated, DestinationName)", "#eef6fc")
        + arrow()
        + box("1. LookupDueJobs &mdash; Lookup", "Reads ALL rows of the control table (firstRowOnly = false)", "#fff7e6", "#d68a00")
        + arrow()
        + '<table width="90%" align="center" cellpadding="8" style="margin:3px auto; background-color:#f0f7f0; border:1.4pt dashed #2e7d32;">'
        + '<tr><td align="center"><b>2. ForEach &mdash; loop over each row (batchCount = 20, parallel)</b><br/>'
        + box("CopyDynamicKQLTables &mdash; Copy", "", "#ffffff", "#2e7d32")
        + '<table width="94%" align="center" cellpadding="5"><tr>'
        + '<td width="48%" align="center" style="background-color:#eaf3fb; border:1pt solid #0f6cbd;">'
        + '<b>Source: KQL / Eventhouse</b><br/><font size="7">&lt;SourceName&gt; | where &lt;WatermarkColumn&gt;<br/>&gt; datetime(&lt;LastUpdated&gt;)</font></td>'
        + '<td width="4%" align="center">&#8594;</td>'
        + '<td width="48%" align="center" style="background-color:#eef6ee; border:1pt solid #2e7d32;">'
        + '<b>Sink: Lakehouse table</b><br/><font size="7">dbo.&lt;DestinationName&gt; (Append, V-Order)</font></td>'
        + '</tr></table>'
        + '</td></tr></table>'
        + arrow()
        + box("Lakehouse Delta tables", "One destination Delta table per job", "#eef6ee", "#2e7d32")
    )


CH1 = f"""
<p class="h1">Chapter 1 &ndash; The <font face="Courier">ops_pipeline3</font> pipeline</p>

<p><b>Purpose.</b> <font face="Courier">ops_pipeline3</font> is a <b>metadata-driven incremental
ingestion</b> pipeline. It copies data from an <b>Eventhouse (KQL database)</b> into
<b>Lakehouse Delta tables</b>, driven by a control table so that new source tables can be
onboarded by simply adding a row &ndash; no change to the pipeline itself.</p>

<p class="h2">Parameters &amp; variables</p>
<p class="li">- <font face="Courier">ops_lakehouse</font> &ndash; the target Lakehouse (holds the control table and the destination tables).</p>
<p class="li">- <font face="Courier">ops_kql_db</font> &ndash; the source KQL / Eventhouse database.</p>
<p class="li">- <font face="Courier">vRunId</font> &ndash; a variable capturing the pipeline Run Id.</p>

<p class="h2">Step-by-step</p>
<p class="li"><b>1. LookupDueJobs (Lookup).</b> Reads <b>every row</b> of the control table
<font face="Courier">dbo.datacopyjobsetup</font> in the Lakehouse (<font face="Courier">firstRowOnly = false</font>).
Each row describes one copy job with the columns <font face="Courier">SourceName</font>,
<font face="Courier">WatermarkColumn</font>, <font face="Courier">LastUpdated</font> and
<font face="Courier">DestinationName</font>.</p>

<p class="li"><b>2. ForEach (loop, batchCount = 20).</b> Iterates over the rows returned by the lookup,
processing up to 20 in parallel. For each row it runs one Copy activity:</p>

<p class="li" style="margin-left:22px;"><b>CopyDynamicKQLTables (Copy).</b>
<b>Source</b> = a <b>dynamic KQL query</b> against the Eventhouse:
<font face="Courier">&lt;SourceName&gt; | where &lt;WatermarkColumn&gt; &gt; datetime(&lt;LastUpdated&gt;)</font>,
i.e. only rows newer than the stored watermark (an incremental pull).
<b>Sink</b> = the Lakehouse Delta table <font face="Courier">dbo.&lt;DestinationName&gt;</font>
in <b>Append</b> mode (with V-Order).</p>

<p class="note">Note: the pipeline itself never updates <font face="Courier">LastUpdated</font>. The watermark
must be maintained elsewhere &ndash; the notebook in Chapter 2 offers an optional step to advance it.</p>

<p class="h2">Graphical representation</p>
{diagram()}
"""

CH3 = f"""
<p class="h1">Chapter 3 &ndash; Parallelism &amp; scaling</p>

<p>The pipeline&rsquo;s ForEach used <b>batchCount = 20</b>. When translated to Spark, the real limit is not
the notebook &ndash; it is how much the <b>Eventhouse</b> can serve concurrently. Two reader modes exist,
each with a different constraint:</p>

<p class="li">- <b>Single (query) mode</b> &ndash; reads through the query API. Simple, but capped at
<b>500,000 rows</b> per query. Good only for small tables.</p>
<p class="li">- <b>Distributed mode</b> &ndash; reads via <font face="Courier">.export</font> to storage. <b>No row cap</b>
(used for the large <font face="Courier">Measurements</font> tables), but each export consumes an
<b>export slot</b>.</p>

<p class="h2">Why concurrency was limited to 1</p>
<p>The Eventhouse reported <font face="Courier">Export Capacity: 1</font> &ndash; only one
<font face="Courier">.export</font> may run at a time. Running 8 jobs in parallel therefore got
<b>throttled</b>. The number of concurrent exports scales with the compute:</p>

<p align="center"><b>concurrent exports &#8776; total&nbsp;cores &#215; 0.75</b></p>

<p>So to allow <font face="Courier">max_parallel = 8</font> you need roughly
<b>8 &#247; 0.75 &#8776; 11 warm cores</b>.</p>

<p class="h2">Scaling on your F64 capacity</p>
<p>F64 has ample headroom; the lever is <b>how many Eventhouse cores are kept warm</b>. In the Fabric portal:
open the <b>Eventhouse</b> &rarr; top toolbar <b>Capacity Planner</b> (currently Off) and raise the
<b>Minimum consumption</b> level. Verify with the KQL command <font face="Courier">.show capacity</font>
(look at the <b>Export</b> row) before increasing <font face="Courier">max_parallel</font>.</p>

<table width="70%" align="center" cellpadding="6" style="margin-top:8px; border:1pt solid #999;">
<tr style="background-color:#0f6cbd; color:#ffffff;"><td><b>Desired max_parallel</b></td><td><b>Warm cores (~)</b></td><td><b>Action</b></td></tr>
<tr><td>1 (current)</td><td>any</td><td>nothing &ndash; sequential, safe on Capacity 1</td></tr>
<tr style="background-color:#f3f3f3;"><td>4</td><td>~6</td><td>raise Minimum consumption one&ndash;two levels</td></tr>
<tr><td>8</td><td>~11</td><td>Minimum consumption to a Medium/Large level</td></tr>
</table>

<p class="note">Trade-off: keeping more cores warm increases cost. Raise it for the batch window, then lower it
again. The notebook keeps a retry-with-backoff as a safety net for transient throttling.</p>
"""

CSS = """
@page { size: A4; margin: 1.6cm 1.5cm; }
body { font-family: Helvetica, Arial, sans-serif; font-size: 9.5pt; color: #1b1b1b; line-height: 1.35; }
p { margin: 3px 0; }
.cover-title { font-size: 24pt; color: #0f6cbd; font-weight: bold; margin-top: 220px; text-align: center; }
.cover-sub { font-size: 12pt; color: #555; text-align: center; margin-top: 8px; }
.h1 { font-size: 16pt; color: #0f6cbd; font-weight: bold; margin-top: 6px; border-bottom: 1.5pt solid #0f6cbd; padding-bottom: 3px; }
.h2 { font-size: 12pt; color: #0b5394; font-weight: bold; margin-top: 10px; }
.h3 { font-size: 10.5pt; color: #333; font-weight: bold; margin-top: 6px; }
.h1cell { font-size: 13pt; color: #0f6cbd; font-weight: bold; }
.li { margin: 2px 0 2px 10px; }
.note { background-color: #fff7e6; border-left: 3pt solid #d68a00; padding: 5px 8px; margin: 6px 0; }
.nbmd { margin: 8px 0 2px 0; }
.codecell { margin: 0 0 8px 0; }
.codebar { width: 5pt; background-color: #0f6cbd; }
.codebody { background-color: #f6f8fa; padding: 6px 8px; font-family: Courier, monospace; font-size: 7.5pt; }
pre { margin: 0; font-family: Courier, monospace; font-size: 7.5pt; white-space: pre-wrap; }
"""

HTML_DOC = f"""<html><head><meta charset="utf-8"><style>{CSS}</style></head><body>
<div class="cover-title">Modernizing ops_pipeline3</div>
<div class="cover-sub">From a Data Factory pipeline to a Spark notebook in Microsoft Fabric</div>
<div class="cover-sub">Prepared for the customer &middot; {os.environ.get('REPORT_DATE', '2026-09-03')}</div>
<div style="page-break-after: always;"></div>

{CH1}
<div style="page-break-after: always;"></div>

<p class="h1">Chapter 2 &ndash; The replacement notebook</p>
<p>The following notebook reproduces the pipeline in PySpark. Markdown cells are shown as text; code cells are
rendered with the same syntax highlighting you see in the Fabric notebook editor.</p>
{render_notebook()}
<div style="page-break-after: always;"></div>

{CH3}
</body></html>"""


def main() -> None:
    os.makedirs(os.path.dirname(OUT_PDF), exist_ok=True)
    with open(OUT_PDF, "wb") as fh:
        result = pisa.CreatePDF(HTML_DOC, dest=fh)
    if result.err:
        raise RuntimeError(f"PDF generation failed with {result.err} error(s)")
    print(f"PDF written to {OUT_PDF}")


if __name__ == "__main__":
    main()
